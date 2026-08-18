#!/usr/bin/env python3
"""Patch only the frame interval in the accepted CS15 H1 baseline BDA."""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path


WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
SDK_ROOT = WORKSPACE_ROOT / "h1-bda-sdk"
if str(SDK_ROOT) not in sys.path:
    sys.path.insert(0, str(SDK_ROOT))

from h1_bda.resources import PAYLOAD_OFFSET
from h1_bda.validate import validate_bda


ENTRY_VA = 0x83C00020
EXPECTED_SHA256 = "40DF83013728562A52763F707CD504607DCE5A30FBE3F300E265F4AE10EDE546"
FRAME_INTERVAL_INSTRUCTIONS = (
    (0x83C19A74, bytes.fromhex("28 00 24 24")),
    (0x83C19B68, bytes.fromhex("28 00 31 24")),
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--interval-ms", type=int, default=1)
    args = parser.parse_args()

    if not 1 <= args.interval_ms <= 0x7FFF:
        parser.error("--interval-ms must be between 1 and 32767")

    data = bytearray(args.source.read_bytes())
    source_hash = hashlib.sha256(data).hexdigest().upper()
    if source_hash != EXPECTED_SHA256:
        raise SystemExit(
            "refusing to patch an unrecognized baseline: "
            f"expected {EXPECTED_SHA256}, got {source_hash}"
        )

    replacement_immediate = args.interval_ms.to_bytes(2, "little")
    for virtual_address, expected in FRAME_INTERVAL_INSTRUCTIONS:
        offset = PAYLOAD_OFFSET + virtual_address - ENTRY_VA
        actual = bytes(data[offset : offset + 4])
        if actual != expected:
            raise SystemExit(
                f"instruction mismatch at 0x{virtual_address:08X}: "
                f"expected {expected.hex()}, got {actual.hex()}"
            )
        data[offset : offset + 4] = replacement_immediate + expected[2:]

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(data)
    report = validate_bda(args.output)
    if not report["ok"]:
        args.output.unlink(missing_ok=True)
        raise SystemExit("patched BDA failed validation: " + "; ".join(report["errors"]))

    print(f"output={args.output.name}")
    print(f"size={len(data)}")
    print(f"sha256={hashlib.sha256(data).hexdigest().upper()}")
    print(f"frame_interval_ms={args.interval_ms}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
