from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db, redis_client
from app.core.platform_settings import get_platform_settings
from app.dependencies import customer_user
from app.models import AccountLog, AccountLoginSession, CommentLog, DouyinAccount, Script, Task, TaskAccount, TaskScript, User
from app.schemas import (AccountResponse, CommentLogResponse, DouyinAccountUpdate, LoginPasswordRequest,
                         LoginSessionResponse, LoginVerificationCodeRequest, LoginVerificationMethodRequest,
                         PlatformSettingsResponse, ScriptBulkCreate, ScriptCreate, ScriptResponse,
                         ScriptUpdate, TaskAccountResponse, TaskCreate, TaskResponse)

router = APIRouter(prefix="/api/customer", tags=["customer"])


async def _get_owned_account(account_id: int, user: User, db: AsyncSession) -> DouyinAccount:
    account = await db.scalar(select(DouyinAccount).where(
        DouyinAccount.id == account_id, DouyinAccount.ownership_type == "customer",
        DouyinAccount.owner_customer_id == user.id, DouyinAccount.deleted_at.is_(None),
    ))
    if not account:
        raise HTTPException(404, "自有抖音账号不存在")
    return account


async def _get_owned_session(session_id: int, user: User, db: AsyncSession) -> AccountLoginSession:
    session = await db.scalar(select(AccountLoginSession).join(
        DouyinAccount, DouyinAccount.id == AccountLoginSession.account_id
    ).where(
        AccountLoginSession.id == session_id, AccountLoginSession.deleted_at.is_(None),
        DouyinAccount.ownership_type == "customer", DouyinAccount.owner_customer_id == user.id,
        DouyinAccount.deleted_at.is_(None),
    ))
    if not session:
        raise HTTPException(404, "登录会话不存在")
    return session


