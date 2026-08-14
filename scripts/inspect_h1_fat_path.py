#!/usr/bin/env python3
"""Resolve a FAT path directly through the H1 NAND FTL mapping."""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
from dataclasses import dataclass
from pathlib import Path

from h1_ftl import LOGICAL_UNIT_SIZE, fat_geometry, read_logical_unit, scan_image


@dataclass(frozen=True)
class Entry:
    short_raw: bytes
    short_name: str
    long_name: str | None
    attributes: int
    first_cluster: int
    size: int

    @property
    def is_directory(self) -> bool:
        return bool(self.attributes & 0x10)


class LogicalReader:
    def __init__(self, image: Path, scan_start_block: int) -> None:
        self.result = scan_image(image, scan_start_block)
        self.stream = image.open("rb")

    def close(self) -> None:
        self.stream.close()

    def read(self, offset: int, size: int) -> bytes:
        output = bytearray()
        while size:
            logical = offset // LOGICAL_UNIT_SIZE
            within = offset % LOGICAL_UNIT_SIZE
            count = min(size, LOGICAL_UNIT_SIZE - within)
            unit = read_logical_unit(self.stream, self.result.mapping.get(logical))
            output.extend(unit[within : within + count])
            offset += count
            size -= count
        return bytes(output)


def decode_short_name(raw: bytes) -> str:
    stem = raw[:8].rstrip(b" ").decode("gbk", errors="replace")
    suffix = raw[8:11].rstrip(b" ").decode("gbk", errors="replace")
    return stem + (("." + suffix) if suffix else "")


def decode_lfn(entries: list[bytes]) -> str | None:
    if not entries:
        return None
    units: dict[int, list[int]] = {}
    positions = (1, 3, 5, 7, 9, 14, 16, 18, 20, 22, 24, 28, 30)
    for entry in entries:
        sequence = entry[0] & 0x1F
        units[sequence] = [struct.unpack_from("<H", entry, offset)[0] for offset in positions]
    values = []
    for sequence in sorted(units):
        values.extend(units[sequence])
    values = [value for value in values if value not in {0x0000, 0xFFFF}]
    try:
        return b"".join(struct.pack("<H", value) for value in values).decode("utf-16le")
    except UnicodeDecodeError:
        return None


def parse_directory(data: bytes) -> list[Entry]:
    output = []
    lfn_entries: list[bytes] = []
    for offset in range(0, len(data), 32):
        raw = data[offset : offset + 32]
        if len(raw) != 32 or raw[0] == 0:
            break
        if raw[0] == 0xE5:
            lfn_entries.clear()
            continue
        attributes = raw[11]
        if attributes == 0x0F:
            lfn_entries.append(raw)
            continue
        if attributes & 0x08:
            lfn_entries.clear()
            continue
        short_raw = raw[:11]
        output.append(
            Entry(
                short_raw=short_raw,
                short_name=decode_short_name(short_raw),
                long_name=decode_lfn(lfn_entries),
                attributes=attributes,
                first_cluster=struct.unpack_from("<H", raw, 26)[0],
                size=struct.unpack_from("<I", raw, 28)[0],
            )
        )
        lfn_entries.clear()
    return output


def entry_report(entry: Entry) -> dict[str, object]:
    return {
        "short_name": entry.short_name,
        "short_raw_hex": entry.short_raw.hex(" ").upper(),
        "long_name": entry.long_name,
        "attributes": f"0x{entry.attributes:02X}",
        "directory": entry.is_directory,
        "first_cluster": entry.first_cluster,
        "size": entry.size,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("path")
    parser.add_argument("--scan-start-block", type=lambda value: int(value, 0), default=0x40)
    parser.add_argument("--list", action="store_true", help="include every entry in traversed directories")
    parser.add_argument("--extract", type=Path, help="extract the resolved file payload")
    args = parser.parse_args()

    reader = LogicalReader(args.image, args.scan_start_block)
    try:
        logical_zero = reader.read(0, LOGICAL_UNIT_SIZE)
        geometry = fat_geometry(logical_zero)
        sector_size = int(geometry["bytes_per_sector"])
        volume_base = int(geometry["boot_lba"]) * sector_size
        reserved = int(geometry["reserved_sectors"])
        fat_copies = int(geometry["fat_copies"])
        sectors_per_fat = int(geometry["sectors_per_fat"])
        root_entries = int(geometry["root_entries"])
        sectors_per_cluster = int(geometry["sectors_per_cluster"])
        root_start = volume_base + (reserved + fat_copies * sectors_per_fat) * sector_size
        root_size = root_entries * 32
        data_start = root_start + root_size
        cluster_size = sectors_per_cluster * sector_size
        fat_start = volume_base + reserved * sector_size
        fat = reader.read(fat_start, sectors_per_fat * sector_size)

        def cluster_chain(first: int) -> list[int]:
            result = []
            current = first
            seen = set()
            while 2 <= current < 0xFFF8:
                if current in seen:
                    raise ValueError(f"FAT cluster loop at {current}")
                seen.add(current)
                result.append(current)
                current = struct.unpack_from("<H", fat, current * 2)[0]
            return result

        def directory_data(first: int | None) -> bytes:
            if first is None:
                return reader.read(root_start, root_size)
            return b"".join(
                reader.read(data_start + (cluster - 2) * cluster_size, cluster_size)
                for cluster in cluster_chain(first)
            )

        components = [item for item in args.path.replace("/", "\\").split("\\") if item]
        current_cluster: int | None = None
        traversed = []
        matched: Entry | None = None
        for index, component in enumerate(components):
            entries = parse_directory(directory_data(current_cluster))
            matched = next(
                (
                    entry
                    for entry in entries
                    if component.casefold()
                    in {entry.short_name.casefold(), (entry.long_name or "").casefold()}
                ),
                None,
            )
            row: dict[str, object] = {
                "component": component,
                "directory_cluster": current_cluster,
                "matched": entry_report(matched) if matched else None,
            }
            if args.list:
                row["entries"] = [entry_report(entry) for entry in entries]
            traversed.append(row)
            if matched is None:
                break
            if index != len(components) - 1:
                if not matched.is_directory:
                    break
                current_cluster = matched.first_cluster

        resolved = bool(components) and len(traversed) == len(components) and matched is not None
        report: dict[str, object] = {
            "format": "bbk-h1-fat-path-v1",
            "path": args.path,
            "resolved": resolved,
            "geometry": geometry,
            "traversed": traversed,
        }
        if args.extract:
            if not resolved or matched is None or matched.is_directory:
                raise ValueError("--extract requires a resolved file path")
            payload = b"".join(
                reader.read(data_start + (cluster - 2) * cluster_size, cluster_size)
                for cluster in cluster_chain(matched.first_cluster)
            )[: matched.size]
            if len(payload) != matched.size:
                raise IOError("resolved FAT file chain is shorter than its directory size")
            args.extract.parent.mkdir(parents=True, exist_ok=True)
            args.extract.write_bytes(payload)
            report["extraction"] = {
                "output_name": args.extract.name,
                "bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest().upper(),
            }
        print(json.dumps(report, ensure_ascii=True, indent=2))
    finally:
        reader.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
