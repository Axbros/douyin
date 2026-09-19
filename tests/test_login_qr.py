import base64
import json
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from backend.workers import login_worker
from backend.workers.login_worker import read_login_qr


class FakeImage:
    def __init__(self, src, area, visible=True):
        self.src = src
        self.area = area
        self.visible = visible

    async def is_visible(self):
        return self.visible

    async def get_attribute(self, name):
        return self.src if name == "src" else None

    async def evaluate(self, _script):
        return self.area


class FakeLocator:
    def __init__(self, images):
        self.images = images

    async def count(self):
        return len(self.images)

    def nth(self, index):
        return self.images[index]


class FakePage:
    def __init__(self, images):
        self.images = images

    def locator(self, selector):
        return FakeLocator(self.images if selector == 'img[aria-label="二维码"]' else [])


class LoginQrTest(unittest.IsolatedAsyncioTestCase):
    async def test_manual_login_click_uses_current_page(self):
        responses = []

        class FakePipeline:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args):
                return False

            def rpush(self, _key, value):
                responses.append(json.loads(value))

            def expire(self, _key, _seconds):
                pass

            async def execute(self):
                pass

        redis = SimpleNamespace(lpop=AsyncMock(side_effect=[b"request-1", None]), pipeline=lambda transaction=True: FakePipeline())
        platform = SimpleNamespace(click_login_button=AsyncMock(return_value=True))
        page = object()
        with patch.object(login_worker, "redis_client", redis):
            self.assertTrue(await login_worker.answer_login_click_requests(7, page, platform))
        platform.click_login_button.assert_awaited_once_with(page, log_missing=False, force=True)
        self.assertEqual(responses, [{"clicked": True, "message": "已点击浏览器登录按钮"}])

    async def test_refresh_reloads_same_page_and_replaces_qr(self):
        class FakePipeline:
            def __init__(self):
                self.response = None

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args):
                return False

            def rpush(self, _key, value):
                self.response = json.loads(value)

            def expire(self, _key, _seconds):
                pass

            async def execute(self):
                pass

        class FakeRedis:
            def __init__(self):
                self.items = [b"request-1"]
                self.pipe = FakePipeline()

            async def lpop(self, _key):
                return self.items.pop(0) if self.items else None

            def pipeline(self, transaction=True):
                return self.pipe

        page = SimpleNamespace(reload=AsyncMock())
        platform = SimpleNamespace(click_login_button=AsyncMock(return_value=True))
        session = SimpleNamespace(status="waiting", expires_at=datetime.now() + timedelta(seconds=10), qr_payload="old", failure_reason=None)
        db = SimpleNamespace(commit=AsyncMock())
        redis = FakeRedis()
        with patch.object(login_worker, "redis_client", redis), \
             patch.object(login_worker, "get_platform_settings", new=AsyncMock(return_value={"qr_expire_minutes": 5})), \
             patch.object(login_worker, "read_login_qr", new=AsyncMock(return_value=("new", "image/png", 30000))), \
             patch.object(login_worker, "publish", new=AsyncMock()):
            self.assertTrue(await login_worker.answer_login_qr_refresh_requests(7, page, platform, session, db))
        page.reload.assert_awaited_once()
        platform.click_login_button.assert_awaited_once()
        self.assertEqual(session.qr_payload, "new")
        self.assertGreater((session.expires_at - datetime.now()).total_seconds(), 250)
        self.assertTrue(redis.pipe.response["found"])

    async def test_manual_scan_ignores_other_images_and_accepts_late_qr(self):
        page = FakePage([])
        self.assertIsNone(await read_login_qr(page))
        page.images = [FakeImage("data:image/jpeg;base64," + base64.b64encode(b"x" * 510).decode(), 30000)]
        self.assertIsNone(await read_login_qr(page))
        encoded = base64.b64encode(b"\x89PNG" + b"q" * 510).decode()
        page.images = [FakeImage("data:image/png;base64," + encoded, 30000)]
        self.assertEqual((await read_login_qr(page))[0], encoded)
