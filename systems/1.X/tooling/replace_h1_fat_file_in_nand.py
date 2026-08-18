#!/usr/bin/env python3
"""Replace one FAT file in an H1 raw NAND without changing its cluster chain."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
from dataclasses import dataclass
from pathlib import Path

from build_h1_system_nand import EccEncoder, write_mapped_unit
from h1_ftl import LOGICAL_UNIT_SIZE, fat_geometry, read_logical_unit, scan_image
from inspect_h1_fat_path import decode_lfn, decode_short_name


@dataclass(frozen=True)
class LocatedEntry:
    short_name: str
    short_name_raw: bytes
    long_name: str | None
    attributes: int
    first_cluster: int
    size: int
    directory_offset: int
    lfn_offsets: tuple[int, ...]

    @property
    def is_directory(self) -> bool:
        return bool(self.attributes & 0x10)


class LogicalVolume:
    def __init__(
        self,
        image: Path,
        scan_start_block: int,
        scan_end_block: int | None = None,
        writable: bool = False,
    ) -> None:
        self.image = image
        self.result = scan_image(image, scan_start_block, scan_end_block)
        self.stream = image.open("r+b" if writable else "rb", buffering=0)
        self.cache: dict[int, bytearray] = {}
        self.dirty: set[int] = set()

    def close(self) -> None:
        self.stream.close()

    def unit(self, logical: int) -> bytearray:
        if logical not in self.cache:
            self.cache[logical] = bytearray(
                read_logical_unit(self.stream, self.result.mapping.get(logical))
            )
        return self.cache[logical]

    def read(self, offset: int, size: int) -> bytes:
        output = bytearray()
        while size:
            logical = offset // LOGICAL_UNIT_SIZE
            within = offset % LOGICAL_UNIT_SIZE
            count = min(size, LOGICAL_UNIT_SIZE - within)
            output.extend(self.unit(logical)[within : within + count])
            offset += count
            size -= count
        return bytes(output)

    def write(self, offset: int, data: bytes) -> None:
        view = memoryview(data)
        position = 0
        while position < len(view):
            logical = offset // LOGICAL_UNIT_SIZE
            within = offset % LOGICAL_UNIT_SIZE
            count = min(len(view) - position, LOGICAL_UNIT_SIZE - within)
            unit = self.unit(logical)
            unit[within : within + count] = view[position : position + count]
            self.dirty.add(logical)
            offset += count
            position += count

    def flush(self, helper: Path | None) -> dict[str, object]:
        pages = 0
        with EccEncoder(helper) as encoder:
            for logical in sorted(self.dirty):
                record = self.result.mapping.get(logical)
                if record is None or record.sequence is None:
                    raise ValueError(f"logical unit {logical} has no writable mapped record")
                pages += write_mapped_unit(
                    self.stream,
                    record,
                    logical,
                    bytes(self.cache[logical]),
                    record.sequence,
                    encoder,
                )
        self.stream.flush()
        os.fsync(self.stream.fileno())
        return {"logical_units": sorted(self.dirty), "programmed_pages": pages}


class FatResolver:
    def __init__(self, volume: LogicalVolume) -> None:
        self.volume = volume
        logical_zero = volume.read(0, LOGICAL_UNIT_SIZE)
        self.geometry = fat_geometry(logical_zero)
        self.sector_size = int(self.geometry["bytes_per_sector"])
        self.volume_base = int(self.geometry["boot_lba"]) * self.sector_size
        reserved = int(self.geometry["reserved_sectors"])
        fat_copies = int(self.geometry["fat_copies"])
        sectors_per_fat = int(self.geometry["sectors_per_fat"])
        root_entries = int(self.geometry["root_entries"])
        sectors_per_cluster = int(self.geometry["sectors_per_cluster"])
        self.root_start = self.volume_base + (
            reserved + fat_copies * sectors_per_fat
        ) * self.sector_size
        self.root_size = root_entries * 32
        self.data_start = self.root_start + self.root_size
        self.cluster_size = sectors_per_cluster * self.sector_size
        fat_start = self.volume_base + reserved * self.sector_size
        self.fat = volume.read(fat_start, sectors_per_fat * self.sector_size)

    def cluster_chain(self, first: int) -> list[int]:
        result = []
        current = first
        seen = set()
        while 2 <= current < 0xFFF8:
            if current in seen:
                raise ValueError(f"FAT cluster loop at {current}")
            seen.add(current)
            result.append(current)
            current = struct.unpack_from("<H", self.fat, current * 2)[0]
        return result

    def cluster_offset(self, cluster: int) -> int:
        return self.data_start + (cluster - 2) * self.cluster_size

    def directory_chunks(self, first: int | None) -> list[tuple[int, bytes]]:
        if first is None:
            return [(self.root_start, self.volume.read(self.root_start, self.root_size))]
        return [
            (offset, self.volume.read(offset, self.cluster_size))
            for offset in (self.cluster_offset(cluster) for cluster in self.cluster_chain(first))
        ]

    def entries(self, first: int | None) -> list[LocatedEntry]:
        output = []
        lfn_entries: list[tuple[int, bytes]] = []
        for chunk_offset, data in self.directory_chunks(first):
            for within in range(0, len(data), 32):
                raw = data[within : within + 32]
                if len(raw) != 32 or raw[0] == 0:
                    return output
                if raw[0] == 0xE5:
                    lfn_entries.clear()
                    continue
                attributes = raw[11]
                if attributes == 0x0F:
                    lfn_entries.append((chunk_offset + within, raw))
                    continue
                if attributes & 0x08:
                    lfn_entries.clear()
                    continue
                output.append(
                    LocatedEntry(
                        short_name=decode_short_name(raw[:11]),
                        short_name_raw=bytes(raw[:11]),
                        long_name=decode_lfn([item[1] for item in lfn_entries]),
                        attributes=attributes,
                        first_cluster=struct.unpack_from("<H", raw, 26)[0],
                        size=struct.unpack_from("<I", raw, 28)[0],
                        directory_offset=chunk_offset + within,
                        lfn_offsets=tuple(item[0] for item in lfn_entries),
                    )
                )
                lfn_entries.clear()
        return output

    def resolve(self, path: str) -> LocatedEntry:
        components = [item for item in path.replace("/", "\\").split("\\") if item]
        if not components:
            raise ValueError("FAT path must not be empty")
        directory: int | None = None
        matched: LocatedEntry | None = None
        for index, component in enumerate(components):
            matched = next(
                (
                    entry
                    for entry in self.entries(directory)
                    if component.casefold()
                    in {entry.short_name.casefold(), (entry.long_name or "").casefold()}
                ),
                None,
            )
            if matched is None:
                raise FileNotFoundError(path)
            if index != len(components) - 1:
                if not matched.is_directory:
                    raise NotADirectoryError(component)
                directory = matched.first_cluster
        assert matched is not None
        return matched

    def read_file(self, entry: LocatedEntry) -> bytes:
        if entry.is_directory:
            raise IsADirectoryError(entry.long_name or entry.short_name)
        payload = b"".join(
            self.volume.read(self.cluster_offset(cluster), self.cluster_size)
            for cluster in self.cluster_chain(entry.first_cluster)
        )
        if len(payload) < entry.size:
            raise IOError("FAT chain is shorter than the directory size")
        return payload[: entry.size]


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def default_ecc_helper(repository: Path) -> Path:
    candidates = (
        repository / "work" / "tools" / "jz4740-ecc-x86_64.exe",
        repository / "work" / "rebuild" / "tools" / "jz4740-ecc-x86_64.exe",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return candidates[0]


def main() -> int:
    repository = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("path")
    parser.add_argument("replacement", type=Path)
    parser.add_argument("--scan-start-block", type=lambda value: int(value, 0), default=0x40)
    parser.add_argument(
        "--scan-end-block",
        type=lambda value: int(value, 0),
        help="exclusive physical FTL boundary; use 0x6F4 for the V2 A volume",
    )
    parser.add_argument(
        "--ecc-helper",
        type=Path,
        default=default_ecc_helper(repository),
    )
    parser.add_argument("--python-ecc", action="store_true")
    parser.add_argument("--in-place", action="store_true", required=True)
    args = parser.parse_args()

    image = args.image.resolve(strict=True)
    replacement_path = args.replacement.resolve(strict=True)
    replacement = replacement_path.read_bytes()
    helper = None if args.python_ecc else args.ecc_helper.resolve(strict=True)

    volume = LogicalVolume(
        image,
        args.scan_start_block,
        args.scan_end_block,
        writable=True,
    )
    try:
        resolver = FatResolver(volume)
        entry = resolver.resolve(args.path)
        if entry.is_directory:
            raise IsADirectoryError(args.path)
        chain = resolver.cluster_chain(entry.first_cluster)
        capacity = len(chain) * resolver.cluster_size
        if len(replacement) > capacity:
            raise ValueError(
                f"replacement requires {len(replacement)} bytes but existing chain holds {capacity}"
            )
        original = resolver.read_file(entry)
        padded = replacement + bytes(capacity - len(replacement))
        for index, cluster in enumerate(chain):
            start = index * resolver.cluster_size
            volume.write(
                resolver.cluster_offset(cluster),
                padded[start : start + resolver.cluster_size],
            )
        volume.write(entry.directory_offset + 28, struct.pack("<I", len(replacement)))
        write_report = volume.flush(helper)
        original_mapping_count = len(volume.result.mapping)
    finally:
        volume.close()

    check = LogicalVolume(image, args.scan_start_block, args.scan_end_block)
    try:
        checked_resolver = FatResolver(check)
        checked_entry = checked_resolver.resolve(args.path)
        readback = checked_resolver.read_file(checked_entry)
        if readback != replacement:
            raise IOError("replacement readback differs from input")
        if len(check.result.mapping) != original_mapping_count:
            raise IOError("FTL mapping count changed during in-place replacement")
    finally:
        check.close()

    report = {
        "format": "bbk-h1-in-place-fat-replacement-v1",
        "image_name": image.name,
        "path": args.path,
        "replacement_name": replacement_path.name,
        "original_bytes": len(original),
        "original_sha256": sha256(original),
        "replacement_bytes": len(replacement),
        "replacement_sha256": sha256(replacement),
        "chain_clusters": len(chain),
        "chain_capacity": capacity,
        "ftl_mapping_count": original_mapping_count,
        "scan_start_block": volume.result.scan_start_block,
        "scan_end_block": volume.result.scan_end_block,
        "write": write_report,
        "readback_verified": True,
    }
    print(json.dumps(report, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