@router.get("/platform-settings", response_model=PlatformSettingsResponse)
async def customer_platform_settings(user: Annotated[User, Depends(customer_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    return await get_platform_settings(db)


@router.get("/douyin-accounts", response_model=list[AccountResponse])
async def list_owned_accounts(user: Annotated[User, Depends(customer_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    return list(await db.scalars(select(DouyinAccount).where(
        DouyinAccount.ownership_type == "customer", DouyinAccount.owner_customer_id == user.id,
        DouyinAccount.deleted_at.is_(None),
    ).order_by(DouyinAccount.id.desc())))


@router.get("/douyin-account-quota")
async def owned_account_quota(user: Annotated[User, Depends(customer_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    settings = await get_platform_settings(db)
    used = await db.scalar(select(func.count(DouyinAccount.id)).where(
        DouyinAccount.ownership_type == "customer", DouyinAccount.owner_customer_id == user.id,
        DouyinAccount.deleted_at.is_(None),
    ))
    base = settings["default_customer_account_quota"]
    return {"base_quota": base, "extra_quota": user.extra_douyin_account_quota,
            "total_quota": base + user.extra_douyin_account_quota, "used": used}


@router.post("/douyin-accounts", response_model=AccountResponse, status_code=201)
async def create_owned_account(display_name: str, user: Annotated[User, Depends(customer_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    locked_user = await db.scalar(select(User).where(User.id == user.id).with_for_update())
    settings = await get_platform_settings(db)
    used = await db.scalar(select(func.count(DouyinAccount.id)).where(
        DouyinAccount.ownership_type == "customer", DouyinAccount.owner_customer_id == user.id,
        DouyinAccount.deleted_at.is_(None),
    ))
    quota = settings["default_customer_account_quota"] + locked_user.extra_douyin_account_quota
    if used >= quota:
        raise HTTPException(409, f"自有抖音账号额度已用完（{used}/{quota}），请购买额外额度")
    account = DouyinAccount(display_name=display_name.strip() or "我的抖音账号", ownership_type="customer",
                            owner_customer_id=user.id, status="unlogged", enabled=True)
    db.add(account); await db.flush()
    db.add(AccountLog(account_id=account.id, event_type="account_created", detail={"customer_id": user.id, "ownership_type": "customer"}))
    await db.commit(); await db.refresh(account)
    return account


@router.patch("/douyin-accounts/{account_id}", response_model=AccountResponse)
async def update_owned_account(account_id: int, payload: DouyinAccountUpdate, user: Annotated[User, Depends(customer_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    account = await _get_owned_account(account_id, user, db)
    account.display_name = payload.display_name.strip()
    if not account.display_name:
        raise HTTPException(422, "账号名称不能为空")
    db.add(AccountLog(account_id=account.id, event_type="account_updated", detail={"customer_id": user.id}))
    await db.commit(); await db.refresh(account)
    return account


@router.delete("/douyin-accounts/{account_id}", status_code=204)
async def delete_owned_account(account_id: int, user: Annotated[User, Depends(customer_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    account = await _get_owned_account(account_id, user, db)
    if account.current_task_id is not None:
        raise HTTPException(409, "账号正在执行任务，暂时不能删除")
    account.deleted_at = datetime.now(); account.enabled = False; account.status = "disabled"
    db.add(AccountLog(account_id=account.id, event_type="account_deleted", detail={"customer_id": user.id}))
    await db.commit(); await redis_client.rpush(f"douyin:account-browser:close:{account.id}", "close")


@router.post("/douyin-accounts/{account_id}/login-session", response_model=LoginSessionResponse, status_code=201)
async def create_owned_login_session(account_id: int, user: Annotated[User, Depends(customer_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    await _get_owned_account(account_id, user, db)
    from app.api.admin import create_login_session
    return await create_login_session(account_id, user, db)


@router.get("/douyin-login-sessions/{session_id}", response_model=LoginSessionResponse)
async def owned_login_session_status(session_id: int, user: Annotated[User, Depends(customer_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    await _get_owned_session(session_id, user, db)
    from app.api.admin import login_session_status
    return await login_session_status(session_id, user, db)


@router.post("/douyin-login-sessions/{session_id}/verification-method", status_code=202)
async def owned_verification_method(session_id: int, payload: LoginVerificationMethodRequest, user: Annotated[User, Depends(customer_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    await _get_owned_session(session_id, user, db)
    from app.api.admin import select_login_verification_method
    return await select_login_verification_method(session_id, payload, user, db)


@router.post("/douyin-login-sessions/{session_id}/verification-code", status_code=202)
async def owned_verification_code(session_id: int, payload: LoginVerificationCodeRequest, user: Annotated[User, Depends(customer_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    await _get_owned_session(session_id, user, db)
    from app.api.admin import submit_login_verification_code
    return await submit_login_verification_code(session_id, payload, user, db)


@router.post("/douyin-login-sessions/{session_id}/login-password", status_code=202)
async def owned_login_password(session_id: int, payload: LoginPasswordRequest, user: Annotated[User, Depends(customer_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    await _get_owned_session(session_id, user, db)
    from app.api.admin import submit_login_password
    return await submit_login_password(session_id, payload, user, db)


@router.post("/douyin-login-sessions/{session_id}/close", response_model=LoginSessionResponse)
async def close_owned_login_session(session_id: int, user: Annotated[User, Depends(customer_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    await _get_owned_session(session_id, user, db)
    from app.api.admin import close_login_session
    return await close_login_session(session_id, user, db)


@router.get("/scripts", response_model=list[ScriptResponse])
async def list_scripts(user: Annotated[User, Depends(customer_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    result = await db.scalars(select(Script).where(Script.customer_id == user.id, Script.deleted_at.is_(None)).order_by(Script.id.desc()))
    return list(result)


@router.post("/scripts", response_model=ScriptResponse, status_code=201)
async def create_script(payload: ScriptCreate, user: Annotated[User, Depends(customer_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    script = Script(customer_id=user.id, **payload.model_dump())
    db.add(script)
    await db.commit()
    await db.refresh(script)
    return script


@router.post("/scripts/bulk", response_model=list[ScriptResponse], status_code=201)
async def bulk_create_scripts(payload: ScriptBulkCreate, user: Annotated[User, Depends(customer_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    platform_settings = await get_platform_settings(db)
    contents = [content.strip() for content in payload.contents if content.strip()]
    if not contents:
        raise HTTPException(422, "没有可导入的话术")
    if any(len(content) > 500 for content in contents):
        raise HTTPException(422, "单条话术不能超过 500 字")
    if len(contents) > platform_settings["script_bulk_import_limit"]:
        raise HTTPException(422, f"单次最多导入 {platform_settings['script_bulk_import_limit']} 条话术")
    scripts = [Script(
        customer_id=user.id,
        title=f"导入话术 {index + 1}",
        content=content,
        weight=1,
        status="draft",
    ) for index, content in enumerate(contents)]
    db.add_all(scripts)
    await db.commit()
    for script in scripts:
        await db.refresh(script)
    return scripts


@router.post("/scripts/{script_id}/submit-review", response_model=ScriptResponse)
async def submit_review(script_id: int, user: Annotated[User, Depends(customer_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    script = await db.scalar(select(Script).where(Script.id == script_id, Script.customer_id == user.id, Script.deleted_at.is_(None)))
    if not script:
        raise HTTPException(404, "话术不存在")
    if script.status not in {"draft", "rejected"}:
        raise HTTPException(409, "当前状态不能提交审核")
    script.status = "pending_review"
    script.review_reason = None
    await db.commit()
    await db.refresh(script)
    return script


@router.patch("/scripts/{script_id}", response_model=ScriptResponse)
async def update_script(script_id: int, payload: ScriptUpdate, user: Annotated[User, Depends(customer_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    script = await db.scalar(select(Script).where(
        Script.id == script_id, Script.customer_id == user.id, Script.deleted_at.is_(None)
    ))
    if not script:
        raise HTTPException(404, "话术不存在")
    if script.status not in {"draft", "rejected"}:
        raise HTTPException(409, "只有草稿或审核未通过的话术可以修改")
    values = payload.model_dump(exclude_unset=True)
    for name in ("title", "content"):
        if name in values:
            values[name] = values[name].strip()
            if not values[name]:
                raise HTTPException(422, "话术标题和内容不能为空")
    for name, value in values.items():
        setattr(script, name, value)
    script.status = "draft"
    script.review_reason = None
    await db.commit(); await db.refresh(script)
    return script


@router.delete("/scripts/{script_id}", status_code=204)
async def delete_script(script_id: int, user: Annotated[User, Depends(customer_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    script = await db.scalar(select(Script).where(
        Script.id == script_id, Script.customer_id == user.id, Script.deleted_at.is_(None)
    ))
    if not script:
        raise HTTPException(404, "话术不存在")
    if script.status not in {"draft", "rejected"}:
        raise HTTPException(409, "只有草稿或审核未通过的话术可以删除")
    script.deleted_at = datetime.now()
    await db.commit()


@router.post("/tasks", response_model=TaskResponse, status_code=201)
async def create_task(payload: TaskCreate, user: Annotated[User, Depends(customer_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    platform_settings = await get_platform_settings(db)
    # 锁定客户行，避免同一客户并发请求同时创建多个活动任务。
    await db.scalar(select(User).where(User.id == user.id).with_for_update())
    active_task_count = await db.scalar(select(func.count(Task.id)).where(
        Task.customer_id == user.id,
        Task.status.in_(("pending", "running", "paused")),
        Task.deleted_at.is_(None),
    ))
    if active_task_count >= platform_settings["max_active_tasks_per_customer"]:
        raise HTTPException(409, f"当前活动任务已达到上限（{platform_settings['max_active_tasks_per_customer']} 个）")
    if payload.max_interval_seconds < payload.min_interval_seconds:
        raise HTTPException(422, "最大间隔不能小于最小间隔")
    if payload.min_interval_seconds < platform_settings["comment_min_interval_seconds"] or payload.max_interval_seconds > platform_settings["comment_max_interval_seconds"]:
        raise HTTPException(422, f"评论间隔必须在 {platform_settings['comment_min_interval_seconds']}–{platform_settings['comment_max_interval_seconds']} 秒之间")
    if len(set(payload.script_ids)) != len(payload.script_ids):
        raise HTTPException(422, "话术不能重复选择")
    if len(payload.script_ids) > platform_settings["max_scripts_per_task"]:
        raise HTTPException(422, f"单个任务最多选择 {platform_settings['max_scripts_per_task']} 条话术")
    scripts = list(await db.scalars(select(Script).where(
        Script.id.in_(payload.script_ids), Script.customer_id == user.id,
        Script.status == "approved", Script.deleted_at.is_(None),
    )))
    if len(scripts) != len(set(payload.script_ids)):
        raise HTTPException(409, "只能使用审核通过且属于自己的话术")
    # 按任务模式锁定对应账号，避免并发任务抢占同一个浏览器身份。
    if payload.account_source == "customer":
        account_ids = list(dict.fromkeys(payload.account_ids))
        if not account_ids:
            raise HTTPException(422, "使用自有账号时至少选择一个账号")
        accounts = list(await db.scalars(select(DouyinAccount).where(
            DouyinAccount.id.in_(account_ids), DouyinAccount.ownership_type == "customer",
            DouyinAccount.owner_customer_id == user.id, DouyinAccount.enabled.is_(True),
            DouyinAccount.status == "available", DouyinAccount.current_task_id.is_(None),
            DouyinAccount.deleted_at.is_(None),
        ).with_for_update()))
        if len(accounts) != len(account_ids):
            raise HTTPException(409, "所选自有账号中存在未登录、不可用、忙碌或不属于您的账号")
        target_account_count = len(accounts)
        billing_amount_cents = platform_settings["customer_account_task_price_cents"]
    else:
        if payload.account_ids:
            raise HTTPException(422, "平台账号模式不需要选择账号")
        target_account_count = platform_settings["default_target_account_count"]
        accounts = list(await db.scalars(select(DouyinAccount).where(
            DouyinAccount.ownership_type == "platform", DouyinAccount.enabled.is_(True),
            DouyinAccount.status == "available", DouyinAccount.current_task_id.is_(None),
            DouyinAccount.deleted_at.is_(None),
        ).order_by(func.rand()).limit(target_account_count).with_for_update()))
        if len(accounts) < target_account_count:
            raise HTTPException(409, f"平台可用抖音账号不足，需要 {target_account_count} 个，当前只有 {len(accounts)} 个")
        billing_amount_cents = platform_settings["platform_account_task_price_cents"]
    task = Task(customer_id=user.id, room_id=payload.room_id, target_account_count=target_account_count,
                account_source=payload.account_source, billing_amount_cents=billing_amount_cents,
                min_interval_seconds=payload.min_interval_seconds, max_interval_seconds=payload.max_interval_seconds)
    db.add(task)
    await db.flush()
    db.add_all([TaskScript(task_id=task.id, script_id=script.id) for script in scripts])
    for account in accounts:
        account.current_task_id = task.id
        account.status = "busy"
        db.add(TaskAccount(task_id=task.id, account_id=account.id, status="assigned", assigned_by=user.id))
    await db.commit()
    await db.refresh(task)
    await redis_client.rpush("douyin:tasks", str(task.id))
    return task


@router.get("/tasks", response_model=list[TaskResponse])
async def list_tasks(user: Annotated[User, Depends(customer_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    result = await db.scalars(select(Task).where(Task.customer_id == user.id, Task.deleted_at.is_(None)).order_by(Task.id.desc()))
    return list(result)


@router.get("/tasks/{task_id}", response_model=TaskResponse)
async def get_task(task_id: int, user: Annotated[User, Depends(customer_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    task = await db.scalar(select(Task).where(
        Task.id == task_id, Task.customer_id == user.id, Task.deleted_at.is_(None)
    ))
    if not task:
        raise HTTPException(404, "任务不存在")
    return task


@router.get("/tasks/{task_id}/comment-logs", response_model=list[CommentLogResponse])
async def task_comment_logs(task_id: int, user: Annotated[User, Depends(customer_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    task = await db.scalar(select(Task).where(
        Task.id == task_id, Task.customer_id == user.id, Task.deleted_at.is_(None)
    ))
    if not task:
        raise HTTPException(404, "任务不存在")
    result = await db.scalars(select(CommentLog).where(
        CommentLog.task_id == task_id, CommentLog.deleted_at.is_(None)
    ).order_by(CommentLog.id.desc()).limit(200))
    return list(result)


@router.get("/tasks/{task_id}/accounts", response_model=list[TaskAccountResponse])
async def task_accounts(task_id: int, user: Annotated[User, Depends(customer_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    task = await db.scalar(select(Task).where(
        Task.id == task_id, Task.customer_id == user.id, Task.deleted_at.is_(None)
    ))
    if not task:
        raise HTTPException(404, "任务不存在")
    result = await db.scalars(select(TaskAccount).where(
        TaskAccount.task_id == task_id, TaskAccount.deleted_at.is_(None)
    ).order_by(TaskAccount.id))
    return list(result)


async def _change_task_status(task_id: int, status: str, user: User, db: AsyncSession):
    task = await db.scalar(select(Task).where(Task.id == task_id, Task.customer_id == user.id, Task.deleted_at.is_(None)))
    if not task:
        raise HTTPException(404, "任务不存在")
    if status == "paused" and task.status not in {"pending", "running"}:
        raise HTTPException(409, "当前任务状态不能暂停")
    if status == "stopped" and task.status in {"stopped", "failed", "completed"}:
        raise HTTPException(409, "当前任务已经结束")
    task.status = status
    if status == "paused":
        task.paused_at = datetime.now()
    stopped_assignment_ids: list[int] = []
    if status == "stopped":
        task.stopped_at = datetime.now()
        assigned = list(await db.scalars(select(TaskAccount).where(
            TaskAccount.task_id == task.id, TaskAccount.status.not_in(("removed", "completed")),
            TaskAccount.deleted_at.is_(None),
        ).with_for_update()))
        account_ids = [item.account_id for item in assigned]
        if account_ids:
            accounts = await db.scalars(select(DouyinAccount).where(DouyinAccount.id.in_(account_ids)).with_for_update())
            for account in accounts:
                if account.current_task_id == task.id:
                    account.current_task_id = None
                    account.status = "available" if account.enabled else "disabled"
        for item in assigned:
            stopped_assignment_ids.append(item.id)
            item.status = "removed"
            item.removed_at = datetime.now()
    await db.commit()
    await db.refresh(task)
    for assignment_id in stopped_assignment_ids:
        await redis_client.rpush(f"douyin:task-account:stop:{assignment_id}", "stop")
    return task


@router.post("/tasks/{task_id}/pause", response_model=TaskResponse)
async def pause_task(task_id: int, user: Annotated[User, Depends(customer_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    return await _change_task_status(task_id, "paused", user, db)


@router.post("/tasks/{task_id}/resume", response_model=TaskResponse)
async def resume_task(task_id: int, user: Annotated[User, Depends(customer_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    task = await db.scalar(select(Task).where(Task.id == task_id, Task.customer_id == user.id, Task.deleted_at.is_(None)))
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
async def stop_task(task_id: int, user: Annotated[User, Depends(customer_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    return await _change_task_status(task_id, "stopped", user, db)
