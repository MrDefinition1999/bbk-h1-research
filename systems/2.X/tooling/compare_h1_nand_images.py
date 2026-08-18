#!/usr/bin/env python3
"""Compare H1 raw NAND images by erase block and FTL mapping."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict
from pathlib import Path

from h1_ftl import (
    PAGE_SIZE,
    PAGE_STRIDE,
    PAGES_PER_ERASE_BLOCK,
    read_logical_unit,
    scan_image,
)


ERASE_BLOCK_SIZE = PAGE_STRIDE * PAGES_PER_ERASE_BLOCK


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def compare_block(index: int, before: bytes, after: bytes) -> dict[str, object]:
    changed_pages = []
    data_changed_pages = []
    oob_changed_pages = []
    for page in range(PAGES_PER_ERASE_BLOCK):
        offset = page * PAGE_STRIDE
        if before[offset : offset + PAGE_STRIDE] == after[offset : offset + PAGE_STRIDE]:
            continue
        changed_pages.append(page)
        if before[offset : offset + PAGE_SIZE] != after[offset : offset + PAGE_SIZE]:
            data_changed_pages.append(page)
        if before[offset + PAGE_SIZE : offset + PAGE_STRIDE] != after[offset + PAGE_SIZE : offset + PAGE_STRIDE]:
            oob_changed_pages.append(page)
    return {
        "block": index,
        "before_sha256": digest(before),
        "after_sha256": digest(after),
        "changed_pages": changed_pages,
        "data_changed_pages": data_changed_pages,
        "oob_changed_pages": oob_changed_pages,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("before", type=Path)
    parser.add_argument("after", type=Path)
    parser.add_argument("--scan-start-block", type=lambda value: int(value, 0), default=0x40)
    parser.add_argument("--detail-limit", type=int, default=64)
    args = parser.parse_args()

    before_size = args.before.stat().st_size
    after_size = args.after.stat().st_size
    if before_size != after_size or before_size % ERASE_BLOCK_SIZE:
        raise SystemExit("images do not have matching H1 NAND geometry")

    changed_blocks = []
    block_details = []
    with args.before.open("rb") as left, args.after.open("rb") as right:
        for block in range(before_size // ERASE_BLOCK_SIZE):
            before_data = left.read(ERASE_BLOCK_SIZE)
            after_data = right.read(ERASE_BLOCK_SIZE)
            if before_data != after_data:
                changed_blocks.append(block)
                if len(block_details) < args.detail_limit:
                    block_details.append(compare_block(block, before_data, after_data))

    before_scan = scan_image(args.before, args.scan_start_block)
    after_scan = scan_image(args.after, args.scan_start_block)
    changed_records = []
    changed_record_details = []
    before_records = {
        (record.physical_block, record.slot): record for record in before_scan.records
    }
    after_records = {
        (record.physical_block, record.slot): record for record in after_scan.records
    }
    for key in sorted(set(before_records) | set(after_records)):
        left_record = before_records.get(key)
        right_record = after_records.get(key)
        if left_record != right_record:
            changed_records.append(key)
            if len(changed_record_details) < args.detail_limit:
                changed_record_details.append(
                    {
                        "physical_block": key[0],
                        "slot": key[1],
                        "before": asdict(left_record) if left_record else None,
                        "after": asdict(right_record) if right_record else None,
                    }
                )

    changed_logical = []
    changed_logical_details = []
    changed_block_set = set(changed_blocks)
    for logical in sorted(set(before_scan.mapping) | set(after_scan.mapping)):
        left_record = before_scan.mapping.get(logical)
        right_record = after_scan.mapping.get(logical)
        relevant = left_record != right_record or any(
            record is not None and record.physical_block in changed_block_set
            for record in (left_record, right_record)
        )
        if not relevant:
            continue
        changed_logical.append(logical)
        if len(changed_logical_details) < args.detail_limit:
            changed_logical_details.append(
                {
                    "logical": logical,
                    "before_record": asdict(left_record) if left_record else None,
                    "after_record": asdict(right_record) if right_record else None,
                }
            )

    print(
        json.dumps(
            {
                "format": "bbk-h1-nand-comparison-v1",
                "bytes": before_size,
                "scan_start_block": args.scan_start_block,
                "changed_block_count": len(changed_blocks),
                "changed_blocks": changed_blocks,
                "block_details": block_details,
                "block_details_truncated": len(changed_blocks) > len(block_details),
                "changed_record_count": len(changed_records),
                "changed_record_details": changed_record_details,
                "changed_record_details_truncated": len(changed_records) > len(changed_record_details),
                "changed_logical_count": len(changed_logical),
                "changed_logical": changed_logical,
                "changed_logical_details": changed_logical_details,
                "changed_logical_details_truncated": len(changed_logical) > len(changed_logical_details),
            },
            ensure_ascii=True,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
