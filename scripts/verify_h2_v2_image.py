#!/usr/bin/env python3
"""Verify an H2 V2.2L eMMC image against the extracted recovery inputs.

The verifier independently checks the decoded raw regions, encrypted serial
records, FAT16 metadata, and every packet payload without extracting either
packet to the host filesystem.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import build_h2_v2_image as h2


def compare_bytes(actual, offset: int, expected: bytes, description: str) -> None:
    actual.seek(offset)
    found = h2.read_exact(actual, len(expected), description)
    if found != expected:
        raise ValueError(f"{description} differs at image offset 0x{offset:X}")


def compare_streams(
    image,
    image_offset: int,
    packet,
    packet_offset: int,
    size: int,
    description: str,
) -> str:
    digest = hashlib.sha256()
    image.seek(image_offset)
    packet.seek(packet_offset)
    remaining = size
    compared = 0
    while remaining:
        length = min(h2.COPY_CHUNK_SIZE, remaining)
        expected = h2.read_exact(packet, length, description)
        actual = h2.read_exact(image, length, description)
        if actual != expected:
            mismatch = next(
                index for index, (left, right) in enumerate(zip(actual, expected))
                if left != right
            )
            raise ValueError(
                f"{description} differs at payload byte 0x{compared + mismatch:X} "
                f"(image offset 0x{image_offset + compared + mismatch:X})"
            )
        digest.update(actual)
        compared += length
        remaining -= length
    return digest.hexdigest().upper()


def verify_partition(image, spec: h2.PartitionSpec, packet: h2.PacketIndex) -> dict[str, object]:
    geometry = h2.choose_geometry(spec.total_sectors)
    root, bindings = h2.build_packet_tree(packet)
    used_clusters = h2.assign_clusters(root, geometry)
    base = spec.start_sector * h2.SECTOR_SIZE
    fat_start = base + geometry.reserved_sectors * h2.SECTOR_SIZE
    root_start = base + (
        geometry.reserved_sectors + geometry.fat_copies * geometry.sectors_per_fat
    ) * h2.SECTOR_SIZE
    data_start = base + geometry.first_data_sector * h2.SECTOR_SIZE

    compare_bytes(
        image,
        base,
        h2.make_boot_sector(geometry, spec.label, 0x20260825 + spec.start_sector),
        f"{spec.name} boot sector",
    )
    expected_fat = h2.build_fat(root, geometry)
    for copy in range(geometry.fat_copies):
        compare_bytes(
            image,
            fat_start + copy * len(expected_fat),
            expected_fat,
            f"{spec.name} FAT copy {copy + 1}",
        )

    root_capacity = geometry.root_dir_sectors * h2.SECTOR_SIZE
    expected_root = (
        h2.make_volume_label_entry(spec.label) + h2.directory_entries(root, 0)
    ).ljust(root_capacity, b"\0")
    compare_bytes(image, root_start, expected_root, f"{spec.name} root directory")

    binding_by_node = {id(binding.node): binding.entry for binding in bindings}
    files = 0
    payload_bytes = 0
    with packet.path.open("rb") as packet_stream:
        for node in h2.iter_nodes(root):
            if not node.first_cluster:
                continue
            target = data_start + (node.first_cluster - 2) * geometry.cluster_size
            if node.is_dir:
                capacity = node.cluster_count * geometry.cluster_size
                expected = h2.directory_entries(node, node.parent_cluster).ljust(
                    capacity, b"\0"
                )
                compare_bytes(image, target, expected, f"{spec.name} directory {node.name!r}")
                continue
            entry = binding_by_node[id(node)]
            compare_streams(
                image,
                target,
                packet_stream,
                entry.packet_offset,
                entry.size,
                f"{spec.name}:{entry.path}",
            )
            files += 1
            payload_bytes += entry.size

    return {
        "name": spec.name,
        "files": files,
        "payload_bytes": payload_bytes,
        "used_clusters": used_clusters,
        "fat_copies": geometry.fat_copies,
        "metadata": "exact",
        "payloads": "exact",
    }


def verify_image(input_dir: Path, image_path: Path, serial: str) -> dict[str, object]:
    inputs = h2.validate_inputs(input_dir)
    if image_path.stat().st_size != h2.IMAGE_SIZE:
        raise ValueError(
            f"image size is {image_path.stat().st_size}, expected {h2.IMAGE_SIZE}"
        )
    burn = inputs["BurnSys_H2L_V1.0.bin"].read_bytes()
    xor_pattern = burn[h2.XOR_OFFSET : h2.XOR_OFFSET + h2.XOR_SIZE]
    decoded = {
        name: h2.decode_data_file(inputs[name], xor_pattern)
        for name in (
            "data0_L.dat",
            "data1_L.dat",
            "data2_L.dat",
            "data3_L.dat",
            "data4_L.dat",
        )
    }
    packets = {
        spec.packet_name: h2.parse_packet(inputs[spec.packet_name])
        for spec in h2.PARTITIONS
    }

    with image_path.open("rb") as image:
        for segment in h2.RAW_SEGMENTS:
            compare_bytes(
                image,
                segment.offset,
                decoded[segment.source_name],
                f"raw segment {segment.name}",
            )

        encrypted_record = h2.serial_record_bytes(serial)
        serial_sectors = (0x7C00, 0x7E00, 0x8000, 0x8200, 0x7D00, 0x7F00, 0x8100, 0x8300)
        for sector in serial_sectors:
            compare_bytes(
                image,
                sector * h2.SECTOR_SIZE,
                encrypted_record,
                f"serial record sector 0x{sector:X}",
            )

        partitions = [
            verify_partition(image, spec, packets[spec.packet_name])
            for spec in h2.PARTITIONS
        ]

    return {
        "format": "bbk-ibox-h2l-v2.2-emmc-verification-v1",
        "image": image_path.name,
        "image_bytes": image_path.stat().st_size,
        "image_sha256": h2.sha256_file(image_path),
        "raw_segments": len(h2.RAW_SEGMENTS),
        "serial_records": len(serial_sectors),
        "partitions": partitions,
        "status": "verified",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--serial", default="QEMU 20260825")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = verify_image(args.input_dir.resolve(), args.image.resolve(), args.serial)
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
