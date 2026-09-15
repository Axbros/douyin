import os
import socket
from datetime import datetime

from sqlalchemy import select

from app.core.database import SessionLocal
from app.models import Worker


async def register_worker(kind: str) -> tuple[int, str]:
    # systemd 和本地启动脚本会传稳定实例编号；手动启动时退回 PID。
    instance_id = os.getenv("WORKER_INSTANCE_ID", str(os.getpid()))
    worker_key = f"{kind}:{socket.gethostname()}:{instance_id}"[:100]
    async with SessionLocal() as db:
        worker = await db.scalar(select(Worker).where(Worker.worker_key == worker_key))
        if not worker:
            worker = Worker(worker_key=worker_key, hostname=socket.gethostname())
            db.add(worker)
        worker.process_id = os.getpid()
        worker.status = "online"
        worker.last_heartbeat_at = datetime.now()
        await db.commit()
        await db.refresh(worker)
        return worker.id, worker_key


async def heartbeat_worker(worker_id: int):
    async with SessionLocal() as db:
        worker = await db.get(Worker, worker_id)
        if worker:
            worker.status = "online"
            worker.last_heartbeat_at = datetime.now()
            await db.commit()


async def mark_worker_offline(worker_id: int):
    async with SessionLocal() as db:
        worker = await db.get(Worker, worker_id)
        if worker:
            worker.status = "offline"
            worker.last_heartbeat_at = datetime.now()
            await db.commit()
