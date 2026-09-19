import asyncio
import base64
import json
import platform
import re
import socket
import sys
from time import perf_counter
from typing import Annotated

import psutil

from datetime import datetime, timedelta
from hashlib import sha256
from secrets import token_urlsafe
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.database import redis_client
from app.core.browser_preview import screenshot_request_key, screenshot_response_key
from app.core.browser_resources import list_resources, pool_command_key, resource_key
from app.core.crypto import decrypt_transient_secret, encrypt_transient_secret
from app.core.proxy_pool import choose_proxy_for_new_account
from app.core.proxy_speed import measure_proxy
from app.core.platform_settings import get_platform_settings, update_platform_settings
from app.core.security import hash_password
from app.core.task_lifecycle import delete_stopped_task, restart_stopped_task
from app.dependencies import admin_user
from app.models import (AccountLoginSession, AccountLog, CommentLog, DouyinAccount, Proxy, Script,
                        SensitiveWord, SubscriptionPlan, Task, TaskAccount, User, Worker)
from app.schemas import (
    AccountResponse,
    AccountLogResponse,
    AdminCustomerCreate,
    AdminCustomerPasswordReset,
    AdminCustomerResponse,
    AdminCustomerStatusUpdate,
    AdminCustomerUpdate,
    AdminScriptResponse,
    BrowserResourceResponse,
    CommentLogResponse,
    DouyinAccountUpdate,
    LoginSessionResponse,
    LoginPasswordRequest,
    LoginVerificationCodeRequest,
    LoginVerificationMethodRequest,
    ProxyAccountBind,
    ProxyResponse,
    ProxyTestResponse,
    ProxyUpdate,
    ProxyWrite,
    PlatformSettingsResponse,
    PlatformSettingsUpdate,
    ScriptResponse, ScriptBatchReviewRequest,
    ServerStatusResponse,
    ServiceStatus,
    SensitiveWordCreate,
    SensitiveWordResponse,
    SensitiveWordUpdate,
    SubscriptionPlanResponse,
    SubscriptionPlanUpdate,
    TaskAccountResponse,
    TaskResponse,
)

router = APIRouter(prefix="/api/admin", tags=["admin"])
PROXY_TEST_SEMAPHORE = asyncio.Semaphore(3)


def proxy_test_key(proxy_id: int) -> str:
    return f"douyin:proxy:test:{proxy_id}"
ACCOUNT_BROWSER_WORKER_HEARTBEAT_KEY = "douyin:account-browser-worker:heartbeat"
WORKER_HEARTBEAT_KEYS = {
    "扫码登录 Worker": "douyin:login-worker:heartbeat",
    "账号浏览器 Worker": ACCOUNT_BROWSER_WORKER_HEARTBEAT_KEY,
}


def _parse_heartbeat(value: str | bytes | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.decode() if isinstance(value, bytes) else value)
    except (TypeError, ValueError):
        return None


