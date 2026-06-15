#!/usr/bin/env python3
"""Restricted CONNECT proxy from the Docker bridge to Telegram over host IPv6."""

import asyncio
import os
import socket

LISTEN_HOST = os.environ.get("LISTEN_HOST", "172.19.0.1")
LISTEN_PORT = int(os.environ.get("LISTEN_PORT", "8888"))
ALLOWED_TARGET = "api.telegram.org:443"


async def copy_stream(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        while data := await reader.read(65536):
            writer.write(data)
            await writer.drain()
    except (ConnectionError, asyncio.CancelledError):
        pass
    finally:
        writer.close()


async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    upstream_writer = None
    try:
        request_line = (await reader.readline()).decode("ascii", errors="replace").strip()
        method, target, _ = request_line.split(" ", 2)
        while await reader.readline() not in (b"\r\n", b"\n", b""):
            pass

        if method != "CONNECT" or target.lower() != ALLOWED_TARGET:
            writer.write(b"HTTP/1.1 403 Forbidden\r\nConnection: close\r\n\r\n")
            await writer.drain()
            return

        upstream_reader, upstream_writer = await asyncio.open_connection(
            "api.telegram.org", 443, family=socket.AF_INET6
        )
        writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        await writer.drain()
        await asyncio.gather(
            copy_stream(reader, upstream_writer),
            copy_stream(upstream_reader, writer),
        )
    except (ValueError, OSError, asyncio.IncompleteReadError):
        if not writer.is_closing():
            writer.write(b"HTTP/1.1 502 Bad Gateway\r\nConnection: close\r\n\r\n")
            await writer.drain()
    finally:
        writer.close()
        if upstream_writer is not None:
            upstream_writer.close()


async def main() -> None:
    server = await asyncio.start_server(handle_client, LISTEN_HOST, LISTEN_PORT)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
