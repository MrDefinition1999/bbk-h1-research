#!/usr/bin/env python3
"""Copy the two stock V1 Flying Video AVI samples onto a copied V2 B volume."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

from add_h1_v1_game_assets_to_nand import (
    FatEntry,
    FatTree,
    LogicalVolume,
    default_ecc_helper,
    dot_entries,
    lfn_entries,
    short_entry,
)
from h1_ftl import RAW_ERASE_BLOCK_SIZE


VIDEO_DIRECTORY = "飞天影音"
VIDEO_FILES = (
    "@ibox学习机广告.avi",
    "拜见罗宾逊一家(meet the robinsons).avi",
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def sha256_file(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(16 * 1024 * 1024):
            value.update(chunk)
    return value.hexdigest().upper()


def hash_region(path: Path, offset: int, size: int | None = None) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        stream.seek(offset)
        remaining = size
        while remaining is None or remaining > 0:
            count = (
                16 * 1024 * 1024
                if remaining is None
                else min(remaining, 16 * 1024 * 1024)
            )
            chunk = stream.read(count)
            if not chunk:
                break
            value.update(chunk)
            if remaining is not None:
                remaining -= len(chunk)
        if remaining not in (None, 0):
            raise IOError(f"short region read from {path.name}")
    return value.hexdigest().upper()


def read_v1_samples(
    image: Path,
    scan_start_block: int,
) -> tuple[FatEntry, dict[str, tuple[bytes, FatEntry]]]:
    volume = LogicalVolume(image, scan_start_block, writable=False)
    try:
        tree = FatTree(volume)
        directory = tree.resolve(VIDEO_DIRECTORY)
        if not directory.is_directory:
            raise NotADirectoryError(VIDEO_DIRECTORY)
        samples: dict[str, tuple[bytes, FatEntry]] = {}
        for name in VIDEO_FILES:
            entry = tree.resolve(f"{VIDEO_DIRECTORY}\\{name}")
            samples[name] = (tree.read_file(entry), entry)
        return directory, samples
    finally:
        volume.close()


def add_file(
    tree: FatTree,
    free_clusters: list[int],
    parent_cluster: int,
    payload: bytes,
    source_entry: FatEntry,
) -> list[int]:
    count = max(1, (len(payload) + tree.cluster_size - 1) // tree.cluster_size)
    chain = tree.allocate_chain(free_clusters, count)
    entries = (
        lfn_entries(source_entry.long_name, source_entry.short_raw)
        if source_entry.long_name
        else []
    )
    entries.append(
        short_entry(source_entry.short_raw, 0x20, chain[0], len(payload))
    )
    tree.put_entries(parent_cluster, entries)
    tree.write_chain(chain, payload)
    return chain


def install_samples(
    template: Path,
    output: Path,
    v1_image: Path,
    manifest_path: Path,
    scan_start_block: int,
    scan_end_block: int,
    v1_scan_start_block: int,
    ecc_helper: Path | None,
) -> dict[str, object]:
    if output.exists():
        raise FileExistsError(f"refusing to overwrite existing output: {output}")

    source_directory, samples = read_v1_samples(v1_image, v1_scan_start_block)
    template_boot_and_a = hash_region(
        template, 0, scan_start_block * RAW_ERASE_BLOCK_SIZE
    )
    b_offset = scan_start_block * RAW_ERASE_BLOCK_SIZE
    template_b = hash_region(template, b_offset)

    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(template, output)
    expected: dict[str, bytes] = {}
    chains: dict[str, dict[str, int]] = {}

    volume = LogicalVolume(
        output,
        scan_start_block,
        writable=True,
        scan_end_block=scan_end_block,
    )
    try:
        tree = FatTree(volume)
        try:
            tree.resolve(VIDEO_DIRECTORY)
            raise FileExistsError(VIDEO_DIRECTORY)
        except FileNotFoundError:
            pass

        free = tree.free_clusters()
        free_before = len(free)
        directory_chain = tree.allocate_chain(free, 1)
        directory_cluster = directory_chain[0]
        tree.write_chain(
            directory_chain,
            b"".join(dot_entries(directory_cluster, 0)),
        )
        directory_entries = (
            lfn_entries(source_directory.long_name, source_directory.short_raw)
            if source_directory.long_name
            else []
        )
        directory_entries.append(
            short_entry(source_directory.short_raw, 0x10, directory_cluster)
        )
        tree.put_entries(None, directory_entries)

        for name in VIDEO_FILES:
            payload, source_entry = samples[name]
            chain = add_file(
                tree,
                free,
                directory_cluster,
                payload,
                source_entry,
            )
            path = f"{VIDEO_DIRECTORY}\\{name}"
            expected[path] = payload
            chains[path] = {"first": chain[0], "clusters": len(chain)}

        tree.write_fat()
        sequences = [record.sequence or 0 for record in volume.result.mapping.values()]
        sequence = ((max(sequences) if sequences else 0) + 1) & 0xFFFF or 1
        write_report = volume.flush(ecc_helper, sequence)
        free_after = len(free)
    except Exception:
        volume.close()
        output.unlink(missing_ok=True)
        raise

    checked = LogicalVolume(
        output,
        scan_start_block,
        writable=False,
        scan_end_block=scan_end_block,
    )
    try:
        checked_tree = FatTree(checked)
        checked_directory = checked_tree.resolve(VIDEO_DIRECTORY)
        if not checked_directory.is_directory:
            raise NotADirectoryError(VIDEO_DIRECTORY)
        readback = {}
        for path, wanted in expected.items():
            entry = checked_tree.resolve(path)
            observed = checked_tree.read_file(entry)
            if observed != wanted:
                raise IOError(f"readback mismatch for {path}")
            readback[path] = {
                "bytes": len(observed),
                "sha256": sha256_bytes(observed),
                "first_cluster": entry.first_cluster,
            }
        mapped_after = len(checked.result.mapping)
    finally:
        checked.close()

    output_boot_and_a = hash_region(
        output, 0, scan_start_block * RAW_ERASE_BLOCK_SIZE
    )
    if output_boot_and_a != template_boot_and_a:
        output.unlink(missing_ok=True)
        raise IOError("boot/A byte range changed while adding B-volume AVI files")
    output_b = hash_region(output, b_offset)
    if output_b == template_b:
        output.unlink(missing_ok=True)
        raise IOError("B byte range did not change while adding AVI files")

    report = {
        "format": "h1-v2-flying-video-samples-v1",
        "template_name": template.name,
        "template_sha256": sha256_file(template),
        "output_name": output.name,
        "output_bytes": output.stat().st_size,
        "output_sha256": sha256_file(output),
        "v1_image_name": v1_image.name,
        "v1_image_sha256": sha256_file(v1_image),
        "scan_window": {
            "start_block": scan_start_block,
            "end_block_exclusive": scan_end_block,
        },
        "target_volume": "B:",
        "directory": VIDEO_DIRECTORY,
        "installed_files": readback,
        "installed_bytes": sum(len(payload) for payload in expected.values()),
        "chains": chains,
        "fat_free_clusters_before": free_before,
        "fat_free_clusters_after": free_after,
        "ftl_mapped_logical_units_after": mapped_after,
        "write": write_report,
        "boot_and_a_sha256": output_boot_and_a,
        "template_b_sha256": template_b,
        "output_b_sha256": output_b,
        "v1_game_suite_preserved": True,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--v1-image", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--scan-start-block", type=lambda value: int(value, 0), default=0x6F4)
    parser.add_argument("--scan-end-block", type=lambda value: int(value, 0), default=0x1000)
    parser.add_argument("--v1-scan-start-block", type=lambda value: int(value, 0), default=0x40)
    parser.add_argument("--ecc-helper", type=Path, default=default_ecc_helper())
    parser.add_argument("--python-ecc", action="store_true")
    args = parser.parse_args()
    report = install_samples(
        args.template.resolve(strict=True),
        args.output.resolve(),
        args.v1_image.resolve(strict=True),
        args.manifest.resolve(),
        args.scan_start_block,
        args.scan_end_block,
        args.v1_scan_start_block,
        None if args.python_ecc else args.ecc_helper.resolve(strict=True),
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
