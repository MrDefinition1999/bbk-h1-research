#!/usr/bin/env python3
"""Inspect the payload and commit metadata of H1 FTL bbt8 records."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from h1_ftl import PAGE_SIZE, PAGE_STRIDE, SPARE_SIZE, scan_image


def parse_int(value: str) -> int:
    return int(value, 0)


def non_ff_ranges(data: bytes) -> list[dict[str, int]]:
    ranges: list[dict[str, int]] = []
    start: int | None = None
    for offset, value in enumerate(data):
        if value != 0xFF and start is None:
            start = offset
        elif value == 0xFF and start is not None:
            ranges.append({"start": start, "end": offset, "bytes": offset - start})
            start = None
    if start is not None:
        ranges.append({"start": start, "end": len(data), "bytes": len(data) - start})
    return ranges


def inspect(path: Path, scan_start_block: int) -> dict[str, object]:
    scan = scan_image(path, scan_start_block)
    records = []
    with scan.path.open("rb") as stream:
        for record in scan.records:
            if record.kind != "bbt":
                continue
            page_count = (record.last_valid_page or 0) + 1
            payload = bytearray()
            oob = []
            for page_offset in range(page_count):
                stream.seek((record.first_page + page_offset) * PAGE_STRIDE)
                payload.extend(stream.read(PAGE_SIZE))
                page_oob = stream.read(SPARE_SIZE)
                oob.append(page_oob.hex().upper())
            data = bytes(payload)
            records.append(
                {
                    "physical_block": record.physical_block,
                    "slot": record.slot,
                    "sequence": record.sequence,
                    "last_valid_page": record.last_valid_page,
                    "payload_bytes": len(data),
                    "payload_sha256": hashlib.sha256(data).hexdigest().upper(),
                    "non_ff_ranges": non_ff_ranges(data),
                    "prefix_hex": data[:256].hex().upper(),
                    "u32_prefix": [
                        int.from_bytes(data[offset : offset + 4], "little")
                        for offset in range(0, min(len(data), 256), 4)
                    ],
                    "oob_hex": oob,
                }
            )
    return {
        "format": "bbk-h1-bbt-inspection-v1",
        "image_name": path.name,
        "scan_start_block": scan_start_block,
        "records": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path, nargs="+")
    parser.add_argument("--scan-start-block", type=parse_int, default=0x40)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    report = {
        "format": "bbk-h1-bbt-inspection-set-v1",
        "images": [inspect(path, args.scan_start_block) for path in args.image],
    }
    rendered = json.dumps(report, ensure_ascii=True, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
