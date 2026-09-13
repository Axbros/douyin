"""抖音扫码登录 Worker。

运行：PYTHONPATH=backend:项目根目录 python backend/workers/login_worker.py
二维码以 base64 PNG 写入登录会话，并通过 Redis pub/sub 通知管理端。
"""
import asyncio
import base64
import json
import os
import sys
from datetime import datetime

# 兼容仓库内较早生成的 protobuf 文件；必须在导入 src.platforms 前设置。
os.environ.setdefault("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION", "python")

from playwright.async_api import async_playwright
from sqlalchemy import select

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.core.crypto import encrypt_storage_state
from app.core.database import SessionLocal, redis_client
from app.models import AccountLoginSession, DouyinAccount
from src.platforms import create_platform


async def wait_for_manual_close(session_id: int, browser, context, playwright):
    """浏览器保持打开，直到管理员调用关闭接口。"""
    print(f"[LoginWorker] 浏览器保持打开，等待手动关闭，会话 {session_id}", flush=True)
    while True:
        item = await redis_client.blpop(f"douyin:login:close:{session_id}", timeout=5)
        if item:
            print(f"[LoginWorker] 收到手动关闭指令，会话 {session_id}", flush=True)
            try:
                await context.close()
            finally:
                try:
                    await browser.close()
                finally:
                    # Playwright driver 也要在浏览器关闭后停止，否则会遗留后台进程。
                    await playwright.stop()
            return


async def publish(session_id: int, event: str, **data):
    await redis_client.publish(f"douyin:login:{session_id}", json.dumps({"event": event, **data}, ensure_ascii=False))


