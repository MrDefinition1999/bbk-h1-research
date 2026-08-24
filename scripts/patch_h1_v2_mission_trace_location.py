#!/usr/bin/env python3
"""Move a legacy V2 Mission wrapper marker into its reserved stage arena."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


OLD_TRACE_BASE = bytes.fromhex("f1 a3 01 3c")  # lui at, 0xA3F1
NEW_TRACE_BASE = bytes.fromhex("f0 83 01 3c")  # lui at, 0x83F0
OLD_FS_OFFSET = bytes.fromhex("00 0f 34 34")  # ori s4, at, 0x0F00
NEW_FS_OFFSET = bytes.fromhex("00 e0 34 34")  # ori s4, at, 0xE000
OLD_GAME_OFFSET = bytes.fromhex("00 0f 31 34")  # ori s1, at, 0x0F00
NEW_GAME_OFFSET = bytes.fromhex("00 e0 31 34")  # ori s1, at, 0xE000

PATCHES = (
    (OLD_TRACE_BASE + OLD_FS_OFFSET, NEW_TRACE_BASE + NEW_FS_OFFSET, "filesystem-phase"),
    (OLD_TRACE_BASE + OLD_GAME_OFFSET, NEW_TRACE_BASE + NEW_GAME_OFFSET, "game-phase"),
)


def load_sdk_validation():
    candidates = (
        ROOT / "h1-bda-sdk",
        ROOT / ".local" / "components" / "sdk",
    )
    for candidate in candidates:
        if (candidate / "h1_bda").is_dir():
            if str(candidate) not in sys.path:
                sys.path.insert(0, str(candidate))
            from h1_bda.header import decode_header
            from h1_bda.validate import validate_bda

            return decode_header, validate_bda
    raise ModuleNotFoundError(
        "cannot find the H1 BDA SDK; run scripts/bootstrap_components.py in "
        "the standalone project or place h1-bda-sdk beside scripts"
    )


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def patch_trace_location(data: bytes, payload_offset: int) -> tuple[bytes, list[dict[str, object]]]:
    if not 0x88 <= payload_offset < len(data):
        raise ValueError("BDA payload offset is outside the file")
    output = bytearray(data)
    changes: list[dict[str, object]] = []
    for old, new, label in PATCHES:
        locations = []
        start = payload_offset
        while True:
            offset = data.find(old, start)
            if offset < 0:
                break
            locations.append(offset)
            start = offset + 1
        if len(locations) != 1:
            raise ValueError(
                f"expected one {label} trace sequence below the payload, found {len(locations)}"
            )
        offset = locations[0]
        output[offset : offset + len(old)] = new
        changes.append(
            {
                "label": label,
                "file_offset": offset,
                "old_hex": old.hex().upper(),
                "new_hex": new.hex().upper(),
            }
        )
    changed = bytes(output)
    expected_changed_bytes = sum(
        sum(left != right for left, right in zip(old, new)) for old, new, _ in PATCHES
    )
    actual_changed_bytes = sum(left != right for left, right in zip(data, changed))
    if actual_changed_bytes != expected_changed_bytes:
        raise AssertionError(
            f"changed {actual_changed_bytes} bytes, expected {expected_changed_bytes}"
        )
    return changed, changes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    source = args.input.resolve(strict=True)
    output = args.output.resolve()
    if source == output:
        parser.error("input and output must be different files")

    decode_header, validate_bda = load_sdk_validation()
    original = source.read_bytes()
    decoded = decode_header(original)
    payload_offset = int.from_bytes(decoded[0x14:0x18], "little")
    patched, changes = patch_trace_location(original, payload_offset)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(patched)
    report = validate_bda(output)
    if not report["ok"]:
        output.unlink(missing_ok=True)
        raise ValueError("patched wrapper failed validation: " + "; ".join(report["errors"]))

    result = {
        "format": "h1-v2-mission-trace-relocation-v1",
        "input_name": source.name,
        "output_name": output.name,
        "bytes": len(patched),
        "input_sha256": sha256(original),
        "output_sha256": sha256(patched),
        "payload_offset": payload_offset,
        "trace_virtual_address": "0x83F0E000",
        "trace_physical_address": "0x03F0E000",
        "changes": changes,
        "validation_ok": True,
    }
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
