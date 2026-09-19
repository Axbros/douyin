"""抖音扫码登录 Worker。

运行：PYTHONPATH=backend:项目根目录 python backend/workers/login_worker.py
二维码以 base64 PNG 写入登录会话，并通过 Redis pub/sub 通知管理端。
"""
import asyncio
import base64
import json
import os
import re
import socket
import sys
from datetime import datetime, timedelta

# 兼容仓库内较早生成的 protobuf 文件；必须在导入 src.platforms 前设置。
os.environ.setdefault("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION", "python")

from playwright.async_api import Error as PlaywrightError, TimeoutError as PlaywrightTimeoutError, async_playwright
from sqlalchemy import select

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.core.crypto import decrypt_transient_secret, encrypt_storage_state
from app.core.browser_preview import answer_screenshot_requests
from app.core.browser_resources import pool_command_key, remove_resource, resource_heartbeat, touch_resource
from app.core.database import SessionLocal, redis_client
from app.core.login_browser_pool import LoginBrowserPool, PreparedBrowser
from app.core.platform_settings import get_platform_settings
from app.core.proxy_pool import browser_proxy_for_account, choose_proxy_for_new_account
from app.core.proxy_tunnel import Socks5Bridge
from app.models import AccountLoginSession, AccountLog, DouyinAccount
from src.platforms import create_platform

WORKER_HEARTBEAT_KEY = "douyin:login-worker:heartbeat"
WORKER_HEARTBEAT_TTL_SECONDS = 300
LOGIN_HOME_URL = "https://www.douyin.com/"
LOGIN_FALLBACK_URL = "https://live.douyin.com/"


async def login_home_usable(page) -> bool:
    try:
        if "验证码中间页" in await page.title():
            return False
        await page.get_by_text("登录", exact=True).first.wait_for(state="visible", timeout=5000)
        return True
    except Exception:
        return False


async def wait_for_optional_load(page) -> None:
    # A few Douyin resources can keep `load` pending even after the login UI is ready.
    try:
        await page.wait_for_load_state("load", timeout=3000)
    except PlaywrightTimeoutError:
        pass


async def dispose_prepared_browser(item: PreparedBrowser) -> None:
    for resource in (item.context, item.browser, item.playwright):
        if resource:
            try:
                await (resource.stop() if resource is item.playwright else resource.close())
            except Exception:
                pass
    if item.proxy_bridge:
        await item.proxy_bridge.close()


async def prepare_login_browser(proxy_config: dict | None) -> PreparedBrowser:
    """Navigate before the QR session; do not click Login or store account state."""
    item = PreparedBrowser(None, None, None, None, proxy_config)
    try:
        if proxy_config:
            item.proxy_bridge = Socks5Bridge(**proxy_config)
            browser_proxy = await item.proxy_bridge.start()
        else:
            browser_proxy = None
        item.playwright = await async_playwright().start()
        item.browser = await item.playwright.chromium.launch(
            headless=os.getenv("PLAYWRIGHT_HEADLESS", "false").lower() == "true",
            proxy=browser_proxy,
        )
        item.context = await item.browser.new_context()
        item.page = await item.context.new_page()
        try:
            await item.page.goto(LOGIN_HOME_URL, wait_until="domcontentloaded", timeout=20000)
            await wait_for_optional_load(item.page)
        except PlaywrightError as exc:
            # 页面可能停在验证中间页；窗口仍可供管理员查看和后续登录会话使用。
            print(f"[LoginWorker] 备用浏览器导航抖音首页失败，保留窗口: {type(exc).__name__}: {exc}", flush=True)
        print(f"[LoginWorker] 备用 Chromium 已打开，当前页面: {item.page.url}", flush=True)
        return item
    except BaseException:
        await dispose_prepared_browser(item)
        raise


async def recycle_claimed_browser(item: PreparedBrowser, browser_pool: LoginBrowserPool) -> bool:
    """Keep the Chromium process, but discard all cookies and page storage from the login attempt."""
    await item.context.close()
    fresh_context = await item.browser.new_context()
    try:
        fresh_page = await fresh_context.new_page()
        await fresh_page.goto(LOGIN_FALLBACK_URL, wait_until="domcontentloaded", timeout=20000)
        item.context = fresh_context
        item.page = fresh_page
        if item.proxy_config is not None and browser_pool.target_proxy_config != item.proxy_config:
            await browser_pool.retarget(item.proxy_config)
        return await browser_pool.return_claimed(item)
    except BaseException:
        await fresh_context.close()
        raise


async def initial_warm_proxy_config() -> dict | None:
    """Prefer a pending account's proxy, then the proxy used by the next new account."""
    async with SessionLocal() as db:
        pending_accounts = list(await db.scalars(select(DouyinAccount).where(
            DouyinAccount.deleted_at.is_(None), DouyinAccount.enabled.is_(True),
            DouyinAccount.encrypted_storage_state.is_(None), DouyinAccount.proxy_id.is_not(None),
        ).order_by(DouyinAccount.id.desc()).limit(20)))
        for account in pending_accounts:
            try:
                return await browser_proxy_for_account(db, account)
            except RuntimeError:
                continue
        proxy_id = await choose_proxy_for_new_account(db)
        if proxy_id is None:
            return None
        return await browser_proxy_for_account(db, DouyinAccount(proxy_id=proxy_id))


async def heartbeat():
    while True:
        try:
            await redis_client.set(WORKER_HEARTBEAT_KEY, datetime.now().isoformat(), ex=WORKER_HEARTBEAT_TTL_SECONDS)
        except Exception:
            pass
        await asyncio.sleep(5)


async def close_browser(session_id: int, browser, context, playwright):
    print(f"[LoginWorker] 收到手动关闭指令，会话 {session_id}", flush=True)
    try:
        if context:
            await context.close()
    except Exception:
        pass
    try:
        if browser and browser.is_connected():
            await browser.close()
    except Exception:
        pass
    try:
        if playwright:
            await playwright.stop()
    except Exception:
        pass


async def browser_window_closed(browser, context) -> bool:
    try:
        return not browser.is_connected() or not context.pages
    except Exception:
        return True


async def stop_closed_browser(session_id: int, browser, context, playwright):
    print(f"[LoginWorker] 浏览器窗口已关闭，会话 {session_id}，释放资源", flush=True)
    try:
        if context:
            await context.close()
    except Exception:
        pass
    try:
        if browser and browser.is_connected():
            await browser.close()
    except Exception:
        pass
    try:
        if playwright:
            await playwright.stop()
    except Exception:
        pass


async def wait_for_manual_close(session_id: int, browser, context, playwright, page=None, on_close=None):
    """浏览器保持打开，直到管理员调用接口或直接关闭窗口。"""
    print(f"[LoginWorker] 浏览器保持打开，等待手动关闭，会话 {session_id}", flush=True)
    while True:
        if await browser_window_closed(browser, context):
            await stop_closed_browser(session_id, browser, context, playwright)
            return
        if page is not None:
            await answer_screenshot_requests("login", session_id, page)
        if await redis_client.blpop(f"douyin:login:close:{session_id}", timeout=1):
            if on_close:
                await on_close()
            else:
                await close_browser(session_id, browser, context, playwright)
            return


async def navigate_or_close(page, url: str, session_id: int, browser, context, playwright, timeout: int = 60000, on_close=None) -> bool:
    """导航期间同时监听关闭指令；返回 True 表示浏览器已被关闭。"""
    # 完整 load 可能被第三方资源拖住；DOM、登录入口就绪后可继续。
    async def load_login_page():
        await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
        await wait_for_optional_load(page)

    navigation = asyncio.create_task(load_login_page())
    closing = asyncio.create_task(redis_client.blpop(f"douyin:login:close:{session_id}", timeout=0))
    done, _ = await asyncio.wait({navigation, closing}, return_when=asyncio.FIRST_COMPLETED)
    if closing in done:
        navigation.cancel()
        await asyncio.gather(navigation, return_exceptions=True)
        try:
            if on_close:
                await on_close()
            else:
                await close_browser(session_id, browser, context, playwright)
        except Exception:
            pass
        return True
    closing.cancel()
    await asyncio.gather(closing, return_exceptions=True)
    await navigation
    return False


