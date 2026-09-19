"""SOCKS5 authentication bridge must never fall back to direct traffic."""
import asyncio
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.core.proxy_tunnel import Socks5Bridge


class Socks5BridgeTest(unittest.IsolatedAsyncioTestCase):
    async def test_authenticated_connect_and_relay(self):
        async def upstream(reader, writer):
            try:
                self.assertEqual(await reader.readexactly(3), b"\x05\x01\x02")
                writer.write(b"\x05\x02")
                await writer.drain()
                self.assertEqual(await reader.readexactly(1), b"\x01")
                username_size = (await reader.readexactly(1))[0]
                self.assertEqual(await reader.readexactly(username_size), b"user")
                password_size = (await reader.readexactly(1))[0]
                self.assertEqual(await reader.readexactly(password_size), b"secret")
                writer.write(b"\x01\x00")
                await writer.drain()
                self.assertEqual(await reader.readexactly(4), b"\x05\x01\x00\x03")
                name_size = (await reader.readexactly(1))[0]
                self.assertEqual(await reader.readexactly(name_size), b"example.org")
                self.assertEqual(await reader.readexactly(2), b"\x00P")
                writer.write(b"\x05\x00\x00\x01" + b"\x00" * 6)
                await writer.drain()
                self.assertEqual(await reader.readexactly(4), b"PING")
                writer.write(b"PONG")
                await writer.drain()
            finally:
                writer.close()

        server = await asyncio.start_server(upstream, "127.0.0.1", 0)
        bridge = Socks5Bridge("127.0.0.1", server.sockets[0].getsockname()[1], "user", "secret")
        try:
            config = await bridge.start()
            reader, writer = await asyncio.open_connection("127.0.0.1", int(config["server"].split(":")[-1]))
            writer.write(b"\x05\x01\x00")
            await writer.drain()
            self.assertEqual(await reader.readexactly(2), b"\x05\x00")
            writer.write(b"\x05\x01\x00\x03\x0bexample.org\x00P")
            await writer.drain()
            self.assertEqual(await reader.readexactly(10), b"\x05\x00\x00\x01" + b"\x00" * 6)
            writer.write(b"PING")
            await writer.drain()
            self.assertEqual(await reader.readexactly(4), b"PONG")
            writer.close()
            await writer.wait_closed()
        finally:
            await bridge.close()
            server.close()
            await server.wait_closed()


if __name__ == "__main__":
    unittest.main()
