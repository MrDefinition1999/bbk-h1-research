#!/usr/bin/env python3
"""Convert an H1FR RGBA8888 diagnostic frame packet to a PNG."""

from __future__ import annotations

import argparse
import struct
import zlib
from pathlib import Path


HEADER = struct.Struct("<4s5I")
RGBA8888 = int.from_bytes(b"RGBA", "little")


def chunk(name: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", len(payload)) + name + payload + struct.pack(">I", zlib.crc32(name + payload))


def convert(source: Path, output: Path) -> None:
    packet = source.read_bytes()
    if len(packet) < HEADER.size:
        raise ValueError("truncated H1 frame packet")
    magic, _sequence, width, height, stride, frame_format = HEADER.unpack_from(packet)
    if magic != b"H1FR" or frame_format != RGBA8888 or stride != width * 4:
        raise ValueError("input is not an H1 RGBA8888 frame packet")
    pixels = packet[HEADER.size :]
    if len(pixels) != stride * height:
        raise ValueError("H1 frame payload size does not match its header")
    scanlines = b"".join(b"\0" + pixels[y * stride : (y + 1) * stride] for y in range(height))
    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(scanlines, 9))
        + chunk(b"IEND", b"")
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(png)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    convert(args.input, args.output)
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