async def publish(session_id: int, event: str, **data):
    await redis_client.publish(f"douyin:login:{session_id}", json.dumps({"event": event, **data}, ensure_ascii=False))


async def read_login_qr(page) -> tuple[str, str, float] | None:
    """Read only a visible, valid Douyin login QR image from the current page."""
    selectors = [
        "xpath=/html/body/div[36]/div/div/div/div/div/article/div/div[2]/div/div[1]/div/div/div[2]/div/div/div/div/div[2]/img",
        '[role="dialog"] img[aria-label="二维码"]',
        'img[aria-label="二维码"]',
    ]
    chosen = None
    for selector in selectors:
        candidates = page.locator(selector)
        for index in range(await candidates.count()):
            candidate = candidates.nth(index)
            try:
                if not await candidate.is_visible():
                    continue
                src = await candidate.get_attribute("src")
                if not src or not src.startswith("data:image/") or "," not in src:
                    continue
                header, encoded = src.split(",", 1)
                mime = header.split(";", 1)[0][5:]
                decoded = base64.b64decode(encoded, validate=True)
                area = await candidate.evaluate("el => el.getBoundingClientRect().width * el.getBoundingClientRect().height")
            except Exception:
                continue
            if mime == "image/png" and decoded.startswith(b"\x89PNG") and len(decoded) > 500 and (chosen is None or area > chosen[2]):
                chosen = (encoded, mime, area)
    return chosen


async def answer_login_qr_requests(session_id: int, page, session, db) -> bool:
    """Handle manual checks; return whether a QR is now saved on the session."""
    request_key = f"douyin:login:qr-request:{session_id}"
    found = False
    while request_id := await redis_client.lpop(request_key):
        request_id = request_id.decode() if isinstance(request_id, bytes) else request_id
        result = await read_login_qr(page)
        if result:
            encoded, mime, area = result
            session.qr_payload = encoded
            await db.commit()
            await publish(session_id, "qr", image=encoded, expires_at=session.expires_at.isoformat())
            print(f"[LoginWorker] 手动检测获取到登录二维码，会话 {session_id}: mime={mime}, area={area:.0f}", flush=True)
            found = True
        else:
            print(f"[LoginWorker] 手动检测未找到有效登录二维码，会话 {session_id}", flush=True)
        response_key = f"douyin:login:qr-response:{request_id}"
        await redis_client.rpush(response_key, json.dumps({"found": bool(result)}))
        await redis_client.expire(response_key, 30)
    return found


async def answer_login_click_requests(session_id: int, page, platform) -> bool:
    """Click the login entry in this session's browser on explicit UI request."""
    request_key = f"douyin:login:click-request:{session_id}"
    clicked_any = False
    while request_id := await redis_client.lpop(request_key):
        request_id = request_id.decode() if isinstance(request_id, bytes) else request_id
        try:
            clicked = await platform.click_login_button(page, log_missing=False, force=True)
            clicked_any = clicked_any or clicked
            result = {"clicked": clicked, "message": "已点击浏览器登录按钮" if clicked else "当前页面尚未找到登录按钮，请稍后重试"}
            print(f"[LoginWorker] 手动点击登录按钮，会话 {session_id}: {'成功' if clicked else '未找到按钮'}", flush=True)
        except Exception as exc:
            result = {"clicked": False, "message": f"点击登录按钮失败：{type(exc).__name__}: {exc}"[:300]}
        response_key = f"douyin:login:click-response:{request_id}"
        async with redis_client.pipeline(transaction=True) as pipe:
            pipe.rpush(response_key, json.dumps(result, ensure_ascii=False))
            pipe.expire(response_key, 30)
            await pipe.execute()
    return clicked_any


async def answer_login_qr_refresh_requests(session_id: int, page, platform, session, db) -> bool:
    """Refresh the same Chromium page and replace its QR when requested."""
    request_key = f"douyin:login:qr-refresh-request:{session_id}"
    processed = False
    while request_id := await redis_client.lpop(request_key):
        processed = True
        request_id = request_id.decode() if isinstance(request_id, bytes) else request_id
        response_key = f"douyin:login:qr-refresh-response:{request_id}"
        result = {"found": False, "message": "刷新后暂未出现二维码，可稍后点击获取登录二维码"}
        try:
            if session.status != "waiting":
                raise RuntimeError("登录已进入下一阶段，不能刷新二维码")
            settings = await get_platform_settings(db)
            previous_qr = session.qr_payload
            session.expires_at = datetime.now() + timedelta(minutes=settings["qr_expire_minutes"])
            session.qr_payload = None
            session.failure_reason = None
            await db.commit()
            print(f"[LoginWorker] 正在刷新页面并重新点击登录，会话 {session_id}", flush=True)
            await page.reload(wait_until="domcontentloaded", timeout=20000)
            clicked = False
            for _ in range(8):
                if await platform.click_login_button(page, log_missing=False):
                    clicked = True
                    break
                await asyncio.sleep(0.5)
            if not clicked:
                result["message"] = "刷新后未找到登录按钮，可查看浏览器画面后重试"
            else:
                for _ in range(6):
                    qr = await read_login_qr(page)
                    if qr and qr[0] != previous_qr:
                        session.qr_payload = qr[0]
                        await db.commit()
                        await publish(session_id, "qr", image=qr[0], expires_at=session.expires_at.isoformat())
                        result = {"found": True, "qr_payload": qr[0], "expires_at": session.expires_at.isoformat()}
                        print(f"[LoginWorker] 已重新获取登录二维码，会话 {session_id}", flush=True)
                        break
                    await asyncio.sleep(1)
        except Exception as exc:
            result["message"] = f"刷新二维码失败：{type(exc).__name__}: {exc}"[:300]
            print(f"[LoginWorker] 刷新二维码失败，会话 {session_id}: {type(exc).__name__}: {exc}", flush=True)
        async with redis_client.pipeline(transaction=True) as pipe:
            pipe.rpush(response_key, json.dumps(result, ensure_ascii=False))
            pipe.expire(response_key, 30)
            await pipe.execute()
    return processed


async def second_verification_container(page, context=None):
    """定时扫描全部标签页和 iframe，不依赖动态 class。"""
    pages = context.pages if context is not None else [page]
    for browser_page in pages:
        for frame in browser_page.frames:
            try:
                # #uc-second-verify 外层自身可能没有可见尺寸，但内部 article 已经显示。
                # 优先返回实际可见的“身份验证”面板，避免被外层尺寸判断漏掉。
                semantic_panels = frame.locator(
                    'article[class*="verification_component_layout-"]'
                )
                for index in range(await semantic_panels.count()):
                    panel = semantic_panels.nth(index)
                    if not await panel.is_visible():
                        continue
                    panel_text = " ".join((await panel.inner_text()).split())
                    has_identity_title = "身份验证" in panel_text
                    has_verification_content = any(marker in panel_text for marker in (
                        "手机刷脸验证",
                        "验证登录密码",
                        "接收短信验证码",
                        "发送短信验证",
                        "请输入验证码",
                        "请输入登录密码",
                    ))
                    if has_identity_title and has_verification_content:
                        return panel
                containers = frame.locator("#uc-second-verify")
                for index in range(await containers.count()):
                    container = containers.nth(index)
                    # 有些弹层根 div 自身没有尺寸，但内部文字或输入框可见。
                    sms_items = container.locator("div").filter(has_text=re.compile(r"接收\s*短信\s*验证码"))
                    method_items = container.locator(
                        '[class*="verification_component_list_item-"]'
                    )
                    inputs = container.locator(
                        '#button-input, input[placeholder="请输入验证码"], '
                        'input[placeholder*="登录密码"], input[type="password"]'
                    )
                    child_visible = any([
                        *[await sms_items.nth(i).is_visible() for i in range(await sms_items.count())],
                        *[await method_items.nth(i).is_visible() for i in range(await method_items.count())],
                        *[await inputs.nth(i).is_visible() for i in range(await inputs.count())],
                    ])
                    if child_visible or await container.is_visible():
                        return container
                # 页面结构外层变化时，先按文案定位，再向上找到认证容器。
                text_items = frame.locator("div").filter(has_text=re.compile(r"^\s*接收\s*短信\s*验证码\s*$"))
                for index in range(await text_items.count()):
                    item = text_items.nth(index)
                    if await item.is_visible():
                        ancestor = item.locator("xpath=ancestor::*[@id='uc-second-verify'][1]")
                        if await ancestor.count():
                            return ancestor.first
            except Exception:
                continue
    return None


