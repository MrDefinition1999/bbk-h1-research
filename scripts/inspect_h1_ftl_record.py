#!/usr/bin/env python3
"""Compare selected H1 FTL records and validate their programmed-page ECC."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

if __package__:
    from .h1_ftl import (
        PAGE_SIZE,
        PAGE_STRIDE,
        PAGES_PER_FTL_UNIT,
        SPARE_SIZE,
        read_logical_unit,
        scan_image,
    )
    from .jz4740_ecc import jz4740_page_oob_ecc
else:
    from h1_ftl import (
        PAGE_SIZE,
        PAGE_STRIDE,
        PAGES_PER_FTL_UNIT,
        SPARE_SIZE,
        read_logical_unit,
        scan_image,
    )
    from jz4740_ecc import jz4740_page_oob_ecc

DATA_ECC_OOB_OFFSET = 4
ECC_BYTES_PER_PAGE = 36
RESERVED_OOB_START = DATA_ECC_OOB_OFFSET + ECC_BYTES_PER_PAGE
COMMIT_TAIL_START = SPARE_SIZE - 6


def parse_int(value: str) -> int:
    return int(value, 0)


def inspect_record(path: Path, logical: int) -> dict[str, object]:
    result = scan_image(path)
    record = result.mapping.get(logical)
    if record is None:
        return {
            "image": str(result.path),
            "logical": logical,
            "present": False,
        }

    programmed: list[int] = []
    ecc_mismatches: list[int] = []
    bad_marker_mismatches: list[int] = []
    valid_marker_mismatches: list[int] = []
    last_valid_mismatches: list[int] = []
    reserved_oob_mismatches: list[int] = []
    tail_mismatches: list[int] = []
    erased_oob_mismatches: list[int] = []
    first_oob = b""
    last_oob = b""
    expected_tail = (record.sequence or 0).to_bytes(2, "little") + (
        record.tail or 0
    ).to_bytes(4, "little")
    with result.path.open("rb") as stream:
        unit = read_logical_unit(stream, record)
        for page_offset in range(PAGES_PER_FTL_UNIT):
            page = record.first_page + page_offset
            stream.seek(page * PAGE_STRIDE)
            data = stream.read(PAGE_SIZE)
            oob = stream.read(SPARE_SIZE)
            if len(data) != PAGE_SIZE or len(oob) != SPARE_SIZE:
                raise IOError(f"short NAND page read at physical page 0x{page:x}")
            if page_offset == 0:
                first_oob = oob
            if page_offset == record.last_valid_page:
                last_oob = oob
            if oob[1] == 0xFF:
                if oob != b"\xFF" * SPARE_SIZE:
                    erased_oob_mismatches.append(page_offset)
                continue
            programmed.append(page_offset)
            if oob[0] != 0xFF:
                bad_marker_mismatches.append(page_offset)
            if oob[1] != 0:
                valid_marker_mismatches.append(page_offset)
            if int.from_bytes(oob[2:4], "little") != record.last_valid_page:
                last_valid_mismatches.append(page_offset)
            if oob[RESERVED_OOB_START:COMMIT_TAIL_START] != b"\xFF" * (
                COMMIT_TAIL_START - RESERVED_OOB_START
            ):
                reserved_oob_mismatches.append(page_offset)
            if oob[-6:] != expected_tail:
                tail_mismatches.append(page_offset)
            expected_ecc = jz4740_page_oob_ecc(
                data, offset=DATA_ECC_OOB_OFFSET
            )[DATA_ECC_OOB_OFFSET:]
            actual_ecc = oob[
                DATA_ECC_OOB_OFFSET : DATA_ECC_OOB_OFFSET + ECC_BYTES_PER_PAGE
            ]
            if actual_ecc != expected_ecc:
                ecc_mismatches.append(page_offset)

    return {
        "image": str(result.path),
        "logical": logical,
        "present": True,
        "physical_block": record.physical_block,
        "slot": record.slot,
        "sequence": record.sequence,
        "last_valid_page": record.last_valid_page,
        "unit_sha256": hashlib.sha256(unit).hexdigest().upper(),
        "programmed_pages": programmed,
        "programmed_page_count": len(programmed),
        "first_oob_hex": first_oob.hex().upper(),
        "last_oob_hex": last_oob.hex().upper(),
        "bad_marker_mismatches": bad_marker_mismatches,
        "valid_marker_mismatches": valid_marker_mismatches,
        "last_valid_mismatches": last_valid_mismatches,
        "ecc_mismatches": ecc_mismatches,
        "reserved_oob_mismatches": reserved_oob_mismatches,
        "tail_mismatches": tail_mismatches,
        "erased_oob_mismatches": erased_oob_mismatches,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path, nargs="+")
    parser.add_argument("--logical", type=parse_int, action="append", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    report = {
        "format": "bbk-h1-ftl-record-inspection-v2",
        "records": [
            inspect_record(path, logical)
            for path in args.image
            for logical in args.logical
        ],
    }
    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
