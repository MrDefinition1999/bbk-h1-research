#!/usr/bin/env python3
"""Summarize headers and gaps around EEBBKBLM blocks in the V2 UPD tail."""

from __future__ import annotations

import argparse
import json
import mmap
import struct
from pathlib import Path


def read_words(data: mmap.mmap, offset: int, count: int = 12) -> list[str]:
    result = []
    for index in range(count):
        position = offset + index * 4
        if position + 4 > len(data):
            break
        result.append(f"0x{struct.unpack_from('<I', data, position)[0]:08x}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("upd", type=Path)
    parser.add_argument("analysis", type=Path, help="JSON from analyze_h1_v2_upd_tail.py")
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()
    analysis = json.loads(args.analysis.read_text(encoding="utf-8"))
    tail_start = int(analysis["indexed_end"])
    markers = [
        int(hit["offset"])
        for hit in analysis["marker_hits"]
        if hit["marker"] == "EEBBKBLM"
    ]
    with args.upd.open("rb") as handle, mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ) as data:
        blocks = []
        for index, marker in enumerate(markers):
            absolute = tail_start + marker
            next_marker = markers[index + 1] if index + 1 < len(markers) else int(analysis["unindexed_tail"])
            block_length = next_marker - marker
            blocks.append(
                {
                    "index": index,
                    "tail_offset": marker,
                    "absolute_offset": absolute,
                    "block_length": block_length,
                    "header_hex": bytes(data[absolute : absolute + 32]).hex(),
                    "header_words_le": read_words(data, absolute, 8),
                    "payload_first_32_hex": bytes(data[absolute + 32 : absolute + 64]).hex(),
                }
            )
        result = {
            "indexed_end": tail_start,
            "tail_size": int(analysis["unindexed_tail"]),
            "block_count": len(blocks),
            "blocks": blocks,
        }
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
