#!/usr/bin/env python3
"""Redirect only Mission's private game-data paths from A: to B:."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


MISSION_DATA_ROOT_A = "A:\\应用\\数据\\游戏\\".encode("gbk")
MISSION_DATA_ROOT_B = "B:\\应用\\数据\\游戏\\".encode("gbk")
DEFAULT_EXPECTED_PATHS = 5


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def patch_payload(data: bytes, expected_paths: int) -> tuple[bytes, list[int]]:
    offsets: list[int] = []
    start = 0
    while True:
        offset = data.find(MISSION_DATA_ROOT_A, start)
        if offset < 0:
            break
        offsets.append(offset)
        start = offset + len(MISSION_DATA_ROOT_A)
    if len(offsets) != expected_paths:
        raise ValueError(
            f"expected {expected_paths} Mission A: data paths, found {len(offsets)}"
        )

    patched = data.replace(MISSION_DATA_ROOT_A, MISSION_DATA_ROOT_B)
    if len(patched) != len(data):
        raise AssertionError("drive rewrite changed the payload size")
    if MISSION_DATA_ROOT_A in patched:
        raise AssertionError("an A: Mission data root remains after rewriting")
    changed = [index for index, (old, new) in enumerate(zip(data, patched)) if old != new]
    if changed != offsets:
        raise AssertionError("rewrite changed bytes outside the five drive letters")
    return patched, offsets


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--expected-paths",
        type=int,
        default=DEFAULT_EXPECTED_PATHS,
        help="exact number of Mission private paths that must be rewritten",
    )
    args = parser.parse_args()
    if args.expected_paths <= 0:
        parser.error("--expected-paths must be positive")

    source = args.source.resolve(strict=True)
    output = args.output.resolve()
    if output == source:
        raise ValueError("output must not overwrite the source")
    if output.exists():
        raise FileExistsError(f"refusing to overwrite {output}")
    original = source.read_bytes()
    patched, offsets = patch_payload(original, args.expected_paths)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(patched)
    print(
        json.dumps(
            {
                "format": "bbk-h1-v2-mission-resource-drive-v1",
                "source_name": source.name,
                "output_name": output.name,
                "bytes": len(original),
                "source_sha256": sha256(original),
                "output_sha256": sha256(patched),
                "old_root": "A:\\应用\\数据\\游戏\\",
                "new_root": "B:\\应用\\数据\\游戏\\",
                "patched_paths": len(offsets),
                "drive_byte_offsets": [f"0x{offset:X}" for offset in offsets],
                "size_preserved": len(original) == len(patched),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