async def second_verification_probe(page, context=None) -> tuple[int, int, int, int, int]:
    """返回标签页、frame、认证根节点和短信文案数量，便于定位页面改版。"""
    pages = context.pages if context is not None else [page]
    frame_count = root_count = text_count = password_count = 0
    for browser_page in pages:
        for frame in browser_page.frames:
            frame_count += 1
            try:
                root_count += await frame.locator("#uc-second-verify").count()
                text_count += await frame.get_by_text("接收短信验证码", exact=True).count()
                password_count += await frame.locator(
                    'input[type="password"], input[name="normal-input"], input[placeholder*="登录密码"]'
                ).count()
            except Exception:
                pass
    return len(pages), frame_count, root_count, text_count, password_count


async def click_sms_verification(container) -> bool:
    try:
        candidates = container.locator("div").filter(has_text=re.compile(r"^\s*接收\s*短信\s*验证码\s*$"))
        for index in range(await candidates.count()):
            candidate = candidates.nth(index)
            if await candidate.is_visible():
                try:
                    await candidate.click(timeout=3000)
                except Exception:
                    # 某些版本有透明遮罩，但目标 div 自身仍绑定点击事件。
                    await candidate.evaluate("element => element.click()")
                return True
    except Exception:
        pass
    return False


async def verification_methods(container) -> list[dict[str, str | None]]:
    """读取认证方式列表，兼容抖音新旧版动态 class。"""
    candidates = container.locator('[class*="verification_component_list_item-"]')
    if not await candidates.count():
        # 页面去掉语义 class 时，按“直属 SVG 图标 + 直属文本内容”的列表项结构兜底。
        await container.evaluate("""
            root => {
                let index = 0;
                for (const element of root.querySelectorAll('div')) {
                    const children = Array.from(element.children);
                    const hasDirectIcon = children.some(child => child.querySelector(':scope > svg'));
                    const hasDirectText = children.some(child => (child.innerText || '').trim().length > 0);
                    if (hasDirectIcon && hasDirectText) {
                        element.setAttribute('data-login-method-fallback', String(index++));
                    }
                }
            }
        """)
        candidates = container.locator('[data-login-method-fallback]')
    options: list[dict[str, str | None]] = []
    seen_labels: set[str] = set()
    for index in range(await candidates.count()):
        candidate = candidates.nth(index)
        try:
            if not await candidate.is_visible():
                continue
            lines = [line.strip() for line in (await candidate.inner_text()).splitlines() if line.strip()]
            if not lines or lines[0] in seen_labels:
                continue
            method_id = f"method-{len(options)}"
            await candidate.evaluate("(element, value) => element.setAttribute('data-login-method-id', value)", method_id)
            seen_labels.add(lines[0])
            options.append({
                "id": method_id,
                "label": lines[0],
                "description": " ".join(lines[1:]) or None,
            })
        except Exception:
            continue

    # 新版身份验证弹窗不再保留 verification_component_list_item 语义 class。
    # 这些文案是用户可见的产品文字，比每次发布都会变化的 class 稳定。
    known_labels = (
        "手机刷脸验证",
        "验证登录密码",
        "接收短信验证码",
        "发送短信验证",
        "手机验证码验证",
        "短信验证码验证",
    )
    for label in known_labels:
        if label in seen_labels:
            continue
        try:
            labels = container.get_by_text(label, exact=True)
            visible_label = None
            for index in range(await labels.count()):
                item = labels.nth(index)
                if await item.is_visible():
                    visible_label = item
                    break
            if visible_label is None:
                continue
            method_id = f"method-{len(options)}"
            await visible_label.evaluate(
                "(element, value) => element.setAttribute('data-login-method-id', value)",
                method_id,
            )
            seen_labels.add(label)
            options.append({"id": method_id, "label": label, "description": None})
        except Exception:
            continue
    return options


async def click_verification_method(container, method_id: str, label: str | None = None) -> bool:
    # 优先点击管理员实际选择的文字。抖音的 React 点击事件绑定在列表项上，
    # 从文字节点触发原生 click 会冒泡到列表项，同时避开透明遮罩和动态 class。
    if label:
        try:
            label_candidates = container.get_by_text(label, exact=True)
            for index in range(await label_candidates.count()):
                label_item = label_candidates.nth(index)
                if not await label_item.is_visible():
                    continue
                list_item = label_item.locator(
                    'xpath=ancestor::*[contains(@class, "verification_component_list_item-")][1]'
                )
                target = list_item.first if await list_item.count() else label_item
                await target.evaluate("element => element.click()")
                return True
        except Exception:
            pass

    candidate = container.locator(f'[data-login-method-id="{method_id}"]')
    if not await candidate.count():
        return False
    candidate = candidate.first
    try:
        await candidate.click(timeout=3000)
    except Exception:
        try:
            await candidate.evaluate("element => element.click()")
        except Exception:
            return False
    return True


async def verification_input(container):
    try:
        for selector in ('#button-input', 'input[placeholder="请输入验证码"]', 'input[type="tel"][maxlength="6"]'):
            candidates = container.locator(selector)
            for index in range(await candidates.count()):
                candidate = candidates.nth(index)
                if await candidate.is_visible():
                    return candidate
    except Exception:
        pass
    return None


async def login_password_input(container):
    try:
        for selector in ('input[placeholder="请输入登录密码"]', 'input[placeholder*="登录密码"]', 'input[name="normal-input"][type="password"]', 'input[type="password"][maxlength="50"]', 'input[type="password"]'):
            candidates = container.locator(selector)
            for index in range(await candidates.count()):
                candidate = candidates.nth(index)
                if await candidate.is_visible():
                    return candidate
    except Exception:
        pass
    return None


async def find_login_password_context(page, context=None):
    """跨标签页和 iframe 查找密码框，并返回适合点击验证按钮的作用域。"""
    pages = context.pages if context is not None else [page]
    for browser_page in pages:
        for frame in browser_page.frames:
            try:
                frame_scope = frame.locator("body")
                input_box = await login_password_input(frame_scope)
                if input_box is None:
                    continue
                ancestor = input_box.locator("xpath=ancestor::*[@id='uc-second-verify'][1]")
                if await ancestor.count():
                    return ancestor.first, input_box
                return frame_scope, input_box
            except Exception:
                continue
    return None, None


async def trigger_and_confirm_click(button) -> str | None:
    """点击目标节点并确认 click 事件确实到达；返回实际触发方式。"""
    marker = "data-codex-click-seen"
    try:
        await button.evaluate(
            """(element, marker) => {
                element.setAttribute(marker, '0');
                element.addEventListener('click', () => {
                    element.setAttribute(marker, '1');
                }, { capture: true, once: true });
            }""",
            marker,
        )
        try:
            # force 可跳过服务端虚拟屏幕上偶发的透明遮罩拦截检查。
            await button.click(timeout=3000, force=True)
        except Exception:
            pass
        try:
            if await button.get_attribute(marker) == "1":
                await button.evaluate("(element, marker) => element.removeAttribute(marker)", marker)
                return "mouse"
        except Exception:
            # 点击导致面板卸载或页面跳转，也表示提交动作已经触发。
            return "mouse"
        try:
            await button.evaluate("element => element.click()")
            if await button.get_attribute(marker) == "1":
                await button.evaluate("(element, marker) => element.removeAttribute(marker)", marker)
                return "dom"
        except Exception:
            # DOM click 后节点被卸载，同样视为已触发。
            return "dom"
    except Exception:
        return None
    return None


