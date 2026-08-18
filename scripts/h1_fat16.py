#!/usr/bin/env python3
"""Plan a deterministic H1 FAT16 volume without materializing a disk image."""

from __future__ import annotations

import math
import re
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

BYTES_PER_SECTOR = 512
MEDIA_DESCRIPTOR = 0xF8
END_CLUSTER = 0xFFFF
LOGICAL_UNIT_SIZE = 256 * 1024


@dataclass(frozen=True)
class FatGeometry:
    boot_lba: int = 32
    bytes_per_sector: int = BYTES_PER_SECTOR
    sectors_per_cluster: int = 32
    reserved_sectors: int = 480
    fat_copies: int = 2
    root_entries: int = 512
    sectors_per_fat: int = 512
    hidden_sectors: int = 1
    total_sectors: int = 2_001_376

    @property
    def root_dir_sectors(self) -> int:
        return math.ceil(self.root_entries * 32 / self.bytes_per_sector)

    @property
    def first_data_sector(self) -> int:
        return (
            self.reserved_sectors
            + self.fat_copies * self.sectors_per_fat
            + self.root_dir_sectors
        )

    @property
    def cluster_size(self) -> int:
        return self.bytes_per_sector * self.sectors_per_cluster

    @property
    def cluster_count(self) -> int:
        return (self.total_sectors - self.first_data_sector) // self.sectors_per_cluster

    @property
    def disk_bytes(self) -> int:
        return (self.boot_lba + self.total_sectors) * self.bytes_per_sector

    def validate(self) -> None:
        if self.bytes_per_sector != BYTES_PER_SECTOR:
            raise ValueError("H1 requires 512-byte FAT sectors")
        if self.sectors_per_cluster not in {32, 64}:
            raise ValueError("H1 guest geometry requires 32 or 64 sectors per cluster")
        if not 4085 <= self.cluster_count <= 0xFFF5:
            raise ValueError(f"geometry is not FAT16-compatible: {self.cluster_count} clusters")
        if (self.cluster_count + 2) * 2 > self.sectors_per_fat * self.bytes_per_sector:
            raise ValueError("FAT table is too small for the data-cluster count")


@dataclass
class FsNode:
    name: str
    source: Path | None
    is_dir: bool
    size: int = 0
    short_name: bytes = b""
    first_cluster: int = 0
    cluster_count: int = 0
    parent_cluster: int = 0
    children: list["FsNode"] = field(default_factory=list)


@dataclass(frozen=True)
class Extent:
    start: int
    length: int
    name: str
    data: bytes | None = None
    source: Path | None = None

    @property
    def end(self) -> int:
        return self.start + self.length


@dataclass(frozen=True)
class FatPlan:
    geometry: FatGeometry
    root: FsNode
    extents: tuple[Extent, ...]
    used_clusters: int
    source_files: int
    source_directories: int
    source_bytes: int

    @property
    def free_clusters(self) -> int:
        return self.geometry.cluster_count - self.used_clusters


def fat_date_time() -> tuple[int, int]:
    date = ((2026 - 1980) << 9) | (1 << 5) | 1
    return date, 0


def sanitize_short_part(text: str, fallback: str) -> str:
    text = re.sub(r"[^A-Z0-9$%'-_@~`!(){}^#&]", "_", text.upper())
    return text.strip(" .") or fallback


def make_gbk_short_name(name: str, is_dir: bool) -> bytes | None:
    stem, dot, suffix = name.rpartition(".")
    if not dot or is_dir:
        stem, suffix = name, ""
    try:
        stem_bytes = stem.upper().encode("gbk")
        suffix_bytes = suffix.upper().encode("ascii") if suffix else b""
    except UnicodeEncodeError:
        return None
    invalid = set(b' "+,./:;<=>?[\\]|*')
    all_bytes = stem_bytes + suffix_bytes
    if (
        not stem_bytes
        or len(stem_bytes) > 8
        or len(suffix_bytes) > 3
        or not any(byte >= 0x80 for byte in stem_bytes)
        or any(byte < 0x20 or byte in invalid for byte in all_bytes)
    ):
        return None
    return stem_bytes.ljust(8, b" ") + suffix_bytes.ljust(3, b" ")


