#!/usr/bin/env python3
"""Validate V2 BDA headers in the SD UPD and a PC updater BZip2 member.

The PC updater member expands to hundreds of megabytes.  This tool streams it
once and retains only the 0x88-byte header of each BDA record, so source-format
validation does not require another extracted package copy.
"""

from __future__ import annotations

import argparse
import bz2
import json
import struct
from dataclasses import dataclass
from pathlib import Path

from decode_bda import (
    CHECKSUM_XOR,
    EXPECTED_MARKER,
    HEADER_SIZE,
    decode_header,
    xor_repeating,
)
from parse_h1_v2_upd import locate_table, open_image, parse_entries


WRAPPER_HEADER_SIZE = 16
WRAPPER_RECORD_SIZE = 0x100
WRAPPER_RECORD_CAPACITY = 500
WRAPPER_PREFIX_SIZE = WRAPPER_HEADER_SIZE + WRAPPER_RECORD_CAPACITY * WRAPPER_RECORD_SIZE
READ_CHUNK = 1024 * 1024


@dataclass(frozen=True)
class Capture:
    index: int
    path: str
    file_size: int
    start: int


def validate_header(raw: bytes, file_size: int) -> tuple[bool, str]:
    if len(raw) != HEADER_SIZE:
        return False, f"short header ({len(raw)}/{HEADER_SIZE})"
    header = decode_header(raw)
    if header[:4] != b"BBK\0":
        return False, f"magic={header[:4].hex()}"
    marker = struct.unpack_from("<I", header, 4)[0]
    if marker != EXPECTED_MARKER:
        return False, f"marker=0x{marker:08x}"
    stored = struct.unpack("<I", xor_repeating(header[0x84:0x88], CHECKSUM_XOR))[0]
    calculated = sum(header[:0x84])
    if stored != calculated:
        return False, f"checksum={stored}/{calculated}"
    payload_offset = struct.unpack_from("<I", header, 0x14)[0]
    if not HEADER_SIZE <= payload_offset <= file_size:
        return False, f"payload_offset=0x{payload_offset:x} file_size={file_size}"
    return True, "valid"


def parse_wrapper(prefix: bytes, paths: list[str]) -> list[Capture]:
    if len(prefix) != WRAPPER_PREFIX_SIZE or prefix[:4] != b"bbk.":
        raise ValueError("invalid or incomplete bbk. wrapper prefix")
    count = struct.unpack_from("<I", prefix, 8)[0]
    if count != len(paths):
        raise ValueError(f"wrapper/UPD record count differs: {count}/{len(paths)}")
    captures = []
    for index, path in enumerate(paths):
        base = WRAPPER_HEADER_SIZE + index * WRAPPER_RECORD_SIZE
        size, relative_offset = struct.unpack_from("<II", prefix, base)
        if path.lower().endswith(".bda"):
            captures.append(
                Capture(
                    index=index,
                    path=path,
                    file_size=size,
                    start=WRAPPER_HEADER_SIZE + relative_offset,
                )
            )
    return captures


def capture_pc_headers(source: Path, member_offset: int, paths: list[str]) -> tuple[dict[int, bytes], dict[str, int]]:
    decoder = bz2.BZ2Decompressor()
    prefix = bytearray()
    captures: list[Capture] | None = None
    retained: dict[int, bytearray] = {}
    output_offset = 0
    compressed_read = 0

    with source.open("rb") as stream:
        stream.seek(member_offset)
        while not decoder.eof:
            chunk = stream.read(READ_CHUNK)
            if not chunk:
                raise ValueError("truncated BZip2 member")
            compressed_read += len(chunk)
            produced = decoder.decompress(chunk)
            if not produced:
                continue
            chunk_start = output_offset
            chunk_end = chunk_start + len(produced)
            output_offset = chunk_end

            if len(prefix) < WRAPPER_PREFIX_SIZE:
                amount = min(WRAPPER_PREFIX_SIZE - len(prefix), len(produced))
                prefix.extend(produced[:amount])
                if len(prefix) == WRAPPER_PREFIX_SIZE:
                    captures = parse_wrapper(bytes(prefix), paths)
                    retained = {capture.index: bytearray() for capture in captures}

            if captures is None:
                continue
            for capture in captures:
                wanted_start = capture.start
                wanted_end = wanted_start + HEADER_SIZE
                overlap_start = max(chunk_start, wanted_start)
                overlap_end = min(chunk_end, wanted_end)
                if overlap_start < overlap_end:
                    retained[capture.index].extend(
                        produced[overlap_start - chunk_start : overlap_end - chunk_start]
                    )

    compressed_size = compressed_read - len(decoder.unused_data)
    return (
        {index: bytes(value) for index, value in retained.items()},
        {"compressed_size": compressed_size, "output_size": output_offset},
    )


def inspect(sd_upd: Path, pc_updater: Path, member_offset: int) -> dict[str, object]:
    handle, image = open_image(sd_upd)
    try:
        entries = parse_entries(image, locate_table(image))
        paths = [entry.path for entry in entries]
        pc_headers, pc_member = capture_pc_headers(pc_updater, member_offset, paths)
        rows = []
        for entry in entries:
            if not entry.path.lower().endswith(".bda"):
                continue
            sd_raw = bytes(image[entry.payload_offset : entry.payload_offset + HEADER_SIZE])
            sd_valid, sd_reason = validate_header(sd_raw, entry.size)
            pc_raw = pc_headers.get(entry.index, b"")
            pc_valid, pc_reason = validate_header(pc_raw, entry.size)
            rows.append(
                {
                    "index": entry.index,
                    "path": entry.path,
                    "size": entry.size,
                    "sd_valid": sd_valid,
                    "sd_reason": sd_reason,
                    "sd_raw_prefix": sd_raw[:20].hex(),
                    "pc_valid": pc_valid,
                    "pc_reason": pc_reason,
                    "pc_raw_prefix": pc_raw[:20].hex(),
                }
            )
        return {
            "sd_image": sd_upd.name,
            "pc_updater": pc_updater.name,
            "pc_member_offset": member_offset,
            "pc_member": pc_member,
            "bda_count": len(rows),
            "sd_valid_count": sum(1 for row in rows if row["sd_valid"]),
            "pc_valid_count": sum(1 for row in rows if row["pc_valid"]),
            "rows": rows,
        }
    finally:
        image.close()
        handle.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sd_upd", type=Path)
    parser.add_argument("pc_updater", type=Path)
    parser.add_argument("member_offset", type=lambda value: int(value, 0))
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()
    result = inspect(args.sd_upd, args.pc_updater, args.member_offset)
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
