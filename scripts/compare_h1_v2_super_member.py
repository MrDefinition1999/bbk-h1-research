#!/usr/bin/env python3
"""Compare one BZip2 member in the PC updater with an UPD region.

The comparison is streaming and keeps neither the decompressed member nor a
second firmware image on disk.  It is intended to test whether the PC
updater's large embedded ``bbk.`` member is the same data as the SD UPD tail.
"""

from __future__ import annotations

import argparse
import bz2
import hashlib
import json
import mmap
from pathlib import Path


def compare(
    super_path: Path,
    member_offset: int,
    target_path: Path,
    target_offset: int,
    output_skip: int,
) -> dict[str, object]:
    with super_path.open("rb") as source_handle, target_path.open("rb") as target_handle:
        with mmap.mmap(source_handle.fileno(), 0, access=mmap.ACCESS_READ) as source, mmap.mmap(
            target_handle.fileno(), 0, access=mmap.ACCESS_READ
        ) as target:
            decoder = bz2.BZ2Decompressor()
            cursor = member_offset
            target_cursor = target_offset
            output_size = 0
            first_mismatch: dict[str, object] | None = None
            output_hash = hashlib.sha256()
            target_hash = hashlib.sha256()
            marker_offsets: list[int] = []
            carry = b""
            while cursor < len(source) and not decoder.eof:
                chunk = source[cursor : min(cursor + 1024 * 1024, len(source))]
                produced = decoder.decompress(chunk)
                cursor += len(chunk)
                if not produced:
                    continue
                produced_start = output_size
                produced_end = produced_start + len(produced)
                compare_start = max(0, output_skip - produced_start)
                comparable = produced[compare_start:] if produced_end > output_skip else b""
                output_hash.update(comparable)
                output_size += len(produced)
                scan = carry + produced
                base = output_size - len(scan)
                search = 0
                while True:
                    found = scan.find(b"EEBBKBLM", search)
                    if found < 0:
                        break
                    marker_offsets.append(base + found)
                    search = found + 1
                carry = scan[-7:]
                if target_cursor < len(target):
                    expected = bytes(target[target_cursor : target_cursor + len(comparable)])
                else:
                    expected = b""
                target_hash.update(expected)
                if first_mismatch is None:
                    common = min(len(comparable), len(expected))
                    if comparable[:common] != expected[:common]:
                        mismatch = next(index for index in range(common) if comparable[index] != expected[index])
                        first_mismatch = {
                            "output_offset": produced_start + compare_start + mismatch,
                            "target_offset": target_cursor + mismatch,
                            "output_byte": comparable[mismatch],
                            "target_byte": expected[mismatch],
                        }
                    elif len(produced) != len(expected):
                        first_mismatch = {
                            "output_offset": produced_start + compare_start + common,
                            "target_offset": target_cursor + common,
                            "output_byte": None if common == len(comparable) else comparable[common],
                            "target_byte": None if common == len(expected) else expected[common],
                        }
                target_cursor += len(comparable)
            consumed = cursor - len(decoder.unused_data)
            suffix_size = max(0, output_size - output_skip)
            target_size = max(0, min(len(target), target_offset + suffix_size) - target_offset)
            return {
                "member_offset": member_offset,
                "compressed_size": consumed - member_offset,
                "output_size": output_size,
                "output_skip": output_skip,
                "output_sha256_after_skip": output_hash.hexdigest(),
                "target_region_size": target_size,
                "target_region_sha256": target_hash.hexdigest(),
                "first_mismatch": first_mismatch,
                "byte_equal": first_mismatch is None and suffix_size == target_size and output_hash.digest() == target_hash.digest(),
                "eebbkblm_offsets": marker_offsets,
                "target_file_size": len(target),
            }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("super_exe", type=Path)
    parser.add_argument("member_offset", type=lambda value: int(value, 0))
    parser.add_argument("upd", type=Path)
    parser.add_argument("--target-offset", type=lambda value: int(value, 0), required=True)
    parser.add_argument("--output-skip", type=lambda value: int(value, 0), default=0)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()
    rendered = json.dumps(
        compare(args.super_exe, args.member_offset, args.upd, args.target_offset, args.output_skip),
        ensure_ascii=False,
        indent=2,
    ) + "\n"
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
