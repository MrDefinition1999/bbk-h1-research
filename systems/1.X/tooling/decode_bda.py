#!/usr/bin/env python3
"""Validate and extract a BBK BDA executable payload."""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path


HEADER_SIZE = 0x88
HEADER_XOR = b"DWRD"
CHECKSUM_XOR = b"KF-2"
EXPECTED_MARKER = 0x5D245562
# The address is not stored in the BDA header. H1's module loader and the
# payload's absolute references agree on this device-specific code address.
H1_RECOVERY_LOAD_ADDRESS = 0x83C00040


def xor_repeating(data: bytes, key: bytes) -> bytes:
    return bytes(value ^ key[index % len(key)] for index, value in enumerate(data))


def decode_header(raw_header: bytes) -> bytes:
    if len(raw_header) != HEADER_SIZE:
        raise ValueError(f"short BDA header: expected {HEADER_SIZE} bytes")
    return xor_repeating(raw_header[: 11 * 4], HEADER_XOR) + raw_header[11 * 4 :]


def decode_text(value: bytes) -> str:
    return value.split(b"\0", 1)[0].decode("gbk", errors="replace")


def inspect_bda(
    path: Path, load_address: int = H1_RECOVERY_LOAD_ADDRESS
) -> tuple[dict[str, object], bytes]:
    raw = path.read_bytes()
    if len(raw) < HEADER_SIZE:
        raise ValueError(f"{path}: file is smaller than the BDA header")

    header = decode_header(raw[:HEADER_SIZE])
    if header[:4] != b"BBK\0":
        raise ValueError(f"{path}: invalid BDA magic")

    marker = struct.unpack_from("<I", header, 4)[0]
    if marker != EXPECTED_MARKER:
        raise ValueError(f"{path}: unexpected marker 0x{marker:08x}")

    stored_checksum = struct.unpack("<I", xor_repeating(header[0x84:0x88], CHECKSUM_XOR))[0]
    calculated_checksum = sum(header[:0x84])
    if stored_checksum != calculated_checksum:
        raise ValueError(
            f"{path}: header checksum mismatch: stored={stored_checksum}, "
            f"calculated={calculated_checksum}"
        )

    data_offset = struct.unpack_from("<I", header, 0x14)[0]
    if not HEADER_SIZE <= data_offset <= len(raw):
        raise ValueError(f"{path}: invalid payload offset 0x{data_offset:x}")

    payload = raw[data_offset:]
    metadata: dict[str, object] = {
        "input": str(path.resolve()),
        "file_size": len(raw),
        "file_sha256": hashlib.sha256(raw).hexdigest(),
        "marker": f"0x{marker:08x}",
        "version_fields": list(header[8:12]),
        "declared_size": struct.unpack_from("<I", header, 0x10)[0],
        "payload_offset": data_offset,
        "payload_size": len(payload),
        "payload_sha256": hashlib.sha256(payload).hexdigest(),
        "load_address": f"0x{load_address:08x}",
        "entry_address": f"0x{load_address:08x}",
        "address_source": (
            "caller-supplied H1 runtime address; not encoded in the BDA header"
        ),
        "title": decode_text(header[0x2C:0x3C]),
        "build_time": decode_text(header[0x3C:0x50]),
        "description": decode_text(header[0x50:0x64]),
        "header_checksum": stored_checksum,
    }
    return metadata, payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="input .bda file")
    parser.add_argument("output", type=Path, help="extracted payload path")
    parser.add_argument("--metadata", type=Path, help="optional JSON metadata path")
    parser.add_argument(
        "--load-address",
        type=lambda value: int(value, 0),
        default=H1_RECOVERY_LOAD_ADDRESS,
        help=(
            "runtime payload/entry address used only for metadata "
            "(default: 0x83c00040, H1 system recovery)"
        ),
    )
    args = parser.parse_args()

    metadata, payload = inspect_bda(args.input, args.load_address)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(payload)

    rendered = json.dumps(metadata, ensure_ascii=False, indent=2)
    if args.metadata:
        args.metadata.parent.mkdir(parents=True, exist_ok=True)
        args.metadata.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
