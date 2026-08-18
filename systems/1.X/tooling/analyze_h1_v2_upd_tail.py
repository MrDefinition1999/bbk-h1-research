#!/usr/bin/env python3
"""Inspect the unindexed tail of an H1 V2 UPD image without extracting it.

The indexed records are handled by :mod:`parse_h1_v2_upd`.  V2.20 has an
additional tail beginning at the end of the last indexed payload.  This tool
records bounded metadata and signature/entropy observations so that format
work is reproducible without making another copy of the 834 MB image.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import mmap
import re
import struct
from pathlib import Path

from parse_h1_v2_upd import locate_table, open_image, parse_entries


MARKERS = (
    b"EEBBKBLM",
    b"B1A89588",
    bytes.fromhex("8895a8b1"),
    b"BZh",
    b"MZ",
    b"DLX",
    b"BBK\x00",
    b"zlb\x1a",
)
WINDOW_SIZE = 4096


def entropy(block: bytes) -> float:
    if not block:
        return 0.0
    counts = [0] * 256
    for value in block:
        counts[value] += 1
    length = len(block)
    return -sum(
        (count / length) * math.log2(count / length)
        for count in counts
        if count
    )


def words(block: bytes, count: int = 64) -> list[str]:
    usable = min(len(block) // 4, count)
    return [f"0x{struct.unpack_from('<I', block, i * 4)[0]:08x}" for i in range(usable)]


def ascii_runs(block: bytes, minimum: int = 6) -> list[dict[str, object]]:
    result = []
    for match in re.finditer(rb"[ -~]{%d,}" % minimum, block):
        result.append({"offset": match.start(), "text": match.group()[:160].decode("ascii")})
    return result


def marker_hits(data: mmap.mmap, tail_offset: int) -> list[dict[str, object]]:
    result = []
    for marker in MARKERS:
        cursor = tail_offset
        while True:
            found = data.find(marker, cursor)
            if found < 0:
                break
            result.append(
                {
                    "marker": marker.decode("ascii") if marker.isascii() else marker.hex(),
                    "offset": found - tail_offset,
                    "absolute_offset": found,
                }
            )
            cursor = found + 1
    return sorted(result, key=lambda hit: (int(hit["offset"]), str(hit["marker"])))


def inspect(path: Path) -> dict[str, object]:
    handle, image = open_image(path)
    try:
        table = locate_table(image)
        entries = parse_entries(image, table)
        indexed_end = max(entry.payload_offset + entry.size for entry in entries)
        tail_size = len(image) - indexed_end
        prefix = bytes(image[indexed_end : indexed_end + 0x400])
        marker_offset = image.find(b"EEBBKBLM", indexed_end)
        windows = []
        for offset in (0, 0x400, 0x800, 0x1000, 0x2000, 0x4000, 0x10000, 0x100000, 0x1000000, 0x10000000):
            if offset >= tail_size:
                continue
            block = bytes(image[indexed_end + offset : indexed_end + offset + WINDOW_SIZE])
            windows.append(
                {
                    "offset": offset,
                    "size": len(block),
                    "entropy_bits_per_byte": round(entropy(block), 6),
                    "unique_bytes": len(set(block)),
                    "zero_bytes": block.count(0),
                    "ff_bytes": block.count(0xFF),
                    "sha256": hashlib.sha256(block).hexdigest(),
                }
            )
        result = {
            "image_size": len(image),
            "table_offset": table,
            "entry_count": len(entries),
            "indexed_end": indexed_end,
            "unindexed_tail": tail_size,
            "tail_prefix_sha256": hashlib.sha256(prefix).hexdigest(),
            "tail_prefix_hex": prefix.hex(),
            "tail_prefix_words_le": words(prefix),
            "tail_prefix_ascii_runs": ascii_runs(prefix),
            "eebbkblm_first_offset": None if marker_offset < 0 else marker_offset - indexed_end,
            "marker_hits": marker_hits(image, indexed_end),
            "windows": windows,
        }
        if marker_offset >= 0:
            context_start = max(indexed_end, marker_offset - 0x40)
            context_end = min(len(image), marker_offset + 0x200)
            context = bytes(image[context_start:context_end])
            result["eebbkblm_context"] = {
                "offset": context_start - indexed_end,
                "hex": context.hex(),
                "words_le": words(context, 160),
                "ascii_runs": ascii_runs(context),
            }
        return result
    finally:
        image.close()
        handle.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()
    rendered = json.dumps(inspect(args.image), ensure_ascii=False, indent=2) + "\n"
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