def make_short_name(name: str, used: set[bytes], is_dir: bool, index: int) -> bytes:
    gbk_plain = make_gbk_short_name(name, is_dir)
    if gbk_plain is not None and gbk_plain not in used:
        used.add(gbk_plain)
        return gbk_plain

    stem, dot, suffix = name.rpartition(".")
    if not dot or is_dir:
        stem, suffix = name, ""
    base = sanitize_short_part(stem, "DIR" if is_dir else "FILE")
    ext = sanitize_short_part(suffix, "")[:3]
    plain = (base[:8].ljust(8) + ext.ljust(3)).encode("ascii")
    valid_plain = name.upper() == (base[:8] + (("." + ext) if ext else ""))
    if valid_plain and plain not in used:
        used.add(plain)
        return plain

    for serial in range(1, 1000):
        tail = f"~{serial}"
        keep = max(1, 8 - len(tail))
        candidate = ((base[:keep] + tail)[:8].ljust(8) + ext.ljust(3)).encode("ascii")
        if candidate not in used:
            used.add(candidate)
            return candidate

    prefix = "D" if is_dir else "F"
    for serial in range(index, index + 100_000):
        candidate = (f"{prefix}{serial:06d}"[:8].ljust(8) + ext.ljust(3)).encode("ascii")
        if candidate not in used:
            used.add(candidate)
            return candidate
    raise RuntimeError(f"unable to allocate an 8.3 alias for {name!r}")


def read_node(path: Path, name: str) -> FsNode:
    if path.is_dir():
        node = FsNode(name=name, source=path, is_dir=True)
        entries = sorted(path.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower()))
        node.children = [read_node(child, child.name) for child in entries]
        return node
    return FsNode(name=name, source=path, is_dir=False, size=path.stat().st_size)


def iter_nodes(node: FsNode) -> Iterator[FsNode]:
    for child in node.children:
        yield child
        if child.is_dir:
            yield from iter_nodes(child)


def find_child(node: FsNode, name: str, *, directory: bool | None = None) -> FsNode | None:
    for child in node.children:
        if child.name == name and (directory is None or child.is_dir == directory):
            return child
    return None


def add_bbk_compat_aliases(root: FsNode) -> None:
    system = find_child(root, "系统", directory=True)
    if system is None or find_child(system, "SysTp.cfg") is not None:
        return
    data_dir = find_child(system, "数据", directory=True)
    if data_dir is None:
        return
    systp = find_child(data_dir, "SysTp.cfg", directory=False)
    if systp is not None and systp.source is not None:
        system.children.append(
            FsNode("SysTp.cfg", systp.source, is_dir=False, size=systp.size)
        )


def assign_short_names(node: FsNode) -> None:
    used: set[bytes] = set()
    for index, child in enumerate(sorted(node.children, key=lambda item: item.name.lower()), 1):
        child.short_name = make_short_name(child.name, used, child.is_dir, index)
        if child.is_dir:
            assign_short_names(child)


def build_tree(system_data_root: Path) -> tuple[FsNode, int, int, int]:
    source_root = system_data_root.resolve()
    if not source_root.is_dir():
        raise NotADirectoryError(source_root)
    children = sorted(source_root.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower()))
    root = FsNode(name="", source=None, is_dir=True)
    root.children = [read_node(child, child.name) for child in children]
    source_nodes = list(iter_nodes(root))
    source_files = sum(not node.is_dir for node in source_nodes)
    source_directories = sum(node.is_dir for node in source_nodes)
    source_bytes = sum(node.size for node in source_nodes if not node.is_dir)
    add_bbk_compat_aliases(root)
    assign_short_names(root)
    return root, source_files, source_directories, source_bytes


def lfn_checksum(short_name: bytes) -> int:
    total = 0
    for byte in short_name:
        total = (((total & 1) << 7) + (total >> 1) + byte) & 0xFF
    return total


def make_lfn_entries(name: str, checksum: int) -> list[bytes]:
    raw = name.encode("utf-16le")
    units = [raw[index] | (raw[index + 1] << 8) for index in range(0, len(raw), 2)]
    if len(units) > 255:
        raise ValueError(f"VFAT name exceeds 255 UTF-16 code units: {name!r}")
    chunks = [units[index : index + 13] for index in range(0, len(units), 13)] or [[]]
    entries: list[bytes] = []
    positions = (1, 3, 5, 7, 9, 14, 16, 18, 20, 22, 24, 28, 30)
    for disk_index, chunk in enumerate(reversed(chunks), 1):
        sequence = len(chunks) - disk_index + 1
        if disk_index == 1:
            sequence |= 0x40
        padded = list(chunk)
        if len(padded) < 13:
            padded.append(0)
        padded.extend([0xFFFF] * (13 - len(padded)))
        entry = bytearray(32)
        entry[0] = sequence
        entry[11] = 0x0F
        entry[13] = checksum
        for position, value in zip(positions, padded):
            struct.pack_into("<H", entry, position, value)
        entries.append(bytes(entry))
    return entries


