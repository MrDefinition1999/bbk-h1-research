#!/usr/bin/env python3
"""Reversibly rename one FAT file in an H1 raw NAND image."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath

from h1_fat16 import lfn_checksum, make_lfn_entries
from replace_h1_fat_file_in_nand import FatResolver, LogicalVolume, default_ecc_helper


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def parent_cluster(resolver: FatResolver, path: PurePosixPath) -> int | None:
    directory: int | None = None
    for component in path.parts[1:-1]:
        entry = next(
            (
                item
                for item in resolver.entries(directory)
                if component.casefold()
                in {item.short_name.casefold(), (item.long_name or "").casefold()}
            ),
            None,
        )
        if entry is None:
            raise FileNotFoundError(str(path))
        if not entry.is_directory:
            raise NotADirectoryError(component)
        directory = entry.first_cluster
    return directory


def renamed_short_name(original: bytes, new_name: str) -> bytes:
    path = PurePosixPath(new_name)
    suffix = path.suffix.removeprefix(".").upper()
    if not suffix or len(suffix) > 3 or not suffix.isascii() or not suffix.isalnum():
        raise ValueError("new name must have a one-to-three character ASCII extension")
    stem = path.stem.upper()
    if stem and len(stem) <= 8 and stem.isascii() and stem.isalnum():
        return stem.encode("ascii").ljust(8, b" ") + suffix.encode("ascii").ljust(3, b" ")
    return original[:8] + suffix.encode("ascii").ljust(3, b" ")


def main() -> int:
    repository = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("path")
    parser.add_argument("new_name")
    parser.add_argument("--scan-start-block", type=lambda value: int(value, 0), default=0x40)
    parser.add_argument("--ecc-helper", type=Path, default=default_ecc_helper(repository))
    parser.add_argument("--python-ecc", action="store_true")
    parser.add_argument("--in-place", action="store_true", required=True)
    args = parser.parse_args()

    if not args.new_name or any(separator in args.new_name for separator in ("/", "\\")):
        parser.error("new_name must be a file name, not a path")

    image = args.image.resolve(strict=True)
    source_path = PurePosixPath("/" + args.path.replace("\\", "/").lstrip("/"))
    destination_path = source_path.with_name(args.new_name)
    helper = None if args.python_ecc else args.ecc_helper.resolve(strict=True)

    volume = LogicalVolume(image, args.scan_start_block, writable=True)
    try:
        resolver = FatResolver(volume)
        entry = resolver.resolve(str(source_path))
        if entry.is_directory:
            raise IsADirectoryError(str(source_path))
        directory = parent_cluster(resolver, source_path)
        names = {
            name.casefold()
            for item in resolver.entries(directory)
            for name in (item.short_name, item.long_name or "")
            if name
        }
        if args.new_name.casefold() in names:
            raise FileExistsError(str(destination_path))

        original = resolver.read_file(entry)
        new_short = renamed_short_name(entry.short_name_raw, args.new_name)
        new_lfn = make_lfn_entries(args.new_name, lfn_checksum(new_short))
        if len(new_lfn) != len(entry.lfn_offsets):
            raise ValueError(
                "new long name must use the same number of VFAT directory entries"
            )
        for offset, encoded in zip(entry.lfn_offsets, new_lfn):
            volume.write(offset, encoded)
        volume.write(entry.directory_offset, new_short)
        write_report = volume.flush(helper)
        mapping_count = len(volume.result.mapping)
    finally:
        volume.close()

    check = LogicalVolume(image, args.scan_start_block)
    try:
        resolver = FatResolver(check)
        renamed = resolver.resolve(str(destination_path))
        readback = resolver.read_file(renamed)
        if readback != original:
            raise IOError("renamed file payload differs from the original")
        try:
            resolver.resolve(str(source_path))
        except FileNotFoundError:
            pass
        else:
            raise IOError("old FAT path still resolves after rename")
        if len(check.result.mapping) != mapping_count:
            raise IOError("FTL mapping count changed during rename")
    finally:
        check.close()

    print(
        json.dumps(
            {
                "format": "bbk-h1-reversible-fat-rename-v1",
                "image_name": image.name,
                "old_path": str(source_path),
                "new_path": str(destination_path),
                "payload_bytes": len(original),
                "payload_sha256": sha256(original),
                "write": write_report,
                "readback_verified": True,
            },
            ensure_ascii=True,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
