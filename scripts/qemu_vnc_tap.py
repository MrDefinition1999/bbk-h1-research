#!/usr/bin/env python3
"""Send one deterministic absolute-pointer tap to a local QEMU VNC server."""

from __future__ import annotations

import argparse
import socket
import struct
import time


def recv_exact(sock: socket.socket, size: int) -> bytes:
    data = bytearray()
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            raise ConnectionError("VNC server closed the connection")
        data.extend(chunk)
    return bytes(data)


def connect(host: str, port: int, timeout: float) -> tuple[socket.socket, int, int]:
    sock = socket.create_connection((host, port), timeout=timeout)
    sock.settimeout(timeout)
    version = recv_exact(sock, 12)
    if not version.startswith(b"RFB 003."):
        raise RuntimeError(f"unexpected VNC banner: {version!r}")
    sock.sendall(b"RFB 003.008\n")

    security_count = recv_exact(sock, 1)[0]
    if security_count == 0:
        reason_size = struct.unpack(">I", recv_exact(sock, 4))[0]
        reason = recv_exact(sock, reason_size).decode("utf-8", "replace")
        raise RuntimeError(f"VNC security negotiation failed: {reason}")
    security_types = recv_exact(sock, security_count)
    if 1 not in security_types:
        raise RuntimeError(
            "local VNC server does not offer the expected no-auth security type"
        )
    sock.sendall(b"\x01")
    result = struct.unpack(">I", recv_exact(sock, 4))[0]
    if result != 0:
        raise RuntimeError(f"VNC security result was {result}")

    # Shared=1 keeps the browser's noVNC session connected during diagnostics.
    sock.sendall(b"\x01")
    width, height = struct.unpack(">HH", recv_exact(sock, 4))
    recv_exact(sock, 16)
    name_size = struct.unpack(">I", recv_exact(sock, 4))[0]
    recv_exact(sock, name_size)
    # Advertise QEMU's PointerTypeChange pseudo-encoding.  QEMU then queries
    # the active absolute Ingenic touchscreen and routes X/Y as absolute axes;
    # a minimal client that omits SetEncodings is treated as a relative mouse.
    sock.sendall(struct.pack(">BBHii", 2, 0, 2, 0, -257))
    return sock, width, height


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("x", type=int)
    parser.add_argument("y", type=int)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5900)
    parser.add_argument("--hold-ms", type=int, default=300)
    parser.add_argument("--timeout", type=float, default=3.0)
    args = parser.parse_args()

    sock, width, height = connect(args.host, args.port, args.timeout)
    try:
        if not 0 <= args.x < width or not 0 <= args.y < height:
            raise ValueError(
                f"tap ({args.x},{args.y}) is outside VNC framebuffer {width}x{height}"
            )
        hold_seconds = max(0.08, min(args.hold_ms / 1000.0, 2.0))
        sock.sendall(struct.pack(">BBHH", 5, 1, args.x, args.y))
        time.sleep(hold_seconds)
        sock.sendall(struct.pack(">BBHH", 5, 0, args.x, args.y))
        print(
            f"tap=({args.x},{args.y}) framebuffer={width}x{height} "
            f"hold_ms={round(hold_seconds * 1000)}"
        )
    finally:
        sock.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