def make_short_entry(node: FsNode) -> bytes:
    entry = bytearray(32)
    entry[0:11] = node.short_name
    entry[11] = 0x10 if node.is_dir else 0x20
    date, time = fat_date_time()
    for offset in (14, 22):
        struct.pack_into("<H", entry, offset, time)
    for offset in (16, 18, 24):
        struct.pack_into("<H", entry, offset, date)
    struct.pack_into("<H", entry, 26, node.first_cluster if node.is_dir or node.size else 0)
    struct.pack_into("<I", entry, 28, 0 if node.is_dir else node.size)
    return bytes(entry)


def make_dot_entry(name: bytes, cluster: int) -> bytes:
    node = FsNode("", None, True, short_name=name.ljust(11), first_cluster=cluster)
    return make_short_entry(node)


def directory_entries(node: FsNode, parent_cluster: int) -> bytes:
    entries: list[bytes] = []
    if node.first_cluster:
        entries.extend(
            (make_dot_entry(b".", node.first_cluster), make_dot_entry(b"..", parent_cluster))
        )
    for child in sorted(node.children, key=lambda item: item.name.lower()):
        entries.extend(make_lfn_entries(child.name, lfn_checksum(child.short_name)))
        entries.append(make_short_entry(child))
    return b"".join(entries) + b"\x00" * 32


def clusters_for_size(size: int, cluster_size: int) -> int:
    return math.ceil(size / cluster_size) if size else 0


def assign_clusters(root: FsNode, geometry: FatGeometry) -> int:
    next_cluster = 2
    for node in iter_nodes(root):
        size = len(directory_entries(node, 0)) if node.is_dir else node.size
        node.cluster_count = max(1, clusters_for_size(size, geometry.cluster_size)) if node.is_dir else clusters_for_size(size, geometry.cluster_size)
        if node.cluster_count:
            node.first_cluster = next_cluster
            next_cluster += node.cluster_count
    assign_parent_clusters(root, 0)
    return next_cluster - 2


def assign_parent_clusters(node: FsNode, parent_cluster: int) -> None:
    for child in node.children:
        child.parent_cluster = parent_cluster
        if child.is_dir:
            assign_parent_clusters(child, child.first_cluster)


def build_fat(root: FsNode, geometry: FatGeometry) -> bytes:
    fat = bytearray(geometry.sectors_per_fat * geometry.bytes_per_sector)
    struct.pack_into("<H", fat, 0, MEDIA_DESCRIPTOR | 0xFF00)
    struct.pack_into("<H", fat, 2, END_CLUSTER)
    for node in iter_nodes(root):
        for index in range(node.cluster_count):
            value = END_CLUSTER if index == node.cluster_count - 1 else node.first_cluster + index + 1
            struct.pack_into("<H", fat, (node.first_cluster + index) * 2, value)
    return bytes(fat)


