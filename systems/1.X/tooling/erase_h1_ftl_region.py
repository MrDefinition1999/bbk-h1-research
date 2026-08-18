#!/usr/bin/env python3
"""Erase only the FTL region of an existing H1 raw NAND image in place."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

from h1_ftl import RAW_ERASE_BLOCK_SIZE


H1_PHYSICAL_BLOCKS = 4096
ERASE_CHUNK = b"\xFF" * (16 * 1024 * 1024)


def parse_int(value: str) -> int:
    return int(value, 0)


def digest_prefix(path: Path, size: int) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        remaining = size
        while remaining:
            chunk = stream.read(min(16 * 1024 * 1024, remaining))
            if not chunk:
                raise IOError("short read while hashing preserved NAND prefix")
            digest.update(chunk)
            remaining -= len(chunk)
    return digest.hexdigest().upper()


def digest_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(16 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest().upper()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("--ftl-start-block", type=parse_int, required=True)
    args = parser.parse_args()

    image = args.image.resolve()
    expected_size = H1_PHYSICAL_BLOCKS * RAW_ERASE_BLOCK_SIZE
    if image.stat().st_size != expected_size:
        raise ValueError(
            f"H1 NAND must contain {H1_PHYSICAL_BLOCKS} physical blocks "
            f"({expected_size} bytes)"
        )
    if not 0 < args.ftl_start_block < H1_PHYSICAL_BLOCKS:
        raise ValueError("FTL start block is outside the H1 NAND geometry")

    preserved_bytes = args.ftl_start_block * RAW_ERASE_BLOCK_SIZE
    prefix_before = digest_prefix(image, preserved_bytes)
    with image.open("r+b", buffering=0) as stream:
        stream.seek(preserved_bytes)
        remaining = expected_size - preserved_bytes
        while remaining:
            count = min(remaining, len(ERASE_CHUNK))
            stream.write(ERASE_CHUNK[:count])
            remaining -= count
        stream.flush()
        os.fsync(stream.fileno())
    prefix_after = digest_prefix(image, preserved_bytes)
    if prefix_after != prefix_before:
        raise ValueError("preserved NAND prefix changed while erasing FTL")

    print(
        json.dumps(
            {
                "format": "bbk-h1-erased-ftl-v1",
                "image_name": image.name,
                "physical_blocks": H1_PHYSICAL_BLOCKS,
                "ftl_start_block": args.ftl_start_block,
                "preserved_bytes": preserved_bytes,
                "preserved_sha256": prefix_after,
                "output_sha256": digest_file(image),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
