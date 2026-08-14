#!/usr/bin/env python3
"""Inspect the bounded ``bbk.`` wrapper prefix from a V2 PC member."""

from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path


def u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def inspect(path: Path, record_limit: int) -> dict[str, object]:
    data = path.read_bytes()
    if len(data) < 24 or data[:4] != b"bbk.":
        raise ValueError("missing bbk. wrapper prefix")
    record_count = u32(data, 8)
    records = []
    for index in range(min(record_count, record_limit)):
        offset = 16 + index * 0x100
        if offset + 0x100 > len(data):
            break
        record = data[offset : offset + 0x100]
        size, payload_offset = struct.unpack_from("<II", record, 0)
        path_field = record[8:]
        nul = path_field.find(b"\0")
        text = path_field[: nul if nul >= 0 else len(path_field)]
        records.append(
            {
                "index": index,
                "offset": offset,
                "size": size,
                "payload_offset": payload_offset,
                "prefix_hex": record[:24].hex(),
                "ascii_prefix": text[:160].decode("ascii", "replace"),
                "raw_sha256": __import__("hashlib").sha256(record).hexdigest(),
            }
        )
    return {
        "path": path.name,
        "prefix_size": len(data),
        "header_hex": data[:24].hex(),
        "header_words_le": [f"0x{u32(data, offset):08x}" for offset in range(0, 24, 4)],
        "record_count": record_count,
        "record_stride": 0x100,
        "records": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prefix", type=Path)
    parser.add_argument("--record-limit", type=int, default=20)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()
    rendered = json.dumps(inspect(args.prefix, args.record_limit), ensure_ascii=True, indent=2) + "\n"
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