def build_plan(
    system_data_root: Path,
    template_logical_zero: bytes,
    geometry: FatGeometry = FatGeometry(),
    root_volume_label_entry: bytes | None = None,
) -> FatPlan:
    geometry.validate()
    if len(template_logical_zero) != LOGICAL_UNIT_SIZE:
        raise ValueError("template logical unit zero must be exactly 256 KiB")
    boot_offset = geometry.boot_lba * geometry.bytes_per_sector
    boot = template_logical_zero[boot_offset : boot_offset + geometry.bytes_per_sector]
    if boot[510:512] != b"\x55\xAA":
        raise ValueError("template logical unit zero has no H1 FAT boot sector")

    root, source_files, source_directories, source_bytes = build_tree(system_data_root)
    used_clusters = assign_clusters(root, geometry)
    if used_clusters > geometry.cluster_count:
        required = used_clusters * geometry.cluster_size
        available = geometry.cluster_count * geometry.cluster_size
        raise ValueError(f"system tree needs {required} data bytes; FAT has {available}")

    volume_base = boot_offset
    fat_start = volume_base + geometry.reserved_sectors * geometry.bytes_per_sector
    root_start = volume_base + (
        geometry.reserved_sectors + geometry.fat_copies * geometry.sectors_per_fat
    ) * geometry.bytes_per_sector
    data_start = volume_base + geometry.first_data_sector * geometry.bytes_per_sector
    fat = build_fat(root, geometry)
    if root_volume_label_entry is not None:
        if len(root_volume_label_entry) != 32:
            raise ValueError("FAT root volume-label entry must be 32 bytes")
        attributes = root_volume_label_entry[11]
        if not attributes & 0x08 or attributes == 0x0F:
            raise ValueError("template FAT root entry is not a volume label")
    root_data = (root_volume_label_entry or b"") + directory_entries(root, 0)
    root_capacity = geometry.root_dir_sectors * geometry.bytes_per_sector
    if len(root_data) > root_capacity:
        raise ValueError(f"root directory needs {len(root_data)} bytes; capacity is {root_capacity}")

    extents: list[Extent] = [
        Extent(0, len(template_logical_zero), "guest MBR and boot-sector template", data=template_logical_zero)
    ]
    for copy in range(geometry.fat_copies):
        extents.append(Extent(fat_start + copy * len(fat), len(fat), f"FAT copy {copy + 1}", data=fat))
    extents.append(Extent(root_start, len(root_data), "FAT root directory", data=root_data))

    for node in iter_nodes(root):
        if not node.first_cluster:
            continue
        start = data_start + (node.first_cluster - 2) * geometry.cluster_size
        relative = node.source.name if node.source is not None else node.name
        if node.is_dir:
            payload = directory_entries(node, node.parent_cluster)
            extents.append(Extent(start, len(payload), f"directory {relative}", data=payload))
        else:
            if node.source is None:
                raise ValueError(f"file node has no source: {node.name}")
            extents.append(Extent(start, node.size, f"file {relative}", source=node.source))

    extents.sort(key=lambda extent: extent.start)
    for previous, current in zip(extents, extents[1:]):
        if previous.end > current.start:
            raise ValueError(f"planned extents overlap: {previous.name!r} and {current.name!r}")
    if extents[-1].end > geometry.disk_bytes:
        raise ValueError("planned data exceeds the guest-created FAT volume")
    return FatPlan(
        geometry=geometry,
        root=root,
        extents=tuple(extents),
        used_clusters=used_clusters,
        source_files=source_files,
        source_directories=source_directories,
        source_bytes=source_bytes,
    )


def iter_logical_units(
    plan: FatPlan, *, map_zero_units_through_used: bool = False
) -> Iterator[tuple[int, bytes]]:
    extents = plan.extents
    extent_index = 0
    active_source: Path | None = None
    active_stream = None
    try:
        unit_count = math.ceil(
            (extents[-1].end if map_zero_units_through_used else plan.geometry.disk_bytes)
            / LOGICAL_UNIT_SIZE
        )
        for logical in range(unit_count):
            unit_start = logical * LOGICAL_UNIT_SIZE
            unit_end = unit_start + LOGICAL_UNIT_SIZE
            while extent_index < len(extents) and extents[extent_index].end <= unit_start:
                extent_index += 1
            index = extent_index
            if (
                not map_zero_units_through_used
                and (index >= len(extents) or extents[index].start >= unit_end)
            ):
                continue
            output = bytearray(LOGICAL_UNIT_SIZE)
            while index < len(extents) and extents[index].start < unit_end:
                extent = extents[index]
                overlap_start = max(unit_start, extent.start)
                overlap_end = min(unit_end, extent.end)
                source_offset = overlap_start - extent.start
                target_offset = overlap_start - unit_start
                length = overlap_end - overlap_start
                if extent.data is not None:
                    chunk = extent.data[source_offset : source_offset + length]
                else:
                    if extent.source is None:
                        raise ValueError(f"extent has no content: {extent.name}")
                    if active_source != extent.source:
                        if active_stream is not None:
                            active_stream.close()
                        active_source = extent.source
                        active_stream = extent.source.open("rb")
                    active_stream.seek(source_offset)
                    chunk = active_stream.read(length)
                if len(chunk) != length:
                    raise IOError(f"short source read for {extent.name}: wanted {length}, got {len(chunk)}")
                output[target_offset : target_offset + length] = chunk
                index += 1
            if map_zero_units_through_used or any(output):
                yield logical, bytes(output)
    finally:
        if active_stream is not None:
            active_stream.close()


def node_relative_path(node: FsNode, source_root: Path) -> str:
    if node.source is None:
        return node.name
    try:
        return str(node.source.resolve().relative_to(source_root.resolve()))
    except ValueError:
        return node.name
