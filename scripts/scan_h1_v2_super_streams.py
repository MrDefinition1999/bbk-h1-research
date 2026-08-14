#!/usr/bin/env python3
"""Validate framed BZip2 members in the V2 PC recovery executable.

The executable is never loaded or run.  Each candidate ``BZh`` marker in the
PE overlay is decoded into a streaming hash/size summary only; decompressed
members are not written to disk.  This distinguishes real package members
from coincidental byte sequences in the overlay without creating duplicate
firmware copies.
"""

from __future__ import annotations

import argparse
import bz2
import hashlib
import json
import mmap
import struct
from pathlib import Path


def u32(data: mmap.mmap, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def pe_overlay_start(data: mmap.mmap) -> int:
    pe = u32(data, 0x3C)
    if bytes(data[pe : pe + 4]) != b"PE\0\0":
        raise ValueError("input is not a PE image")
    coff = pe + 4
    sections = struct.unpack_from("<H", data, coff + 2)[0]
    optional_size = struct.unpack_from("<H", data, coff + 16)[0]
    table = coff + 20 + optional_size
    end = table + sections * 40
    for index in range(sections):
        section = table + index * 40
        raw_size = u32(data, section + 16)
        raw_pointer = u32(data, section + 20)
        end = max(end, raw_pointer + raw_size)
    return end


def decode_member(data: mmap.mmap, marker: int) -> dict[str, object] | None:
    decoder = bz2.BZ2Decompressor()
    cursor = marker
    digest = hashlib.sha256()
    output_size = 0
    prefix = bytearray()
    try:
        while cursor < len(data) and not decoder.eof:
            chunk = data[cursor : min(cursor + 1024 * 1024, len(data))]
            produced = decoder.decompress(chunk)
            if produced:
                digest.update(produced)
                output_size += len(produced)
                if len(prefix) < 64:
                    prefix.extend(produced[: 64 - len(prefix)])
            cursor += len(chunk)
    except OSError:
        return None
    if not decoder.eof:
        return None
    consumed = cursor - len(decoder.unused_data)
    return {
        "compressed_offset": marker,
        "compressed_size": consumed - marker,
        "output_size": output_size,
        "output_sha256": digest.hexdigest(),
        "output_prefix_hex": bytes(prefix).hex(),
        "output_prefix_ascii": bytes(prefix).decode("ascii", "replace"),
    }


def scan(path: Path) -> dict[str, object]:
    with path.open("rb") as handle, mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ) as data:
        overlay = pe_overlay_start(data)
        members = []
        cursor = overlay
        while True:
            marker = data.find(b"BZh", cursor)
            if marker < 0:
                break
            member = decode_member(data, marker)
            if member is not None:
                members.append(member)
                cursor = marker + int(member["compressed_size"])
            else:
                cursor = marker + 1
        return {
            "path": path.name,
            "image_size": len(data),
            "overlay_start": overlay,
            "overlay_size": len(data) - overlay,
            "valid_member_count": len(members),
            "members": members,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()
    rendered = json.dumps(scan(args.input), ensure_ascii=False, indent=2) + "\n"
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