async def click_verification_button(container, input_box=None) -> bool:
    try:
        if input_box is not None:
            # 管理员提供的实测 XPath优先；第二个定位不依赖 body 下动态弹层序号，
            # 从当前密码框所属 article 精确找到页脚里的主按钮。
            exact_buttons = (
                input_box.locator(
                    "xpath=/html/body/div[40]/div/div/article/div[3]/div[1]/div[2]"
                ),
                input_box.locator(
                    "xpath=ancestor::article[1]//div[contains(@class, 'footer_container-')]"
                    "//div[contains(@class, 'primary-') and normalize-space(.)='验证']"
                ),
            )
            for candidates in exact_buttons:
                for index in range(await candidates.count()):
                    button = candidates.nth(index)
                    if not await button.is_visible():
                        continue
                    text = " ".join((await button.inner_text()).split())
                    class_name = await button.get_attribute("class") or ""
                    if text != "验证" or not (
                        "verification_component_btn-" in class_name or "primary-" in class_name
                    ):
                        continue
                    for _ in range(30):
                        class_name = await button.get_attribute("class") or ""
                        if "disabled-" not in class_name:
                            break
                        await asyncio.sleep(0.1)
                    try:
                        click_method = await trigger_and_confirm_click(button)
                        if click_method:
                            state = "disabled" if "disabled-" in class_name else "enabled"
                            method_text = "鼠标点击" if click_method == "mouse" else "DOM 点击"
                            print(
                                f"[LoginWorker] 已按精确 XPath触发验证点击事件: "
                                f"state={state}, method={method_text}",
                                flush=True,
                            )
                        else:
                            raise RuntimeError("目标节点没有收到 click 事件")
                        return True
                    except Exception as exc:
                        print(
                            f"[LoginWorker] 精确 XPath点击验证按钮失败: "
                            f"{type(exc).__name__}: {exc}",
                            flush=True,
                        )
        # 密码验证页可能还有其他“验证”文字。从已经填写的输入框开始，优先
        # 点击它后方最近的按钮，确保命中输入框底部的提交操作。
        if input_box is not None:
            following_labels = input_box.locator(
                "xpath=following::*[normalize-space(string(.))='验证']"
            )
            fallback_label = None
            for index in range(await following_labels.count()):
                label = following_labels.nth(index)
                if not await label.is_visible():
                    continue
                if fallback_label is None:
                    fallback_label = label
                clickable_ancestor = label.locator(
                    "xpath=ancestor-or-self::*[self::button or @role='button' or "
                    "contains(@class, 'btn')][1]"
                )
                if not await clickable_ancestor.count():
                    continue
                target = clickable_ancestor.first
                try:
                    await target.click(timeout=3000)
                except Exception:
                    await target.evaluate("element => element.click()")
                print("[LoginWorker] 已点击密码输入框底部的验证按钮", flush=True)
                return True
            if fallback_label is not None:
                await fallback_label.evaluate("element => element.click()")
                print("[LoginWorker] 已触发密码输入框底部的验证文字", flush=True)
                return True
        selectors = (
            '[class*="verification_component_btn-"]',
            'button',
            '[role="button"]',
            'div',
        )
        for selector in selectors:
            buttons = container.locator(selector).filter(has_text=re.compile(r"^\s*验证\s*$"))
            for index in range(await buttons.count()):
                button = buttons.nth(index)
                if not await button.is_visible():
                    continue
                # 按钮是 div，disabled 状态由动态 class/aria 表达，is_enabled() 无法判断。
                # 最多等待 3 秒让 React 处理输入事件并启用按钮。
                clickable = False
                for _ in range(30):
                    class_name = await button.get_attribute("class") or ""
                    aria_disabled = await button.get_attribute("aria-disabled")
                    if "disabled-" not in class_name and aria_disabled != "true":
                        clickable = True
                        break
                    await asyncio.sleep(0.1)
                if not clickable:
                    # 抖音偶尔不会及时移除动态 disabled class，但输入状态已经更新。
                    # 直接触发 DOM click，让页面自身决定是否可以提交，后续再读取
                    # 页面明确返回的验证结果。
                    try:
                        await button.evaluate("element => element.click()")
                        print("[LoginWorker] 验证按钮状态未刷新，已直接触发验证", flush=True)
                        return True
                    except Exception:
                        continue
                try:
                    await button.click(timeout=3000)
                except Exception:
                    await button.evaluate("element => element.click()")
                return True
        # 标签结构再次变化时，从“验证”文字向上寻找按钮或带 btn class 的容器。
        labels = container.get_by_text("验证", exact=True)
        for index in range(await labels.count()):
            label = labels.nth(index)
            if not await label.is_visible():
                continue
            clickable_ancestor = label.locator(
                "xpath=ancestor-or-self::*[self::button or @role='button' or "
                "contains(@class, 'btn')][1]"
            )
            target = clickable_ancestor.first if await clickable_ancestor.count() else label
            await target.evaluate("element => element.click()")
            print("[LoginWorker] 已通过验证文字触发验证按钮", flush=True)
            return True
    except Exception as exc:
        print(
            f"[LoginWorker] 定位或点击验证按钮异常: {type(exc).__name__}: {exc}",
            flush=True,
        )
    return False


async def fill_and_submit_verification(container, code: str) -> bool:
    try:
        input_box = await verification_input(container)
        if input_box is None:
            return False
        await input_box.fill(code)
        await asyncio.sleep(0.2)
        return await click_verification_button(container, input_box)
    except Exception:
        pass
    return False


async def fill_login_password(container, password: str, input_box=None) -> bool:
    try:
        if input_box is None:
            input_box = await login_password_input(container)
        if input_box is None:
            print("[LoginWorker] 未找到二次认证登录密码输入框", flush=True)
            return False
        # 直接聚焦输入框，不依赖鼠标坐标，避免虚拟屏幕上的透明遮罩拦截。
        await input_box.focus(timeout=3000)
        await input_box.fill("")
        # 优先模拟真实键盘输入，让抖音的 React 表单同步密码状态并解除按钮禁用。
        await input_box.press_sequentially(password, delay=35)
        await asyncio.sleep(0.2)
        if await input_box.input_value() != password:
            await input_box.fill(password)
            await asyncio.sleep(0.2)
        if await input_box.input_value() != password:
            # React 受控输入框可能把自动输入回滚为空；调用原生 value setter 后
            # 再派发 input/change，让 React 的值追踪器接收到真实变化。
            await input_box.evaluate(
                """(element, value) => {
                    const setter = Object.getOwnPropertyDescriptor(
                        HTMLInputElement.prototype, 'value'
                    )?.set;
                    if (setter) setter.call(element, value);
                    else element.value = value;
                    element.dispatchEvent(new InputEvent('input', {
                        bubbles: true,
                        inputType: 'insertText',
                        data: value,
                    }));
                    element.dispatchEvent(new Event('change', { bubbles: true }));
                }""",
                password,
            )
            await asyncio.sleep(0.3)
        # 即便输入框的 DOM value 已显示密码，React 的内部 value tracker 仍可能
        # 保留空值，使提交按钮一直处于 disabled。重置 tracker 后重新派发事件。
        await input_box.evaluate(
            """(element, value) => {
                const setter = Object.getOwnPropertyDescriptor(
                    HTMLInputElement.prototype, 'value'
                )?.set;
                if (setter) {
                    setter.call(element, '');
                    if (element._valueTracker) element._valueTracker.setValue('');
                    setter.call(element, value);
                } else {
                    element.value = value;
                }
                element.dispatchEvent(new InputEvent('input', {
                    bubbles: true,
                    inputType: 'insertText',
                    data: value,
                }));
                element.dispatchEvent(new Event('change', { bubbles: true }));
            }""",
            password,
        )
        await asyncio.sleep(0.5)
        if await input_box.input_value() != password:
            print("[LoginWorker] 登录密码写入后被页面清空", flush=True)
            return False
        print("[LoginWorker] 已确认登录密码写入二次认证输入框", flush=True)
        await input_box.press("Tab")
        # 失焦后让抖音完成表单状态更新；点击由后台的“验证密码”按钮单独触发。
        await asyncio.sleep(0.3)
        if await input_box.input_value() != password:
            print("[LoginWorker] 登录密码输入框失焦后被页面清空", flush=True)
            return False
        return True
    except Exception as exc:
        print(
            f"[LoginWorker] 填写登录密码异常: {type(exc).__name__}: {exc}",
            flush=True,
        )
        return False


