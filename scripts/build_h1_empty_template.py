#!/usr/bin/env python3
"""Create a deterministic H1 A5 empty-volume FTL template or format seed.

The original guest-created template was lost in the storage incident.  A
format seed contains no FTL records and is initialized by the official guest;
system files are added later by build_h1_system_nand.py.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path

from h1_ftl import (
    BBT8_TAG,
    LOGICAL_UNIT_SIZE,
    PAGE_SIZE,
    PAGE_STRIDE,
    PAGES_PER_ERASE_BLOCK,
    scan_image,
)
from jz4740_ecc import jz4740_page_oob_ecc


PHYSICAL_BLOCKS = 4096
SCAN_START_BLOCK = 0x3E
SPARE_SIZE = 64
LAST_VALID = {
    0: (0x44, 8),
    1: (0x41, 60),
    2: (0x42, 60),
    3: (0x43, 7),
}
SEQUENCES = {0: 4, 1: 1, 2: 2, 3: 3}
BBT_BLOCK = 0x45
OUTPUT_SIZE = PHYSICAL_BLOCKS * PAGES_PER_ERASE_BLOCK * PAGE_STRIDE
REPLACEABLE_FAILED_TEMPLATE_SHA256 = (
    "5B678854F5253A9B7DC55073BD8D6E86274FD327753BB6D3FA4939251671C638"
)
GUEST_FORMATTED_TEMPLATE_SHA256 = (
    "BC6AAF9EA42E1F9BC3A546E85254D4BC4CA9B99461C2155BE28C7131FA8E0FD7"
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(16 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest().upper()


def fat_boot_sector() -> bytes:
    boot = bytearray(512)
    boot[0:3] = b"\xEB\x3C\x90"
    boot[3:11] = b"MSDOS5.0"
    struct.pack_into("<H", boot, 11, 512)
    boot[13] = 32
    struct.pack_into("<H", boot, 14, 480)
    boot[16] = 2
    struct.pack_into("<H", boot, 17, 512)
    struct.pack_into("<H", boot, 19, 0)
    boot[21] = 0xF8
    struct.pack_into("<H", boot, 22, 512)
    struct.pack_into("<H", boot, 24, 32)
    struct.pack_into("<H", boot, 26, 64)
    struct.pack_into("<I", boot, 28, 1)
    struct.pack_into("<I", boot, 32, 2_001_376)
    boot[36] = 0x80
    boot[38] = 0x29
    boot[39:43] = b"H1A5"
    boot[43:54] = b"9388       "
    boot[54:62] = b"FAT16   "
    boot[510:512] = b"\x55\xAA"
    return bytes(boot)


def page_oob(data: bytes, logical: int, sequence: int, last_valid: int, *, bbt: bool = False) -> bytes:
    parity = jz4740_page_oob_ecc(data, offset=4)[4:]
    if len(parity) != 36:
        raise ValueError("unexpected JZ4740 parity length")
    oob = bytearray(b"\xFF" * SPARE_SIZE)
    oob[1] = 0
    struct.pack_into("<H", oob, 2, last_valid)
    oob[4:40] = parity
    struct.pack_into("<H", oob, 58, sequence)
    struct.pack_into("<I", oob, 60, BBT8_TAG if bbt else 0xFFFF0000 | logical)
    return bytes(oob)


def write_mapping(output, logical: int, block: int, last_valid: int, data: bytes, sequence: int) -> None:
    for page in range(last_valid + 1):
        page_data = data[page * PAGE_SIZE : (page + 1) * PAGE_SIZE]
        offset = (block * PAGES_PER_ERASE_BLOCK + page) * PAGE_STRIDE
        output.seek(offset)
        output.write(page_data)
        output.write(page_oob(page_data, logical, sequence, last_valid))


def build(output: Path, *, format_seed: bool = False) -> dict[str, object]:
    if output.exists():
        existing_sha256 = sha256(output)
        if not format_seed or existing_sha256 != REPLACEABLE_FAILED_TEMPLATE_SHA256:
            raise SystemExit(
                f"refusing to overwrite existing template: {output} sha256={existing_sha256}"
            )
    output.parent.mkdir(parents=True, exist_ok=True)
    logical_zero = bytearray(LOGICAL_UNIT_SIZE)
    logical_zero[0x20 * 512 : 0x20 * 512 + 512] = fat_boot_sector()
    logical_empty = bytes(LOGICAL_UNIT_SIZE)
    root_label = bytearray(LOGICAL_UNIT_SIZE)
    root_label[0:11] = b"9388       "
    root_label[11] = 0x08

    erased = b"\xFF" * (1024 * 1024)
    with output.open("w+b") as stream:
        remaining = OUTPUT_SIZE
        while remaining:
            count = min(remaining, len(erased))
            stream.write(erased[:count])
            remaining -= count
        if not format_seed:
            for logical, (block, last_valid) in LAST_VALID.items():
                data = logical_zero if logical == 0 else root_label if logical == 3 else logical_empty
                write_mapping(stream, logical, block, last_valid, data, SEQUENCES[logical])
            bbt_data = bytes(LOGICAL_UNIT_SIZE)
            for page in range(2):
                page_data = bbt_data[page * PAGE_SIZE : (page + 1) * PAGE_SIZE]
                offset = (BBT_BLOCK * PAGES_PER_ERASE_BLOCK + page) * PAGE_STRIDE
                stream.seek(offset)
                stream.write(page_data)
                stream.write(page_oob(page_data, 0, 5, 1, bbt=True))
        stream.flush()

    result = scan_image(output)
    if format_seed:
        if result.mapping or any(record.kind != "free" for record in result.records):
            raise ValueError("format seed contains programmed FTL records")
        return {
            "format": "bbk-h1-a5-format-seed-v1",
            "physical_blocks": PHYSICAL_BLOCKS,
            "scan_start_block": SCAN_START_BLOCK,
            "output": str(output.resolve()),
            "output_bytes": output.stat().st_size,
            "output_sha256": sha256(output),
        }
    if set(result.mapping) != {0, 1, 2, 3}:
        raise ValueError(f"unexpected initial FTL mapping: {sorted(result.mapping)}")
    with output.open("rb") as stream:
        logical = bytearray()
        record = result.mapping[0]
        stream.seek(record.first_page * PAGE_STRIDE)
        for _ in range(9):
            logical.extend(stream.read(PAGE_SIZE))
            stream.seek(SPARE_SIZE, 1)
    if logical[0x20 * 512 + 510 : 0x20 * 512 + 512] != b"\x55\xAA":
        raise ValueError("reconstructed FAT boot signature is missing")
    return {
        "format": "bbk-h1-a5-empty-template-v1",
        "physical_blocks": PHYSICAL_BLOCKS,
        "scan_start_block": SCAN_START_BLOCK,
        "output": str(output.resolve()),
        "output_bytes": output.stat().st_size,
        "output_sha256": sha256(output),
        "mapping": {str(key): value[0] for key, value in LAST_VALID.items()},
        "bbt_block": BBT_BLOCK,
    }


def overlay_boot(output: Path, boot: Path) -> dict[str, object]:
    """Restore the 0x3e-block recovery area without touching FTL records."""
    if not output.is_file() or sha256(output) != GUEST_FORMATTED_TEMPLATE_SHA256:
        raise SystemExit("refusing boot overlay: template is not the guest-formatted image")
    if boot.stat().st_size != SCAN_START_BLOCK * PAGES_PER_ERASE_BLOCK * PAGE_STRIDE:
        raise ValueError("boot NAND does not contain exactly the reserved 0x3e blocks")
    with output.open("r+b") as target, boot.open("rb") as source:
        remaining = boot.stat().st_size
        while remaining:
            chunk = source.read(min(1024 * 1024, remaining))
            if not chunk:
                raise IOError("short boot NAND read")
            target.write(chunk)
            remaining -= len(chunk)
        target.flush()
    return {
        "format": "bbk-h1-a5-guest-template-v1",
        "physical_blocks": PHYSICAL_BLOCKS,
        "scan_start_block": SCAN_START_BLOCK,
        "output": str(output.resolve()),
        "output_bytes": output.stat().st_size,
        "output_sha256": sha256(output),
        "boot_source": str(boot.resolve()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument(
        "--format-seed",
        action="store_true",
        help="create erased NAND for the official firmware to format",
    )
    parser.add_argument(
        "--overlay-boot",
        type=Path,
        help="restore the reserved boot NAND area into a guest-formatted template",
    )
    args = parser.parse_args()
    if not args.format_seed and args.overlay_boot is None:
        parser.error(
            "use --format-seed and the official guest formatter, then --overlay-boot; "
            "the legacy synthetic writer is disabled"
        )
    if args.overlay_boot:
        report = overlay_boot(args.output.resolve(), args.overlay_boot.resolve())
    else:
        report = build(args.output.resolve(), format_seed=args.format_seed)
    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.manifest:
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        args.manifest.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
