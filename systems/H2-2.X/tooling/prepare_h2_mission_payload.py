#!/usr/bin/env python3
"""Extract the real V1 Mission game from the deployed H1 wrapper and retarget data to B:."""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPOSITORY_ROOT / "h1-bda-sdk"))

from h1_bda.header import decode_header  # noqa: E402


BDA_PAYLOAD_OFFSET = 0x785C
EMBEDDED_GAME_OFFSET = 0x734
EMBEDDED_GAME_SIZE = 0x79374
CONTAINER_PAYLOAD_SHA256 = (
    "14AC9F9BBE54696C0F05740CC60284E712DD66D821C9DB7250909451EE0F0704"
)
ORIGINAL_GAME_SHA256 = (
    "6B80B93F3B3D2352ACCC46A9F2D593C7B707690717BD15C4B4CDE2D2608F9CC9"
)
RESOURCE_ROOT_A = "A:\\应用\\数据\\游戏\\".encode("gbk")
RESOURCE_ROOT_B = "B:\\应用\\数据\\游戏\\".encode("gbk")
EXPECTED_RESOURCE_PATHS = 5


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def prepare_payload(
    mission_bda: Path, output: Path, original_output: Path | None = None
) -> None:
    source = mission_bda.read_bytes()
    decoded = decode_header(source)
    payload_offset = int.from_bytes(decoded[0x14:0x18], "little")
    if payload_offset != BDA_PAYLOAD_OFFSET:
        raise ValueError(f"unexpected container payload offset 0x{payload_offset:X}")
    container = source[payload_offset:]
    if sha256(container) != CONTAINER_PAYLOAD_SHA256:
        raise ValueError("Mission container payload hash mismatch")
    end = EMBEDDED_GAME_OFFSET + EMBEDDED_GAME_SIZE
    original = container[EMBEDDED_GAME_OFFSET:end]
    if len(original) != EMBEDDED_GAME_SIZE or sha256(original) != ORIGINAL_GAME_SHA256:
        raise ValueError("embedded original Mission game hash mismatch")

    offsets: list[int] = []
    cursor = 0
    while True:
        offset = original.find(RESOURCE_ROOT_A, cursor)
        if offset < 0:
            break
        offsets.append(offset)
        cursor = offset + len(RESOURCE_ROOT_A)
    if len(offsets) != EXPECTED_RESOURCE_PATHS:
        raise ValueError(
            f"expected {EXPECTED_RESOURCE_PATHS} Mission resource roots, found {len(offsets)}"
        )
    patched = original.replace(RESOURCE_ROOT_A, RESOURCE_ROOT_B)
    if len(patched) != len(original):
        raise AssertionError("drive retarget changed Mission payload size")
    changed = [index for index, pair in enumerate(zip(original, patched)) if pair[0] != pair[1]]
    if changed != offsets:
        raise AssertionError("bytes outside the five drive letters changed")

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(patched)
    if original_output is not None:
        original_output.parent.mkdir(parents=True, exist_ok=True)
        original_output.write_bytes(original)
    print(f"output={output}")
    print(f"bytes={len(patched)}")
    print(f"original_sha256={ORIGINAL_GAME_SHA256}")
    print(f"patched_sha256={sha256(patched)}")
    print("drive_offsets=" + ",".join(f"0x{offset:X}" for offset in offsets))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mission-bda", type=Path, required=True)
    parser.add_argument("-o", "--output", type=Path, required=True)
    parser.add_argument("--original-output", type=Path)
    args = parser.parse_args()
    prepare_payload(args.mission_bda, args.output, args.original_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
