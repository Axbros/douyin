"""抖音扫码登录 Worker。

运行：PYTHONPATH=backend:项目根目录 python backend/workers/login_worker.py
二维码以 base64 PNG 写入登录会话，并通过 Redis pub/sub 通知管理端。
"""
import asyncio
import base64
import json
import os
import re
import sys
from datetime import datetime

# 兼容仓库内较早生成的 protobuf 文件；必须在导入 src.platforms 前设置。
os.environ.setdefault("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION", "python")

from playwright.async_api import async_playwright
from sqlalchemy import select

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.core.crypto import decrypt_transient_secret, encrypt_storage_state
from app.core.browser_preview import answer_screenshot_requests
from app.core.database import SessionLocal, redis_client
from app.models import AccountLoginSession, AccountLog, DouyinAccount
from src.platforms import create_platform

WORKER_HEARTBEAT_KEY = "douyin:login-worker:heartbeat"
WORKER_HEARTBEAT_TTL_SECONDS = 300


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


async def wait_for_manual_close(session_id: int, browser, context, playwright, page=None):
    """浏览器保持打开，直到管理员调用接口或直接关闭窗口。"""
    print(f"[LoginWorker] 浏览器保持打开，等待手动关闭，会话 {session_id}", flush=True)
    while True:
        if await browser_window_closed(browser, context):
            await stop_closed_browser(session_id, browser, context, playwright)
            return
        if page is not None:
            await answer_screenshot_requests("login", session_id, page)
        if await redis_client.blpop(f"douyin:login:close:{session_id}", timeout=1):
            await close_browser(session_id, browser, context, playwright)
            return


async def navigate_or_close(page, url: str, session_id: int, browser, context, playwright) -> bool:
    """导航期间同时监听关闭指令；返回 True 表示浏览器已被关闭。"""
    # 必须等页面触发 load 事件后才允许点击登录按钮，避免页面初始化过程中
    # 弹层或遮罩尚未稳定，导致点击落在旧节点上。
    navigation = asyncio.create_task(page.goto(url, wait_until="load", timeout=60000))
    closing = asyncio.create_task(redis_client.blpop(f"douyin:login:close:{session_id}", timeout=0))
    done, _ = await asyncio.wait({navigation, closing}, return_when=asyncio.FIRST_COMPLETED)
    if closing in done:
        navigation.cancel()
        await asyncio.gather(navigation, return_exceptions=True)
        try:
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


