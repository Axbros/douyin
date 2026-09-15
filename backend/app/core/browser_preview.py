"""通过 Redis 请求正在运行的 Playwright Worker 截取当前页面。"""

import base64
import json

from app.core.database import redis_client


def screenshot_request_key(browser_type: str, browser_id: int) -> str:
    return f"douyin:browser-preview:request:{browser_type}:{browser_id}"


def screenshot_response_key(request_id: str) -> str:
    return f"douyin:browser-preview:response:{request_id}"


async def answer_screenshot_requests(browser_type: str, browser_id: int, page) -> None:
    """处理当前浏览器的全部待处理截图请求。"""
    request_key = screenshot_request_key(browser_type, browser_id)
    while request_id := await redis_client.lpop(request_key):
        if isinstance(request_id, bytes):
            request_id = request_id.decode()
        response_key = screenshot_response_key(request_id)
        try:
            image = await page.screenshot(type="jpeg", quality=75, full_page=False)
            payload = {
                "ok": True,
                "image": base64.b64encode(image).decode(),
            }
        except Exception as exc:
            payload = {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:500]}
        async with redis_client.pipeline(transaction=True) as pipe:
            pipe.rpush(response_key, json.dumps(payload, ensure_ascii=False))
            pipe.expire(response_key, 30)
            await pipe.execute()