@router.get("/server-status", response_model=ServerStatusResponse)
async def server_status(user: Annotated[User, Depends(admin_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    collected_at = datetime.now()
    platform_settings = await get_platform_settings(db)
    services: list[ServiceStatus] = []

    started = perf_counter()
    try:
        await db.execute(select(1))
        services.append(ServiceStatus(name="MySQL", status="online", latency_ms=round((perf_counter() - started) * 1000, 1)))
    except Exception:
        services.append(ServiceStatus(name="MySQL", status="offline"))

    started = perf_counter()
    try:
        await redis_client.ping()
        services.append(ServiceStatus(name="Redis", status="online", latency_ms=round((perf_counter() - started) * 1000, 1)))
        heartbeat_values = await redis_client.mget(*WORKER_HEARTBEAT_KEYS.values())
    except Exception:
        services.append(ServiceStatus(name="Redis", status="offline"))
        heartbeat_values = [None] * len(WORKER_HEARTBEAT_KEYS)

    for (name, _), heartbeat_value in zip(WORKER_HEARTBEAT_KEYS.items(), heartbeat_values):
        heartbeat_at = _parse_heartbeat(heartbeat_value)
        online = bool(heartbeat_at and (collected_at - heartbeat_at).total_seconds() <= platform_settings["worker_heartbeat_timeout_seconds"])
        services.append(ServiceStatus(name=name, status="online" if online else "offline", last_heartbeat_at=heartbeat_at))

    task_workers = list(await db.scalars(select(Worker).where(
        Worker.worker_key.like("task:%"), Worker.status == "online", Worker.deleted_at.is_(None)
    )))
    online_task_workers = [worker for worker in task_workers if worker.last_heartbeat_at and (collected_at - worker.last_heartbeat_at).total_seconds() <= platform_settings["worker_heartbeat_timeout_seconds"]]
    latest_task_heartbeat = max((worker.last_heartbeat_at for worker in task_workers if worker.last_heartbeat_at), default=None)
    services.append(ServiceStatus(
        name=f"任务执行 Worker（{len(online_task_workers)} 在线）",
        status="online" if online_task_workers else "offline",
        last_heartbeat_at=latest_task_heartbeat,
    ))

    cpu_percent = await asyncio.to_thread(psutil.cpu_percent, 0.1)
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    memory_used = memory.total - memory.available
    disk_used = disk.total - disk.free
    boot_time = datetime.fromtimestamp(psutil.boot_time())
    try:
        load_average = [round(value, 2) for value in psutil.getloadavg()]
    except (AttributeError, OSError):
        load_average = []
    return ServerStatusResponse(
        collected_at=collected_at,
        hostname=socket.gethostname(),
        platform=f"{platform.system()} {platform.release()}",
        python_version=sys.version.split()[0],
        uptime_seconds=max(0, int((collected_at - boot_time).total_seconds())),
        cpu_percent=round(cpu_percent, 1),
        cpu_count=psutil.cpu_count() or 1,
        load_average=load_average,
        memory_total=memory.total,
        memory_used=memory_used,
        memory_percent=round(memory.percent, 1),
        disk_total=disk.total,
        disk_used=disk_used,
        disk_percent=round(disk_used / disk.total * 100, 1) if disk.total else 0,
        services=services,
    )


@router.get("/platform-settings", response_model=PlatformSettingsResponse)
async def read_platform_settings(user: Annotated[User, Depends(admin_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    return await get_platform_settings(db)


@router.put("/platform-settings", response_model=PlatformSettingsResponse)
async def save_platform_settings(payload: PlatformSettingsUpdate, user: Annotated[User, Depends(admin_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    return await update_platform_settings(db, payload.model_dump(), user.id)


@router.get("/customers", response_model=list[AdminCustomerResponse])
async def list_customers(user: Annotated[User, Depends(admin_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    result = await db.scalars(select(User).where(
        User.role == "customer", User.deleted_at.is_(None)
    ).order_by(User.id.desc()))
    return list(result)


@router.post("/customers", response_model=AdminCustomerResponse, status_code=201)
async def create_customer(payload: AdminCustomerCreate, user: Annotated[User, Depends(admin_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    login = payload.login.strip()
    display_name = payload.display_name.strip()
    if not login or not display_name:
        raise HTTPException(422, "登录名和客户名称不能为空")
    if await db.scalar(select(User.id).where(User.login == login)):
        raise HTTPException(409, "登录名已存在")
    standard_plan_id = await db.scalar(select(SubscriptionPlan.id).where(
        SubscriptionPlan.code == "standard", SubscriptionPlan.enabled.is_(True),
        SubscriptionPlan.deleted_at.is_(None),
    ))
    if not standard_plan_id:
        raise HTTPException(503, "平台尚未配置标准套餐")
    customer = User(
        role="customer",
        login=login,
        display_name=display_name,
        password_hash=hash_password(payload.password),
        status="disabled",
        subscription_plan_id=standard_plan_id,
    )
    db.add(customer)
    await db.commit()
    await db.refresh(customer)
    return customer


async def _get_customer(customer_id: int, db: AsyncSession) -> User:
    customer = await db.scalar(select(User).where(
        User.id == customer_id, User.role == "customer", User.deleted_at.is_(None)
    ))
    if not customer:
        raise HTTPException(404, "客户不存在")
    return customer


async def _customer_has_active_task(customer_id: int, db: AsyncSession) -> bool:
    return bool(await db.scalar(select(Task.id).where(
        Task.customer_id == customer_id,
        Task.status.in_(("pending", "running", "paused")),
        Task.deleted_at.is_(None),
    ).limit(1)))


@router.patch("/customers/{customer_id}", response_model=AdminCustomerResponse)
async def update_customer(customer_id: int, payload: AdminCustomerUpdate, user: Annotated[User, Depends(admin_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    customer = await _get_customer(customer_id, db)
    if payload.login is not None:
        login = payload.login.strip()
        if not login:
            raise HTTPException(422, "登录名不能为空")
        exists = await db.scalar(select(User.id).where(User.login == login, User.id != customer.id))
        if exists:
            raise HTTPException(409, "登录名已存在")
        customer.login = login
    if payload.display_name is not None:
        display_name = payload.display_name.strip()
        if not display_name:
            raise HTTPException(422, "客户名称不能为空")
        customer.display_name = display_name
    if payload.extra_douyin_account_quota is not None:
        customer.extra_douyin_account_quota = payload.extra_douyin_account_quota
    await db.commit()
    await db.refresh(customer)
    return customer


@router.patch("/customers/{customer_id}/status", response_model=AdminCustomerResponse)
async def update_customer_status(customer_id: int, payload: AdminCustomerStatusUpdate, user: Annotated[User, Depends(admin_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    customer = await _get_customer(customer_id, db)
    if payload.status == "disabled" and await _customer_has_active_task(customer.id, db):
        raise HTTPException(409, "客户存在活动任务，请先停止任务")
    if payload.status == "active" and (customer.expires_at is None or customer.expires_at <= datetime.now()):
        raise HTTPException(409, "客户尚未激活或已经到期，请使用激活/续签操作")
    customer.status = payload.status
    await db.commit()
    await db.refresh(customer)
    return customer


@router.post("/customers/{customer_id}/activate", response_model=AdminCustomerResponse)
async def activate_customer(customer_id: int, user: Annotated[User, Depends(admin_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    customer = await _get_customer(customer_id, db)
    customer.expires_at = datetime.now() + timedelta(days=30)
    customer.status = "active"
    await db.commit()
    await db.refresh(customer)
    return customer


@router.post("/customers/{customer_id}/renew", response_model=AdminCustomerResponse)
async def renew_customer(customer_id: int, user: Annotated[User, Depends(admin_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    customer = await _get_customer(customer_id, db)
    base = customer.expires_at if customer.expires_at and customer.expires_at > datetime.now() else datetime.now()
    customer.expires_at = base + timedelta(days=30)
    customer.status = "active"
    await db.commit()
    await db.refresh(customer)
    return customer


@router.post("/customers/{customer_id}/reset-password", status_code=204)
async def reset_customer_password(customer_id: int, payload: AdminCustomerPasswordReset, user: Annotated[User, Depends(admin_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    customer = await _get_customer(customer_id, db)
    customer.password_hash = hash_password(payload.new_password)
    await db.commit()


@router.delete("/customers/{customer_id}", status_code=204)
async def delete_customer(customer_id: int, user: Annotated[User, Depends(admin_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    customer = await _get_customer(customer_id, db)
    if await _customer_has_active_task(customer.id, db):
        raise HTTPException(409, "客户存在活动任务，请先停止任务")
    customer.status = "disabled"
    customer.deleted_at = datetime.now()
    await db.commit()


@router.get("/subscription-plans", response_model=list[SubscriptionPlanResponse])
async def admin_subscription_plans(user: Annotated[User, Depends(admin_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    return list(await db.scalars(select(SubscriptionPlan).where(
        SubscriptionPlan.deleted_at.is_(None),
    ).order_by(SubscriptionPlan.tier_level.asc())))


@router.patch("/subscription-plans/{plan_id}", response_model=SubscriptionPlanResponse)
async def update_subscription_plan(plan_id: int, payload: SubscriptionPlanUpdate, user: Annotated[User, Depends(admin_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    plan = await db.scalar(select(SubscriptionPlan).where(
        SubscriptionPlan.id == plan_id, SubscriptionPlan.deleted_at.is_(None),
    ))
    if not plan:
        raise HTTPException(404, "套餐不存在")
    values = payload.model_dump(exclude_unset=True)
    if "name" in values:
        values["name"] = values["name"].strip()
    for name, value in values.items():
        setattr(plan, name, value)
    await db.commit()
    await db.refresh(plan)
    return plan


@router.get("/tasks", response_model=list[TaskResponse])
async def list_tasks(user: Annotated[User, Depends(admin_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    result = await db.scalars(select(Task).where(Task.deleted_at.is_(None)).order_by(Task.id.desc()))
    return list(result)


@router.get("/tasks/{task_id}/accounts", response_model=list[TaskAccountResponse])
async def list_task_accounts(task_id: int, user: Annotated[User, Depends(admin_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    task = await db.scalar(select(Task).where(Task.id == task_id, Task.deleted_at.is_(None)))
    if not task:
        raise HTTPException(404, "任务不存在")
    result = await db.scalars(select(TaskAccount).where(TaskAccount.task_id == task_id, TaskAccount.deleted_at.is_(None)))
    return list(result)


@router.get("/tasks/{task_id}/comment-logs", response_model=list[CommentLogResponse])
async def admin_task_comment_logs(task_id: int, user: Annotated[User, Depends(admin_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    task = await db.scalar(select(Task.id).where(Task.id == task_id, Task.deleted_at.is_(None)))
    if not task:
        raise HTTPException(404, "任务不存在")
    result = await db.scalars(select(CommentLog).where(
        CommentLog.task_id == task_id, CommentLog.deleted_at.is_(None)
    ).order_by(CommentLog.id.desc()).limit(500))
    return list(result)


@router.post("/tasks/{task_id}/accounts/{account_id}", response_model=TaskAccountResponse, status_code=201)
async def add_task_account(task_id: int, account_id: int, user: Annotated[User, Depends(admin_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    task = await db.scalar(select(Task).where(Task.id == task_id, Task.deleted_at.is_(None)).with_for_update())
    if not task or task.status in {"stopped", "failed", "completed"}:
        raise HTTPException(409, "任务不存在或已经结束")
    account = await db.scalar(select(DouyinAccount).where(
        DouyinAccount.id == account_id, DouyinAccount.enabled.is_(True),
        DouyinAccount.status == "available", DouyinAccount.current_task_id.is_(None),
        DouyinAccount.deleted_at.is_(None),
    ).with_for_update())
    if not account:
        raise HTTPException(409, "抖音账号不可用或正在执行其他任务")
    if task.account_source == "platform" and account.ownership_type != "platform":
        raise HTTPException(409, "平台账号模式只能添加平台账号")
    if task.account_source == "customer" and (account.ownership_type != "customer" or account.owner_customer_id != task.customer_id):
        raise HTTPException(409, "客户自有账号模式只能添加该客户自己的账号")
    assignment = await db.scalar(select(TaskAccount).where(
        TaskAccount.task_id == task_id, TaskAccount.account_id == account_id,
        TaskAccount.deleted_at.is_(None),
    ).with_for_update())
    if assignment and assignment.status not in {"removed", "completed"}:
        raise HTTPException(409, "该账号已经分配给此任务")
    if assignment:
        assignment.status = "assigned"
        assignment.assigned_by = user.id
        assignment.removed_at = None
    else:
        assignment = TaskAccount(task_id=task_id, account_id=account_id, assigned_by=user.id, status="assigned")
        db.add(assignment)
    account.current_task_id = task_id
    account.status = "busy"
    await db.commit()
    await db.refresh(assignment)
    await redis_client.delete(f"douyin:task-account:stop:{assignment.id}")
    if task.status in {"running", "paused"}:
        await redis_client.rpush("douyin:task-accounts", str(assignment.id))
    return assignment


@router.delete("/tasks/{task_id}/accounts/{account_id}", status_code=204)
async def remove_task_account(task_id: int, account_id: int, user: Annotated[User, Depends(admin_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    assignment = await db.scalar(select(TaskAccount).where(
        TaskAccount.task_id == task_id, TaskAccount.account_id == account_id,
        TaskAccount.deleted_at.is_(None), TaskAccount.status.not_in(("removed", "completed")),
    ).with_for_update())
    if not assignment:
        raise HTTPException(404, "任务账号分配不存在")
    assignment.status = "removed"
    assignment.removed_at = datetime.now()
    account = await db.scalar(select(DouyinAccount).where(DouyinAccount.id == account_id).with_for_update())
    if account and account.current_task_id == task_id:
        account.current_task_id = None
        account.status = "available" if account.enabled else "disabled"
    await db.commit()
    await redis_client.rpush(f"douyin:task-account:stop:{assignment.id}", "stop")


@router.post("/tasks/{task_id}/pause", response_model=TaskResponse)
async def admin_pause_task(task_id: int, user: Annotated[User, Depends(admin_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    task = await db.scalar(select(Task).where(Task.id == task_id, Task.deleted_at.is_(None)).with_for_update())
    if not task:
        raise HTTPException(404, "任务不存在")
    if task.status not in {"pending", "running"}:
        raise HTTPException(409, "当前任务状态不能暂停")
    task.status = "paused"
    task.paused_at = datetime.now()
    await db.commit()
    await db.refresh(task)
    return task


@router.post("/tasks/{task_id}/resume", response_model=TaskResponse)
async def admin_resume_task(task_id: int, user: Annotated[User, Depends(admin_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    task = await db.scalar(select(Task).where(Task.id == task_id, Task.deleted_at.is_(None)).with_for_update())
    if not task:
        raise HTTPException(404, "任务不存在")
    if task.status != "paused":
        raise HTTPException(409, "只有已暂停任务可以继续")
    task.status = "running" if task.started_at else "pending"
    task.paused_at = None
    await db.commit()
    await db.refresh(task)
    if task.status == "pending":
        await redis_client.rpush("douyin:tasks", str(task.id))
    return task


@router.post("/tasks/{task_id}/stop", response_model=TaskResponse)
async def admin_stop_task(task_id: int, user: Annotated[User, Depends(admin_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    task = await db.scalar(select(Task).where(Task.id == task_id, Task.deleted_at.is_(None)).with_for_update())
    if not task:
        raise HTTPException(404, "任务不存在")
    if task.status not in {"pending", "running", "paused"}:
        raise HTTPException(409, "当前任务已经结束")
    task.status = "stopped"
    task.stopped_at = datetime.now()
    assignments = list(await db.scalars(select(TaskAccount).where(
        TaskAccount.task_id == task.id,
        TaskAccount.status.not_in(("removed", "completed")),
        TaskAccount.deleted_at.is_(None),
    ).with_for_update()))
    account_ids = [assignment.account_id for assignment in assignments]
    if account_ids:
        assigned_accounts = await db.scalars(select(DouyinAccount).where(DouyinAccount.id.in_(account_ids)).with_for_update())
        for account in assigned_accounts:
            if account.current_task_id == task.id:
                account.current_task_id = None
                account.status = "available" if account.enabled else "disabled"
    for assignment in assignments:
        assignment.status = "removed"
        assignment.removed_at = datetime.now()
    await db.commit()
    await db.refresh(task)
    for assignment in assignments:
        await redis_client.rpush(f"douyin:task-account:stop:{assignment.id}", "stop")
    return task


@router.post("/tasks/{task_id}/start", response_model=TaskResponse)
async def admin_restart_task(task_id: int, user: Annotated[User, Depends(admin_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    task = await db.scalar(select(Task).where(
        Task.id == task_id, Task.deleted_at.is_(None),
    ).with_for_update())
    if not task:
        raise HTTPException(404, "任务不存在")
    return await restart_stopped_task(task, user.id, db)


@router.delete("/tasks/{task_id}", status_code=204)
async def admin_delete_task(task_id: int, user: Annotated[User, Depends(admin_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    task = await db.scalar(select(Task).where(
        Task.id == task_id, Task.deleted_at.is_(None),
    ).with_for_update())
    if not task:
        raise HTTPException(404, "任务不存在")
    await delete_stopped_task(task, db)


@router.get("/sensitive-words", response_model=list[SensitiveWordResponse])
async def list_sensitive_words(user: Annotated[User, Depends(admin_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    result = await db.scalars(select(SensitiveWord).where(SensitiveWord.deleted_at.is_(None)).order_by(SensitiveWord.id.desc()))
    return list(result)


@router.post("/sensitive-words", response_model=SensitiveWordResponse, status_code=201)
async def create_sensitive_word(payload: SensitiveWordCreate, user: Annotated[User, Depends(admin_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    word = payload.word.strip()
    if not word:
        raise HTTPException(422, "敏感词不能为空")
    if payload.match_type == "regex":
        try:
            re.compile(word)
        except re.error as exc:
            raise HTTPException(422, f"正则表达式无效：{exc}") from exc
    exists = await db.scalar(select(SensitiveWord).where(SensitiveWord.word == word))
    if exists and exists.deleted_at is None:
        raise HTTPException(409, "敏感词已存在")
    if exists:
        item = exists
        item.deleted_at = None
        item.enabled = True
        item.match_type = payload.match_type
        item.created_by = user.id
    else:
        item = SensitiveWord(created_by=user.id, word=word, match_type=payload.match_type)
        db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


async def _get_sensitive_word(word_id: int, db: AsyncSession) -> SensitiveWord:
    item = await db.scalar(select(SensitiveWord).where(SensitiveWord.id == word_id, SensitiveWord.deleted_at.is_(None)))
    if not item:
        raise HTTPException(404, "敏感词不存在")
    return item


@router.patch("/sensitive-words/{word_id}", response_model=SensitiveWordResponse)
async def update_sensitive_word(word_id: int, payload: SensitiveWordUpdate, user: Annotated[User, Depends(admin_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    item = await _get_sensitive_word(word_id, db)
    next_word = payload.word.strip() if payload.word is not None else item.word
    next_match_type = payload.match_type if payload.match_type is not None else item.match_type
    if next_match_type == "regex":
        try:
            re.compile(next_word)
        except re.error as exc:
            raise HTTPException(422, f"正则表达式无效：{exc}") from exc
    if payload.word is not None:
        word = next_word
        if not word:
            raise HTTPException(422, "敏感词不能为空")
        exists = await db.scalar(select(SensitiveWord.id).where(SensitiveWord.word == word, SensitiveWord.id != word_id))
        if exists:
            raise HTTPException(409, "敏感词已存在")
        item.word = word
    if payload.match_type is not None:
        item.match_type = payload.match_type
    await db.commit()
    await db.refresh(item)
    return item


@router.patch("/sensitive-words/{word_id}/disable", response_model=SensitiveWordResponse)
async def disable_sensitive_word(word_id: int, user: Annotated[User, Depends(admin_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    item = await _get_sensitive_word(word_id, db)
    item.enabled = False
    await db.commit()
    await db.refresh(item)
    return item


@router.patch("/sensitive-words/{word_id}/enable", response_model=SensitiveWordResponse)
async def enable_sensitive_word(word_id: int, user: Annotated[User, Depends(admin_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    item = await _get_sensitive_word(word_id, db)
    item.enabled = True
    await db.commit()
    await db.refresh(item)
    return item


@router.delete("/sensitive-words/{word_id}", status_code=204)
async def delete_sensitive_word(word_id: int, user: Annotated[User, Depends(admin_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    item = await _get_sensitive_word(word_id, db)
    item.enabled = False
    item.deleted_at = datetime.now()
    await db.commit()


async def _get_proxy(proxy_id: int, db: AsyncSession) -> Proxy:
    proxy = await db.scalar(select(Proxy).where(Proxy.id == proxy_id, Proxy.deleted_at.is_(None)))
    if not proxy:
        raise HTTPException(404, "代理不存在")
    return proxy


async def _proxy_response(proxy: Proxy, db: AsyncSession) -> dict:
    result = ProxyResponse.model_validate(proxy).model_dump()
    result["account_count"] = await db.scalar(select(func.count(DouyinAccount.id)).where(
        DouyinAccount.proxy_id == proxy.id, DouyinAccount.deleted_at.is_(None)
    )) or 0
    cached = await redis_client.get(proxy_test_key(proxy.id))
    if cached:
        result["test_result"] = json.loads(cached)
    return result


async def _ensure_proxy_account_idle(account: DouyinAccount, db: AsyncSession) -> None:
    if account.status in ("busy", "paused", "browser_open") or account.current_task_id:
        raise HTTPException(409, "账号浏览器正在运行，请先关闭或停止任务")
    active_login = await db.scalar(select(AccountLoginSession.id).where(
        AccountLoginSession.account_id == account.id,
        AccountLoginSession.status.in_(("waiting", "method_required", "method_processing", "password_required", "password_filling", "password_ready", "password_clicking", "password_verifying", "verify_required", "verifying")),
        AccountLoginSession.expires_at > datetime.now(),
        AccountLoginSession.deleted_at.is_(None),
    ).limit(1))
    if active_login:
        raise HTTPException(409, "账号正在扫码登录，请先关闭登录会话")


@router.get("/proxies", response_model=list[ProxyResponse])
async def list_proxies(user: Annotated[User, Depends(admin_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    items = list(await db.scalars(select(Proxy).where(Proxy.deleted_at.is_(None)).order_by(Proxy.id.desc())))
    return [await _proxy_response(item, db) for item in items]


@router.post("/proxies", response_model=ProxyResponse, status_code=201)
async def create_proxy(payload: ProxyWrite, user: Annotated[User, Depends(admin_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    if payload.expires_at <= datetime.now():
        raise HTTPException(422, "代理到期时间必须晚于当前时间")
    proxy = Proxy(domain=payload.domain.strip(), port=payload.port, username=payload.username,
                  encrypted_password=encrypt_transient_secret(payload.password).encode(),
                  expires_at=payload.expires_at, max_accounts=3)
    db.add(proxy)
    await db.commit()
    await db.refresh(proxy)
    return await _proxy_response(proxy, db)


@router.patch("/proxies/{proxy_id}", response_model=ProxyResponse)
async def update_proxy(proxy_id: int, payload: ProxyUpdate, user: Annotated[User, Depends(admin_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    proxy = await _get_proxy(proxy_id, db)
    if payload.expires_at <= datetime.now():
        raise HTTPException(422, "代理到期时间必须晚于当前时间")
    bound_accounts = list(await db.scalars(select(DouyinAccount).where(
        DouyinAccount.proxy_id == proxy_id, DouyinAccount.deleted_at.is_(None),
    )))
    for account in bound_accounts:
        await _ensure_proxy_account_idle(account, db)
    proxy.domain = payload.domain.strip()
    proxy.port = payload.port
    proxy.username = payload.username
    proxy.expires_at = payload.expires_at
    if payload.password:
        proxy.encrypted_password = encrypt_transient_secret(payload.password).encode()
    await db.commit()
    await redis_client.delete(proxy_test_key(proxy_id))
    await db.refresh(proxy)
    return await _proxy_response(proxy, db)


@router.post("/proxies/{proxy_id}/test", response_model=ProxyTestResponse)
async def test_proxy(proxy_id: int, user: Annotated[User, Depends(admin_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    proxy = await _get_proxy(proxy_id, db)
    config = {
        "host": proxy.domain, "port": proxy.port, "username": proxy.username,
        "password": decrypt_transient_secret(proxy.encrypted_password.decode()),
    }
    async with PROXY_TEST_SEMAPHORE:
        result = await measure_proxy(config)
    await redis_client.set(proxy_test_key(proxy_id), json.dumps(result, ensure_ascii=False), ex=86400)
    return result


@router.get("/proxies/{proxy_id}/accounts", response_model=list[AccountResponse])
async def proxy_accounts(proxy_id: int, user: Annotated[User, Depends(admin_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    await _get_proxy(proxy_id, db)
    return list(await db.scalars(select(DouyinAccount).where(
        DouyinAccount.proxy_id == proxy_id, DouyinAccount.deleted_at.is_(None)
    ).order_by(DouyinAccount.id)))


@router.post("/proxies/{proxy_id}/accounts", response_model=AccountResponse)
async def bind_proxy_account(proxy_id: int, payload: ProxyAccountBind, user: Annotated[User, Depends(admin_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    proxy = await _get_proxy(proxy_id, db)
    if proxy.expires_at <= datetime.now():
        raise HTTPException(409, "代理已过期")
    account = await _get_douyin_account(payload.account_id, db)
    await _ensure_proxy_account_idle(account, db)
    account.proxy_id = proxy.id
    db.add(AccountLog(account_id=account.id, event_type="proxy_bound", detail={"proxy_id": proxy.id, "admin_id": user.id}))
    await db.commit()
    await db.refresh(account)
    return account


@router.delete("/proxies/{proxy_id}/accounts/{account_id}", status_code=204)
async def unbind_proxy_account(proxy_id: int, account_id: int, user: Annotated[User, Depends(admin_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    account = await _get_douyin_account(account_id, db)
    if account.proxy_id != proxy_id:
        raise HTTPException(404, "账号未绑定此代理")
    await _ensure_proxy_account_idle(account, db)
    account.proxy_id = None
    db.add(AccountLog(account_id=account.id, event_type="proxy_unbound", detail={"proxy_id": proxy_id, "admin_id": user.id}))
    await db.commit()


@router.delete("/proxies/{proxy_id}", status_code=204)
async def delete_proxy(proxy_id: int, user: Annotated[User, Depends(admin_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    proxy = await _get_proxy(proxy_id, db)
    if await db.scalar(select(DouyinAccount.id).where(
        DouyinAccount.proxy_id == proxy_id, DouyinAccount.deleted_at.is_(None)
    ).limit(1)):
        raise HTTPException(409, "代理仍绑定抖音账号，请先移除账号绑定")
    proxy.deleted_at = datetime.now()
    await db.commit()
    await redis_client.delete(proxy_test_key(proxy_id))


@router.get("/douyin-accounts", response_model=list[AccountResponse])
async def list_accounts(user: Annotated[User, Depends(admin_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    result = await db.scalars(select(DouyinAccount).where(DouyinAccount.deleted_at.is_(None)).order_by(DouyinAccount.id.desc()))
    return list(result)


@router.post("/douyin-accounts", response_model=AccountResponse, status_code=201)
async def create_account(display_name: str, user: Annotated[User, Depends(admin_user)], db: Annotated[AsyncSession, Depends(get_db)], direct_ok: bool = False):
    proxy_id = await choose_proxy_for_new_account(db)
    if proxy_id is None and not direct_ok:
        raise HTTPException(409, "无可用代理，确认后可创建不使用代理的直连账号")
    account = DouyinAccount(display_name=display_name.strip() or "未命名账号", ownership_type="platform", status="unlogged", enabled=True, proxy_id=proxy_id)
    db.add(account)
    await db.flush()
    db.add(AccountLog(account_id=account.id, event_type="account_created", detail={"admin_id": user.id, "proxy_id": proxy_id}))
    await db.commit()
    await db.refresh(account)
    return account


async def _get_douyin_account(account_id: int, db: AsyncSession) -> DouyinAccount:
    account = await db.scalar(select(DouyinAccount).where(
        DouyinAccount.id == account_id, DouyinAccount.deleted_at.is_(None)
    ))
    if not account:
        raise HTTPException(404, "抖音账号不存在")
    return account


@router.patch("/douyin-accounts/{account_id}", response_model=AccountResponse)
async def update_account(account_id: int, payload: DouyinAccountUpdate, user: Annotated[User, Depends(admin_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    account = await _get_douyin_account(account_id, db)
    display_name = payload.display_name.strip()
    if not display_name:
        raise HTTPException(422, "账号名称不能为空")
    old_name = account.display_name
    account.display_name = display_name
    db.add(AccountLog(account_id=account.id, event_type="account_updated", detail={"old_name": old_name, "new_name": display_name, "admin_id": user.id}))
    await db.commit()
    await db.refresh(account)
    return account


@router.patch("/douyin-accounts/{account_id}/disable", response_model=AccountResponse)
async def disable_account(account_id: int, user: Annotated[User, Depends(admin_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    account = await _get_douyin_account(account_id, db)
    if account.current_task_id is not None:
        raise HTTPException(409, "账号正在执行任务，请先从任务中移除")
    account.enabled = False
    account.status = "disabled"
    db.add(AccountLog(account_id=account.id, event_type="account_disabled", detail={"admin_id": user.id}))
    await db.commit()
    await redis_client.rpush(f"douyin:account-browser:close:{account.id}", "close")
    await db.refresh(account)
    return account


@router.patch("/douyin-accounts/{account_id}/enable", response_model=AccountResponse)
async def enable_account(account_id: int, user: Annotated[User, Depends(admin_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    account = await _get_douyin_account(account_id, db)
    account.enabled = True
    account.status = "available" if account.encrypted_storage_state else "unlogged"
    account.last_error = None
    account.risk_code = None
    account.risk_message = None
    db.add(AccountLog(account_id=account.id, event_type="account_enabled", detail={"admin_id": user.id}))
    await db.commit()
    await db.refresh(account)
    return account


@router.post("/douyin-accounts/{account_id}/browser/open", status_code=202)
async def open_account_browser(account_id: int, user: Annotated[User, Depends(admin_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    account = await db.scalar(select(DouyinAccount).where(
        DouyinAccount.id == account_id, DouyinAccount.deleted_at.is_(None)
    ))
    if not account:
        raise HTTPException(404, "抖音账号不存在")
    if not account.enabled:
        raise HTTPException(409, "抖音账号已禁用")
    if not account.encrypted_storage_state:
        raise HTTPException(409, "该账号没有已保存的登录状态，请先扫码登录")
    if account.current_task_id is not None or account.status in {"busy", "paused"}:
        raise HTTPException(409, "该账号正在执行直播任务，不能打开调试浏览器")
    if account.status == "browser_open":
        raise HTTPException(409, "该账号的浏览器已经打开")
    heartbeat_at = _parse_heartbeat(await redis_client.get(ACCOUNT_BROWSER_WORKER_HEARTBEAT_KEY))
    platform_settings = await get_platform_settings(db)
    if not heartbeat_at or (datetime.now() - heartbeat_at).total_seconds() > platform_settings["worker_heartbeat_timeout_seconds"]:
        raise HTTPException(503, "账号浏览器 Worker 未启动，请先启动后再唤醒")
    # 关闭指令只对当时运行的浏览器有效，不能让历史指令关闭新实例。
    async with redis_client.pipeline(transaction=True) as pipe:
        pipe.delete(f"douyin:account-browser:close:{account.id}")
        pipe.rpush("douyin:account-browser:open", str(account.id))
        await pipe.execute()
    # 指令成功入队后立即反映到列表，Worker 失败时会再改为 error/unlogged。
    account.status = "browser_open"
    account.last_error = None
    await db.commit()
    return {"message": "浏览器启动指令已发送", "account_id": account.id}


@router.post("/douyin-accounts/{account_id}/browser/close", status_code=202)
async def close_account_browser(account_id: int, user: Annotated[User, Depends(admin_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    account = await db.scalar(select(DouyinAccount).where(
        DouyinAccount.id == account_id, DouyinAccount.deleted_at.is_(None)
    ))
    if not account:
        raise HTTPException(404, "抖音账号不存在")
    await redis_client.rpush(f"douyin:account-browser:close:{account.id}", "close")
    if account.current_task_id is None:
        if not account.enabled:
            account.status = "disabled"
        else:
            account.status = "available" if account.encrypted_storage_state else "unlogged"
        await db.commit()
    return {"message": "浏览器关闭指令已发送", "account_id": account.id}


@router.delete("/douyin-accounts/{account_id}", status_code=204)
async def delete_account(account_id: int, user: Annotated[User, Depends(admin_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    account = await _get_douyin_account(account_id, db)
    if account.current_task_id is not None:
        raise HTTPException(409, "账号正在执行任务，请先从任务中移除")
    db.add(AccountLog(account_id=account.id, event_type="account_deleted", detail={"admin_id": user.id}))
    account.deleted_at = datetime.now()
    account.enabled = False
    account.status = "disabled"
    await db.commit()
    await redis_client.rpush(f"douyin:account-browser:close:{account.id}", "close")


@router.post("/douyin-accounts/{account_id}/login-session", response_model=LoginSessionResponse, status_code=201)
async def create_login_session(account_id: int, user: Annotated[User, Depends(admin_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    account = await _get_douyin_account(account_id, db)
    if not account.enabled:
        raise HTTPException(409, "抖音账号已禁用，请先启用")
    if account.current_task_id is not None:
        raise HTTPException(409, "账号正在执行任务，不能重新扫码登录")
    active_session = await db.scalar(select(AccountLoginSession.id).where(
        AccountLoginSession.account_id == account.id,
        AccountLoginSession.status.in_(("waiting", "method_required", "method_processing", "password_required", "password_filling", "password_ready", "password_clicking", "password_verifying", "verify_required", "verifying")),
        AccountLoginSession.expires_at > datetime.now(),
        AccountLoginSession.deleted_at.is_(None),
    ).limit(1))
    if active_session:
        raise HTTPException(409, "该账号已有进行中的扫码登录会话")
    raw_token = token_urlsafe(32)
    platform_settings = await get_platform_settings(db)
    session = AccountLoginSession(
        account_id=account.id, created_by=user.id,
        session_token_hash=sha256(raw_token.encode()).hexdigest(),
        # MySQL DATETIME 不带时区；项目统一按服务器本地时间写入。
        status="waiting", expires_at=datetime.now() + timedelta(minutes=platform_settings["qr_expire_minutes"]),
    )
    db.add(session)
    await db.flush()
    db.add(AccountLog(account_id=account.id, event_type="login_session_created", detail={"session_id": session.id}))
    await db.commit()
    await db.refresh(session)
    # Worker 只拿到会话 ID；二维码和登录状态通过 Redis 事件流传递。
    await redis_client.rpush("douyin:login:sessions", str(session.id))
    return session


@router.get("/douyin-login-sessions/{session_id}", response_model=LoginSessionResponse)
async def login_session_status(session_id: int, user: Annotated[User, Depends(admin_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    session = await db.scalar(select(AccountLoginSession).where(AccountLoginSession.id == session_id, AccountLoginSession.deleted_at.is_(None)))
    if not session:
        raise HTTPException(404, "登录会话不存在")
    result = LoginSessionResponse.model_validate(session).model_dump()
    options_raw, selected_raw = await redis_client.mget(
        f"douyin:login:verification-options:{session.id}",
        f"douyin:login:selected-verification:{session.id}",
    )
    try:
        result["verification_options"] = json.loads(options_raw) if options_raw else []
    except (TypeError, ValueError):
        result["verification_options"] = []
    try:
        result["selected_verification_method"] = json.loads(selected_raw) if selected_raw else None
    except (TypeError, ValueError):
        result["selected_verification_method"] = None
    return result


@router.post("/douyin-login-sessions/{session_id}/detect-qr")
async def detect_login_qr(session_id: int, user: Annotated[User, Depends(admin_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    session = await db.scalar(select(AccountLoginSession).where(
        AccountLoginSession.id == session_id, AccountLoginSession.deleted_at.is_(None),
    ))
    if not session:
        raise HTTPException(404, "登录会话不存在")
    if session.status != "waiting" or session.expires_at <= datetime.now():
        raise HTTPException(409, "登录会话已结束，请重新发起扫码登录")
    if session.qr_payload:
        return {"found": True, "qr_payload": session.qr_payload}
    if not await redis_client.exists(resource_key("login", session_id)):
        raise HTTPException(409, "登录浏览器尚未启动或已关闭，请稍后重试")
    request_id = token_urlsafe(18)
    request_key = f"douyin:login:qr-request:{session_id}"
    response_key = f"douyin:login:qr-response:{request_id}"
    async with redis_client.pipeline(transaction=True) as pipe:
        pipe.rpush(request_key, request_id)
        pipe.expire(request_key, 20)
        await pipe.execute()
    item = await redis_client.blpop(response_key, timeout=12)
    if not item:
        raise HTTPException(504, "浏览器检测超时，请稍后重试")
    result = json.loads(item[1])
    if not result.get("found"):
        return {"found": False, "message": "当前浏览器画面尚未出现有效的登录二维码"}
    await db.refresh(session)
    return {"found": True, "qr_payload": session.qr_payload}


async def _request_browser_screenshot(browser_type: str, browser_id: str | int) -> Response:
    request_id = token_urlsafe(18)
    request_key = screenshot_request_key(browser_type, browser_id)
    response_key = screenshot_response_key(request_id)
    async with redis_client.pipeline(transaction=True) as pipe:
        pipe.rpush(request_key, request_id)
        pipe.expire(request_key, 30)
        await pipe.execute()
    item = await redis_client.blpop(response_key, timeout=12)
    if not item:
        raise HTTPException(504, "浏览器画面获取超时，请确认浏览器仍在运行")
    try:
        payload = json.loads(item[1])
    except (TypeError, ValueError):
        raise HTTPException(502, "浏览器返回了无效的截图数据")
    if not payload.get("ok"):
        raise HTTPException(502, payload.get("error") or "浏览器截图失败")
    try:
        image = base64.b64decode(payload["image"], validate=True)
    except (KeyError, TypeError, ValueError):
        raise HTTPException(502, "浏览器返回了无效的截图图片")
    return Response(
        content=image,
        media_type="image/jpeg",
        headers={"Cache-Control": "no-store, max-age=0"},
    )


@router.get("/douyin-login-sessions/{session_id}/screenshot")
async def login_session_screenshot(
    session_id: int,
    user: Annotated[User, Depends(admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    session = await db.scalar(select(AccountLoginSession).where(
        AccountLoginSession.id == session_id,
        AccountLoginSession.deleted_at.is_(None),
    ))
    if not session:
        raise HTTPException(404, "登录会话不存在")
    return await _request_browser_screenshot("login", session.id)


@router.get("/douyin-accounts/{account_id}/browser/screenshot")
async def account_browser_screenshot(
    account_id: int,
    user: Annotated[User, Depends(admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    account = await _get_douyin_account(account_id, db)
    if account.status != "browser_open":
        raise HTTPException(409, "该账号的调试浏览器没有运行")
    return await _request_browser_screenshot("account", account.id)


@router.get("/browser-resources", response_model=list[BrowserResourceResponse])
async def browser_resources(user: Annotated[User, Depends(admin_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    items = await list_resources()
    account_ids = {item["account_id"] for item in items if item.get("account_id")}
    names = {}
    if account_ids:
        accounts = await db.scalars(select(DouyinAccount).where(DouyinAccount.id.in_(account_ids)))
        names = {account.id: account.display_name for account in accounts}
    for item in items:
        item["account_name"] = names.get(item.get("account_id"))
    return items


@router.get("/browser-resources/{kind}/{resource_id}/screenshot")
async def browser_resource_screenshot(kind: str, resource_id: str, user: Annotated[User, Depends(admin_user)]):
    if kind not in {"warm", "login", "account", "task"}:
        raise HTTPException(404, "浏览器类型不存在")
    if not await redis_client.exists(resource_key(kind, resource_id)):
        raise HTTPException(404, "浏览器已关闭或心跳已过期")
    return await _request_browser_screenshot(kind, resource_id)


@router.post("/browser-resources/warm/open", status_code=202)
async def open_warm_browser(user: Annotated[User, Depends(admin_user)]):
    if not await redis_client.exists(WORKER_HEARTBEAT_KEYS["扫码登录 Worker"]):
        raise HTTPException(503, "扫码登录 Worker 未运行")
    await redis_client.rpush("douyin:login:pool:commands", json.dumps({"action": "open"}))
    return {"message": "备用浏览器打开指令已发送"}


@router.post("/browser-resources/{kind}/{resource_id}/close", status_code=202)
async def close_browser_resource(kind: str, resource_id: str, user: Annotated[User, Depends(admin_user)],
                                 db: Annotated[AsyncSession, Depends(get_db)]):
    if kind not in {"warm", "login", "account", "task"}:
        raise HTTPException(404, "浏览器类型不存在")
    if kind != "warm" and not resource_id.isdigit():
        raise HTTPException(422, "浏览器标识无效")
    resource_data = await redis_client.get(resource_key(kind, resource_id))
    if not resource_data:
        raise HTTPException(404, "浏览器已关闭或心跳已过期")
    if kind == "warm":
        owner = json.loads(resource_data)
        await redis_client.rpush(pool_command_key(owner["hostname"], owner["process_id"]),
                                 json.dumps({"action": "close", "resource_id": resource_id}))
    elif kind == "login":
        await close_login_session(int(resource_id), user, db)
    elif kind == "account":
        await close_account_browser(int(resource_id), user, db)
    else:
        assignment = await db.get(TaskAccount, int(resource_id))
        if not assignment or assignment.status not in {"assigned", "running"}:
            raise HTTPException(409, "任务账号已经停止")
        await remove_task_account(assignment.task_id, assignment.account_id, user, db)
        db.add(AccountLog(account_id=assignment.account_id, event_type="task_browser_closed_by_admin",
                          detail={"task_id": assignment.task_id, "admin_id": user.id}))
        remaining = await db.scalar(select(TaskAccount.id).where(
            TaskAccount.task_id == assignment.task_id,
            TaskAccount.status.in_(("assigned", "running")),
            TaskAccount.deleted_at.is_(None),
        ).limit(1))
        if not remaining:
            task = await db.get(Task, assignment.task_id)
            if task and task.status in {"running", "paused"}:
                task.status = "stopped"
                task.stopped_at = datetime.now()
        await db.commit()
    return {"message": "浏览器关闭指令已发送"}


@router.post("/douyin-login-sessions/{session_id}/verification-method", status_code=202)
async def select_login_verification_method(
    session_id: int,
    payload: LoginVerificationMethodRequest,
    user: Annotated[User, Depends(admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    session = await db.scalar(select(AccountLoginSession).where(
        AccountLoginSession.id == session_id,
        AccountLoginSession.deleted_at.is_(None),
    ))
    if not session:
        raise HTTPException(404, "登录会话不存在")
    if session.status != "method_required":
        raise HTTPException(409, "当前登录会话不需要选择验证方式")
    options_raw = await redis_client.get(f"douyin:login:verification-options:{session.id}")
    try:
        options = json.loads(options_raw) if options_raw else []
    except (TypeError, ValueError):
        options = []
    selected = next((option for option in options if option.get("id") == payload.method_id), None)
    if not selected:
        raise HTTPException(422, "验证方式不存在或页面已经变化")
    queue_key = f"douyin:login:verification-method:{session.id}"
    async with redis_client.pipeline(transaction=True) as pipe:
        pipe.delete(queue_key)
        pipe.rpush(queue_key, payload.method_id)
        pipe.expire(queue_key, 300)
        pipe.set(
            f"douyin:login:selected-verification:{session.id}",
            json.dumps(selected, ensure_ascii=False),
            ex=300,
        )
        await pipe.execute()
    db.add(AccountLog(
        account_id=session.account_id,
        event_type="verification_method_selected",
        detail={"session_id": session.id, "method": selected.get("label"), "admin_id": user.id},
    ))
    session.status = "method_processing"
    session.failure_reason = None
    await db.commit()
    return {"message": "验证方式已同步到登录浏览器"}


@router.post("/douyin-login-sessions/{session_id}/verification-code", status_code=202)
async def submit_login_verification_code(
    session_id: int,
    payload: LoginVerificationCodeRequest,
    user: Annotated[User, Depends(admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    session = await db.scalar(select(AccountLoginSession).where(
        AccountLoginSession.id == session_id,
        AccountLoginSession.deleted_at.is_(None),
    ))
    if not session:
        raise HTTPException(404, "登录会话不存在")
    if session.status != "verify_required":
        raise HTTPException(409, "当前登录会话不需要短信验证码")
    if session.expires_at <= datetime.now():
        raise HTTPException(409, "登录会话已过期")
    # 验证码只通过会话专属 Redis 队列传给浏览器，不写数据库或日志。
    queue_key = f"douyin:login:verification:{session.id}"
    async with redis_client.pipeline(transaction=True) as pipe:
        pipe.delete(queue_key)
        pipe.rpush(queue_key, payload.code)
        pipe.expire(queue_key, 300)
        await pipe.execute()
    db.add(AccountLog(
        account_id=session.account_id,
        event_type="verification_code_submitted",
        detail={"session_id": session.id, "admin_id": user.id},
    ))
    await db.commit()
    return {"message": "验证码已提交到登录浏览器"}


@router.post("/douyin-login-sessions/{session_id}/login-password", status_code=202)
async def submit_login_password(
    session_id: int,
    payload: LoginPasswordRequest,
    user: Annotated[User, Depends(admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    session = await db.scalar(select(AccountLoginSession).where(
        AccountLoginSession.id == session_id,
        AccountLoginSession.deleted_at.is_(None),
    ))
    if not session:
        raise HTTPException(404, "登录会话不存在")
    if session.status not in ("password_required", "password_ready"):
        selected_raw = await redis_client.get(f"douyin:login:selected-verification:{session.id}")
        try:
            selected = json.loads(selected_raw) if selected_raw else None
        except (TypeError, ValueError):
            selected = None
        password_method_pending = (
            session.status == "method_processing"
            and selected
            and "密码" in str(selected.get("label", ""))
        )
        if not password_method_pending:
            raise HTTPException(409, "当前登录会话不需要输入登录密码")
    if session.expires_at <= datetime.now():
        raise HTTPException(409, "登录会话已过期")
    # 登录密码只进入会话专属临时队列，不写数据库、不写日志内容。
    queue_key = f"douyin:login:password:{session.id}"
    async with redis_client.pipeline(transaction=True) as pipe:
        pipe.delete(queue_key)
        pipe.rpush(queue_key, encrypt_transient_secret(payload.password))
        pipe.expire(queue_key, 120)
        await pipe.execute()
    session.status = "password_filling"
    session.failure_reason = None
    db.add(AccountLog(
        account_id=session.account_id,
        event_type="login_password_submitted",
        detail={"session_id": session.id, "admin_id": user.id},
    ))
    await db.commit()
    return {"message": "登录密码已提交到登录浏览器，填写完成后请点击验证密码"}


@router.post("/douyin-login-sessions/{session_id}/verify-login-password", status_code=202)
async def verify_login_password(
    session_id: int,
    user: Annotated[User, Depends(admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    session = await db.scalar(select(AccountLoginSession).where(
        AccountLoginSession.id == session_id,
        AccountLoginSession.deleted_at.is_(None),
    ))
    if not session:
        raise HTTPException(404, "登录会话不存在")
    if session.status != "password_ready":
        raise HTTPException(409, "登录密码尚未填写到浏览器，请先提交密码")
    if session.expires_at <= datetime.now():
        raise HTTPException(409, "登录会话已过期")
    queue_key = f"douyin:login:password-verify:{session.id}"
    async with redis_client.pipeline(transaction=True) as pipe:
        pipe.delete(queue_key)
        pipe.rpush(queue_key, "verify")
        pipe.expire(queue_key, 120)
        await pipe.execute()
    session.status = "password_clicking"
    session.failure_reason = None
    db.add(AccountLog(
        account_id=session.account_id,
        event_type="login_password_verify_requested",
        detail={"session_id": session.id, "admin_id": user.id},
    ))
    await db.commit()
    return {"message": "验证密码指令已发送到登录浏览器"}


@router.post("/douyin-login-sessions/{session_id}/close", response_model=LoginSessionResponse)
async def close_login_session(session_id: int, user: Annotated[User, Depends(admin_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    session = await db.scalar(select(AccountLoginSession).where(AccountLoginSession.id == session_id, AccountLoginSession.deleted_at.is_(None)))
    if not session:
        raise HTTPException(404, "登录会话不存在")
    # 使用会话专属队列，避免关闭已结束会话的指令影响其他登录会话。
    await redis_client.rpush(f"douyin:login:close:{session.id}", "close")
    await redis_client.delete(
        f"douyin:login:verification:{session.id}",
        f"douyin:login:password:{session.id}",
        f"douyin:login:password-verify:{session.id}",
        f"douyin:login:verification-method:{session.id}",
        f"douyin:login:verification-options:{session.id}",
        f"douyin:login:selected-verification:{session.id}",
    )
    # 登录已成功时仅关闭浏览器，不覆盖成功状态；其余状态按管理员取消处理。
    if session.status != "success":
        session.status = "cancelled"
        session.completed_at = datetime.now()
    await db.commit()
    await db.refresh(session)
    return session


@router.get("/douyin-accounts/{account_id}/logs", response_model=list[AccountLogResponse])
async def account_logs(account_id: int, user: Annotated[User, Depends(admin_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    await _get_douyin_account(account_id, db)
    result = await db.scalars(select(AccountLog).where(AccountLog.account_id == account_id, AccountLog.deleted_at.is_(None)).order_by(AccountLog.id.desc()).limit(200))
    return list(result)


@router.get("/douyin-accounts/{account_id}/comment-logs", response_model=list[CommentLogResponse])
async def account_comment_logs(account_id: int, user: Annotated[User, Depends(admin_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    await _get_douyin_account(account_id, db)
    result = await db.scalars(select(CommentLog).where(
        CommentLog.account_id == account_id, CommentLog.deleted_at.is_(None),
    ).order_by(CommentLog.id.desc()).limit(500))
    return list(result)


def _script_result(script: Script, customer_login: str, customer_name: str) -> dict:
    return {
        "id": script.id,
        "customer_id": script.customer_id,
        "customer_login": customer_login,
        "customer_name": customer_name,
        "title": script.title,
        "content": script.content,
        "weight": script.weight,
        "status": script.status,
        "review_reason": script.review_reason,
        "created_at": script.created_at,
        "reviewed_at": script.reviewed_at,
    }


@router.get("/scripts", response_model=list[AdminScriptResponse])
async def list_admin_scripts(user: Annotated[User, Depends(admin_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    rows = (await db.execute(select(Script, User.login, User.display_name).join(
        User, User.id == Script.customer_id
    ).where(Script.deleted_at.is_(None)).order_by(Script.id.desc()))).all()
    return [_script_result(script, customer_login, customer_name) for script, customer_login, customer_name in rows]


@router.get("/scripts/review-queue", response_model=list[AdminScriptResponse])
async def review_queue(user: Annotated[User, Depends(admin_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    rows = (await db.execute(select(Script, User.login, User.display_name).join(
        User, User.id == Script.customer_id
    ).where(
        Script.status == "pending_review", Script.deleted_at.is_(None)
    ).order_by(Script.created_at))).all()
    return [_script_result(script, customer_login, customer_name) for script, customer_login, customer_name in rows]


async def _review(script_id: int, status: str, reason: str | None, user: User, db: AsyncSession):
    script = await db.scalar(select(Script).where(Script.id == script_id, Script.deleted_at.is_(None)))
    if not script:
        raise HTTPException(404, "话术不存在")
    if script.status != "pending_review":
        raise HTTPException(409, "话术不在待审核状态")
    script.status = status
    script.review_reason = reason
    script.reviewed_by = user.id
    script.reviewed_at = datetime.now()
    await db.commit()
    await db.refresh(script)
    return script


@router.post("/scripts/{script_id}/approve", response_model=ScriptResponse)
async def approve_script(script_id: int, user: Annotated[User, Depends(admin_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    return await _review(script_id, "approved", None, user, db)


@router.post("/scripts/batch-review", response_model=list[ScriptResponse])
async def batch_review_scripts(
    payload: ScriptBatchReviewRequest,
    user: Annotated[User, Depends(admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    scripts = list(await db.scalars(select(Script).where(
        Script.id.in_(payload.script_ids), Script.status == "pending_review",
        Script.deleted_at.is_(None),
    ).with_for_update()))
    if len(scripts) != len(payload.script_ids):
        raise HTTPException(409, "所选话术中存在已处理或不存在的数据，请刷新后重试")
    status = "approved" if payload.action == "approve" else "rejected"
    reason = None if status == "approved" else payload.reason.strip()
    reviewed_at = datetime.now()
    for script in scripts:
        script.status = status
        script.review_reason = reason
        script.reviewed_by = user.id
        script.reviewed_at = reviewed_at
    await db.commit()
    return scripts


@router.post("/scripts/{script_id}/reject", response_model=ScriptResponse)
async def reject_script(script_id: int, reason: str = "管理员拒绝", user: Annotated[User, Depends(admin_user)] = None, db: Annotated[AsyncSession, Depends(get_db)] = None):
    return await _review(script_id, "rejected", reason, user, db)
