from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import redis_client
from app.core.douyin_urls import extract_douyin_live_url
from app.core.platform_settings import get_platform_settings
from app.core.subscriptions import get_customer_plan
from app.models import DouyinAccount, Script, Task, TaskAccount, TaskScript, User
from app.schemas import TaskUpdate


async def update_stopped_task(task: Task, payload: TaskUpdate, db: AsyncSession) -> Task:
    if task.status != "stopped":
        raise HTTPException(409, "只有已停止任务可以编辑")
    try:
        live_url = extract_douyin_live_url(payload.live_share_text)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

    customer = await db.scalar(select(User).where(User.id == task.customer_id).with_for_update())
    if not customer:
        raise HTTPException(404, "所属客户不存在")
    plan = await get_customer_plan(db, customer)
    settings = await get_platform_settings(db)
    if payload.max_interval_seconds < payload.min_interval_seconds:
        raise HTTPException(422, "最大间隔不能小于最小间隔")
    if (payload.min_interval_seconds < settings["comment_min_interval_seconds"]
            or payload.max_interval_seconds > settings["comment_max_interval_seconds"]):
        raise HTTPException(422, f"评论间隔必须在 {settings['comment_min_interval_seconds']}–{settings['comment_max_interval_seconds']} 秒之间")
    if len(set(payload.script_ids)) != len(payload.script_ids):
        raise HTTPException(422, "话术不能重复选择")
    if len(payload.script_ids) > plan.max_scripts_per_task:
        raise HTTPException(422, f"当前套餐单个任务最多选择 {plan.max_scripts_per_task} 条话术")
    scripts = list(await db.scalars(select(Script).where(
        Script.id.in_(payload.script_ids), Script.customer_id == customer.id,
        Script.status == "approved", Script.deleted_at.is_(None),
    )))
    if len(scripts) != len(payload.script_ids):
        raise HTTPException(409, "只能使用审核通过且属于自己的话术")

    account_ids: list[int] = []
    if payload.account_source == "customer":
        account_ids = list(dict.fromkeys(payload.account_ids))
        if not account_ids:
            raise HTTPException(422, "使用自有账号时至少选择一个账号")
        accounts = list(await db.scalars(select(DouyinAccount).where(
            DouyinAccount.id.in_(account_ids),
            DouyinAccount.ownership_type == "customer",
            DouyinAccount.owner_customer_id == customer.id,
            DouyinAccount.enabled.is_(True),
            DouyinAccount.status == "available",
            DouyinAccount.current_task_id.is_(None),
            DouyinAccount.encrypted_storage_state.is_not(None),
            DouyinAccount.deleted_at.is_(None),
        ).with_for_update()))
        if len(accounts) != len(account_ids):
            raise HTTPException(409, "所选自有账号中存在未登录、不可用、忙碌或不属于您的账号")
        target_account_count = len(account_ids)
    else:
        if payload.account_ids:
            raise HTTPException(422, "平台账号模式不需要选择账号")
        target_account_count = plan.platform_account_count

    now = datetime.now()
    existing_scripts = list(await db.scalars(select(TaskScript).where(TaskScript.task_id == task.id).with_for_update()))
    script_links = {link.script_id: link for link in existing_scripts}
    for index, script_id in enumerate(payload.script_ids):
        link = script_links.get(script_id)
        if link:
            link.sort_order = index
            link.deleted_at = None
        else:
            db.add(TaskScript(task_id=task.id, script_id=script_id, sort_order=index))
    selected_script_ids = set(payload.script_ids)
    for link in existing_scripts:
        if link.script_id not in selected_script_ids:
            link.deleted_at = now

    if payload.account_source == "customer":
        existing_accounts = list(await db.scalars(select(TaskAccount).where(TaskAccount.task_id == task.id).with_for_update()))
        account_links = {link.account_id: link for link in existing_accounts}
        selected_account_ids = set(account_ids)
        for account_id in account_ids:
            link = account_links.get(account_id)
            if link:
                link.status = "removed"
                link.removed_at = now
                link.last_error = None
                link.deleted_at = None
            else:
                db.add(TaskAccount(
                    task_id=task.id, account_id=account_id, status="removed",
                    assigned_by=customer.id, removed_at=now,
                ))
        for link in existing_accounts:
            if link.account_id not in selected_account_ids:
                link.deleted_at = now

    task.live_url = live_url
    task.account_source = payload.account_source
    task.target_account_count = target_account_count
    task.script_order_mode = payload.script_order_mode
    task.min_interval_seconds = payload.min_interval_seconds
    task.max_interval_seconds = payload.max_interval_seconds
    task.failure_reason = None
    await db.commit()
    await db.refresh(task)
    await redis_client.delete(f"douyin:task:script-sequence:{task.id}")
    return task


