import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

from fastapi import FastAPI, HTTPException
from sqlalchemy import or_, select, text

from app.api import admin, auth, customer
from app.core.database import SessionLocal, engine, redis_client
from app.core.platform_settings import get_platform_settings
from app.models import AccountLog, DouyinAccount, Task, TaskAccount, Worker


async def reconcile_stale_task_accounts():
    """任务 Worker 离线后释放遗留的执行账号，避免永久占用。"""
    while True:
        await asyncio.sleep(10)
        try:
            async with SessionLocal() as db:
                platform_settings = await get_platform_settings(db)
                worker_cutoff = datetime.now() - timedelta(seconds=platform_settings["worker_heartbeat_timeout_seconds"])
                stale_workers = list(await db.scalars(select(Worker).where(
                    Worker.worker_key.like("task:%"),
                    Worker.status == "online",
                    or_(Worker.last_heartbeat_at.is_(None), Worker.last_heartbeat_at < worker_cutoff),
                    Worker.deleted_at.is_(None),
                )))
                if not stale_workers:
                    continue
                stale_worker_ids = [worker.id for worker in stale_workers]
                for worker in stale_workers:
                    worker.status = "offline"
                cutoff = datetime.now() - timedelta(seconds=platform_settings["account_reclaim_seconds"])
                rows = (await db.execute(select(DouyinAccount, TaskAccount).join(
                    TaskAccount,
                    (TaskAccount.account_id == DouyinAccount.id) &
                    (TaskAccount.task_id == DouyinAccount.current_task_id),
                ).where(
                    TaskAccount.status == "running",
                    TaskAccount.deleted_at.is_(None),
                    DouyinAccount.current_worker_id.in_(stale_worker_ids),
                    DouyinAccount.current_task_id.is_not(None),
                    or_(DouyinAccount.last_heartbeat_at.is_(None), DouyinAccount.last_heartbeat_at < cutoff),
                    DouyinAccount.deleted_at.is_(None),
                ))).all()
                task_ids: set[int] = set()
                for account, assignment in rows:
                    task_ids.add(assignment.task_id)
                    assignment.status = "error"
                    assignment.last_error = "任务 Worker 心跳丢失，系统已自动释放账号"
                    account.current_task_id = None
                    account.current_worker_id = None
                    account.status = "error"
                    account.last_error = assignment.last_error
                    db.add(AccountLog(account_id=account.id, event_type="worker_lost", detail={"task_id": assignment.task_id}))
                await db.flush()
                for task_id in task_ids:
                    active_assignment = await db.scalar(select(TaskAccount.id).where(
                        TaskAccount.task_id == task_id,
                        TaskAccount.status.in_(("assigned", "running")),
                        TaskAccount.deleted_at.is_(None),
                    ).limit(1))
                    if not active_assignment:
                        task = await db.get(Task, task_id)
                        if task and task.status in {"running", "paused"}:
                            task.status = "failed"
                            task.failure_reason = "任务 Worker 异常退出，执行账号已自动释放"
                await db.commit()
                if rows:
                    print(f"[API] 已释放 {len(rows)} 个失去 Worker 心跳的抖音账号", flush=True)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(f"[API] 清理异常执行账号失败: {type(exc).__name__}: {exc}", flush=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    reconcile_task = asyncio.create_task(reconcile_stale_task_accounts())
    try:
        yield
    finally:
        reconcile_task.cancel()
        await asyncio.gather(reconcile_task, return_exceptions=True)
        await redis_client.aclose()
        await engine.dispose()


app = FastAPI(title="Douyin Comment Platform API", version="0.1.0", lifespan=lifespan)
app.include_router(auth.router)
app.include_router(customer.router)
app.include_router(admin.router)


@app.get("/healthz", tags=["system"])
async def healthz():
    return {"status": "ok"}


@app.get("/readyz", tags=["system"])
async def readyz():
    """确认 API 依赖的 MySQL 和 Redis 均可用，供 Nginx/监控探活。"""
    checks = {"mysql": False, "redis": False}
    try:
        async with SessionLocal() as db:
            await db.execute(text("SELECT 1"))
        checks["mysql"] = True
    except Exception:
        pass
    try:
        checks["redis"] = bool(await redis_client.ping())
    except Exception:
        pass
    if not all(checks.values()):
        raise HTTPException(status_code=503, detail={"status": "not_ready", "checks": checks})
    return {"status": "ready", "checks": checks}
