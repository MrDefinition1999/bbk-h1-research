#!/usr/bin/env python3
"""Inspect and extract the @ibox H1 NAND FTL logical volume."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

PAGE_SIZE = 2048
SPARE_SIZE = 64
PAGE_STRIDE = PAGE_SIZE + SPARE_SIZE
PAGES_PER_ERASE_BLOCK = 128
PAGES_PER_FTL_UNIT = 128
FTL_UNITS_PER_ERASE_BLOCK = PAGES_PER_ERASE_BLOCK // PAGES_PER_FTL_UNIT
RAW_ERASE_BLOCK_SIZE = PAGE_STRIDE * PAGES_PER_ERASE_BLOCK
LOGICAL_UNIT_SIZE = PAGE_SIZE * PAGES_PER_FTL_UNIT
DEFAULT_SCAN_START_BLOCK = 0x3E
DEFAULT_VOLUME_LBA = 0x20
BBT8_TAG = 0x38746262


@dataclass(frozen=True)
class FtlRecord:
    physical_block: int
    slot: int
    kind: str
    sequence: int | None = None
    logical: int | None = None
    tail: int | None = None
    last_valid_page: int | None = None
    marker: int | None = None
    reason: str | None = None

    @property
    def first_page(self) -> int:
        return (
            self.physical_block * PAGES_PER_ERASE_BLOCK
            + self.slot * PAGES_PER_FTL_UNIT
        )


@dataclass(frozen=True)
class ScanResult:
    path: Path
    physical_blocks: int
    scan_start_block: int
    scan_end_block: int
    records: tuple[FtlRecord, ...]
    mapping: dict[int, FtlRecord]


def parse_int(value: str) -> int:
    return int(value, 0)


def sequence_is_newer(candidate: int, current: int) -> bool:
    return ((current - candidate) & 0xFFFF) > 0x8000


def read_oob(stream, page: int) -> bytes:
    stream.seek(page * PAGE_STRIDE + PAGE_SIZE)
    value = stream.read(SPARE_SIZE)
    if len(value) != SPARE_SIZE:
        raise IOError(f"short OOB read at physical page 0x{page:x}")
    return value


def scan_image(
    path: Path,
    scan_start_block: int = DEFAULT_SCAN_START_BLOCK,
    scan_end_block: int | None = None,
) -> ScanResult:
    image = path.resolve()
    size = image.stat().st_size
    if size == 0 or size % RAW_ERASE_BLOCK_SIZE:
        raise ValueError(f"unsupported H1 NAND geometry: {image} size={size}")
    physical_blocks = size // RAW_ERASE_BLOCK_SIZE
    if scan_end_block is None:
        scan_end_block = physical_blocks
    if not 0 <= scan_start_block <= scan_end_block <= physical_blocks:
        raise ValueError("FTL scan start is outside the NAND image")

    records: list[FtlRecord] = []
    mapping: dict[int, FtlRecord] = {}
    with image.open("rb") as stream:
        for physical in range(scan_start_block, scan_end_block):
            last_page = (physical + 1) * PAGES_PER_ERASE_BLOCK - 1
            bad_marker = read_oob(stream, last_page)[0]
            if bad_marker != 0xFF:
                for slot in range(FTL_UNITS_PER_ERASE_BLOCK):
                    records.append(
                        FtlRecord(
                            physical_block=physical,
                            slot=slot,
                            kind="bad",
                            marker=bad_marker,
                            reason="last physical page bad-block marker is programmed",
                        )
                    )
                continue

            for slot in range(FTL_UNITS_PER_ERASE_BLOCK):
                first_page = (
                    physical * PAGES_PER_ERASE_BLOCK
                    + slot * PAGES_PER_FTL_UNIT
                )
                first = read_oob(stream, first_page)
                marker = first[1]
                last_valid = int.from_bytes(first[2:4], "little")
                sequence = int.from_bytes(first[-6:-4], "little")
                tail = int.from_bytes(first[-4:], "little")

                if tail == 0xFFFFFFFF:
                    records.append(
                        FtlRecord(
                            physical,
                            slot,
                            "free",
                            sequence=sequence,
                            tail=tail,
                            last_valid_page=last_valid,
                            marker=marker,
                        )
                    )
                    continue
                if tail == BBT8_TAG:
                    kind = "bbt"
                    logical = None
                    reason = None
                else:
                    logical = tail & 0xFFFF
                    if marker == 0xFF:
                        kind = "invalid"
                        reason = "mapping tail is present but the slot marker is erased"
                    elif last_valid >= PAGES_PER_FTL_UNIT:
                        kind = "invalid"
                        reason = "last-valid page is outside the 128-page FTL unit"
                    elif logical >= physical_blocks * FTL_UNITS_PER_ERASE_BLOCK:
                        kind = "invalid"
                        reason = "logical unit is outside the NAND geometry"
                    else:
                        kind = "mapped"
                        reason = None

                if kind in {"mapped", "bbt"} and last_valid < PAGES_PER_FTL_UNIT:
                    last = read_oob(stream, first_page + last_valid)
                    if last[-6:] != first[-6:]:
                        kind = "torn"
                        reason = "first and last-valid-page commit tails differ"

                record = FtlRecord(
                    physical_block=physical,
                    slot=slot,
                    kind=kind,
                    sequence=sequence,
                    logical=logical,
                    tail=tail,
                    last_valid_page=last_valid,
                    marker=marker,
                    reason=reason,
                )
                records.append(record)
                if record.kind == "mapped" and logical is not None:
                    current = mapping.get(logical)
                    if current is None or sequence_is_newer(
                        record.sequence or 0, current.sequence or 0
                    ):
                        mapping[logical] = record

    return ScanResult(
        path=image,
        physical_blocks=physical_blocks,
        scan_start_block=scan_start_block,
        scan_end_block=scan_end_block,
        records=tuple(records),
        mapping=mapping,
    )


def read_logical_unit(stream, record: FtlRecord | None) -> bytes:
    if record is None:
        return b"\x00" * LOGICAL_UNIT_SIZE
    output = bytearray()
    expected_tail = (record.sequence or 0).to_bytes(2, "little") + (
        record.tail or 0
    ).to_bytes(4, "little")
    for page_offset in range(PAGES_PER_FTL_UNIT):
        page = record.first_page + page_offset
        stream.seek(page * PAGE_STRIDE)
        data = stream.read(PAGE_SIZE)
        oob = stream.read(SPARE_SIZE)
        if len(data) != PAGE_SIZE or len(oob) != SPARE_SIZE:
            raise IOError(f"short NAND page read at 0x{page:x}")
        if oob[1] != 0xFF and oob[-6:] == expected_tail:
            output.extend(data)
        else:
            output.extend(b"\x00" * PAGE_SIZE)
    return bytes(output)


def fat_geometry(logical_zero: bytes) -> dict[str, int | str]:
    boot_offset = DEFAULT_VOLUME_LBA * 512
    boot = logical_zero[boot_offset : boot_offset + 512]
    if len(boot) != 512 or boot[510:512] != b"\x55\xAA":
        raise ValueError("logical unit zero has no FAT boot sector at LBA 0x20")
    total16 = int.from_bytes(boot[19:21], "little")
    total32 = int.from_bytes(boot[32:36], "little")
    total = total16 or total32
    return {
        "boot_lba": DEFAULT_VOLUME_LBA,
        "bytes_per_sector": int.from_bytes(boot[11:13], "little"),
        "sectors_per_cluster": boot[13],
        "reserved_sectors": int.from_bytes(boot[14:16], "little"),
        "fat_copies": boot[16],
        "root_entries": int.from_bytes(boot[17:19], "little"),
        "sectors_per_fat": int.from_bytes(boot[22:24], "little"),
        "hidden_sectors": int.from_bytes(boot[28:32], "little"),
        "total_sectors": total,
        "volume_label": boot[43:54].decode("ascii", errors="replace").rstrip(),
        "fs_type": boot[54:62].decode("ascii", errors="replace").rstrip(),
    }


def summary(result: ScanResult, record_limit: int) -> dict[str, object]:
    counts: dict[str, int] = {}
    for record in result.records:
        counts[record.kind] = counts.get(record.kind, 0) + 1
    interesting = [record for record in result.records if record.kind != "free"]
    with result.path.open("rb") as stream:
        logical_zero = read_logical_unit(stream, result.mapping.get(0))
    geometry = None
    try:
        geometry = fat_geometry(logical_zero)
    except ValueError:
        pass
    return {
        "format": "bbk-h1-ftl-scan-v1",
        "image": str(result.path),
        "geometry": {
            "page_size": PAGE_SIZE,
            "spare_size": SPARE_SIZE,
            "pages_per_erase_block": PAGES_PER_ERASE_BLOCK,
            "pages_per_ftl_unit": PAGES_PER_FTL_UNIT,
            "physical_blocks": result.physical_blocks,
            "scan_start_block": result.scan_start_block,
            "scan_end_block": result.scan_end_block,
        },
        "counts": counts,
        "mapped_logical_units": len(result.mapping),
        "logical_min": min(result.mapping) if result.mapping else None,
        "logical_max": max(result.mapping) if result.mapping else None,
        "fat": geometry,
        "records": [asdict(record) for record in interesting[:record_limit]],
        "records_truncated": len(interesting) > record_limit,
    }


def extract_volume(result: ScanResult, output: Path, logical_units: int | None) -> dict[str, object]:
    with result.path.open("rb") as source:
        logical_zero = read_logical_unit(source, result.mapping.get(0))
        geometry = fat_geometry(logical_zero)
        output_bytes = None
        if logical_units is None:
            output_bytes = (
                DEFAULT_VOLUME_LBA * 512
                + int(geometry["total_sectors"]) * int(geometry["bytes_per_sector"])
            )
            logical_units = (output_bytes + LOGICAL_UNIT_SIZE - 1) // LOGICAL_UNIT_SIZE
        if logical_units <= 0:
            raise ValueError("logical unit count must be positive")
        if output_bytes is None:
            output_bytes = logical_units * LOGICAL_UNIT_SIZE
        output.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        remaining = output_bytes
        with output.open("wb") as target:
            for logical in range(logical_units):
                data = read_logical_unit(source, result.mapping.get(logical))
                chunk = data[:remaining]
                target.write(chunk)
                digest.update(chunk)
                remaining -= len(chunk)
                if remaining == 0:
                    break
    return {
        "output": str(output.resolve()),
        "output_bytes": output.stat().st_size,
        "output_sha256": digest.hexdigest().upper(),
        "logical_units": logical_units,
        "fat": geometry,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("--scan-start-block", type=parse_int, default=DEFAULT_SCAN_START_BLOCK)
    parser.add_argument(
        "--scan-end-block",
        type=parse_int,
        help="exclusive last physical FTL block (default: end of NAND)",
    )
    parser.add_argument("--record-limit", type=int, default=64)
    parser.add_argument("--extract", type=Path)
    parser.add_argument("--logical-units", type=parse_int)
    parser.add_argument("--output", type=Path, help="write JSON report")
    args = parser.parse_args()

    result = scan_image(args.image, args.scan_start_block, args.scan_end_block)
    report = summary(result, max(0, args.record_limit))
    if args.extract:
        report["extraction"] = extract_volume(result, args.extract, args.logical_units)
    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
