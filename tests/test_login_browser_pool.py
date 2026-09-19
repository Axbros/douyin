import asyncio
import unittest

from backend.app.core.login_browser_pool import LoginBrowserPool, PreparedBrowser


class FakeBrowser:
    def is_connected(self):
        return True


class FakePage:
    url = "https://www.douyin.com/"

    def is_closed(self):
        return False

    async def goto(self, url, **_kwargs):
        self.url = url


class LoginBrowserPoolTest(unittest.IsolatedAsyncioTestCase):
    async def test_failed_initial_preheat_can_be_retried(self):
        attempts = 0

        async def prepare(config):
            nonlocal attempts
            attempts += 1
            if attempts <= 2:
                raise RuntimeError("temporary navigation failure")
            return PreparedBrowser(attempts, FakeBrowser(), None, FakePage(), config)

        async def dispose(item):
            pass

        pool = LoginBrowserPool(prepare, dispose)
        await pool.initialize(None)
        self.assertEqual(len(pool.ready), 0)
        await pool.replenish(pool.target_proxy_config)
        await asyncio.gather(*list(pool.pending))
        self.assertEqual(len(pool.ready), 2)
        await pool.close()

    async def test_manual_close_and_open_change_idle_capacity(self):
        created = []
        disposed = []

        async def prepare(config):
            item = PreparedBrowser(len(created) + 1, FakeBrowser(), None, FakePage(), config)
            created.append(item)
            return item

        async def dispose(item):
            disposed.append(item.resource_id)

        pool = LoginBrowserPool(prepare, dispose)
        await pool.initialize(None)
        first_id = pool.ready[0].resource_id
        self.assertTrue(await pool.close_slot(first_id))
        self.assertFalse(await pool.close_slot(first_id))
        self.assertEqual(pool.desired_size, 1)
        await pool.replenish(None)
        self.assertEqual(len(pool.ready), 1)
        await pool.open_slot(None)
        await asyncio.gather(*list(pool.pending))
        self.assertEqual(len(pool.ready), 2)
        self.assertEqual(pool.desired_size, 2)
        self.assertIn(first_id, disposed)
        await pool.close()

    async def test_fifo_replenish_and_proxy_isolation(self):
        created = []
        disposed = []

        async def prepare(config):
            number = len(created) + 1
            created.append(number)
            # The proxy page loads first; initialization still keeps direct first.
            await asyncio.sleep(0.02 if number == 1 else 0)
            return PreparedBrowser(number, FakeBrowser(), None, FakePage(), config)

        async def dispose(item):
            disposed.append(item)

        proxy_a = {"host": "a", "port": 1, "username": "u", "password": "p"}
        proxy_b = {"host": "b", "port": 2, "username": "u", "password": "p"}
        pool = LoginBrowserPool(prepare, dispose)
        await pool.initialize(proxy_a)
        self.assertEqual(len(pool.ready), 2)
        self.assertEqual([item.proxy_config for item in pool.ready], [None, proxy_a])
        self.assertIsNone(await pool.claim(proxy_b))
        first = await pool.claim(proxy_a)
        self.assertIsNotNone(first)
        self.assertEqual(first.playwright, 2)
        self.assertEqual(len(pool.ready), 1)
        await pool.retarget(proxy_b)
        await asyncio.gather(*list(pool.pending))
        self.assertEqual(len(pool.ready), 2)
        self.assertEqual(len(disposed), 0)
        self.assertIsNone(pool.ready[0].proxy_config)
        self.assertEqual((await pool.claim(proxy_b)).proxy_config, proxy_b)
        await pool.close()
        self.assertEqual(len(disposed), 1)

    async def test_navigate_only_ready_browser(self):
        async def prepare(config):
            return PreparedBrowser(None, FakeBrowser(), None, FakePage(), config)

        async def dispose(item):
            pass

        pool = LoginBrowserPool(prepare, dispose)
        await pool.initialize(None)
        resource_id = pool.ready[0].resource_id
        self.assertEqual(await pool.navigate_slot(resource_id, "https://live.douyin.com/"), "https://live.douyin.com/")
        await pool.claim(None)
        with self.assertRaises(ValueError):
            await pool.navigate_slot(resource_id, "https://www.douyin.com/")
        await pool.close()

    async def test_second_initial_browser_precedes_replacement(self):
        next_number = 0

        async def prepare(config):
            nonlocal next_number
            next_number += 1
            return PreparedBrowser(next_number, FakeBrowser(), None, FakePage(), config)

        async def dispose(item):
            pass

        pool = LoginBrowserPool(prepare, dispose)
        await pool.initialize(None)
        self.assertEqual((await pool.claim(None)).playwright, 1)
        await pool.retarget(None)
        await asyncio.gather(*list(pool.pending))
        self.assertEqual((await pool.claim(None)).playwright, 2)
        await pool.close()


if __name__ == "__main__":
    unittest.main()
