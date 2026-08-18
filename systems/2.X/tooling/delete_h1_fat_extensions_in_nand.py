#!/usr/bin/env python3
"""Logically delete selected FAT files from an H1 NAND image.

The image is modified in place because the NAND FTL must be rewritten through
its existing logical-to-physical mapping.  Callers should move the image to
the Windows Recycle Bin before invoking this tool when a recoverable backup is
required.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path

from replace_h1_fat_file_in_nand import FatResolver, LogicalVolume, default_ecc_helper


TARGET_EXTENSIONS = (".avi", ".mp3")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def walk_files(resolver: FatResolver, directory: int | None, prefix: str = "", seen=None):
    seen = set() if seen is None else seen
    marker = -1 if directory is None else directory
    if marker in seen:
        return
    seen.add(marker)
    for entry in resolver.entries(directory):
        name = entry.long_name or entry.short_name
        if name in {".", ".."}:
            continue
        path = f"{prefix}\\{name}" if prefix else name
        if entry.is_directory:
            yield from walk_files(resolver, entry.first_cluster, path, seen)
        else:
            yield path, entry


def fat_cluster_count(resolver: FatResolver) -> int:
    bytes_per_sector = int(resolver.geometry["bytes_per_sector"])
    total_sectors = int(resolver.geometry["total_sectors"])
    data_bytes = total_sectors * bytes_per_sector - resolver.data_start
    return data_bytes // resolver.cluster_size


def delete_entries(volume: LogicalVolume, resolver: FatResolver, targets):
    resolver.fat = bytearray(resolver.fat)
    deleted = []
    for path, entry in targets:
        original = resolver.read_file(entry)
        chain = resolver.cluster_chain(entry.first_cluster)
        for offset in entry.lfn_offsets:
            volume.write(offset, b"\xE5")
        volume.write(entry.directory_offset, b"\xE5")
        for cluster in chain:
            struct.pack_into("<H", resolver.fat, cluster * 2, 0)
        deleted.append(
            {
                "path": path,
                "bytes": entry.size,
                "capacity": len(chain) * resolver.cluster_size,
                "clusters": len(chain),
                "sha256": sha256(original),
            }
        )
    fat_start = resolver.volume_base + int(resolver.geometry["reserved_sectors"]) * resolver.sector_size
    fat_size = int(resolver.geometry["sectors_per_fat"]) * resolver.sector_size
    copies = int(resolver.geometry["fat_copies"])
    for copy in range(copies):
        volume.write(fat_start + copy * fat_size, resolver.fat)
    return deleted


def main() -> int:
    repository = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("--scan-start-block", type=lambda value: int(value, 0), default=0x40)
    parser.add_argument("--ecc-helper", type=Path, default=default_ecc_helper(repository))
    parser.add_argument("--python-ecc", action="store_true")
    parser.add_argument("--in-place", action="store_true", required=True)
    args = parser.parse_args()

    image = args.image.resolve(strict=True)
    helper = None if args.python_ecc else args.ecc_helper.resolve(strict=True)
    volume = LogicalVolume(image, args.scan_start_block, writable=True)
    try:
        resolver = FatResolver(volume)
        all_files = list(walk_files(resolver, None))
        targets = [
            (path, entry)
            for path, entry in all_files
            if any(path.casefold().endswith(ext) for ext in TARGET_EXTENSIONS)
        ]
        deleted = delete_entries(volume, resolver, targets)
        write_report = volume.flush(helper)
        free_after = sum(
            1
            for cluster in range(2, fat_cluster_count(resolver) + 2)
            if struct.unpack_from("<H", resolver.fat, cluster * 2)[0] == 0
        )
    finally:
        volume.close()

    check = LogicalVolume(image, args.scan_start_block, writable=False)
    try:
        checked = FatResolver(check)
        remaining = [
            path
            for path, _entry in walk_files(checked, None)
            if any(path.casefold().endswith(ext) for ext in TARGET_EXTENSIONS)
        ]
        if remaining:
            raise IOError("target extensions remain after deletion: " + ", ".join(remaining))
        readback_free = sum(
            1
            for cluster in range(2, fat_cluster_count(checked) + 2)
            if struct.unpack_from("<H", checked.fat, cluster * 2)[0] == 0
        )
        mapping_count = len(check.result.mapping)
    finally:
        check.close()

    print(json.dumps({
        "format": "bbk-h1-fat-extension-delete-v1",
        "image_name": image.name,
        "extensions": list(TARGET_EXTENSIONS),
        "deleted": deleted,
        "deleted_bytes": sum(item["bytes"] for item in deleted),
        "released_clusters": sum(item["clusters"] for item in deleted),
        "free_clusters_after_write": free_after,
        "free_clusters_readback": readback_free,
        "ftl_mapping_count": mapping_count,
        "write": write_report,
        "readback_verified": True,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
