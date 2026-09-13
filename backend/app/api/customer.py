from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies import customer_user
from app.models import Script, Task, TaskScript, User
from app.schemas import ScriptCreate, ScriptResponse, TaskCreate, TaskResponse

router = APIRouter(prefix="/api/customer", tags=["customer"])


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


@router.post("/tasks", response_model=TaskResponse, status_code=201)
async def create_task(payload: TaskCreate, user: Annotated[User, Depends(customer_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    if payload.max_interval_seconds < payload.min_interval_seconds:
        raise HTTPException(422, "最大间隔不能小于最小间隔")
    scripts = list(await db.scalars(select(Script).where(
        Script.id.in_(payload.script_ids), Script.customer_id == user.id,
        Script.status == "approved", Script.deleted_at.is_(None),
    )))
    if len(scripts) != len(set(payload.script_ids)):
        raise HTTPException(409, "只能使用审核通过且属于自己的话术")
    task = Task(customer_id=user.id, room_id=payload.room_id, target_account_count=payload.target_account_count,
                min_interval_seconds=payload.min_interval_seconds, max_interval_seconds=payload.max_interval_seconds)
    db.add(task)
    await db.flush()
    db.add_all([TaskScript(task_id=task.id, script_id=script.id) for script in scripts])
    await db.commit()
    await db.refresh(task)
    return task


@router.get("/tasks", response_model=list[TaskResponse])
async def list_tasks(user: Annotated[User, Depends(customer_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    result = await db.scalars(select(Task).where(Task.customer_id == user.id, Task.deleted_at.is_(None)).order_by(Task.id.desc()))
    return list(result)


async def _change_task_status(task_id: int, status: str, user: User, db: AsyncSession):
    task = await db.scalar(select(Task).where(Task.id == task_id, Task.customer_id == user.id, Task.deleted_at.is_(None)))
    if not task:
        raise HTTPException(404, "任务不存在")
    task.status = status
    if status == "paused":
        task.paused_at = datetime.now()
    if status == "stopped":
        task.stopped_at = datetime.now()
    await db.commit()
    await db.refresh(task)
    return task


@router.post("/tasks/{task_id}/pause", response_model=TaskResponse)
async def pause_task(task_id: int, user: Annotated[User, Depends(customer_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    return await _change_task_status(task_id, "paused", user, db)


@router.post("/tasks/{task_id}/stop", response_model=TaskResponse)
async def stop_task(task_id: int, user: Annotated[User, Depends(customer_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    return await _change_task_status(task_id, "stopped", user, db)
