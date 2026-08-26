#!/usr/bin/env python3
"""Build a BBK @ibox H2L V2.2 eMMC image without loop devices or mounts.

The layout follows the H2 reverse-engineering notes and the public-domain
``eebbk_tools/process_4750l.py`` reference implementation.  Packet payloads
are copied directly from packet1.dat/packet2.dat so the roughly 1 GiB source
tree is never expanded on the host.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import struct
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from h1_fat16 import (
    END_CLUSTER,
    FsNode,
    assign_clusters,
    assign_short_names,
    build_fat,
    directory_entries,
    iter_nodes,
)


SECTOR_SIZE = 512
IMAGE_SIZE = 2 * 1024 * 1024 * 1024
IMAGE_SECTORS = IMAGE_SIZE // SECTOR_SIZE
PACKET_MAGIC = 0x2E6B6262
PACKET_HEADER_SIZE = 16
PACKET_ENTRY_SIZE = 0x100
XOR_OFFSET = 0x800561F0 - 0x80004000
XOR_SIZE = 0x1000
ERASE_CHUNK_SIZE = 8 * 1024 * 1024
COPY_CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True)
class RawSegment:
    name: str
    source_name: str
    offset: int


RAW_SEGMENTS = (
    RawSegment("first-stage", "data0_L.dat", 0x00000000),
    RawSegment("kernel-a", "data2_L.dat", 0x00180000),
    RawSegment("classic-os-a", "data3_L.dat", 0x00400000),
    RawSegment("cartoon-os-a", "data4_L.dat", 0x00C80000),
    RawSegment("kernel-b", "data2_L.dat", 0x01080000),
    RawSegment("classic-os-b", "data3_L.dat", 0x01300000),
    RawSegment("cartoon-os-b", "data4_L.dat", 0x01B80000),
)


@dataclass(frozen=True)
class PartitionSpec:
    name: str
    packet_name: str
    start_sector: int
    total_sectors: int
    label: str


PARTITIONS = (
    PartitionSpec("system", "packet1.dat", 0x0000F400, 0x000DEC00 - 0x0000F400, "H2 V2.2L"),
    PartitionSpec("user", "packet2.dat", 0x000DEC00, (2048 - 446) * 2048, "@ibox H2"),
)


@dataclass(frozen=True)
class FatGeometry:
    total_sectors: int
    bytes_per_sector: int = SECTOR_SIZE
    sectors_per_cluster: int = 64
    reserved_sectors: int = 64
    fat_copies: int = 2
    root_entries: int = 512
    sectors_per_fat: int = 0
    sectors_per_track: int = 32
    heads: int = 64
    hidden_sectors: int = 1

    @property
    def root_dir_sectors(self) -> int:
        return math.ceil(self.root_entries * 32 / SECTOR_SIZE)

    @property
    def first_data_sector(self) -> int:
        return self.reserved_sectors + self.fat_copies * self.sectors_per_fat + self.root_dir_sectors

    @property
    def cluster_size(self) -> int:
        return self.sectors_per_cluster * SECTOR_SIZE

    @property
    def cluster_count(self) -> int:
        return (self.total_sectors - self.first_data_sector) // self.sectors_per_cluster


@dataclass(frozen=True)
class PacketEntry:
    size: int
    packet_offset: int
    path: str


@dataclass(frozen=True)
class PacketIndex:
    path: Path
    header: tuple[int, int, int, int]
    entries: tuple[PacketEntry, ...]


@dataclass(frozen=True)
class FileBinding:
    node: FsNode
    entry: PacketEntry


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(COPY_CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest().upper()


def read_exact(stream, length: int, description: str) -> bytes:
    data = stream.read(length)
    if len(data) != length:
        raise IOError(f"short read for {description}: expected {length}, got {len(data)}")
    return data


def decode_data_file(path: Path, xor_pattern: bytes) -> bytes:
    encoded = path.read_bytes()
    if len(encoded) <= PACKET_HEADER_SIZE:
        raise ValueError(f"encrypted image is too short: {path.name}")
    payload = encoded[PACKET_HEADER_SIZE:]
    return bytes(value ^ xor_pattern[index % len(xor_pattern)] for index, value in enumerate(payload))


def parse_packet(path: Path) -> PacketIndex:
    packet_size = path.stat().st_size
    with path.open("rb") as stream:
        raw_header = read_exact(stream, PACKET_HEADER_SIZE, f"{path.name} global header")
        header = struct.unpack("<4I", raw_header)
        if header[0] != PACKET_MAGIC:
            raise ValueError(f"{path.name}: bad packet magic 0x{header[0]:08X}")
        count = header[2]
        if count > 100_000:
            raise ValueError(f"{path.name}: unreasonable entry count {count}")
        index_end = PACKET_HEADER_SIZE + count * PACKET_ENTRY_SIZE
        entries: list[PacketEntry] = []
        ranges: list[tuple[int, int, str]] = []
        seen_paths: set[str] = set()
        for entry_index in range(count):
            raw = read_exact(stream, PACKET_ENTRY_SIZE, f"{path.name} entry {entry_index}")
            size, relative_offset = struct.unpack_from("<II", raw, 0)
            descriptor = raw[8:].split(b"\0", 1)[0].decode("gbk")
            fields = descriptor.split(" ", 2)
            if len(fields) != 3:
                raise ValueError(f"{path.name}: malformed path descriptor {descriptor!r}")
            guest_path = fields[2].replace("\\", "/")
            if guest_path.endswith("_4720"):
                continue
            if guest_path.endswith("_4750l"):
                guest_path = guest_path[:-6]
            pure = PurePosixPath(guest_path)
            if pure.is_absolute() or not pure.parts or any(part in {"", ".", ".."} for part in pure.parts):
                raise ValueError(f"{path.name}: unsafe guest path {guest_path!r}")
            folded = guest_path.casefold()
            if folded in seen_paths:
                raise ValueError(f"{path.name}: duplicate guest path {guest_path!r}")
            seen_paths.add(folded)
            absolute_offset = PACKET_HEADER_SIZE + relative_offset
            end = absolute_offset + size
            if absolute_offset < index_end or end > packet_size:
                raise ValueError(
                    f"{path.name}: payload {guest_path!r} range 0x{absolute_offset:X}..0x{end:X} is invalid"
                )
            entries.append(PacketEntry(size, absolute_offset, guest_path))
            ranges.append((absolute_offset, end, guest_path))
        for previous, current in zip(sorted(ranges), sorted(ranges)[1:]):
            if previous[1] > current[0]:
                raise ValueError(
                    f"{path.name}: payload ranges overlap: {previous[2]!r} and {current[2]!r}"
                )
    return PacketIndex(path, header, tuple(entries))


def add_packet_file(root: FsNode, entry: PacketEntry, packet_path: Path) -> FsNode:
    current = root
    parts = PurePosixPath(entry.path).parts
    for part in parts[:-1]:
        child = next((item for item in current.children if item.name.casefold() == part.casefold()), None)
        if child is None:
            child = FsNode(part, None, is_dir=True)
            current.children.append(child)
        elif not child.is_dir:
            raise ValueError(f"guest path collides with a file: {entry.path!r}")
        current = child
    leaf_name = parts[-1]
    if any(item.name.casefold() == leaf_name.casefold() for item in current.children):
        raise ValueError(f"duplicate FAT path: {entry.path!r}")
    leaf = FsNode(leaf_name, packet_path, is_dir=False, size=entry.size)
    current.children.append(leaf)
    return leaf


def build_packet_tree(packet: PacketIndex) -> tuple[FsNode, tuple[FileBinding, ...]]:
    root = FsNode("", None, is_dir=True)
    bindings = tuple(FileBinding(add_packet_file(root, entry, packet.path), entry) for entry in packet.entries)

    def sort_children(node: FsNode) -> None:
        node.children.sort(key=lambda item: (not item.is_dir, item.name.casefold()))
        for child in node.children:
            if child.is_dir:
                sort_children(child)

    sort_children(root)
    assign_short_names(root)
    return root, bindings


def choose_geometry(total_sectors: int) -> FatGeometry:
    sectors_per_fat = 1
    while True:
        geometry = FatGeometry(total_sectors=total_sectors, sectors_per_fat=sectors_per_fat)
        required = math.ceil((geometry.cluster_count + 2) * 2 / SECTOR_SIZE)
        if required == sectors_per_fat:
            break
        sectors_per_fat = required
    if not 4085 <= geometry.cluster_count <= 0xFFF5:
        raise ValueError(f"partition has {geometry.cluster_count} clusters and is not FAT16")
    return geometry


def make_boot_sector(geometry: FatGeometry, label: str, serial: int) -> bytes:
    label_bytes = label.encode("ascii")
    if len(label_bytes) > 11:
        raise ValueError(f"FAT label is too long: {label!r}")
    label_bytes = label_bytes.ljust(11, b" ")
    boot = bytearray(SECTOR_SIZE)
    boot[0:3] = b"\xEB\x3C\x90"
    boot[3:11] = b"mkfs.fat"
    struct.pack_into("<H", boot, 0x0B, SECTOR_SIZE)
    boot[0x0D] = geometry.sectors_per_cluster
    struct.pack_into("<H", boot, 0x0E, geometry.reserved_sectors)
    boot[0x10] = geometry.fat_copies
    struct.pack_into("<H", boot, 0x11, geometry.root_entries)
    struct.pack_into("<H", boot, 0x13, 0)
    boot[0x15] = 0xF8
    struct.pack_into("<H", boot, 0x16, geometry.sectors_per_fat)
    struct.pack_into("<H", boot, 0x18, geometry.sectors_per_track)
    struct.pack_into("<H", boot, 0x1A, geometry.heads)
    struct.pack_into("<I", boot, 0x1C, geometry.hidden_sectors)
    struct.pack_into("<I", boot, 0x20, geometry.total_sectors)
    boot[0x24] = 0x80
    boot[0x26] = 0x29
    struct.pack_into("<I", boot, 0x27, serial)
    boot[0x2B:0x36] = label_bytes
    boot[0x36:0x3E] = b"FAT16   "
    boot[0x3E:0x46] = b"H2V22L  "
    boot[510:512] = b"\x55\xAA"
    return bytes(boot)


def make_volume_label_entry(label: str) -> bytes:
    encoded = label.encode("ascii").ljust(11, b" ")
    entry = bytearray(32)
    entry[:11] = encoded
    entry[11] = 0x08
    return bytes(entry)


def write_repeated(stream, value: bytes, total: int) -> None:
    remaining = total
    while remaining:
        chunk = value if remaining >= len(value) else value[:remaining]
        stream.write(chunk)
        remaining -= len(chunk)


def write_packet_payload(output, packet_stream, target: int, entry: PacketEntry) -> None:
    packet_stream.seek(entry.packet_offset)
    output.seek(target)
    remaining = entry.size
    while remaining:
        chunk = read_exact(packet_stream, min(COPY_CHUNK_SIZE, remaining), entry.path)
        output.write(chunk)
        remaining -= len(chunk)


def write_partition(output, spec: PartitionSpec, packet: PacketIndex) -> dict[str, object]:
    geometry = choose_geometry(spec.total_sectors)
    root, bindings = build_packet_tree(packet)
    used_clusters = assign_clusters(root, geometry)  # compatible geometry surface
    if used_clusters > geometry.cluster_count:
        raise ValueError(f"{spec.name} packet contents do not fit in the FAT16 partition")

    base = spec.start_sector * SECTOR_SIZE
    fat_start = base + geometry.reserved_sectors * SECTOR_SIZE
    root_start = base + (
        geometry.reserved_sectors + geometry.fat_copies * geometry.sectors_per_fat
    ) * SECTOR_SIZE
    data_start = base + geometry.first_data_sector * SECTOR_SIZE
    metadata_bytes = geometry.first_data_sector * SECTOR_SIZE
    output.seek(base)
    write_repeated(output, b"\0" * min(ERASE_CHUNK_SIZE, metadata_bytes), metadata_bytes)
    output.seek(base)
    output.write(make_boot_sector(geometry, spec.label, 0x20260825 + spec.start_sector))
    fat = build_fat(root, geometry)
    for copy in range(geometry.fat_copies):
        output.seek(fat_start + copy * len(fat))
        output.write(fat)
    root_data = make_volume_label_entry(spec.label) + directory_entries(root, 0)
    root_capacity = geometry.root_dir_sectors * SECTOR_SIZE
    if len(root_data) > root_capacity:
        raise ValueError(f"{spec.name} root directory exceeds {root_capacity} bytes")
    output.seek(root_start)
    output.write(root_data.ljust(root_capacity, b"\0"))

    binding_by_node = {id(binding.node): binding.entry for binding in bindings}
    with packet.path.open("rb") as packet_stream:
        for node in iter_nodes(root):
            if not node.first_cluster:
                continue
            target = data_start + (node.first_cluster - 2) * geometry.cluster_size
            if node.is_dir:
                payload = directory_entries(node, node.parent_cluster)
                capacity = node.cluster_count * geometry.cluster_size
                if len(payload) > capacity:
                    raise ValueError(f"directory {node.name!r} exceeds its cluster allocation")
                output.seek(target)
                output.write(payload.ljust(capacity, b"\0"))
            else:
                write_packet_payload(output, packet_stream, target, binding_by_node[id(node)])

    return {
        "name": spec.name,
        "packet": spec.packet_name,
        "packet_files": len(packet.entries),
        "packet_bytes": sum(entry.size for entry in packet.entries),
        "start_sector": spec.start_sector,
        "total_sectors": geometry.total_sectors,
        "sectors_per_cluster": geometry.sectors_per_cluster,
        "reserved_sectors": geometry.reserved_sectors,
        "fat_copies": geometry.fat_copies,
        "root_entries": geometry.root_entries,
        "sectors_per_fat": geometry.sectors_per_fat,
        "cluster_count": geometry.cluster_count,
        "used_clusters": used_clusters,
        "free_clusters": geometry.cluster_count - used_clusters,
        "label": spec.label,
    }


# Minimal AES-256 encryption for the eight 512-byte H2 serial-number records.
# The table and transformations follow FIPS 197 and are kept local to avoid a
# binary Python dependency in the reproducible image builder.
AES_SBOX = bytes.fromhex(
    "637c777bf26b6fc53001672bfed7ab76ca82c97dfa5947f0add4a2af9ca472c0"
    "b7fd9326363ff7cc34a5e5f171d8311504c723c31896059a071280e2eb27b275"
    "09832c1a1b6e5aa0523bd6b329e32f8453d100ed20fcb15b6acbbe394a4c58cf"
    "d0efaafb434d338545f9027f503c9fa851a3408f929d38f5bcb6da2110fff3d2"
    "cd0c13ec5f974417c4a77e3d645d197360814fdc222a908846eeb814de5e0bdb"
    "e0323a0a4906245cc2d3ac629195e479e7c8376d8dd54ea96c56f4ea657aae08"
    "ba78252e1ca6b4c6e8dd741f4bbd8b8a703eb5664803f60e613557b986c11d9e"
    "e1f8981169d98e949b1e87e9ce5528df8ca1890dbfe6426841992d0fb054bb16"
)


def _gf_mul2(value: int) -> int:
    return ((value << 1) ^ (0x11B if value & 0x80 else 0)) & 0xFF


def _aes_expand_key(key: bytes) -> list[bytes]:
    if len(key) != 32 or len(AES_SBOX) != 256:
        raise ValueError("AES-256 requires a 32-byte key and a complete S-box")
    words = [bytearray(key[index : index + 4]) for index in range(0, 32, 4)]
    rcon = 1
    while len(words) < 60:
        temp = bytearray(words[-1])
        index = len(words)
        if index % 8 == 0:
            temp = bytearray(AES_SBOX[value] for value in temp[1:] + temp[:1])
            temp[0] ^= rcon
            rcon = _gf_mul2(rcon)
        elif index % 8 == 4:
            temp = bytearray(AES_SBOX[value] for value in temp)
        words.append(bytearray(a ^ b for a, b in zip(words[index - 8], temp)))
    return [bytes().join(words[index : index + 4]) for index in range(0, 60, 4)]


def _aes_encrypt_block(block: bytes, round_keys: list[bytes]) -> bytes:
    state = bytearray(a ^ b for a, b in zip(block, round_keys[0]))
    for round_index in range(1, 15):
        state = bytearray(AES_SBOX[value] for value in state)
        state = bytearray(
            state[index]
            for index in (0, 5, 10, 15, 4, 9, 14, 3, 8, 13, 2, 7, 12, 1, 6, 11)
        )
        if round_index != 14:
            for column in range(4):
                offset = column * 4
                a0, a1, a2, a3 = state[offset : offset + 4]
                total = a0 ^ a1 ^ a2 ^ a3
                state[offset + 0] ^= total ^ _gf_mul2(a0 ^ a1)
                state[offset + 1] ^= total ^ _gf_mul2(a1 ^ a2)
                state[offset + 2] ^= total ^ _gf_mul2(a2 ^ a3)
                state[offset + 3] ^= total ^ _gf_mul2(a3 ^ a0)
        state = bytearray(a ^ b for a, b in zip(state, round_keys[round_index]))
    return bytes(state)


def aes256_ecb_encrypt(data: bytes, key: bytes) -> bytes:
    if len(data) % 16:
        raise ValueError("AES ECB input length must be a multiple of 16")
    round_keys = _aes_expand_key(key)
    return b"".join(
        _aes_encrypt_block(data[offset : offset + 16], round_keys)
        for offset in range(0, len(data), 16)
    )


def serial_record_bytes(serial: str) -> bytes:
    encoded = serial.encode("gbk")
    if len(encoded) > 13:
        raise ValueError("H2 serial number must fit in 13 GBK bytes")
    clear = bytearray(b"\xAA" * SECTOR_SIZE)
    clear[-1] = 0
    struct.pack_into("<III", clear, 0, 0x20101228, 0x44313030, 0x5D245588)
    clear[0x1C:0x29] = encoded.ljust(13, b"\0")
    clear[0x2C:0x34] = b"JZ4750L\0"
    key = bytes([0x21, 0x21, 0x01, 0xDE, 0xAD, 0xBE, 0xEF, 0x29] + [0xAA] * 24)
    return aes256_ecb_encrypt(bytes(clear), key)


def write_serial_records(output, serial: str) -> dict[str, object]:
    encrypted = serial_record_bytes(serial)
    sectors = (0x7C00, 0x7E00, 0x8000, 0x8200, 0x7D00, 0x7F00, 0x8100, 0x8300)
    for sector in sectors:
        output.seek(sector * SECTOR_SIZE)
        output.write(encrypted)
    return {
        "serial": serial,
        "sectors": list(sectors),
        "ciphertext_sha256": hashlib.sha256(encrypted).hexdigest().upper(),
        "key_source": "QEMU eMMC CID bytes 7..14 followed by 0xAA padding",
    }


def validate_inputs(input_dir: Path) -> dict[str, Path]:
    names = {
        "BurnSys_H2L_V1.0.bin",
        "data0_L.dat",
        "data1_L.dat",
        "data2_L.dat",
        "data3_L.dat",
        "data4_L.dat",
        "packet1.dat",
        "packet2.dat",
    }
    paths = {name: input_dir / name for name in names}
    missing = sorted(name for name, path in paths.items() if not path.is_file())
    if missing:
        raise FileNotFoundError(f"missing H2 recovery inputs: {', '.join(missing)}")
    return paths


def build_image(input_dir: Path, output_path: Path, serial: str, plan_only: bool) -> dict[str, object]:
    inputs = validate_inputs(input_dir)
    burn = inputs["BurnSys_H2L_V1.0.bin"].read_bytes()
    xor_pattern = burn[XOR_OFFSET : XOR_OFFSET + XOR_SIZE]
    if len(xor_pattern) != XOR_SIZE:
        raise ValueError("BurnSys_H2L_V1.0.bin does not contain the complete XOR pattern")
    decoded = {
        name: decode_data_file(inputs[name], xor_pattern)
        for name in ("data0_L.dat", "data1_L.dat", "data2_L.dat", "data3_L.dat", "data4_L.dat")
    }
    if decoded["data0_L.dat"][:4] != b"LPSM":
        raise ValueError("decoded H2L first stage does not begin with LPSM")
    packets = {spec.packet_name: parse_packet(inputs[spec.packet_name]) for spec in PARTITIONS}
    for segment in RAW_SEGMENTS:
        end = segment.offset + len(decoded[segment.source_name])
        if end > PARTITIONS[0].start_sector * SECTOR_SIZE:
            raise ValueError(f"raw segment {segment.name} overlaps the system FAT partition")

    report: dict[str, object] = {
        "format": "bbk-ibox-h2l-v2.2-emmc-v1",
        "image_bytes": IMAGE_SIZE,
        "input_files": {
            name: {
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
            for name, path in sorted(inputs.items())
        },
        "xor": {
            "source": "BurnSys_H2L_V1.0.bin",
            "offset": XOR_OFFSET,
            "bytes": XOR_SIZE,
            "sha256": hashlib.sha256(xor_pattern).hexdigest().upper(),
        },
        "decoded_images": {
            name: {
                "bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest().upper(),
            }
            for name, payload in sorted(decoded.items())
        },
        "raw_segments": [
            {
                "name": segment.name,
                "source": segment.source_name,
                "offset": segment.offset,
                "bytes": len(decoded[segment.source_name]),
            }
            for segment in RAW_SEGMENTS
        ],
        "partitions": [],
    }
    for spec in PARTITIONS:
        geometry = choose_geometry(spec.total_sectors)
        root, _ = build_packet_tree(packets[spec.packet_name])
        used = assign_clusters(root, geometry)
        report["partitions"].append(
            {
                "name": spec.name,
                "packet": spec.packet_name,
                "packet_files": len(packets[spec.packet_name].entries),
                "packet_bytes": sum(item.size for item in packets[spec.packet_name].entries),
                "start_sector": spec.start_sector,
                "total_sectors": spec.total_sectors,
                "sectors_per_cluster": geometry.sectors_per_cluster,
                "reserved_sectors": geometry.reserved_sectors,
                "fat_copies": geometry.fat_copies,
                "root_entries": geometry.root_entries,
                "sectors_per_fat": geometry.sectors_per_fat,
                "cluster_count": geometry.cluster_count,
                "used_clusters": used,
                "free_clusters": geometry.cluster_count - used,
                "label": spec.label,
            }
        )
    if plan_only:
        return report

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        raise FileExistsError(f"refusing to overwrite {output_path}")
    temporary = output_path.with_name(output_path.name + ".building")
    if temporary.exists():
        raise FileExistsError(f"stale temporary output exists: {temporary}")
    try:
        with temporary.open("w+b", buffering=0) as output:
            erased = b"\xFF" * ERASE_CHUNK_SIZE
            write_repeated(output, erased, IMAGE_SIZE)
            for segment in RAW_SEGMENTS:
                output.seek(segment.offset)
                output.write(decoded[segment.source_name])
            serial_report = write_serial_records(output, serial)
            partition_reports = [
                write_partition(output, spec, packets[spec.packet_name]) for spec in PARTITIONS
            ]
            output.flush()
            os.fsync(output.fileno())
        report["serial_record"] = serial_report
        report["partitions"] = partition_reports
        report["output"] = output_path.name
        report["output_sha256"] = sha256_file(temporary)
        os.replace(temporary, output_path)
    except BaseException:
        if temporary.exists():
            temporary.unlink()
        raise
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True, help="directory containing extracted recovery app files")
    parser.add_argument("--output", type=Path, required=True, help="2 GiB raw eMMC image")
    parser.add_argument("--manifest", type=Path, help="JSON build manifest")
    parser.add_argument("--serial", default="QEMU 20260825", help="up to 13 GBK bytes")
    parser.add_argument("--plan-only", action="store_true", help="validate and report without writing the image")
    args = parser.parse_args()

    report = build_image(args.input_dir.resolve(), args.output.resolve(), args.serial, args.plan_only)
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.manifest and not args.plan_only:
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        args.manifest.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
