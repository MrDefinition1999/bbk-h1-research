#!/usr/bin/env python3
"""Apply or undo the H2 simulator-only idle WAIT workaround.

The H2 V2.2L OS enters a JZ4750L low-power WAIT instruction after roughly one
minute.  OpenNoah's current H2 QEMU model does not implement the matching wake
path, so a sleeping guest cannot be woken by SADC or GPIO input.  Replacing the
two A/B copies of this one WAIT instruction with a NOP keeps the simulator
interactive without changing the H2 Mission wrapper used on physical hardware.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


EXPECTED_IMAGE_BYTES = 2 * 1024 * 1024 * 1024
WAIT = bytes.fromhex("20000042")
NOP = bytes.fromhex("00000000")
PATCHES = (
    ("classic-os-a-idle-wait", 0x004159BC),
    ("classic-os-b-idle-wait", 0x013159BC),
)


def validate_image(path: Path) -> None:
    if not path.is_file():
        raise FileNotFoundError(path)
    if path.stat().st_size != EXPECTED_IMAGE_BYTES:
        raise ValueError(
            f"expected a {EXPECTED_IMAGE_BYTES}-byte H2 image, got {path.stat().st_size}"
        )


def read_patch_bytes(path: Path) -> list[tuple[str, int, bytes]]:
    rows = []
    with path.open("rb") as stream:
        for name, offset in PATCHES:
            stream.seek(offset)
            rows.append((name, offset, stream.read(len(WAIT))))
    return rows


def verify(path: Path, expected: bytes) -> list[dict[str, object]]:
    validate_image(path)
    result = []
    for name, offset, actual in read_patch_bytes(path):
        if actual != expected:
            raise ValueError(
                f"{name} mismatch at 0x{offset:X}: "
                f"expected {expected.hex().upper()}, found {actual.hex().upper()}"
            )
        result.append(
            {"name": name, "offset": offset, "bytes": actual.hex().upper()}
        )
    return result


def apply(image: Path, journal: Path) -> list[dict[str, object]]:
    validate_image(image)
    rows = read_patch_bytes(image)
    for name, offset, actual in rows:
        if actual != WAIT:
            raise ValueError(
                f"refusing unknown {name} bytes at 0x{offset:X}: {actual.hex().upper()}"
            )
    if journal.exists():
        raise FileExistsError(f"journal already exists: {journal}")
    record = {
        "format": "bbk-h2-simulator-idle-undo-v1",
        "image": image.name,
        "image_bytes": image.stat().st_size,
        "patches": [
            {
                "name": name,
                "offset": offset,
                "original": actual.hex().upper(),
                "replacement": NOP.hex().upper(),
            }
            for name, offset, actual in rows
        ],
    }
    journal.parent.mkdir(parents=True, exist_ok=True)
    journal.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    with image.open("r+b", buffering=0) as stream:
        for _name, offset, _actual in rows:
            stream.seek(offset)
            stream.write(NOP)
        stream.flush()
        os.fsync(stream.fileno())
    return verify(image, NOP)


def undo(image: Path, journal: Path) -> list[dict[str, object]]:
    validate_image(image)
    record = json.loads(journal.read_text(encoding="utf-8"))
    if record.get("format") != "bbk-h2-simulator-idle-undo-v1":
        raise ValueError("unsupported idle patch journal")
    expected = {(name, offset) for name, offset in PATCHES}
    restored: list[tuple[str, int, bytes]] = []
    for row in record.get("patches", []):
        name = row["name"]
        offset = int(row["offset"])
        if (name, offset) not in expected:
            raise ValueError(f"journal contains an unexpected patch: {name}")
        original = bytes.fromhex(row["original"])
        replacement = bytes.fromhex(row["replacement"])
        if original != WAIT or replacement != NOP:
            raise ValueError(f"journal bytes are invalid for {name}")
        restored.append((name, offset, original))
    if {(name, offset) for name, offset, _data in restored} != expected:
        raise ValueError("journal does not cover both H2 A/B OS copies")
    verify(image, NOP)
    with image.open("r+b", buffering=0) as stream:
        for _name, offset, original in restored:
            stream.seek(offset)
            stream.write(original)
        stream.flush()
        os.fsync(stream.fileno())
    return verify(image, WAIT)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--apply", action="store_true")
    modes.add_argument("--verify", action="store_true")
    modes.add_argument("--undo", action="store_true")
    parser.add_argument("--journal", type=Path)
    args = parser.parse_args()
    image = args.image.resolve()
    if args.apply or args.undo:
        if args.journal is None:
            parser.error("--apply and --undo require --journal")
        result = apply(image, args.journal.resolve()) if args.apply else undo(
            image, args.journal.resolve()
        )
    else:
        result = verify(image, NOP)
    print(json.dumps(result, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