async def restart_stopped_task(task: Task, assigned_by: int, db: AsyncSession) -> Task:
    if task.status != "stopped":
        raise HTTPException(409, "只有已停止任务可以重新启动")

    customer = await db.scalar(select(User).where(User.id == task.customer_id).with_for_update())
    now = datetime.now()
    if not customer or customer.status != "active" or not customer.expires_at or customer.expires_at <= now:
        raise HTTPException(409, "所属客户已禁用、未激活或服务已到期")

    plan = await get_customer_plan(db, customer)
    active_count = await db.scalar(select(func.count(Task.id)).where(
        Task.customer_id == customer.id,
        Task.id != task.id,
        Task.status.in_(("pending", "running", "paused")),
        Task.deleted_at.is_(None),
    ))
    if active_count >= plan.max_active_tasks:
        raise HTTPException(409, f"当前套餐的活动任务已达到上限（{plan.max_active_tasks} 个）")

    task_script_ids = list(await db.scalars(select(TaskScript.script_id).where(
        TaskScript.task_id == task.id, TaskScript.deleted_at.is_(None),
    )))
    approved_script_ids = list(await db.scalars(select(Script.id).where(
        Script.id.in_(task_script_ids), Script.customer_id == customer.id,
        Script.status == "approved", Script.deleted_at.is_(None),
    ))) if task_script_ids else []
    if len(approved_script_ids) != len(task_script_ids) or not approved_script_ids:
        raise HTTPException(409, "任务中的话术已失效或不再处于审核通过状态")

    if task.account_source == "customer":
        historical_ids = list(await db.scalars(select(TaskAccount.account_id).where(
            TaskAccount.task_id == task.id, TaskAccount.deleted_at.is_(None),
        ).order_by(TaskAccount.id.asc())))
        historical_ids = list(dict.fromkeys(historical_ids))
        available = list(await db.scalars(select(DouyinAccount).where(
            DouyinAccount.id.in_(historical_ids),
            DouyinAccount.ownership_type == "customer",
            DouyinAccount.owner_customer_id == customer.id,
            DouyinAccount.enabled.is_(True),
            DouyinAccount.status == "available",
            DouyinAccount.current_task_id.is_(None),
            DouyinAccount.encrypted_storage_state.is_not(None),
            DouyinAccount.deleted_at.is_(None),
        ).with_for_update())) if historical_ids else []
        available_by_id = {account.id: account for account in available}
        accounts = [available_by_id[account_id] for account_id in historical_ids if account_id in available_by_id]
        accounts = accounts[:task.target_account_count]
        if len(accounts) < task.target_account_count:
            raise HTTPException(409, f"原任务的自有抖音账号不足，需要 {task.target_account_count} 个可用账号")
    else:
        accounts = list(await db.scalars(select(DouyinAccount).where(
            DouyinAccount.ownership_type == "platform",
            DouyinAccount.enabled.is_(True),
            DouyinAccount.status == "available",
            DouyinAccount.current_task_id.is_(None),
            DouyinAccount.encrypted_storage_state.is_not(None),
            DouyinAccount.deleted_at.is_(None),
        ).order_by(func.rand()).limit(task.target_account_count).with_for_update()))
        if len(accounts) < task.target_account_count:
            raise HTTPException(409, f"平台可用抖音账号不足，需要 {task.target_account_count} 个，当前只有 {len(accounts)} 个")

    account_ids = [account.id for account in accounts]
    assignments = list(await db.scalars(select(TaskAccount).where(
        TaskAccount.task_id == task.id, TaskAccount.account_id.in_(account_ids),
    ).with_for_update()))
    assignment_by_account = {assignment.account_id: assignment for assignment in assignments}
    active_assignments: list[TaskAccount] = []
    for account in accounts:
        assignment = assignment_by_account.get(account.id)
        if assignment:
            assignment.status = "assigned"
            assignment.assigned_by = assigned_by
            assignment.assigned_at = now
            assignment.removed_at = None
            assignment.last_error = None
            assignment.deleted_at = None
        else:
            assignment = TaskAccount(
                task_id=task.id, account_id=account.id, status="assigned", assigned_by=assigned_by,
            )
            db.add(assignment)
        account.current_task_id = task.id
        account.status = "busy"
        active_assignments.append(assignment)

    task.status = "pending"
    task.started_at = None
    task.paused_at = None
    task.stopped_at = None
    task.failure_reason = None
    await db.commit()
    await db.refresh(task)
    await redis_client.delete(f"douyin:task:script-sequence:{task.id}")
    for assignment in active_assignments:
        await redis_client.delete(f"douyin:task-account:stop:{assignment.id}")
    await redis_client.rpush("douyin:tasks", str(task.id))
    return task


async def delete_stopped_task(task: Task, db: AsyncSession) -> None:
    if task.status != "stopped":
        raise HTTPException(409, "只有已停止任务可以删除")
    task.deleted_at = datetime.now()
    await db.commit()
