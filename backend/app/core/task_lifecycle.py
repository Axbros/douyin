from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import redis_client
from app.core.subscriptions import get_customer_plan
from app.models import DouyinAccount, Script, Task, TaskAccount, TaskScript, User


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
