#!/usr/bin/env python3
"""Add V1 Mission DataLib assets to a copied V2 NAND image.

The V1 Mission payload addresses DataLibIndex.dat records by their fixed
12-byte ID slot.  This tool keeps the original IDs 0x2711..0x2717 but packs
only those chunks by default.  ``--full`` instead copies both original files
without repacking, which is useful while discovering indirect resource IDs.
The files are appended below A:\\应用\\数据\\游戏\\LYXZ.  The tool writes a
new image and never mutates the template image in place.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import struct
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from build_h1_system_nand import EccEncoder, write_mapped_unit  # noqa: E402
from h1_ftl import (  # noqa: E402
    LOGICAL_UNIT_SIZE,
    PAGES_PER_FTL_UNIT,
    fat_geometry,
    read_logical_unit,
    scan_image,
)
from inspect_h1_fat_path import decode_lfn, decode_short_name  # noqa: E402


PAGE_SIZE = 2048
SELECTED_IDS = tuple(range(0x2711, 0x2718))
LFN_POSITIONS = (1, 3, 5, 7, 9, 14, 16, 18, 20, 22, 24, 28, 30)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


class LogicalVolume:
    """Read/write logical FTL units, allocating free slots when needed."""

    def __init__(self, image: Path, scan_start_block: int, writable: bool) -> None:
        self.image = image
        self.result = scan_image(image, scan_start_block)
        self.stream = image.open("r+b" if writable else "rb", buffering=0)
        self.cache: dict[int, bytearray] = {}
        self.records = dict(self.result.mapping)
        self.dirty: set[int] = set()
        bbt = [r for r in self.result.records if r.kind == "bbt"]
        allocation_start = max((r.physical_block for r in bbt), default=scan_start_block)
        self.free_records = iter(
            r
            for r in self.result.records
            if r.kind == "free" and r.physical_block >= allocation_start
        )

    def close(self) -> None:
        self.stream.close()

    def _ensure_record(self, logical: int):
        record = self.records.get(logical)
        if record is None:
            try:
                record = next(self.free_records)
            except StopIteration as error:
                raise RuntimeError(f"no free FTL slot for logical unit {logical}") from error
            self.records[logical] = record
        return record

    def unit(self, logical: int) -> bytearray:
        if logical not in self.cache:
            record = self.records.get(logical)
            self.cache[logical] = bytearray(read_logical_unit(self.stream, record))
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
        position = 0
        while position < len(data):
            logical = offset // LOGICAL_UNIT_SIZE
            within = offset % LOGICAL_UNIT_SIZE
            count = min(len(data) - position, LOGICAL_UNIT_SIZE - within)
            self._ensure_record(logical)
            unit = self.unit(logical)
            unit[within : within + count] = data[position : position + count]
            self.dirty.add(logical)
            offset += count
            position += count

    def flush(self, helper: Path | None, sequence: int) -> dict[str, object]:
        programmed_pages = 0
        with EccEncoder(helper) as encoder:
            for logical in sorted(self.dirty):
                programmed_pages += write_mapped_unit(
                    self.stream,
                    self.records[logical],
                    logical,
                    bytes(self.cache[logical]),
                    sequence,
                    encoder,
                )
        self.stream.flush()
        self.stream.close()
        return {
            "logical_units": sorted(self.dirty),
            "mapped_logical_units_added": sum(
                logical not in self.result.mapping for logical in self.dirty
            ),
            "programmed_pages": programmed_pages,
            "sequence": sequence & 0xFFFF,
        }


@dataclass(frozen=True)
class FatEntry:
    short_name: str
    short_raw: bytes
    long_name: str | None
    attributes: int
    first_cluster: int
    size: int
    offset: int

    @property
    def is_directory(self) -> bool:
        return bool(self.attributes & 0x10)


class FatTree:
    def __init__(self, volume: LogicalVolume) -> None:
        self.volume = volume
        geometry = fat_geometry(volume.read(0, LOGICAL_UNIT_SIZE))
        self.sector_size = int(geometry["bytes_per_sector"])
        self.boot_lba = int(geometry["boot_lba"])
        self.reserved = int(geometry["reserved_sectors"])
        self.fat_copies = int(geometry["fat_copies"])
        self.sectors_per_fat = int(geometry["sectors_per_fat"])
        self.root_entries = int(geometry["root_entries"])
        self.sectors_per_cluster = int(geometry["sectors_per_cluster"])
        self.total_sectors = int(geometry["total_sectors"])
        self.volume_base = self.boot_lba * self.sector_size
        self.fat_start = self.volume_base + self.reserved * self.sector_size
        self.root_start = self.volume_base + (
            self.reserved + self.fat_copies * self.sectors_per_fat
        ) * self.sector_size
        self.root_size = self.root_entries * 32
        self.data_start = self.root_start + self.root_size
        self.cluster_size = self.sectors_per_cluster * self.sector_size
        self.fat_size = self.sectors_per_fat * self.sector_size
        self.fat = bytearray(volume.read(self.fat_start, self.fat_size))
        self.cluster_count = (self.total_sectors * self.sector_size - self.data_start) // self.cluster_size

    def cluster_offset(self, cluster: int) -> int:
        if cluster < 2 or cluster >= self.cluster_count + 2:
            raise ValueError(f"cluster outside FAT data area: {cluster}")
        return self.data_start + (cluster - 2) * self.cluster_size

    def fat_value(self, cluster: int) -> int:
        return struct.unpack_from("<H", self.fat, cluster * 2)[0]

    def set_fat_value(self, cluster: int, value: int) -> None:
        struct.pack_into("<H", self.fat, cluster * 2, value & 0xFFFF)

    def chain(self, first_cluster: int) -> list[int]:
        result = []
        current = first_cluster
        seen: set[int] = set()
        while 2 <= current < 0xFFF8:
            if current in seen:
                raise ValueError(f"FAT cluster loop at {current}")
            seen.add(current)
            result.append(current)
            current = self.fat_value(current)
        return result

    def directory_offsets(self, first_cluster: int | None) -> list[int]:
        if first_cluster is None:
            return [self.root_start + offset for offset in range(0, self.root_size, self.cluster_size)]
        return [self.cluster_offset(c) for c in self.chain(first_cluster)]

    def entries(self, first_cluster: int | None) -> list[FatEntry]:
        result: list[FatEntry] = []
        lfn: list[bytes] = []
        for base in self.directory_offsets(first_cluster):
            data = self.volume.read(base, self.cluster_size)
            for within in range(0, len(data), 32):
                raw = data[within : within + 32]
                if raw[0] == 0:
                    return result
                if raw[0] == 0xE5:
                    lfn.clear()
                    continue
                if raw[11] == 0x0F:
                    lfn.append(raw)
                    continue
                if raw[11] & 0x08:
                    lfn.clear()
                    continue
                result.append(
                    FatEntry(
                        short_name=decode_short_name(raw[:11]),
                        short_raw=bytes(raw[:11]),
                        long_name=decode_lfn(lfn),
                        attributes=raw[11],
                        first_cluster=struct.unpack_from("<H", raw, 26)[0],
                        size=struct.unpack_from("<I", raw, 28)[0],
                        offset=base + within,
                    )
                )
                lfn.clear()
        return result

    def resolve(self, path: str) -> FatEntry:
        components = [part for part in path.replace("/", "\\").split("\\") if part]
        if not components:
            raise ValueError("empty FAT path")
        current: int | None = None
        entry: FatEntry | None = None
        for index, component in enumerate(components):
            entry = next(
                (
                    item
                    for item in self.entries(current)
                    if component.casefold()
                    in {item.short_name.casefold(), (item.long_name or "").casefold()}
                ),
                None,
            )
            if entry is None:
                raise FileNotFoundError(path)
            if index != len(components) - 1:
                if not entry.is_directory:
                    raise NotADirectoryError(component)
                current = entry.first_cluster
        assert entry is not None
        return entry

    def read_file(self, entry: FatEntry) -> bytes:
        if entry.is_directory:
            raise IsADirectoryError(entry.short_name)
        return b"".join(
            self.volume.read(self.cluster_offset(cluster), self.cluster_size)
            for cluster in self.chain(entry.first_cluster)
        )[: entry.size]

    def write_fat(self) -> None:
        for copy in range(self.fat_copies):
            start = self.fat_start + copy * self.fat_size
            self.volume.write(start, bytes(self.fat))

    def free_clusters(self) -> list[int]:
        return [
            cluster
            for cluster in range(2, self.cluster_count + 2)
            if self.fat_value(cluster) == 0
        ]

    def allocate_chain(self, free: list[int], count: int) -> list[int]:
        if count <= 0:
            raise ValueError("FAT allocation count must be positive")
        if len(free) < count:
            raise RuntimeError(f"FAT has only {len(free)} free clusters, needs {count}")
        chain = free[:count]
        del free[:count]
        for index, cluster in enumerate(chain):
            self.set_fat_value(cluster, chain[index + 1] if index + 1 < len(chain) else 0xFFFF)
        return chain

    def write_chain(self, chain: list[int], data: bytes) -> None:
        capacity = len(chain) * self.cluster_size
        if len(data) > capacity:
            raise ValueError("data exceeds allocated FAT chain")
        padded = data + bytes(capacity - len(data))
        for index, cluster in enumerate(chain):
            start = index * self.cluster_size
            self.volume.write(self.cluster_offset(cluster), padded[start : start + self.cluster_size])

    def find_free_slots(self, first_cluster: int, count: int) -> int:
        for base in self.directory_offsets(first_cluster):
            data = self.volume.read(base, self.cluster_size)
            for within in range(0, self.cluster_size - count * 32 + 1, 32):
                if all(data[within + n * 32] in (0x00, 0xE5) for n in range(count)):
                    return base + within
        raise RuntimeError(f"directory cluster {first_cluster} has no {count}-entry free run")

    def put_entries(self, first_cluster: int, entries: list[bytes]) -> None:
        offset = self.find_free_slots(first_cluster, len(entries))
        self.volume.write(offset, b"".join(entries))


def short_entry(raw: bytes, attributes: int, first_cluster: int, size: int = 0) -> bytes:
    if len(raw) != 11:
        raise ValueError("FAT short name must be 11 bytes")
    entry = bytearray(32)
    entry[:11] = raw
    entry[11] = attributes
    struct.pack_into("<H", entry, 26, first_cluster)
    struct.pack_into("<I", entry, 28, size)
    return bytes(entry)


def lfn_checksum(short_raw: bytes) -> int:
    value = 0
    for byte in short_raw:
        value = ((value & 1) << 7) + (value >> 1) + byte
        value &= 0xFF
    return value


def lfn_entries(name: str, short_raw: bytes) -> list[bytes]:
    units = list(struct.unpack(f"<{len(name)}H", name.encode("utf-16le")))
    chunks = [units[index : index + 13] for index in range(0, len(units), 13)]
    checksum = lfn_checksum(short_raw)
    output: list[bytes] = []
    for index in reversed(range(len(chunks))):
        values = list(chunks[index])
        if index == len(chunks) - 1:
            values.append(0)
        values.extend([0xFFFF] * (13 - len(values)))
        raw = bytearray(32)
        sequence = index + 1
        if index == len(chunks) - 1:
            sequence |= 0x40
        raw[0] = sequence
        raw[11] = 0x0F
        raw[13] = checksum
        for value, offset in zip(values, LFN_POSITIONS):
            struct.pack_into("<H", raw, offset, value)
        output.append(bytes(raw))
    return output


def dot_entries(self_cluster: int, parent_cluster: int) -> list[bytes]:
    dot = b"." + b" " * 10
    dotdot = b".." + b" " * 9
    return [
        short_entry(dot, 0x10, self_cluster),
        short_entry(dotdot, 0x10, parent_cluster),
    ]


def read_v1_file(image: Path, path: str, scan_start_block: int) -> tuple[bytes, FatEntry]:
    volume = LogicalVolume(image, scan_start_block, writable=False)
    try:
        tree = FatTree(volume)
        entry = tree.resolve(path)
        return tree.read_file(entry), entry
    finally:
        volume.close()


def pack_assets(v1_image: Path, scan_start_block: int) -> tuple[bytes, bytes, dict[str, object]]:
    index_raw, index_entry = read_v1_file(
        v1_image,
        "应用\\数据\\游戏\\LYXZ\\DataLibIndex.dat",
        scan_start_block,
    )
    index = bytearray(index_raw)
    data_volume = LogicalVolume(v1_image, scan_start_block, writable=False)
    try:
        data_tree = FatTree(data_volume)
        data_entry = data_tree.resolve("应用\\数据\\游戏\\LYXZ\\DataLib.dat")
        data_chain = data_tree.chain(data_entry.first_cluster)
        records = {
            record_id: struct.unpack_from("<HHII", index, (record_id - 1) * 12)
            for record_id in SELECTED_IDS
        }
        packed = bytearray()
        selected_report = []
        for record_id in SELECTED_IDS:
            observed_id, record_type, offset, size = records[record_id]
            if observed_id != record_id or size == 0:
                raise ValueError(f"V1 index has no usable record 0x{record_id:04X}")
            if offset + size > data_entry.size:
                raise ValueError(f"V1 DataLib record 0x{record_id:04X} exceeds file size")
            remaining = size
            cursor = offset
            chunk = bytearray()
            while remaining:
                cluster_index, within_cluster = divmod(cursor, data_tree.cluster_size)
                if cluster_index >= len(data_chain):
                    raise ValueError("V1 DataLib chain is shorter than its directory size")
                take = min(remaining, data_tree.cluster_size - within_cluster)
                chunk.extend(
                    data_volume.read(
                        data_tree.cluster_offset(data_chain[cluster_index]) + within_cluster,
                        take,
                    )
                )
                cursor += take
                remaining -= take
            packed_offset = len(packed)
            packed.extend(chunk)
            struct.pack_into(
                "<HHII",
                index,
                (record_id - 1) * 12,
                record_id,
                record_type,
                packed_offset,
                size,
            )
            selected_report.append(
                {
                    "id": f"0x{record_id:04X}",
                    "type": record_type,
                    "source_offset": offset,
                    "bytes": size,
                    "packed_offset": packed_offset,
                    "sha256": sha256(bytes(chunk)),
                }
            )
    finally:
        data_volume.close()
    return bytes(index), bytes(packed), {
        "mode": "compact",
        "index_source_bytes": len(index),
        "index_source_sha256": sha256(index_raw),
        "data_source_bytes": data_entry.size,
        "data_source_sha256": None,
        "selected": selected_report,
        "packed_index_bytes": len(index),
        "packed_data_bytes": len(packed),
        "packed_data_sha256": sha256(bytes(packed)),
        "index_entry": index_entry.size,
    }


def copy_full_assets(
    v1_image: Path,
    scan_start_block: int,
) -> tuple[bytes, bytes, dict[str, object]]:
    index_data, index_entry = read_v1_file(
        v1_image,
        "应用\\数据\\游戏\\LYXZ\\DataLibIndex.dat",
        scan_start_block,
    )
    data_data, data_entry = read_v1_file(
        v1_image,
        "应用\\数据\\游戏\\LYXZ\\DataLib.dat",
        scan_start_block,
    )
    return index_data, data_data, {
        "mode": "full",
        "index_source_bytes": len(index_data),
        "index_source_sha256": sha256(index_data),
        "data_source_bytes": len(data_data),
        "data_source_sha256": sha256(data_data),
        "selected": "all",
        "packed_index_bytes": len(index_data),
        "packed_data_bytes": len(data_data),
        "packed_data_sha256": sha256(data_data),
        "index_entry": index_entry.size,
        "data_entry": data_entry.size,
    }


def default_ecc_helper() -> Path:
    return ROOT / "work" / "rebuild" / "tools" / "jz4740-ecc-x86_64.exe"


def install_assets(
    template: Path,
    output: Path,
    v1_image: Path,
    scan_start_block: int,
    helper: Path | None,
    full: bool = False,
) -> dict[str, object]:
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise FileExistsError(f"refusing to overwrite existing output: {output}")
    shutil.copyfile(template, output)
    asset_reader = copy_full_assets if full else pack_assets
    index_data, data_data, pack_report = asset_reader(v1_image, scan_start_block)

    volume = LogicalVolume(output, scan_start_block, writable=True)
    try:
        tree = FatTree(volume)
        free = tree.free_clusters()
        chains: dict[str, list[int]] = {}
        app_cluster = tree.resolve("应用").first_cluster
        data_cluster = tree.resolve("应用\\数据").first_cluster
        game_cluster = tree.resolve("应用\\数据\\游戏").first_cluster
        try:
            lyxz_cluster = tree.resolve("应用\\数据\\游戏\\LYXZ").first_cluster
        except FileNotFoundError:
            chains["LYXZ"] = tree.allocate_chain(free, 1)
            lyxz_cluster = chains["LYXZ"][0]
            tree.put_entries(
                game_cluster,
                [short_entry(b"LYXZ" + b" " * 7, 0x10, lyxz_cluster)],
            )
            tree.put_entries(lyxz_cluster, dot_entries(lyxz_cluster, game_cluster))
        for name, payload in (
            ("DataLibIndex.dat", index_data),
            ("DataLib.dat", data_data),
        ):
            count = max(1, (len(payload) + tree.cluster_size - 1) // tree.cluster_size)
            chains[name] = tree.allocate_chain(free, count)
        index_short = b"DATALI~1DAT"
        data_short = b"DATALIB DAT"
        try:
            tree.resolve("应用\\数据\\游戏\\LYXZ\\DataLibIndex.dat")
            raise FileExistsError("DataLibIndex.dat already exists in target LYXZ directory")
        except FileNotFoundError:
            pass
        tree.put_entries(
            lyxz_cluster,
            lfn_entries("DataLibIndex.dat", index_short)
            + [short_entry(index_short, 0x20, chains["DataLibIndex.dat"][0], len(index_data))]
            + [short_entry(data_short, 0x20, chains["DataLib.dat"][0], len(data_data))],
        )
        tree.write_chain(chains["DataLibIndex.dat"], index_data)
        tree.write_chain(chains["DataLib.dat"], data_data)
        tree.write_fat()
        current_sequences = [r.sequence or 0 for r in volume.result.mapping.values()]
        sequence = ((max(current_sequences) if current_sequences else 0) + 1) & 0xFFFF
        if sequence == 0:
            sequence = 1
        write_report = volume.flush(helper, sequence)
    except Exception:
        volume.close()
        raise

    check = LogicalVolume(output, scan_start_block, writable=False)
    try:
        checked_tree = FatTree(check)
        expected_files = {
            "应用\\数据\\游戏\\LYXZ\\DataLibIndex.dat": index_data,
            "应用\\数据\\游戏\\LYXZ\\DataLib.dat": data_data,
        }
        readback = {}
        for path, expected in expected_files.items():
            entry = checked_tree.resolve(path)
            observed = checked_tree.read_file(entry)
            if observed != expected:
                raise IOError(f"readback mismatch for {path}")
            readback[path] = {
                "bytes": len(observed),
                "sha256": sha256(observed),
                "first_cluster": entry.first_cluster,
            }
        scan_after = check.result
        report = {
            "format": "h1-v1-game-assets-on-v2-nand-v2",
            "template_name": template.name,
            "output_name": output.name,
            "v1_image_name": v1_image.name,
            "paths": list(expected_files),
            "pack": pack_report,
            "chains": {name: {"first": values[0], "clusters": len(values)} for name, values in chains.items()},
            "write": write_report,
            "readback": readback,
            "ftl_mapped_logical_units": len(scan_after.mapping),
            "ftl_max_logical_unit": max(scan_after.mapping),
            "fat_free_clusters_after": len(checked_tree.free_clusters()),
        }
    finally:
        check.close()
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--v1-image", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--scan-start-block", type=lambda value: int(value, 0), default=0x40)
    parser.add_argument("--ecc-helper", type=Path, default=default_ecc_helper())
    parser.add_argument("--python-ecc", action="store_true")
    parser.add_argument(
        "--full",
        action="store_true",
        help="copy the complete V1 DataLib files instead of packing known startup IDs",
    )
    args = parser.parse_args()
    report = install_assets(
        args.template.resolve(strict=True),
        args.output.resolve(),
        args.v1_image.resolve(strict=True),
        args.scan_start_block,
        None if args.python_ecc else args.ecc_helper.resolve(strict=True),
        args.full,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
