"""Loopback SOCKS5 bridge for Chromium, which lacks upstream SOCKS5 auth."""
import asyncio


class Socks5Bridge:
    def __init__(self, host: str, port: int, username: str, password: str):
        self.host, self.port = host, port
        self.username, self.password = username, password
        self.server: asyncio.AbstractServer | None = None
        self.connections: set[asyncio.Task] = set()

    async def start(self) -> dict:
        self.server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        port = self.server.sockets[0].getsockname()[1]
        return {"server": f"socks5://127.0.0.1:{port}"}

    async def close(self):
        if self.server:
            self.server.close()
            await self.server.wait_closed()
        connections = list(self.connections)
        for task in connections:
            task.cancel()
        await asyncio.gather(*connections, return_exceptions=True)

    async def _handle(self, local_reader, local_writer):
        handler = asyncio.current_task()
        self.connections.add(handler)
        upstream_writer = None
        pipes = []
        try:
            version, count = await asyncio.wait_for(local_reader.readexactly(2), 15)
            methods = await local_reader.readexactly(count)
            if version != 5 or 0 not in methods:
                return
            local_writer.write(b"\x05\x00")
            await local_writer.drain()
            header = await asyncio.wait_for(local_reader.readexactly(4), 15)
            if header[0] != 5 or header[1] != 1:
                return
            address_type = header[3]
            if address_type == 1:
                address = await local_reader.readexactly(4)
            elif address_type == 4:
                address = await local_reader.readexactly(16)
            elif address_type == 3:
                length = await local_reader.readexactly(1)
                address = length + await local_reader.readexactly(length[0])
            else:
                return
            target_port = await local_reader.readexactly(2)
            upstream_reader, upstream_writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port), 15
            )
            upstream_writer.write(b"\x05\x01\x02")
            await upstream_writer.drain()
            if await upstream_reader.readexactly(2) != b"\x05\x02":
                raise ConnectionError("上游 SOCKS5 不接受用户名密码认证")
            username, password = self.username.encode(), self.password.encode()
            if len(username) > 255 or len(password) > 255:
                raise ValueError("SOCKS5 用户名或密码超过 255 字节")
            upstream_writer.write(b"\x01" + bytes([len(username)]) + username + bytes([len(password)]) + password)
            await upstream_writer.drain()
            if await upstream_reader.readexactly(2) != b"\x01\x00":
                raise ConnectionError("上游 SOCKS5 认证失败")
            upstream_writer.write(header + address + target_port)
            await upstream_writer.drain()
            response = await upstream_reader.readexactly(4)
            if response[0] != 5:
                raise ConnectionError("上游 SOCKS5 响应无效")
            if response[3] == 1:
                bound = await upstream_reader.readexactly(4)
            elif response[3] == 4:
                bound = await upstream_reader.readexactly(16)
            elif response[3] == 3:
                length = await upstream_reader.readexactly(1)
                bound = length + await upstream_reader.readexactly(length[0])
            else:
                raise ConnectionError("上游 SOCKS5 地址类型无效")
            bound_port = await upstream_reader.readexactly(2)
            local_writer.write(response + bound + bound_port)
            await local_writer.drain()
            if response[1] != 0:
                return

            async def pipe(reader, writer):
                try:
                    while data := await reader.read(65536):
                        writer.write(data)
                        await writer.drain()
                except (ConnectionError, OSError):
                    pass

            pipes = [asyncio.create_task(pipe(local_reader, upstream_writer)),
                     asyncio.create_task(pipe(upstream_reader, local_writer))]
            done, pending = await asyncio.wait(pipes, return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
            await asyncio.gather(*pipes, return_exceptions=True)
        except (asyncio.IncompleteReadError, ConnectionError, OSError, TimeoutError, ValueError):
            try:
                local_writer.write(b"\x05\x01\x00\x01" + b"\x00" * 6)
                await local_writer.drain()
            except (ConnectionError, OSError):
                pass
        finally:
            for task in pipes:
                task.cancel()
            await asyncio.gather(*pipes, return_exceptions=True)
            local_writer.close()
            if upstream_writer:
                upstream_writer.close()
            self.connections.discard(handler)
