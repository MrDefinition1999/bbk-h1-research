#!/usr/bin/env python3
"""Relocate the H1 QEMU diagnostic RAM base in a verified test executable.

The checked source overlay is authoritative.  This small binary transformer is
only for validating an overlay change when the matching QEMU source/build tree
is not locally available; a release must still be rebuilt from the overlay.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


SUPPORTED_SHA256 = "5D1B27450309293F32CA69AD9B57124F37885E6AEAE806E3A45ACEE75B32946F"
OLD_BASE = 0x83E00000
NEW_BASE = 0x83F80000
# The optimized x86-64 build folds KSEG addresses to physical constants at
# every recorder call site.  Counts make this a build-specific, fail-closed
# transform instead of a broad byte replacement.
PATCH_VALUES = {
    0x03E00018: 2,
    0x03E00040: 1,
    0x03E00100: 1,
    0x03E00300: 1,
    0x03E00500: 1,
    0x03E00600: 1,
    0x03E01000: 1,
    0x03E02000: 1,
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def patch(source: bytes) -> bytes:
    if sha256(source) != SUPPORTED_SHA256:
        raise ValueError("input is not the verified H1 x86-64 QEMU test build")
    output = source
    delta = NEW_BASE - OLD_BASE
    for old_value, expected_count in PATCH_VALUES.items():
        old = old_value.to_bytes(4, "little")
        new = (old_value + delta).to_bytes(4, "little")
        if output.count(old) != expected_count:
            raise ValueError(
                f"diagnostic address 0x{old_value:08X} occurrence count does not "
                "match the verified build"
            )
        output = output.replace(old, new)
        if output.count(old) != 0 or output.count(new) < expected_count:
            raise AssertionError("diagnostic address relocation did not complete")
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    source = args.source.read_bytes()
    output = patch(source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(output)
    report = {
        "format": "bbk-h1-qemu-diag-base-patch-v1",
        "source_name": args.source.name,
        "source_sha256": sha256(source),
        "output_name": args.output.name,
        "output_sha256": sha256(output),
        "old_base": f"0x{OLD_BASE:08X}",
        "new_base": f"0x{NEW_BASE:08X}",
        "patched_occurrences": sum(PATCH_VALUES.values()),
        "release_requires_source_rebuild": True,
    }
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered, encoding="utf-8", newline="\n")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
