import base64
import unittest

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
    async def test_manual_scan_ignores_other_images_and_accepts_late_qr(self):
        page = FakePage([])
        self.assertIsNone(await read_login_qr(page))
        page.images = [FakeImage("data:image/jpeg;base64," + base64.b64encode(b"x" * 510).decode(), 30000)]
        self.assertIsNone(await read_login_qr(page))
        encoded = base64.b64encode(b"\x89PNG" + b"q" * 510).decode()
        page.images = [FakeImage("data:image/png;base64," + encoded, 30000)]
        self.assertEqual((await read_login_qr(page))[0], encoded)
