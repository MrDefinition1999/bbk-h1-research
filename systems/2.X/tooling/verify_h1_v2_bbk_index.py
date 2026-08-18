#!/usr/bin/env python3
"""Cross-check ``bbk.`` member index records against the SD UPD table."""

from __future__ import annotations

import argparse
import mmap
import struct
import zlib
from pathlib import Path

from parse_h1_v2_upd import locate_table, open_image, parse_entries


def inspect_prefix(prefix: Path, limit: int) -> tuple[int, list[dict[str, object]]]:
    data = prefix.read_bytes()
    if len(data) < 16 or data[:4] != b"bbk.":
        raise ValueError("invalid bbk. prefix")
    count = struct.unpack_from("<I", data, 8)[0]
    records = []
    for index in range(min(count, limit)):
        base = 16 + index * 0x100
        if base + 0x100 > len(data):
            break
        size, offset = struct.unpack_from("<II", data, base)
        raw = data[base + 8 : base + 0x100]
        value = raw.split(b"\0", 1)[0]
        records.append(
            {
                "index": index,
                "size": size,
                "offset": offset,
                "text": value.decode("gbk", "replace"),
            }
        )
    return count, records


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prefix", type=Path)
    parser.add_argument("upd", type=Path)
    parser.add_argument("--limit", type=int, default=32)
    args = parser.parse_args()
    wrapper_count, wrapper = inspect_prefix(args.prefix, args.limit)
    handle, image = open_image(args.upd)
    try:
        entries = parse_entries(image, locate_table(image))
        comparisons = []
        for record, entry in zip(wrapper, entries):
            payload = bytes(image[entry.payload_offset : entry.payload_offset + entry.size])
            text = str(record["text"])
            tag_hex = text[3:11] if text.startswith("20 ") else ""
            actual_crc = f"{zlib.crc32(payload) & 0xFFFFFFFF:08X}"
            comparisons.append(
                {
                    "index": record["index"],
                    "wrapper_size": record["size"],
                    "upd_size": entry.size,
                    "size_equal": int(record["size"]) == entry.size,
                    "wrapper_offset": record["offset"],
                    "wrapper_text": text,
                    "upd_path": entry.path,
                    "tag_hex": tag_hex,
                    "crc32": actual_crc,
                    "crc_equal": tag_hex.upper() == actual_crc,
                }
            )
        size_equal = sum(1 for row in comparisons if row["size_equal"])
        crc_equal = sum(1 for row in comparisons if row["crc_equal"])
        contiguous = all(
            int(left["offset"]) + int(left["size"]) == int(right["offset"])
            for left, right in zip(wrapper, wrapper[1:])
        )
        total_size = sum(int(record["size"]) for record in wrapper)
        print(f"wrapper_count={wrapper_count} upd_count={len(entries)} checked={len(comparisons)}")
        print(f"size_equal={size_equal}/{len(comparisons)} tag_crc32_equal={crc_equal}/{len(comparisons)}")
        print(
            f"offsets_contiguous={contiguous} payload_sum={total_size} "
            f"last_end={int(wrapper[-1]['offset']) + int(wrapper[-1]['size']) if wrapper else 0}"
        )
        for row in comparisons:
            print(
                f"{row['index']:03d} size={row['wrapper_size']} offset={row['wrapper_offset']} "
                f"size_ok={row['size_equal']} tag={row['tag_hex']}/{row['crc32']} "
                f"crc_ok={row['crc_equal']} text={row['wrapper_text']}"
            )
    finally:
        image.close()
        handle.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
