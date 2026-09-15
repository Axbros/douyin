"""管理员手动唤醒已登录抖音账号的浏览器。"""
import asyncio
import os
import sys
from datetime import datetime

from playwright.async_api import async_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.core.crypto import decrypt_storage_state
from app.core.browser_preview import answer_screenshot_requests
from app.core.database import SessionLocal, redis_client
from app.models import AccountLog, DouyinAccount
from src.platforms import create_platform

WORKER_HEARTBEAT_KEY = "douyin:account-browser-worker:heartbeat"
WORKER_HEARTBEAT_TTL_SECONDS = 300


class LoginStateExpired(RuntimeError):
    pass


async def run_account_browser(account_id: int, active: set[int]):
    if account_id in active:
        print(f"[AccountBrowserWorker] 账号 {account_id} 浏览器已经运行", flush=True)
        return
    active.add(account_id)
    playwright = browser = context = None
    failed = False
    opened = False
    try:
        async with SessionLocal() as db:
            account = await db.get(DouyinAccount, account_id)
            if not account or not account.encrypted_storage_state:
                return
            state = decrypt_storage_state(account.encrypted_storage_state)
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(
            headless=os.getenv("PLAYWRIGHT_HEADLESS", "false").lower() == "true"
        )
        context = await browser.new_context(storage_state=state)
        page = await context.new_page()
        platform = create_platform("douyin")
        await page.goto(platform.home_url, wait_until="domcontentloaded", timeout=30000)
        if not await platform.check_logged_in(page, context):
            raise LoginStateExpired("登录状态已失效，请重新扫码登录")
        async with SessionLocal() as db:
            account = await db.get(DouyinAccount, account_id)
            if account and account.current_task_id is None:
                account.status = "browser_open"
            db.add(AccountLog(account_id=account_id, event_type="browser_opened", detail={"source": "admin"}))
            await db.commit()
            opened = True
        print(f"[AccountBrowserWorker] 账号 {account_id} 浏览器已唤醒，已恢复登录状态", flush=True)
        while True:
            await answer_screenshot_requests("account", account_id, page)
            if await redis_client.blpop(f"douyin:account-browser:close:{account_id}", timeout=1):
                break
    except Exception as exc:
        failed = True
        print(f"[AccountBrowserWorker] 账号 {account_id} 启动失败: {type(exc).__name__}: {exc}", flush=True)
        async with SessionLocal() as db:
            account = await db.get(DouyinAccount, account_id)
            if account:
                account.last_error = f"{type(exc).__name__}: {exc}"[:1000]
                if isinstance(exc, LoginStateExpired):
                    account.status = "unlogged"
                    account.encrypted_storage_state = None
                else:
                    account.status = "error"
                db.add(AccountLog(account_id=account_id, event_type="login_expired" if isinstance(exc, LoginStateExpired) else "browser_error", detail={"reason": account.last_error}))
                await db.commit()
    finally:
        if context:
            try:
                await context.close()
            except Exception:
                pass
        if browser:
            try:
                await browser.close()
            except Exception:
                pass
        if playwright:
            try:
                await playwright.stop()
            except Exception:
                pass
        active.discard(account_id)
        async with SessionLocal() as db:
            account = await db.get(DouyinAccount, account_id)
            if account and account.current_task_id is None and account.status == "browser_open":
                account.status = "available" if account.enabled else "disabled"
            if account and opened and not failed:
                db.add(AccountLog(account_id=account_id, event_type="browser_closed", detail={"source": "admin"}))
            await db.commit()
        print(f"[AccountBrowserWorker] 账号 {account_id} 浏览器已关闭", flush=True)


async def main():
    print("[AccountBrowserWorker] 已启动，等待浏览器唤醒指令...", flush=True)
    await redis_client.ping()
    active: set[int] = set()
    tasks: set[asyncio.Task] = set()
    def task_finished(task: asyncio.Task):
        tasks.discard(task)
        if not task.cancelled() and task.exception():
            print(f"[AccountBrowserWorker] 后台任务异常: {task.exception()}", flush=True)
    try:
        while True:
            # 管理接口依赖此心跳判断唤醒指令是否真的有人消费。
            await redis_client.set(
                WORKER_HEARTBEAT_KEY,
                datetime.now().isoformat(),
                ex=WORKER_HEARTBEAT_TTL_SECONDS,
            )
            item = await redis_client.blpop("douyin:account-browser:open", timeout=5)
            if item:
                task = asyncio.create_task(run_account_browser(int(item[1]), active))
                tasks.add(task)
                task.add_done_callback(task_finished)
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await redis_client.delete(WORKER_HEARTBEAT_KEY)


if __name__ == "__main__":
    asyncio.run(main())