async def password_verification_error(container) -> str | None:
    """读取抖音页面明确展示的密码验证失败原因。"""
    pattern = re.compile(
        r"密码(?:错误|不正确|有误|无效)|账号或密码|验证失败|"
        r"请重新输入(?:登录)?密码|操作失败|请求失败"
    )
    try:
        candidates = container.locator("div, p, span").filter(has_text=pattern)
        messages: list[str] = []
        for index in range(await candidates.count()):
            candidate = candidates.nth(index)
            if not await candidate.is_visible():
                continue
            text = " ".join((await candidate.inner_text()).split())
            if text and len(text) <= 200 and pattern.search(text):
                messages.append(text)
        if messages:
            # 父级 div 也会包含子节点的错误文案，取最短文本更接近页面实际提示。
            return min(messages, key=len)
    except Exception:
        pass
    return None


async def run_session(session_id: int, browser_pool: LoginBrowserPool):
    print(f"[LoginWorker] 开始处理登录会话: {session_id}", flush=True)
    async with SessionLocal() as db:
        session = await db.scalar(select(AccountLoginSession).where(AccountLoginSession.id == session_id, AccountLoginSession.deleted_at.is_(None)))
        if not session or session.status != "waiting":
            return
        account = await db.get(DouyinAccount, session.account_id)
        if not account:
            return
        platform = create_platform("douyin")
        p = None
        browser = None
        context = None
        page = None
        proxy_bridge = None
        resource_task = None
        proxy_config = None
        browser_claimed = False
        prepared = None

        async def close_or_recycle_browser() -> None:
            nonlocal proxy_bridge, resource_task
            if browser_claimed and prepared is not None and session.status != "success":
                if resource_task:
                    resource_task.cancel()
                    await asyncio.gather(resource_task, return_exceptions=True)
                    resource_task = None
                try:
                    if await recycle_claimed_browser(prepared, browser_pool):
                        # The pool now owns the browser and its authenticated SOCKS5 bridge.
                        proxy_bridge = None
                        print(f"[LoginWorker] 关闭扫码弹窗后已复用 Chromium，会话 {session_id}，页面 {LOGIN_FALLBACK_URL}", flush=True)
                        return
                except Exception as exc:
                    print(f"[LoginWorker] 恢复备用浏览器失败，会话 {session_id}: {type(exc).__name__}: {exc}", flush=True)
            await close_browser(session_id, browser, context, p)
        try:
            try:
                proxy_config = await browser_proxy_for_account(db, account)
            except RuntimeError as exc:
                session.status = "failed"
                session.failure_reason = str(exc)
                account.last_error = session.failure_reason
                db.add(AccountLog(account_id=account.id, event_type="login_failed", detail={"session_id": session.id, "reason": session.failure_reason}))
                await db.commit()
                await publish(session.id, "failed", reason=session.failure_reason)
                print(f"[LoginWorker] 会话 {session_id} 代理不可用: {exc}", flush=True)
                return
            prepared = await browser_pool.claim(proxy_config)
            if prepared:
                await remove_resource("warm", prepared.resource_id)
                p, browser, context, page, proxy_bridge = (
                    prepared.playwright, prepared.browser, prepared.context,
                    prepared.page, prepared.proxy_bridge,
                )
                browser_claimed = True
                print(f"[LoginWorker] 复用已加载抖音首页的备用浏览器，会话 {session_id}", flush=True)
            else:
                # 新代理或备用浏览器尚未准备好时，按账号绑定的代理启动。
                # Linux 无桌面服务器由 Xvfb 提供虚拟屏幕。
                connection = f"代理 {proxy_config['host']}:{proxy_config['port']}" if proxy_config else "直连"
                print(f"[LoginWorker] 无可领取的{connection}备用浏览器，会话 {session_id}，启动新 Chromium", flush=True)
                await browser_pool.retarget(proxy_config)
                if proxy_config:
                    proxy_bridge = Socks5Bridge(**proxy_config)
                    browser_proxy = await proxy_bridge.start()
                else:
                    browser_proxy = None
                p = await async_playwright().start()
                browser = await p.chromium.launch(
                    headless=os.getenv("PLAYWRIGHT_HEADLESS", "false").lower() == "true",
                    proxy=browser_proxy,
                )
                print(f"[LoginWorker] Chromium 已启动，会话 {session_id}", flush=True)
                context = await browser.new_context()
                page = await context.new_page()
            resource_task = asyncio.create_task(resource_heartbeat("login", session_id, page, account_id=account.id))
            try:
                if not browser_claimed:
                    try:
                        if await navigate_or_close(page, LOGIN_HOME_URL, session_id, browser, context, p, timeout=20000, on_close=close_or_recycle_browser):
                            return
                    except PlaywrightError as exc:
                        print(f"[LoginWorker] 抖音首页导航失败，尝试直播首页，会话 {session_id}: {type(exc).__name__}", flush=True)
                    if not await login_home_usable(page):
                        print(f"[LoginWorker] 抖音首页没有可用登录入口，改用直播首页，会话 {session_id}", flush=True)
                        if await navigate_or_close(page, LOGIN_FALLBACK_URL, session_id, browser, context, p, on_close=close_or_recycle_browser):
                            return
                elif not await login_home_usable(page):
                    print(f"[LoginWorker] 备用浏览器页面没有登录入口，尝试直播首页，会话 {session_id}", flush=True)
                    if await navigate_or_close(page, LOGIN_FALLBACK_URL, session_id, browser, context, p, on_close=close_or_recycle_browser):
                        return
                print(f"[LoginWorker] 抖音页面加载完毕，会话 {session_id}，开始查找登录按钮", flush=True)
                clicked = False
                for _ in range(60):
                    if await redis_client.lpop(f"douyin:login:close:{session_id}"):
                        await close_or_recycle_browser()
                        return
                    if await answer_login_click_requests(session_id, page, platform):
                        clicked = True
                        break
                    if await platform.click_login_button(page, log_missing=False):
                        clicked = True
                        break
                    await asyncio.sleep(0.25)
                if not clicked:
                    print(f"[LoginWorker] 未自动找到登录按钮，会话 {session_id} 保持打开供手动点击", flush=True)
                # 自动尝试十次，之后仍保留会话和浏览器，供管理员手动检测迟到的二维码。
                qr_result = None
                for qr_attempt in range(1, 11):
                    await answer_screenshot_requests("login", session_id, page)
                    if await redis_client.lpop(f"douyin:login:close:{session_id}"):
                        await close_or_recycle_browser()
                        return
                    await answer_login_click_requests(session_id, page, platform)
                    if await answer_login_qr_requests(session_id, page, session, db):
                        qr_result = (session.qr_payload, "image/png", 0)
                        break
                    qr_result = await read_login_qr(page)
                    if qr_result:
                        break
                    if qr_attempt < 10:
                        print(
                            f"[LoginWorker] 第 {qr_attempt}/10 次未读取到有效二维码，"
                            "3 秒后重新点击登录并读取",
                            flush=True,
                        )
                        close_requested = await redis_client.blpop(
                            f"douyin:login:close:{session_id}",
                            timeout=3,
                        )
                        if close_requested:
                            await close_or_recycle_browser()
                            return
                        clicked_again = await platform.click_login_button(
                            page,
                            log_missing=False,
                            force=True,
                        )
                        if not clicked_again:
                            print(
                                f"[LoginWorker] 第 {qr_attempt + 1}/10 次重试未找到登录按钮，继续读取二维码",
                                flush=True,
                            )
                if qr_result is None:
                    print(f"[LoginWorker] 连续 10 次未读取到二维码，会话 {session_id} 保持打开，等待手动检测", flush=True)
                    while datetime.now() < session.expires_at:
                        await answer_screenshot_requests("login", session_id, page)
                        if await redis_client.lpop(f"douyin:login:close:{session_id}"):
                            await close_or_recycle_browser()
                            return
                        if await browser_window_closed(browser, context):
                            session.status = "cancelled"
                            session.completed_at = datetime.now()
                            session.failure_reason = "浏览器窗口已关闭"
                            await db.commit()
                            await publish(session.id, "cancelled", reason=session.failure_reason)
                            await stop_closed_browser(session_id, browser, context, p)
                            return
                        await answer_login_click_requests(session_id, page, platform)
                        if await answer_login_qr_requests(session_id, page, session, db):
                            qr_result = (session.qr_payload, "image/png", 0)
                            break
                        await asyncio.sleep(0.5)
                if qr_result:
                    encoded, mime, chosen_area = qr_result
                    if session.qr_payload != encoded:
                        session.qr_payload = encoded
                        await db.commit()
                        await publish(session.id, "qr", image=encoded, expires_at=session.expires_at.isoformat())
                    print(f"[LoginWorker] 获取到登录二维码: mime={mime}, base64_length={len(encoded)}, area={chosen_area:.0f}", flush=True)
                    print(f"[LoginWorker] 登录二维码已保存，会话 {session_id}，等待扫码", flush=True)
                else:
                    session.status = "expired"
                    session.completed_at = datetime.now()
                    await db.commit()
                    await publish(session.id, "expired")
                    print(f"[LoginWorker] 登录会话已过期，会话 {session_id}", flush=True)
                    await wait_for_manual_close(session_id, browser, context, p, page, on_close=close_or_recycle_browser)
                    return
                print(f"[LoginWorker] 已启动二次认证定时检测，会话 {session_id}，间隔 0.5 秒", flush=True)
                deadline = session.expires_at.timestamp()
                verification_detected = False
                verification_announced = False
                verification_submitted_at: float | None = None
                password_announced = False
                password_submitted_at: float | None = None
                method_signature: tuple[tuple[str, str | None], ...] = ()
                selected_method: dict[str, str | None] | None = None
                method_clicked_at: float | None = None
                login_candidate_at: float | None = None
                last_probe_at = asyncio.get_running_loop().time()
                refresh_request_key = f"douyin:login:qr-refresh-request:{session_id}"
                while datetime.now().timestamp() < deadline or await redis_client.llen(refresh_request_key):
                    await answer_screenshot_requests("login", session_id, page)
                    await answer_login_click_requests(session_id, page, platform)
                    if await answer_login_qr_refresh_requests(session_id, page, platform, session, db):
                        deadline = session.expires_at.timestamp()
                        login_candidate_at = None
                        verification_detected = False
                        continue
                    await answer_login_qr_requests(session_id, page, session, db)
                    # 扫码等待期间也要响应后台关闭弹窗的操作。
                    close_requested = await redis_client.lpop(f"douyin:login:close:{session_id}")
                    if close_requested:
                        await close_or_recycle_browser()
                        return
                    if await browser_window_closed(browser, context):
                        session.status = "cancelled"
                        session.completed_at = datetime.now()
                        session.failure_reason = "浏览器窗口已关闭"
                        db.add(AccountLog(
                            account_id=account.id,
                            event_type="login_browser_closed",
                            detail={"session_id": session.id},
                        ))
                        await db.commit()
                        await publish(session.id, "cancelled", reason=session.failure_reason)
                        await stop_closed_browser(session_id, browser, context, p)
                        return
                    password_scope, global_password_box = await find_login_password_context(page, context)
                    second_verify = await second_verification_container(page, context)
                    if second_verify is None and password_scope is not None:
                        second_verify = password_scope
                    if second_verify is not None:
                        login_candidate_at = None
                        if not verification_detected:
                            verification_detected = True
                            print(f"[LoginWorker] 检测到可见二次认证面板，会话 {session_id}", flush=True)
                        input_box = await verification_input(second_verify)
                        second_verify_password_box = await login_password_input(second_verify)
                        if second_verify_password_box is not None:
                            password_box = second_verify_password_box
                            password_action_scope = second_verify
                        else:
                            password_box = global_password_box
                            password_action_scope = password_scope if password_scope is not None else second_verify
                        if input_box is None and password_box is None:
                            methods = await verification_methods(second_verify)
                            current_signature = tuple((str(item["label"]), item["description"]) for item in methods)
                            if selected_method is None and methods:
                                if current_signature != method_signature or session.status != "method_required":
                                    method_signature = current_signature
                                    session.status = "method_required"
                                    session.scanned_at = session.scanned_at or datetime.now()
                                    session.failure_reason = None
                                    await redis_client.set(
                                        f"douyin:login:verification-options:{session_id}",
                                        json.dumps(methods, ensure_ascii=False),
                                        ex=300,
                                    )
                                    db.add(AccountLog(
                                        account_id=account.id,
                                        event_type="second_verification_methods",
                                        detail={"session_id": session.id, "methods": [item["label"] for item in methods]},
                                    ))
                                    await db.commit()
                                    await publish(session.id, "method_required", options=methods)
                                    print(
                                        f"[LoginWorker] 等待后台选择二次验证方式，会话 {session_id}: "
                                        f"{', '.join(str(item['label']) for item in methods)}",
                                        flush=True,
                                    )
                                selected_id = await redis_client.lpop(f"douyin:login:verification-method:{session_id}")
                                selected = next((item for item in methods if item["id"] == selected_id), None)
                                if selected:
                                    if await click_verification_method(
                                        second_verify,
                                        str(selected["id"]),
                                        str(selected["label"]),
                                    ):
                                        selected_method = selected
                                        method_clicked_at = asyncio.get_running_loop().time()
                                        session.status = "method_processing"
                                        session.failure_reason = None
                                        await redis_client.set(
                                            f"douyin:login:selected-verification:{session_id}",
                                            json.dumps(selected, ensure_ascii=False),
                                            ex=300,
                                        )
                                        await db.commit()
                                        await publish(session.id, "method_processing", method=selected)
                                        print(
                                            f"[LoginWorker] 已点击二次验证方式，会话 {session_id}: {selected['label']}",
                                            flush=True,
                                        )
                                    else:
                                        session.status = "method_required"
                                        session.failure_reason = "验证方式页面已经变化，请重新选择"
                                        await db.commit()
                            elif (
                                selected_method is not None
                                and methods
                                and current_signature == method_signature
                                and method_clicked_at is not None
                                and asyncio.get_running_loop().time() - method_clicked_at >= 12
                            ):
                                selected_method = None
                                method_clicked_at = None
                                session.status = "method_required"
                                session.failure_reason = "未能打开该验证方式，请重新选择"
                                await db.commit()
                            await asyncio.sleep(0.5)
                            continue
                        if password_box is not None:
                            if not password_announced:
                                password_announced = True
                                session.status = "password_required"
                                session.scanned_at = session.scanned_at or datetime.now()
                                session.failure_reason = None
                                db.add(AccountLog(
                                    account_id=account.id,
                                    event_type="login_password_required",
                                    detail={"session_id": session.id},
                                ))
                                await db.commit()
                                await publish(session.id, "password_required")
                                print(f"[LoginWorker] 等待后台提交登录密码，会话 {session_id}", flush=True)
                            if (
                                session.status == "password_verifying"
                                and password_submitted_at is not None
                            ):
                                elapsed = asyncio.get_running_loop().time() - password_submitted_at
                                explicit_error = None
                                if elapsed >= 1:
                                    explicit_error = await password_verification_error(password_action_scope)
                                if explicit_error:
                                    session.status = "password_required"
                                    session.failure_reason = explicit_error
                                    password_submitted_at = None
                                    await db.commit()
                                    await publish(session.id, "password_required", reason=session.failure_reason)
                                    print(
                                        f"[LoginWorker] 抖音返回登录密码验证失败，会话 {session_id}: "
                                        f"{session.failure_reason}",
                                        flush=True,
                                    )
                                elif elapsed >= 20:
                                    session.status = "password_required"
                                    session.failure_reason = "登录密码验证超时，未收到抖音验证结果，请重新输入"
                                    password_submitted_at = None
                                    await db.commit()
                                    await publish(session.id, "password_required", reason=session.failure_reason)
                                    print(
                                        f"[LoginWorker] 登录密码验证超时，等待重新提交，会话 {session_id}",
                                        flush=True,
                                    )
                            if session.status in ("password_required", "password_ready"):
                                encrypted_password = await redis_client.lpop(f"douyin:login:password:{session_id}")
                                if encrypted_password:
                                    password = decrypt_transient_secret(encrypted_password)
                                    filled = await fill_login_password(
                                        password_action_scope,
                                        password,
                                        password_box,
                                    )
                                    password = ""
                                    if filled:
                                        session.status = "password_ready"
                                        session.failure_reason = None
                                        await db.commit()
                                        await publish(session.id, "password_ready")
                                        print(
                                            f"[LoginWorker] 登录密码已填入浏览器，等待后台点击验证密码，会话 {session_id}",
                                            flush=True,
                                        )
                                    else:
                                        session.status = "password_required"
                                        session.failure_reason = "未能填写登录密码，请查看浏览器画面后重试"
                                        await db.commit()
                            if session.status == "password_ready":
                                verify_requested = await redis_client.lpop(
                                    f"douyin:login:password-verify:{session_id}"
                                )
                                if verify_requested:
                                    clicked = await click_verification_button(
                                        password_action_scope,
                                        password_box,
                                    )
                                    if clicked:
                                        session.status = "password_verifying"
                                        session.failure_reason = None
                                        await db.commit()
                                        await publish(session.id, "password_verifying")
                                        password_submitted_at = asyncio.get_running_loop().time()
                                        print(f"[LoginWorker] 已点击登录密码验证按钮，会话 {session_id}", flush=True)
                                    else:
                                        session.failure_reason = "未找到可点击的验证按钮，请查看浏览器画面后重试"
                                        await db.commit()
                                        await publish(
                                            session.id,
                                            "password_ready",
                                            reason=session.failure_reason,
                                        )
                            await asyncio.sleep(0.5)
                            continue
                        if input_box is not None and not verification_announced:
                            verification_announced = True
                            session.status = "verify_required"
                            session.scanned_at = session.scanned_at or datetime.now()
                            session.failure_reason = None
                            db.add(AccountLog(
                                account_id=account.id,
                                event_type="second_verification_required",
                                detail={"session_id": session.id},
                            ))
                            await db.commit()
                            await publish(session.id, "verify_required")
                            print(f"[LoginWorker] 等待后台提交短信验证码，会话 {session_id}", flush=True)
                        if (
                            input_box is not None
                            and session.status == "verifying"
                            and verification_submitted_at is not None
                            and asyncio.get_running_loop().time() - verification_submitted_at >= 3
                        ):
                            session.status = "verify_required"
                            session.failure_reason = "验证码未通过或已失效，请重新输入"
                            await db.commit()
                            await publish(session.id, "verify_required", reason=session.failure_reason)
                            print(f"[LoginWorker] 验证码未通过，等待重新提交，会话 {session_id}", flush=True)
                        if input_box is not None and session.status == "verify_required":
                            code = await redis_client.lpop(f"douyin:login:verification:{session_id}")
                            if code and len(code) == 6 and code.isdigit():
                                submitted = await fill_and_submit_verification(second_verify, code)
                                if submitted:
                                    session.status = "verifying"
                                    session.failure_reason = None
                                    await db.commit()
                                    await publish(session.id, "verifying")
                                    verification_submitted_at = asyncio.get_running_loop().time()
                                    print(f"[LoginWorker] 已填写短信验证码并点击验证，会话 {session_id}", flush=True)
                                else:
                                    session.failure_reason = "未找到可点击的验证按钮，请重新提交"
                                    await db.commit()
                        await asyncio.sleep(0.5)
                        continue
                    loop_time = asyncio.get_running_loop().time()
                    if loop_time - last_probe_at >= 10:
                        pages_seen, frames_seen, roots_seen, texts_seen, passwords_seen = await second_verification_probe(page, context)
                        print(
                            f"[LoginWorker] 二次认证轮询中，会话 {session_id}: "
                            f"pages={pages_seen}, frames={frames_seen}, roots={roots_seen}, "
                            f"sms_texts={texts_seen}, password_inputs={passwords_seen}",
                            flush=True,
                        )
                        last_probe_at = loop_time
                    try:
                        logged_in = await platform.check_logged_in(page, context)
                    except Exception:
                        logged_in = False
                    if logged_in:
                        # 扫码后登录 Cookie 可能先于二次认证弹窗写入。连续等待一段时间，
                        # 确认没有出现 #uc-second-verify 后才能判定最终登录成功。
                        loop_time = asyncio.get_running_loop().time()
                        if login_candidate_at is None:
                            login_candidate_at = loop_time
                            print(f"[LoginWorker] 检测到候选登录状态，等待二次认证页面，会话 {session_id}", flush=True)
                        if loop_time - login_candidate_at < 10:
                            await asyncio.sleep(0.5)
                            continue
                        if await second_verification_container(page, context) is not None:
                            login_candidate_at = None
                            continue
                        print(
                            f"[LoginWorker] 检测到登录成功，会话 {session_id}，账号 {account.id}，正在保存登录状态",
                            flush=True,
                        )
                        state = await context.storage_state()
                        account.encrypted_storage_state = encrypt_storage_state(state)
                        # 登录状态已经保存，但扫码浏览器仍然打开；关闭后才允许分配任务。
                        account.status = "browser_open"
                        account.enabled = True
                        account.last_login_at = datetime.now()
                        session.status = "success"
                        session.completed_at = datetime.now()
                        account.last_error = None
                        account.risk_code = None
                        account.risk_message = None
                        db.add(AccountLog(account_id=account.id, event_type="login_success", detail={"session_id": session.id}))
                        await db.commit()
                        await publish(session.id, "success", account_id=account.id)
                        print(f"[LoginWorker] 扫码登录成功，会话 {session_id}", flush=True)
                        # 登录成功的浏览器属于该账号，不再占用备用池名额。
                        if browser_claimed and prepared is not None:
                            await browser_pool.release_claimed(prepared.resource_id)
                        await browser_pool.retarget(proxy_config)
                        await wait_for_manual_close(session_id, browser, context, p, page, on_close=close_or_recycle_browser)
                        account.status = "available" if account.enabled else "disabled"
                        await db.commit()
                        print(f"[LoginWorker] 登录浏览器已关闭，账号 {account.id} 可以分配任务", flush=True)
                        return
                    else:
                        login_candidate_at = None
                    await asyncio.sleep(0.5)
                session.status = "expired"
                session.completed_at = datetime.now()
                db.add(AccountLog(account_id=account.id, event_type="login_session_expired", detail={"session_id": session.id}))
                await db.commit()
                await publish(session.id, "expired")
                print(f"[LoginWorker] 登录会话已过期，会话 {session_id}", flush=True)
                await wait_for_manual_close(session_id, browser, context, p, page, on_close=close_or_recycle_browser)
            except Exception as exc:
                session.status = "failed"
                session.failure_reason = f"{type(exc).__name__}: {exc}"[:500]
                account.last_error = session.failure_reason
                db.add(AccountLog(account_id=account.id, event_type="login_failed", detail={"session_id": session.id, "reason": session.failure_reason}))
                await db.commit()
                await publish(session.id, "failed", reason=session.failure_reason)
                print(f"[LoginWorker] 登录会话失败，会话 {session_id}: {session.failure_reason}", flush=True)
                await wait_for_manual_close(session_id, browser, context, p, page, on_close=close_or_recycle_browser)
        except asyncio.CancelledError:
            await dispose_prepared_browser(PreparedBrowser(p, browser, context, page, proxy_config, proxy_bridge))
            proxy_bridge = None
            raise
        except Exception as exc:
            if browser:
                print(f"[LoginWorker] Worker 内部异常，会话 {session_id}，浏览器仍保持打开", flush=True)
                # 发生未预期异常时也保留浏览器，便于管理员检查页面并手动结束会话。
                await wait_for_manual_close(session_id, browser, context, p, page, on_close=close_or_recycle_browser)
            else:
                # Chromium 尚未启动时没有可保留的浏览器，释放 Playwright 驱动。
                if p:
                    await p.stop()
                session.status = "failed"
                session.failure_reason = f"{type(exc).__name__}: {exc}"[:500]
                account.last_error = session.failure_reason
                db.add(AccountLog(account_id=account.id, event_type="login_failed", detail={"session_id": session.id, "reason": session.failure_reason}))
                await db.commit()
                await publish(session.id, "failed", reason=session.failure_reason)
                print(f"[LoginWorker] 浏览器启动失败，会话 {session_id}: {session.failure_reason}", flush=True)
        finally:
            if resource_task:
                resource_task.cancel()
                await asyncio.gather(resource_task, return_exceptions=True)
                try:
                    await remove_resource("login", session_id)
                except Exception:
                    pass
            if proxy_bridge:
                await proxy_bridge.close()
            if browser_claimed:
                if prepared is not None:
                    await browser_pool.release_claimed(prepared.resource_id)
                await browser_pool.replenish(proxy_config)