async def second_verification_container(page, context=None):
    """定时扫描全部标签页和 iframe，不依赖动态 class。"""
    pages = context.pages if context is not None else [page]
    for browser_page in pages:
        for frame in browser_page.frames:
            try:
                containers = frame.locator("#uc-second-verify")
                for index in range(await containers.count()):
                    container = containers.nth(index)
                    # 有些弹层根 div 自身没有尺寸，但内部文字或输入框可见。
                    sms_items = container.locator("div").filter(has_text=re.compile(r"接收\s*短信\s*验证码"))
                    inputs = container.locator(
                        '#button-input, input[placeholder="请输入验证码"], '
                        'input[placeholder*="登录密码"], input[type="password"]'
                    )
                    child_visible = any([
                        *[await sms_items.nth(i).is_visible() for i in range(await sms_items.count())],
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
    """读取认证方式列表；只使用 class 的语义前缀，不使用动态后缀。"""
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
                        if "disabled-" in class_name:
                            await button.evaluate("element => element.click()")
                            print(
                                "[LoginWorker] 验证按钮仍为 disabled，已按精确 XPath直接触发",
                                flush=True,
                            )
                        else:
                            await button.click(timeout=3000)
                            print("[LoginWorker] 已按精确 XPath点击验证按钮", flush=True)
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


async def fill_and_submit_password(container, password: str, input_box=None) -> bool:
    try:
        if input_box is None:
            input_box = await login_password_input(container)
        if input_box is None:
            print("[LoginWorker] 未找到二次认证登录密码输入框", flush=True)
            return False
        await input_box.click(timeout=3000)
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
            print("[LoginWorker] 登录密码写入后被页面清空，停止点击验证", flush=True)
            return False
        print("[LoginWorker] 已确认登录密码写入二次认证输入框", flush=True)
        await input_box.press("Tab")
        await asyncio.sleep(0.3)
        if await input_box.input_value() != password:
            print("[LoginWorker] 登录密码输入框失焦后被页面清空，停止点击验证", flush=True)
            return False
        return await click_verification_button(container, input_box)
    except Exception as exc:
        print(
            f"[LoginWorker] 填写登录密码或提交验证异常: {type(exc).__name__}: {exc}",
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
        page = None
        try:
            # 与原桌面程序一致：默认打开可见浏览器，让管理员直接扫码。
            # Linux 无桌面服务器由 Xvfb 提供虚拟屏幕，仍保持有界面模式以兼容页面行为。
            browser = await p.chromium.launch(headless=os.getenv("PLAYWRIGHT_HEADLESS", "false").lower() == "true")
            print(f"[LoginWorker] Chromium 已启动，会话 {session_id}", flush=True)
            context = await browser.new_context()
            page = await context.new_page()
            try:
                if await navigate_or_close(page, platform.home_url, session_id, browser, context, p):
                    return
                print(f"[LoginWorker] 抖音页面加载完毕，会话 {session_id}，开始查找登录按钮", flush=True)
                clicked = False
                for _ in range(60):
                    if await redis_client.lpop(f"douyin:login:close:{session_id}"):
                        await close_browser(session_id, browser, context, p)
                        return
                    if await platform.click_login_button(page, log_missing=False):
                        clicked = True
                        break
                    await asyncio.sleep(0.25)
                if not clicked:
                    raise RuntimeError("等待登录按钮出现超时")
                # 只接受语义明确的二维码 img，不能用任意 data:image 兜底，
                # 否则会误取头像、Logo 等页面图片。
                qr_selectors = [
                    # 当前抖音页面实测位置，优先使用管理员提供的完整 XPath。
                    "xpath=/html/body/div[36]/div/div/div/div/div/article/div/div[2]/div/div[1]/div/div/div[2]/div/div/div/div/div[2]/img",
                    # 页面结构变化后的语义兜底：优先弹窗内二维码，再查找所有二维码图片。
                    '[role="dialog"] img[aria-label="二维码"]',
                    'img[aria-label="二维码"]',
                ]
                image = None
                mime = ""
                encoded = ""
                chosen_area = 0
                for qr_attempt in range(1, 11):
                    await answer_screenshot_requests("login", session_id, page)
                    if await redis_client.lpop(f"douyin:login:close:{session_id}"):
                        await close_browser(session_id, browser, context, p)
                        return
                    for selector in qr_selectors:
                        candidates = page.locator(selector)
                        for index in range(await candidates.count()):
                            candidate = candidates.nth(index)
                            if not await candidate.is_visible():
                                continue
                            src = await candidate.get_attribute("src")
                            if not src or not src.startswith("data:image/") or "," not in src:
                                continue
                            header, candidate_encoded = src.split(",", 1)
                            candidate_mime = header.split(";", 1)[0][5:]
                            try:
                                decoded = base64.b64decode(candidate_encoded, validate=True)
                                area = await candidate.evaluate("el => el.getBoundingClientRect().width * el.getBoundingClientRect().height")
                            except Exception:
                                continue
                            if candidate_mime == "image/png" and decoded.startswith(b"\x89PNG") and len(decoded) > 500 and area > chosen_area:
                                image = decoded
                                mime = candidate_mime
                                encoded = candidate_encoded
                                chosen_area = area
                    if image is not None:
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
                            await close_browser(session_id, browser, context, p)
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
                if image is None:
                    raise RuntimeError("连续 10 次未读取到有效的抖音登录二维码 img.src")
                print(
                    f"[LoginWorker] 获取到登录二维码: mime={mime}, base64_length={len(encoded)}, area={chosen_area:.0f}",
                    flush=True,
                )
                print("[LoginWorker] 已读取二维码 img.src", flush=True)
                session.qr_payload = base64.b64encode(image).decode()
                await db.commit()
                print(f"[LoginWorker] 登录二维码已保存，会话 {session_id}，等待扫码", flush=True)
                await publish(session.id, "qr", image=session.qr_payload, expires_at=session.expires_at.isoformat())
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
                while datetime.now().timestamp() < deadline:
                    await answer_screenshot_requests("login", session_id, page)
                    # 扫码等待期间也要响应后台关闭弹窗的操作。
                    close_requested = await redis_client.lpop(f"douyin:login:close:{session_id}")
                    if close_requested:
                        await close_browser(session_id, browser, context, p)
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
                            print(f"[LoginWorker] 检测到二次认证区域 #uc-second-verify，会话 {session_id}", flush=True)
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
                            if session.status == "password_required":
                                encrypted_password = await redis_client.lpop(f"douyin:login:password:{session_id}")
                                if encrypted_password:
                                    password = decrypt_transient_secret(encrypted_password)
                                    submitted = await fill_and_submit_password(
                                        password_action_scope,
                                        password,
                                        password_box,
                                    )
                                    password = ""
                                    if submitted:
                                        session.status = "password_verifying"
                                        session.failure_reason = None
                                        await db.commit()
                                        await publish(session.id, "password_verifying")
                                        password_submitted_at = asyncio.get_running_loop().time()
                                        print(f"[LoginWorker] 已填写登录密码并点击验证，会话 {session_id}", flush=True)
                                    else:
                                        session.status = "password_required"
                                        session.failure_reason = "未能填写登录密码或点击验证按钮，请查看浏览器画面后重试"
                                        await db.commit()
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
                        await wait_for_manual_close(session_id, browser, context, p, page)
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
                await wait_for_manual_close(session_id, browser, context, p, page)
            except Exception as exc:
                session.status = "failed"
                session.failure_reason = f"{type(exc).__name__}: {exc}"[:500]
                account.last_error = session.failure_reason
                db.add(AccountLog(account_id=account.id, event_type="login_failed", detail={"session_id": session.id, "reason": session.failure_reason}))
                await db.commit()
                await publish(session.id, "failed", reason=session.failure_reason)
                print(f"[LoginWorker] 登录会话失败，会话 {session_id}: {session.failure_reason}", flush=True)
                await wait_for_manual_close(session_id, browser, context, p, page)
        except Exception:
            if browser:
                print(f"[LoginWorker] Worker 内部异常，会话 {session_id}，浏览器仍保持打开", flush=True)
                # 发生未预期异常时也保留浏览器，便于管理员检查页面并手动结束会话。
                await wait_for_manual_close(session_id, browser, context, p, page)
            else:
                # Chromium 尚未启动时没有可保留的浏览器，释放 Playwright 驱动。
                await p.stop()
                raise


async def reconcile_interrupted_sessions():
    """Worker 重启后关闭无法恢复浏览器的旧会话，同时保留仍在队列中的新任务。"""
    queued_values = await redis_client.lrange("douyin:login:sessions", 0, -1)
    queued_ids = {int(value) for value in queued_values}
    async with SessionLocal() as db:
        sessions = list(await db.scalars(select(AccountLoginSession).where(
            AccountLoginSession.status.in_(("waiting", "method_required", "method_processing", "password_required", "password_verifying", "verify_required", "verifying")),
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
    print("[LoginWorker] Redis 已连接，等待扫码登录任务...", flush=True)
    heartbeat_task = asyncio.create_task(heartbeat())
    running_sessions: dict[int, asyncio.Task] = {}

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
                item = await redis_client.blpop("douyin:login:sessions", timeout=5)
                if item:
                    session_id = int(item[1])
                    if session_id in running_sessions:
                        continue
                    task = asyncio.create_task(run_session(session_id))
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
        await asyncio.gather(*running_sessions.values(), return_exceptions=True)
        await redis_client.delete(WORKER_HEARTBEAT_KEY)


if __name__ == "__main__":
    asyncio.run(main())
