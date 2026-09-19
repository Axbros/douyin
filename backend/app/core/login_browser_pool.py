"""FIFO pool for already opened, unauthenticated Douyin login browsers."""
import asyncio
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Awaitable, Callable
from uuid import uuid4


@dataclass
class PreparedBrowser:
    playwright: Any
    browser: Any
    context: Any
    page: Any
    proxy_config: dict | None
    proxy_bridge: Any = None
    resource_id: str = field(default_factory=lambda: uuid4().hex)
    opened_at: str = field(default_factory=lambda: datetime.now().isoformat())


class LoginBrowserPool:
    def __init__(self, prepare: Callable[[dict | None], Awaitable[PreparedBrowser]],
                 dispose: Callable[[PreparedBrowser], Awaitable[None]], size: int = 2):
        self.prepare = prepare
        self.dispose = dispose
        self.size = size
        self.desired_size = size
        self.target_proxy_config: dict | None = None
        self.ready: deque[PreparedBrowser] = deque()
        self.pending: dict[asyncio.Task, dict | None] = {}
        self.disposing: set[asyncio.Task] = set()
        self.lock = asyncio.Lock()
        self.closed = False

    async def initialize(self, proxy_config: dict | None) -> None:
        self.target_proxy_config = proxy_config
        # gather preserves launch order even when page loads finish out of order.
        results = await asyncio.gather(
            *(self.prepare(config) for config in self._desired_configs()), return_exceptions=True
        )
        for result in results:
            if isinstance(result, BaseException):
                print(f"[LoginWorker] 预热浏览器失败: {type(result).__name__}: {result}", flush=True)
            else:
                self.ready.append(result)
        print(f"[LoginWorker] 预热浏览器就绪: {len(self.ready)}/{self.size}", flush=True)

    def _desired_configs(self) -> list[dict | None]:
        if self.desired_size <= 0:
            return []
        if self.target_proxy_config is None:
            return [None] * self.desired_size
        if self.desired_size == 1:
            return [self.target_proxy_config]
        return [None] + [self.target_proxy_config] * (self.desired_size - 1)

    async def claim(self, proxy_config: dict | None) -> PreparedBrowser | None:
        async with self.lock:
            for item in list(self.ready):
                if item.proxy_config == proxy_config:
                    self.ready.remove(item)
                    if item.browser.is_connected() and not item.page.is_closed():
                        print(f"[LoginWorker] 领取预热浏览器，剩余 {len(self.ready)} 个", flush=True)
                        return item
                    await self.dispose(item)
        return None

    async def close_slot(self, resource_id: str) -> bool:
        async with self.lock:
            item = next((entry for entry in self.ready if entry.resource_id == resource_id), None)
            if item is None:
                return False
            self.ready.remove(item)
            self.desired_size = max(0, self.desired_size - 1)
            excess = max(0, len(self.ready) + len(self.pending) - self.desired_size)
            surplus_tasks = list(self.pending)[-excess:] if excess else []
            for task in surplus_tasks:
                task.cancel()
        await asyncio.gather(*surplus_tasks, return_exceptions=True)
        await self.dispose(item)
        return True

    async def open_slot(self, proxy_config: dict | None) -> None:
        async with self.lock:
            self.desired_size = min(self.size, self.desired_size + 1)
            self.target_proxy_config = proxy_config
        await self.replenish(proxy_config)

    async def prune_closed(self) -> list[str]:
        async with self.lock:
            stale = [item for item in self.ready if not item.browser.is_connected() or item.page.is_closed()]
            for item in stale:
                self.ready.remove(item)
        await asyncio.gather(*(self.dispose(item) for item in stale))
        if stale:
            await self.replenish(stale[0].proxy_config)
        return [item.resource_id for item in stale]

    async def replenish(self, proxy_config: dict | None) -> None:
        async with self.lock:
            existing = [item.proxy_config for item in self.ready] + list(self.pending.values())
            for config in self._desired_configs():
                if config in existing:
                    existing.remove(config)
                    continue
                if self.closed:
                    break
                task = asyncio.create_task(self.prepare(config))
                self.pending[task] = config
                task.add_done_callback(self._prepared)

    async def retarget(self, proxy_config: dict | None) -> None:
        """After a login, make the two idle slots useful for the next account."""
        async with self.lock:
            self.target_proxy_config = proxy_config
            desired = self._desired_configs()
            stale = []
            kept = deque()
            for item in self.ready:
                if item.proxy_config in desired:
                    desired.remove(item.proxy_config)
                    kept.append(item)
                else:
                    stale.append(item)
            self.ready = kept
            stale_pending = []
            for task, config in self.pending.items():
                if config in desired:
                    desired.remove(config)
                else:
                    stale_pending.append(task)
            for task in stale_pending:
                task.cancel()
        await asyncio.gather(*stale_pending, return_exceptions=True)
        await asyncio.gather(*(self.dispose(item) for item in stale))
        await self.replenish(proxy_config)

    async def navigate_slot(self, resource_id: str, url: str) -> str:
        async with self.lock:
            item = next((entry for entry in self.ready if entry.resource_id == resource_id), None)
            if item is None or not item.browser.is_connected() or item.page.is_closed():
                raise ValueError("备用浏览器已被领取或关闭")
            await item.page.goto(url, wait_until="domcontentloaded", timeout=15000)
            return item.page.url

    def _prepared(self, task: asyncio.Task) -> None:
        self.pending.pop(task, None)
        if task.cancelled():
            return
        try:
            item = task.result()
        except Exception as exc:
            print(f"[LoginWorker] 补充预热浏览器失败: {type(exc).__name__}: {exc}", flush=True)
            return
        remaining = self._desired_configs()
        for ready_item in self.ready:
            if ready_item.proxy_config in remaining:
                remaining.remove(ready_item.proxy_config)
        if self.closed or item.proxy_config not in remaining:
            disposal = asyncio.create_task(self.dispose(item))
            self.disposing.add(disposal)
            disposal.add_done_callback(self.disposing.discard)
        else:
            self.ready.append(item)
            print(f"[LoginWorker] 已补充预热浏览器，现有 {len(self.ready)} 个", flush=True)

    async def close(self) -> None:
        self.closed = True
        for task in list(self.pending):
            task.cancel()
        await asyncio.gather(*self.pending, return_exceptions=True)
        while self.ready:
            await self.dispose(self.ready.popleft())
        await asyncio.gather(*self.disposing, return_exceptions=True)
