"""Bounded SOCKS5 connectivity and sample download-speed measurement."""
import asyncio
import ssl
import time
from datetime import datetime

from app.core.proxy_tunnel import Socks5Bridge

CONNECT_HOST = "live.douyin.com"
SPEED_HOST = "speed.cloudflare.com"
SPEED_PATH = "/__down?bytes=1048576"
SPEED_SAMPLE_BYTES = 1048576
CONNECT_TIMEOUT_SECONDS = 18
SPEED_TIMEOUT_SECONDS = 20


async def _http_get(bridge: Socks5Bridge, host: str, path: str, max_body: int) -> tuple[float, int, float]:
    """Return time to HTTPS response, bytes read, and total request duration."""
    address = bridge.server.sockets[0].getsockname()
    started = time.perf_counter()
    reader, writer = await asyncio.open_connection("127.0.0.1", address[1])
    try:
        writer.write(b"\x05\x01\x00")
        await writer.drain()
        if await reader.readexactly(2) != b"\x05\x00":
            raise ConnectionError("本地 SOCKS5 转接未就绪")
        name = host.encode("ascii")
        writer.write(b"\x05\x01\x00\x03" + bytes([len(name)]) + name + (443).to_bytes(2, "big"))
        await writer.drain()
        reply = await reader.readexactly(4)
        if reply[0] != 5 or reply[1] != 0:
            raise ConnectionError(f"代理拒绝连接 {host}（SOCKS5 错误码 {reply[1]}）")
        if reply[3] == 1:
            address_length = 4
        elif reply[3] == 4:
            address_length = 16
        elif reply[3] == 3:
            address_length = (await reader.readexactly(1))[0]
        else:
            raise ConnectionError("代理返回了无效地址类型")
        await reader.readexactly(address_length + 2)
        await writer.start_tls(ssl.create_default_context(), server_hostname=host, ssl_handshake_timeout=10)
        writer.write((
            f"GET {path} HTTP/1.1\r\nHost: {host}\r\n"
            "Accept-Encoding: identity\r\nCache-Control: no-cache\r\n"
            "Connection: close\r\n\r\n"
        ).encode("ascii"))
        await writer.drain()
        header = await reader.readuntil(b"\r\n\r\n")
        latency_ms = (time.perf_counter() - started) * 1000
        status_line = header.split(b"\r\n", 1)[0].decode("ascii", "replace")
        fields = status_line.split()
        if len(fields) < 2 or fields[1] != "200":
            raise ConnectionError(f"{host} 返回 {status_line[:90]}")
        body_bytes = 0
        while body_bytes < max_body:
            chunk = await reader.read(min(65536, max_body - body_bytes))
            if not chunk:
                break
            body_bytes += len(chunk)
        return round(latency_ms, 1), body_bytes, time.perf_counter() - started
    finally:
        writer.close()
        try:
            await asyncio.wait_for(writer.wait_closed(), timeout=2)
        except (ConnectionError, OSError, ssl.SSLError, asyncio.TimeoutError):
            pass


async def measure_proxy(config: dict) -> dict:
    """The speed sample is 1 MiB; never download an unbounded response."""
    result = {
        "reachable": False,
        "latency_ms": None,
        "download_mbps": None,
        "downloaded_bytes": 0,
        "error": None,
        "speed_error": None,
        "checked_at": datetime.now().isoformat(),
    }
    bridge = Socks5Bridge(**config)
    try:
        await bridge.start()
        try:
            latency, _, _ = await asyncio.wait_for(
                _http_get(bridge, CONNECT_HOST, "/", 1), timeout=CONNECT_TIMEOUT_SECONDS
            )
            result["reachable"] = True
            result["latency_ms"] = latency
        except (Exception, asyncio.TimeoutError) as exc:
            result["error"] = f"{type(exc).__name__}: {exc}"[:240]
            return result
        try:
            _, body_bytes, elapsed = await asyncio.wait_for(
                _http_get(bridge, SPEED_HOST, SPEED_PATH, SPEED_SAMPLE_BYTES),
                timeout=SPEED_TIMEOUT_SECONDS,
            )
            if body_bytes < SPEED_SAMPLE_BYTES // 2:
                raise ConnectionError(f"测速数据不足（仅收到 {body_bytes} 字节）")
            result["downloaded_bytes"] = body_bytes
            result["download_mbps"] = round(body_bytes * 8 / max(elapsed, 0.001) / 1_000_000, 2)
        except (Exception, asyncio.TimeoutError) as exc:
            result["speed_error"] = f"{type(exc).__name__}: {exc}"[:240]
        return result
    finally:
        await bridge.close()
