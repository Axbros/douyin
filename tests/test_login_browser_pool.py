import asyncio
import unittest

from backend.app.core.login_browser_pool import LoginBrowserPool, PreparedBrowser


class FakeBrowser:
    def is_connected(self):
        return True


class FakePage:
    def is_closed(self):
        return False


class LoginBrowserPoolTest(unittest.IsolatedAsyncioTestCase):
    async def test_fifo_replenish_and_proxy_isolation(self):
        created = []
        disposed = []

        async def prepare(config):
            number = len(created) + 1
            created.append(number)
            # The second page loads first; claim must still use launch order.
            await asyncio.sleep(0.02 if number == 1 else 0)
            return PreparedBrowser(number, FakeBrowser(), None, FakePage(), config)

        async def dispose(item):
            disposed.append(item)

        proxy_a = {"host": "a", "port": 1, "username": "u", "password": "p"}
        proxy_b = {"host": "b", "port": 2, "username": "u", "password": "p"}
        pool = LoginBrowserPool(prepare, dispose)
        await pool.initialize(proxy_a)
        self.assertEqual(len(pool.ready), 2)
        self.assertIsNone(await pool.claim(proxy_b))
        first = await pool.claim(proxy_a)
        self.assertIsNotNone(first)
        self.assertEqual(first.playwright, 1)
        self.assertEqual(len(pool.ready), 1)
        await pool.retarget(proxy_b)
        await asyncio.gather(*list(pool.pending))
        self.assertEqual(len(pool.ready), 2)
        self.assertEqual(len(disposed), 1)
        self.assertEqual((await pool.claim(proxy_b)).proxy_config, proxy_b)
        await pool.close()
        self.assertEqual(len(disposed), 2)

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
