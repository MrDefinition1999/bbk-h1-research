#!/usr/bin/env python3
"""Compare a PC ``bbk.`` member with the indexed SD UPD payloads."""

from __future__ import annotations

import argparse
import bz2
import hashlib
import json
import mmap
import struct
from pathlib import Path

from parse_h1_v2_upd import locate_table, open_image, parse_entries


def wrapper_records(prefix: Path) -> list[tuple[int, int]]:
    data = prefix.read_bytes()
    if data[:4] != b"bbk.":
        raise ValueError("invalid bbk. prefix")
    count = struct.unpack_from("<I", data, 8)[0]
    result = []
    for index in range(count):
        base = 16 + index * 0x100
        if base + 8 > len(data):
            raise ValueError("prefix does not contain the complete wrapper index")
        result.append(struct.unpack_from("<II", data, base))
    return result


def compare(
    source_path: Path,
    member_offset: int,
    prefix_path: Path,
    upd_path: Path,
    output_skip: int,
) -> dict[str, object]:
    records = wrapper_records(prefix_path)
    source_handle = source_path.open("rb")
    upd_handle, upd = open_image(upd_path)
    try:
        entries = parse_entries(upd, locate_table(upd))
        if len(records) != len(entries):
            raise ValueError("wrapper/UPD record count differs")
        decoder = bz2.BZ2Decompressor()
        source = mmap.mmap(source_handle.fileno(), 0, access=mmap.ACCESS_READ)
        try:
            cursor = member_offset
            output_size = 0
            expected_index = 0
            expected_offset = 0
            first_mismatch = None
            output_hash = hashlib.sha256()
            expected_hash = hashlib.sha256()
            while cursor < len(source) and not decoder.eof:
                chunk = source[cursor : min(cursor + 1024 * 1024, len(source))]
                produced = decoder.decompress(chunk)
                cursor += len(chunk)
                if not produced:
                    continue
                start = output_size
                output_size += len(produced)
                compare_start = max(0, output_skip - start)
                comparable = produced[compare_start:] if output_size > output_skip else b""
                if not comparable:
                    continue
                output_hash.update(comparable)
                remaining = memoryview(comparable)
                while remaining:
                    if expected_index >= len(entries):
                        if first_mismatch is None:
                            first_mismatch = {"output_offset": output_size - len(remaining), "reason": "extra output"}
                        break
                    entry = entries[expected_index]
                    available = entry.size - expected_offset
                    amount = min(len(remaining), available)
                    expected = bytes(upd[entry.payload_offset + expected_offset : entry.payload_offset + expected_offset + amount])
                    expected_hash.update(expected)
                    if first_mismatch is None and remaining[:amount] != expected:
                        mismatch = next(index for index in range(amount) if remaining[index] != expected[index])
                        first_mismatch = {
                            "entry_index": expected_index,
                            "entry_offset": expected_offset + mismatch,
                            "output_offset": start + compare_start + mismatch,
                            "output_byte": int(remaining[mismatch]),
                            "expected_byte": expected[mismatch],
                        }
                    remaining = remaining[amount:]
                    expected_offset += amount
                    if expected_offset == entry.size:
                        expected_index += 1
                        expected_offset = 0
            consumed = cursor - len(decoder.unused_data)
            expected_size = sum(entry.size for entry in entries)
            output_suffix_size = max(0, output_size - output_skip)
            return {
                "member_offset": member_offset,
                "compressed_size": consumed - member_offset,
                "output_size": output_size,
                "output_skip": output_skip,
                "output_suffix_size": output_suffix_size,
                "expected_size": expected_size,
                "records_checked": expected_index,
                "first_mismatch": first_mismatch,
                "output_sha256": output_hash.hexdigest(),
                "expected_sha256": expected_hash.hexdigest(),
                "byte_equal": first_mismatch is None and expected_index == len(entries) and output_suffix_size == expected_size and output_hash.digest() == expected_hash.digest(),
            }
        finally:
            source.close()
    finally:
        upd.close()
        upd_handle.close()
        source_handle.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("super_exe", type=Path)
    parser.add_argument("member_offset", type=lambda value: int(value, 0))
    parser.add_argument("prefix", type=Path)
    parser.add_argument("upd", type=Path)
    parser.add_argument("--output-skip", type=lambda value: int(value, 0), default=128016)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()
    rendered = json.dumps(
        compare(args.super_exe, args.member_offset, args.prefix, args.upd, args.output_skip),
        ensure_ascii=True,
        indent=2,
    ) + "\n"
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
