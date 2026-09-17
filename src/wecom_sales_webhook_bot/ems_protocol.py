from __future__ import annotations

import socket
import struct


def frame(body: bytes) -> bytes:
    return struct.pack(">I", len(body)) + body


def recv_frame(sock: socket.socket, *, max_bytes: int = 16 * 1024 * 1024) -> bytes:
    header = recv_exact(sock, 4)
    length = struct.unpack(">I", header)[0]
    if length <= 0 or length > max_bytes:
        raise ValueError(f"invalid EMS frame length: {length}")
    return recv_exact(sock, length)


def recv_exact(sock: socket.socket, size: int) -> bytes:
    chunks: list[bytes] = []
    remaining = size
    while remaining:
        chunk = sock.recv(min(65536, remaining))
        if not chunk:
            raise ConnectionError("EMS connection closed before full frame arrived")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)