async def run_session(session_id: int):
    print(f"[LoginWorker] 开始处理登录会话: {session_id}", flush=True)
    async with SessionLocal() as db:
        session = await db.scalar(select(AccountLoginSession).where(AccountLoginSession.id == session_id, AccountLoginSession.deleted_at.is_(None)))
        if not session or session.status != "waiting":
            return
        account = await db.get(DouyinAccount, session.account_id)
        if not account:
            return
        platform = create_platform("douyin")
        p = await async_playwright().start()
        browser = None
        context = None
        try:
            # 与原桌面程序一致：默认打开可见浏览器，让管理员直接扫码。
            # 无桌面服务器可设置 PLAYWRIGHT_HEADLESS=true，并通过二维码截图扫码。
            browser = await p.chromium.launch(headless=os.getenv("PLAYWRIGHT_HEADLESS", "false").lower() == "true")
            print(f"[LoginWorker] Chromium 已启动，会话 {session_id}", flush=True)
            context = await browser.new_context()
            page = await context.new_page()
            try:
                await page.goto(platform.home_url, wait_until="domcontentloaded", timeout=30000)
                print(f"[LoginWorker] 抖音页面已打开，会话 {session_id}", flush=True)
                # 等待首屏脚本和登录入口渲染完成，再点击登录打开扫码面板。
                try:
                    await page.wait_for_load_state("load", timeout=15000)
                except Exception as exc:
                    # 抖音会持续保持网络请求，load 超时不代表页面不可用。
                    print(f"[LoginWorker] 页面 load 等待超时，继续查找登录按钮: {type(exc).__name__}", flush=True)
                await asyncio.sleep(1)
                await platform.click_login_button(page)
                await asyncio.sleep(1)
                # 二维码图片的 class 也是动态的，使用稳定的 aria-label 和 data URL。
                # 直接读取 img.src，后台可以原样拼成 data:image/png;base64 图片展示。
                image = None
                qr_img = page.locator('img[aria-label="二维码"], img[src^="data:image/"]').first
                if await qr_img.count():
                    try:
                        await qr_img.wait_for(state="visible", timeout=10000)
                        src = await qr_img.get_attribute("src")
                        if src and src.startswith("data:image") and "," in src:
                            encoded = src.split(",", 1)[1]
                            print(
                                f"[LoginWorker] 获取到登录二维码: mime={src.split(';', 1)[0][5:]}, "
                                f"base64_length={len(encoded)}",
                                flush=True,
                            )
                            image = base64.b64decode(encoded)
                            print("[LoginWorker] 已读取二维码 img.src", flush=True)
                    except Exception as exc:
                        print(f"[LoginWorker] 读取二维码 img.src 失败: {type(exc).__name__}: {exc}", flush=True)
                if image is None:
                    # 兼容 aria-label 变化或页面结构变化，保留二维码区域/完整页面截图。
                    print("[LoginWorker] 未读取到二维码 img.src，使用页面截图兜底", flush=True)
                    qr = page.locator('[class*="XI37I0dP"]').first
                    if await qr.count():
                        image = await qr.screenshot(type="png")
                    else:
                        image = await page.screenshot(type="png")
                session.qr_payload = base64.b64encode(image).decode()
                await db.commit()
                print(f"[LoginWorker] 登录二维码已保存，会话 {session_id}，等待扫码", flush=True)
                await publish(session.id, "qr", image=session.qr_payload, expires_at=session.expires_at.isoformat())
                deadline = session.expires_at.timestamp()
                while datetime.now().timestamp() < deadline:
                    try:
                        logged_in = await platform.check_logged_in(page, context)
                    except Exception:
                        logged_in = False
                    if logged_in:
                        print(
                            f"[LoginWorker] 检测到登录成功，会话 {session_id}，账号 {account.id}，正在保存登录状态",
                            flush=True,
                        )
                        state = await context.storage_state()
                        account.encrypted_storage_state = encrypt_storage_state(state)
                        account.status = "available"
                        account.enabled = True
                        account.last_login_at = datetime.now()
                        session.status = "success"
                        session.completed_at = datetime.now()
                        await db.commit()
                        await publish(session.id, "success", account_id=account.id)
                        print(f"[LoginWorker] 扫码登录成功，会话 {session_id}", flush=True)
                        await wait_for_manual_close(session_id, browser, context, p)
                        return
                    await asyncio.sleep(2)
                session.status = "expired"
                session.completed_at = datetime.now()
                await db.commit()
                await publish(session.id, "expired")
                print(f"[LoginWorker] 登录会话已过期，会话 {session_id}", flush=True)
                await wait_for_manual_close(session_id, browser, context, p)
            except Exception as exc:
                session.status = "failed"
                session.failure_reason = f"{type(exc).__name__}: {exc}"[:500]
                await db.commit()
                await publish(session.id, "failed", reason=session.failure_reason)
                print(f"[LoginWorker] 登录会话失败，会话 {session_id}: {session.failure_reason}", flush=True)
                await wait_for_manual_close(session_id, browser, context, p)
        except Exception:
            if browser:
                print(f"[LoginWorker] Worker 内部异常，会话 {session_id}，浏览器仍保持打开", flush=True)
                # 发生未预期异常时也保留浏览器，便于管理员检查页面并手动结束会话。
                await wait_for_manual_close(session_id, browser, context, p)
            else:
                # Chromium 尚未启动时没有可保留的浏览器，释放 Playwright 驱动。
                await p.stop()
                raise


async def main():
    print("[LoginWorker] 已启动，正在连接 Redis...", flush=True)
    await redis_client.ping()
    print("[LoginWorker] Redis 已连接，等待扫码登录任务...", flush=True)
    while True:
        try:
            item = await redis_client.blpop("douyin:login:sessions", timeout=5)
            if item:
                await run_session(int(item[1]))
        except Exception as exc:
            # Redis 重启或网络短暂中断后，清理旧连接并自动重连。
            print(f"[LoginWorker] Redis 暂时不可用: {type(exc).__name__}: {exc}")
            try:
                await redis_client.aclose()
            except Exception:
                pass
            await asyncio.sleep(2)


if __name__ == "__main__":
    asyncio.run(main())