async def reconcile_interrupted_sessions():
    """Worker 重启后关闭无法恢复浏览器的旧会话，同时保留仍在队列中的新任务。"""
    queued_values = await redis_client.lrange("douyin:login:sessions", 0, -1)
    queued_ids = {int(value) for value in queued_values}
    async with SessionLocal() as db:
        sessions = list(await db.scalars(select(AccountLoginSession).where(
            AccountLoginSession.status.in_(("waiting", "method_required", "method_processing", "password_required", "password_filling", "password_ready", "password_clicking", "password_verifying", "verify_required", "verifying")),
            AccountLoginSession.deleted_at.is_(None),
        )))
        changed = 0
        for session in sessions:
            if session.status == "waiting" and session.id in queued_ids and session.expires_at > datetime.now():
                continue
            session.status = "expired" if session.expires_at <= datetime.now() else "cancelled"
            session.completed_at = datetime.now()
            session.failure_reason = "登录 Worker 重启，原浏览器会话已释放"
            changed += 1
        if changed:
            await db.commit()
            print(f"[LoginWorker] 已清理 {changed} 个无法恢复的旧登录会话", flush=True)


async def main():
    print("[LoginWorker] 已启动，正在连接 Redis...", flush=True)
    await redis_client.ping()
    await reconcile_interrupted_sessions()
    browser_pool = LoginBrowserPool(prepare_login_browser, dispose_prepared_browser)
    try:
        initial_proxy = await initial_warm_proxy_config()
    except Exception as exc:
        print(f"[LoginWorker] 读取预热代理失败，将预热直连浏览器: {type(exc).__name__}: {exc}", flush=True)
        initial_proxy = None
    await browser_pool.initialize(initial_proxy)
    print("[LoginWorker] Redis 已连接，等待扫码登录任务...", flush=True)
    heartbeat_task = asyncio.create_task(heartbeat())
    targeted_pool_commands = pool_command_key(socket.gethostname(), os.getpid())
    running_sessions: dict[int, asyncio.Task] = {}
    registered_warm_ids: set[str] = set()
    navigation_tasks: set[asyncio.Task] = set()
    last_warm_retry = asyncio.get_running_loop().time()

    async def navigate_warm_browser(command: dict) -> None:
        response_key = command["response_key"]
        try:
            loaded_url = await browser_pool.navigate_slot(str(command["resource_id"]), command["url"])
            result = {"ok": True, "url": loaded_url}
            print(f"[LoginWorker] 备用浏览器已跳转: {loaded_url}", flush=True)
        except Exception as exc:
            result = {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:300]}
            print(f"[LoginWorker] 备用浏览器跳转失败: {result['error']}", flush=True)
        async with redis_client.pipeline(transaction=True) as pipe:
            pipe.rpush(response_key, json.dumps(result, ensure_ascii=False))
            pipe.expire(response_key, 30)
            await pipe.execute()

    def session_finished(session_id: int, task: asyncio.Task):
        running_sessions.pop(session_id, None)
        if task.cancelled():
            return
        error = task.exception()
        if error:
            print(f"[LoginWorker] 登录任务异常，会话 {session_id}: {type(error).__name__}: {error}", flush=True)

    try:
        while True:
            try:
                for resource_id in await browser_pool.prune_closed():
                    await remove_resource("warm", resource_id)
                ready = list(browser_pool.ready)
                current_warm_ids = {prepared.resource_id for prepared in ready}
                for resource_id in registered_warm_ids - current_warm_ids:
                    await remove_resource("warm", resource_id)
                registered_warm_ids = current_warm_ids
                for prepared in ready:
                    proxy = prepared.proxy_config
                    proxy_label = f"{proxy['host']}:{proxy['port']}" if proxy else "直连"
                    await touch_resource("warm", prepared.resource_id, opened_at=prepared.opened_at,
                                         url=prepared.page.url, proxy_label=proxy_label)
                    await answer_screenshot_requests("warm", prepared.resource_id, prepared.page)
                now = asyncio.get_running_loop().time()
                if now - last_warm_retry >= 15:
                    await browser_pool.replenish(browser_pool.target_proxy_config)
                    last_warm_retry = now
                item = await redis_client.blpop(
                    [targeted_pool_commands, "douyin:login:pool:commands", "douyin:login:sessions"], timeout=1
                )
                if item:
                    queue_name = item[0].decode() if isinstance(item[0], bytes) else item[0]
                    if queue_name in {targeted_pool_commands, "douyin:login:pool:commands"}:
                        command = json.loads(item[1])
                        if command.get("action") == "close":
                            resource_id = str(command.get("resource_id", ""))
                            if await browser_pool.close_slot(resource_id):
                                await remove_resource("warm", resource_id)
                                print(f"[LoginWorker] 已手动关闭备用浏览器 {resource_id}", flush=True)
                        elif command.get("action") == "open":
                            await browser_pool.open_slot(await initial_warm_proxy_config())
                            print("[LoginWorker] 已请求打开备用浏览器", flush=True)
                        elif command.get("action") == "navigate":
                            task = asyncio.create_task(navigate_warm_browser(command))
                            navigation_tasks.add(task)
                            task.add_done_callback(navigation_tasks.discard)
                        continue
                    session_id = int(item[1])
                    if session_id in running_sessions:
                        continue
                    task = asyncio.create_task(run_session(session_id, browser_pool))
                    running_sessions[session_id] = task
                    task.add_done_callback(lambda finished, sid=session_id: session_finished(sid, finished))
            except Exception as exc:
                # Redis 重启或网络短暂中断后，清理旧连接并自动重连。
                print(f"[LoginWorker] Redis 暂时不可用: {type(exc).__name__}: {exc}")
                await asyncio.sleep(2)
    finally:
        heartbeat_task.cancel()
        await asyncio.gather(heartbeat_task, return_exceptions=True)
        for task in running_sessions.values():
            task.cancel()
        for task in navigation_tasks:
            task.cancel()
        await asyncio.gather(*running_sessions.values(), return_exceptions=True)
        await asyncio.gather(*navigation_tasks, return_exceptions=True)
        warm_ids = [item.resource_id for item in browser_pool.ready]
        await browser_pool.close()
        for resource_id in warm_ids:
            await remove_resource("warm", resource_id)
        await redis_client.delete(WORKER_HEARTBEAT_KEY)


if __name__ == "__main__":
    asyncio.run(main())
