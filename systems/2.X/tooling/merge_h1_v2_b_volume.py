#!/usr/bin/env python3
"""Combine an unchanged V2 A/boot image with a separately built B FTL volume."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
from pathlib import Path

from h1_ftl import RAW_ERASE_BLOCK_SIZE, fat_geometry, read_logical_unit, scan_image


V2_A_START_BLOCK = 120
V2_B_START_BLOCK = 1780
V2_DEVICE_BLOCKS = 4096
COPY_CHUNK = 16 * 1024 * 1024


def hash_range(path: Path, start: int, length: int) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        stream.seek(start)
        remaining = length
        while remaining:
            chunk = stream.read(min(remaining, COPY_CHUNK))
            if not chunk:
                raise IOError(f"short read from {path} at 0x{stream.tell():X}")
            digest.update(chunk)
            remaining -= len(chunk)
    return digest.hexdigest().upper()


def b_fat(path: Path) -> tuple[object, dict[str, int | str]]:
    result = scan_image(path, V2_B_START_BLOCK, V2_DEVICE_BLOCKS)
    if not result.mapping:
        raise ValueError(f"B-volume source has no mappings: {path}")
    with path.open("rb") as stream:
        geometry = fat_geometry(read_logical_unit(stream, result.mapping.get(0)))
    return result, geometry


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True, help="V2 boot and A-volume image")
    parser.add_argument("--b-volume", type=Path, required=True, help="image containing built B FTL records")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()

    base = args.base.resolve(strict=True)
    b_volume = args.b_volume.resolve(strict=True)
    output = args.output.resolve()
    expected_bytes = V2_DEVICE_BLOCKS * RAW_ERASE_BLOCK_SIZE
    for path in (base, b_volume):
        if path.stat().st_size != expected_bytes:
            raise ValueError(f"V2 image must contain 4096 raw blocks: {path}")
    if output in {base, b_volume}:
        raise ValueError("output must not overwrite an input image")
    if output.exists():
        raise FileExistsError(f"refusing to overwrite {output}")

    base_a = scan_image(base, V2_A_START_BLOCK, V2_B_START_BLOCK)
    if not base_a.mapping:
        raise ValueError("base image has no mounted A volume")
    source_b, source_b_geometry = b_fat(b_volume)
    boundary = V2_B_START_BLOCK * RAW_ERASE_BLOCK_SIZE
    suffix_bytes = expected_bytes - boundary

    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with base.open("rb") as source, output.open("xb") as target:
            shutil.copyfileobj(source, target, COPY_CHUNK)
            target.flush()
            os.fsync(target.fileno())
        with b_volume.open("rb") as source, output.open("r+b", buffering=0) as target:
            source.seek(boundary)
            target.seek(boundary)
            remaining = suffix_bytes
            while remaining:
                chunk = source.read(min(remaining, COPY_CHUNK))
                if not chunk:
                    raise IOError("B-volume source ended before the NAND suffix")
                target.write(chunk)
                remaining -= len(chunk)
            target.flush()
            os.fsync(target.fileno())

        output_a = scan_image(output, V2_A_START_BLOCK, V2_B_START_BLOCK)
        output_b, output_b_geometry = b_fat(output)
        if output_a.mapping.keys() != base_a.mapping.keys():
            raise ValueError("A-volume logical mapping set changed during B merge")
        if output_b_geometry != source_b_geometry:
            raise ValueError("B FAT geometry changed during merge")
        base_prefix_hash = hash_range(base, 0, boundary)
        output_prefix_hash = hash_range(output, 0, boundary)
        source_suffix_hash = hash_range(b_volume, boundary, suffix_bytes)
        output_suffix_hash = hash_range(output, boundary, suffix_bytes)
        if base_prefix_hash != output_prefix_hash:
            raise ValueError("boot/A byte range changed during B merge")
        if source_suffix_hash != output_suffix_hash:
            raise ValueError("B byte range changed during merge")
    except BaseException:
        if output.exists():
            output.unlink()
        raise

    report = {
        "format": "bbk-h1-v2-dual-volume-merge-v1",
        "base_name": base.name,
        "b_volume_name": b_volume.name,
        "output_name": output.name,
        "bytes": expected_bytes,
        "partition_boundary_block": V2_B_START_BLOCK,
        "partition_boundary_bytes": boundary,
        "boot_and_a_sha256": output_prefix_hash,
        "b_suffix_sha256": output_suffix_hash,
        "a_mapped_logical_units": len(output_a.mapping),
        "b_mapped_logical_units": len(output_b.mapping),
        "b_fat": output_b_geometry,
        "byte_ranges_verified": True,
    }
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.manifest:
        manifest = args.manifest.resolve()
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
