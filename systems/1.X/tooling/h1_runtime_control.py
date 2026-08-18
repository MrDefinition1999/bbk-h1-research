#!/usr/bin/env python3
"""Drive and capture a running BBK H1 emulator through its local HTTP API."""

from __future__ import annotations

import argparse
import json
import struct
import time
import urllib.request
import zlib
from pathlib import Path


FRAME_HEADER = struct.Struct("<4sIIIII")


def request(base_url: str, path: str, payload: dict[str, object] | None = None) -> bytes:
    data = None
    headers: dict[str, str] = {}
    if payload is not None:
        data = json.dumps(payload, separators=(",", ":")).encode("ascii")
        headers["Content-Type"] = "application/json"
    operation = urllib.request.Request(base_url + path, data=data, headers=headers)
    with urllib.request.urlopen(operation, timeout=10) as response:
        return response.read()


def touch(base_url: str, x: int, y: int, down: bool) -> None:
    request(base_url, "/api/touch", {"x": x, "y": y, "down": down})


def tap(base_url: str, x: int, y: int, hold_ms: int = 220) -> None:
    touch(base_url, x, y, True)
    time.sleep(hold_ms / 1000)
    touch(base_url, x, y, False)


def swipe(
    base_url: str,
    start_x: int,
    start_y: int,
    end_x: int,
    end_y: int,
    duration_ms: int = 500,
    steps: int = 12,
) -> None:
    steps = max(2, steps)
    touch(base_url, start_x, start_y, True)
    delay = duration_ms / 1000 / steps
    for index in range(1, steps):
        x = round(start_x + (end_x - start_x) * index / steps)
        y = round(start_y + (end_y - start_y) * index / steps)
        time.sleep(delay)
        touch(base_url, x, y, True)
    time.sleep(delay)
    touch(base_url, end_x, end_y, False)


def key(base_url: str, code: int, hold_ms: int = 120) -> None:
    request(base_url, "/api/key", {"code": code, "down": True})
    time.sleep(hold_ms / 1000)
    request(base_url, "/api/key", {"code": code, "down": False})


def status(base_url: str) -> dict[str, object]:
    return json.loads(request(base_url, "/api/status"))


def wait_for_calibration(base_url: str, timeout_seconds: float = 120) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        current = status(base_url)
        if current.get("calibration_status") in {"complete", "not-required"}:
            return
        if not current.get("running"):
            raise SystemExit("emulator stopped while waiting for automatic calibration")
        time.sleep(0.25)
    raise SystemExit("automatic calibration did not complete before timeout")


def boot_to_kov_page(base_url: str, launch: bool = False) -> None:
    request(base_url, "/api/reset", {})
    wait_for_calibration(base_url)
    time.sleep(1.0)
    tap(base_url, 274, 181)  # Select "No" in the changed-time prompt.
    time.sleep(6.0)
    tap(base_url, 237, 181)  # The low-space dialog accepts touch, not Enter.
    time.sleep(3.0)
    for _ in range(6):
        key(base_url, 22)
        time.sleep(0.6)
    if launch:
        tap(base_url, 41, 55)


def png_chunk(kind: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload))


def screenshot(base_url: str, output: Path) -> None:
    packet = request(base_url, "/api/debug/frame")
    if len(packet) < FRAME_HEADER.size:
        raise SystemExit("frame packet is truncated")
    magic, _sequence, width, height, stride, pixel_format = FRAME_HEADER.unpack_from(packet)
    if magic != b"H1FR" or stride != width * 4:
        raise SystemExit("frame packet has an unsupported header")
    pixels = memoryview(packet)[FRAME_HEADER.size:]
    if len(pixels) != stride * height:
        raise SystemExit("frame packet has an invalid payload size")
    rgba_format = 0x41424752
    rows = bytearray()
    for y in range(height):
        rows.append(0)
        row = pixels[y * stride:(y + 1) * stride]
        if pixel_format == rgba_format:
            rows.extend(row)
        else:
            for x in range(0, stride, 4):
                rows.extend((row[x + 2], row[x + 1], row[x], 255))
    png = b"\x89PNG\r\n\x1a\n"
    png += png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
    png += png_chunk(b"IDAT", zlib.compress(rows, 9))
    png += png_chunk(b"IEND", b"")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(png)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8796")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status")
    tap_parser = commands.add_parser("tap")
    tap_parser.add_argument("x", type=int)
    tap_parser.add_argument("y", type=int)
    tap_parser.add_argument("--hold-ms", type=int, default=220)
    swipe_parser = commands.add_parser("swipe")
    swipe_parser.add_argument("start_x", type=int)
    swipe_parser.add_argument("start_y", type=int)
    swipe_parser.add_argument("end_x", type=int)
    swipe_parser.add_argument("end_y", type=int)
    swipe_parser.add_argument("--duration-ms", type=int, default=500)
    swipe_parser.add_argument("--steps", type=int, default=12)
    key_parser = commands.add_parser("key")
    key_parser.add_argument("code", type=int)
    key_parser.add_argument("--hold-ms", type=int, default=120)
    shot_parser = commands.add_parser("screenshot")
    shot_parser.add_argument("output", type=Path)
    boot_parser = commands.add_parser("boot-kov-page")
    boot_parser.add_argument("--launch", action="store_true")
    boot_parser.add_argument("--screenshot", type=Path)
    commands.add_parser("reset")
    commands.add_parser("stop")
    args = parser.parse_args()
    base_url = args.url.rstrip("/")
    if args.command == "status":
        print(json.dumps(status(base_url), ensure_ascii=False, indent=2))
    elif args.command == "tap":
        tap(base_url, args.x, args.y, args.hold_ms)
    elif args.command == "swipe":
        swipe(
            base_url,
            args.start_x,
            args.start_y,
            args.end_x,
            args.end_y,
            args.duration_ms,
            args.steps,
        )
    elif args.command == "key":
        key(base_url, args.code, args.hold_ms)
    elif args.command == "screenshot":
        screenshot(base_url, args.output)
    elif args.command == "boot-kov-page":
        boot_to_kov_page(base_url, args.launch)
        if args.screenshot is not None:
            time.sleep(1.0)
            screenshot(base_url, args.screenshot)
    elif args.command == "reset":
        print(request(base_url, "/api/reset", {}).decode("utf-8"))
    elif args.command == "stop":
        print(request(base_url, "/api/stop", {}).decode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
