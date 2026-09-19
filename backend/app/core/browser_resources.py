"""Short-lived registry of Chromium windows owned by browser workers."""
import asyncio
import json
import os
import socket
from datetime import datetime
from uuid import uuid4

from app.core.database import redis_client

RESOURCE_PREFIX = "douyin:browser-resource:active:"
RESOURCE_TTL_SECONDS = 15


def resource_key(kind: str, resource_id: str | int) -> str:
    return f"{RESOURCE_PREFIX}{kind}:{resource_id}"


def pool_command_key(hostname: str, process_id: int) -> str:
    return f"douyin:login:pool:commands:{hostname}:{process_id}"


def new_browser_id() -> str:
    return uuid4().hex


async def touch_resource(kind: str, resource_id: str | int, *, account_id: int | None = None,
                         task_id: int | None = None, opened_at: str | None = None,
                         url: str = "", proxy_label: str = "", browser_id: str = "",
                         origin: str = "") -> None:
    key = resource_key(kind, resource_id)
    previous = await redis_client.get(key)
    if previous:
        previous_data = json.loads(previous)
        opened_at = previous_data.get("opened_at", opened_at)
    data = {
        "kind": kind, "resource_id": str(resource_id), "account_id": account_id,
        "task_id": task_id, "opened_at": opened_at or datetime.now().isoformat(),
        "heartbeat_at": datetime.now().isoformat(), "url": url,
        "proxy_label": proxy_label, "browser_id": browser_id, "origin": origin,
        "hostname": socket.gethostname(), "process_id": os.getpid(),
    }
    await redis_client.set(key, json.dumps(data, ensure_ascii=False), ex=RESOURCE_TTL_SECONDS)


async def remove_resource(kind: str, resource_id: str | int) -> None:
    await redis_client.delete(resource_key(kind, resource_id))


async def resource_heartbeat(kind: str, resource_id: str | int, page, *,
                             account_id: int | None = None, task_id: int | None = None,
                             browser_id: str | None = None, origin: str = "new") -> None:
    opened_at = datetime.now().isoformat()
    browser_id = browser_id or new_browser_id()
    while True:
        try:
            await touch_resource(kind, resource_id, account_id=account_id, task_id=task_id,
                                 opened_at=opened_at, url=page.url if page else "",
                                 browser_id=browser_id, origin=origin)
        except Exception as exc:
            print(f"[BrowserResource] 浏览器心跳失败 {kind}:{resource_id}: {type(exc).__name__}: {exc}", flush=True)
        await asyncio.sleep(3)


async def list_resources() -> list[dict]:
    keys = [key async for key in redis_client.scan_iter(match=f"{RESOURCE_PREFIX}*", count=100)]
    if not keys:
        return []
    values = await redis_client.mget(keys)
    items = []
    for value in values:
        if value:
            try:
                items.append(json.loads(value))
            except (TypeError, ValueError):
                pass
    return sorted(items, key=lambda item: (item.get("opened_at", ""), item.get("resource_id", "")))
