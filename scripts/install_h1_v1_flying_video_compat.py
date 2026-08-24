#!/usr/bin/env python3
"""Build a copied H1 V1.41 NAND with the 2.X Flying Video compatibility port."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
import sys
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parents[1]
SDK = REPOSITORY / "h1-bda-sdk"
SDK_SCRIPTS = SDK / "scripts"
for search_path in (SDK, SDK_SCRIPTS):
    if str(search_path) not in sys.path:
        sys.path.insert(0, str(search_path))

import install_emulator_path as path_installer  # noqa: E402
from h1_bda.validate import validate_bda  # noqa: E402
from replace_h1_fat_file_in_nand import (  # noqa: E402
    FatResolver,
    LogicalVolume,
    default_ecc_helper,
)


V1_PLAYER_SHA256 = "B964EB9CA0EF7172933D079E7209B7AE6E69CC4CD29C675814FCF348EA1853D0"
V1_RESOURCE_SHA256 = "4D51625BCAAF7F71B071212EEFB095EE9EAC7C2F2CD0DCA37226ADD74B623504"
V2_RESOURCE_SHA256 = "FAB2F3CF69C449167FD7C5C933E6418AC78738720EDC749FEA3AA919A775E0E8"
COMPAT_PLAYER_SHA256 = "753ED2D6EFF71BC51714C11A37EF34AEA1CB8DFBF225497B17835D76C86484A0"

PLAYER_PATH = "/\u5e94\u7528/\u7a0b\u5e8f/\u98de\u5929\u5f71\u97f3.bda"
V1_RESOURCE_PATH = "/\u5e94\u7528/\u6570\u636e/player.bin"
V2_RESOURCE_PATH = "/\u5e94\u7528/\u6570\u636e/play2.bin"
SAMPLE_DIRECTORY = "\u98de\u5929\u5f71\u97f3"
SAMPLE_NAME = "\u6d4b\u8bd5.avi"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def inspect_file(image: Path, path: str) -> tuple[bytes, int]:
    volume = LogicalVolume(image, 0x40)
    try:
        resolver = FatResolver(volume)
        entry = resolver.resolve(path)
        return resolver.read_file(entry), entry.size
    finally:
        volume.close()


def replace_file(
    image: Path,
    path: str,
    replacement: bytes,
    helper: Path | None,
    expected_original_sha256: str,
) -> dict[str, object]:
    volume = LogicalVolume(image, 0x40, writable=True)
    try:
        resolver = FatResolver(volume)
        entry = resolver.resolve(path)
        original = resolver.read_file(entry)
        if sha256(original) != expected_original_sha256:
            raise ValueError(f"{path} is not the supported stock V1.41 file")
        chain = resolver.cluster_chain(entry.first_cluster)
        capacity = len(chain) * resolver.cluster_size
        if len(replacement) > capacity:
            raise ValueError(
                f"replacement requires {len(replacement)} bytes but chain holds {capacity}"
            )
        padded = replacement + bytes(capacity - len(replacement))
        for index, cluster in enumerate(chain):
            start = index * resolver.cluster_size
            volume.write(
                resolver.cluster_offset(cluster),
                padded[start : start + resolver.cluster_size],
            )
        volume.write(entry.directory_offset + 28, struct.pack("<I", len(replacement)))
        write_report = volume.flush(helper)
        mapping_count = len(volume.result.mapping)
    finally:
        volume.close()

    readback, readback_size = inspect_file(image, path)
    if readback != replacement or readback_size != len(replacement):
        raise IOError(f"{path} replacement failed byte-for-byte read-back")
    return {
        "target": path,
        "original_sha256": sha256(original),
        "replacement_sha256": sha256(replacement),
        "replacement_bytes": len(replacement),
        "chain_capacity": capacity,
        "ftl_mapping_count": mapping_count,
        "programmed_pages": write_report["programmed_pages"],
        "readback_match": True,
    }


def compact_install_report(report: dict[str, object]) -> dict[str, object]:
    return {
        key: report[key]
        for key in (
            "target",
            "size",
            "sha256",
            "reused_directory",
            "file_clusters",
            "cluster_capacity",
            "readback_match",
            "invalid_ftl_records",
        )
    }


def install_compatibility_nand(
    stock_nand: Path,
    output_nand: Path,
    compat_bda: Path,
    v2_resource: Path,
    helper: Path | None,
    sample: Path | None = None,
) -> dict[str, object]:
    player = compat_bda.read_bytes()
    resource = v2_resource.read_bytes()
    if sha256(player) != COMPAT_PLAYER_SHA256:
        raise ValueError("compatibility BDA is not the validated reproducible build")
    validation = validate_bda(compat_bda)
    if not validation["ok"]:
        raise ValueError("compatibility BDA failed structural validation")
    if sha256(resource) != V2_RESOURCE_SHA256:
        raise ValueError("2.X player resource is not the analyzed exact build")

    stock_player, _ = inspect_file(stock_nand, PLAYER_PATH)
    stock_resource, _ = inspect_file(stock_nand, V1_RESOURCE_PATH)
    if sha256(stock_player) != V1_PLAYER_SHA256:
        raise ValueError("source NAND does not contain the supported stock V1.41 player")
    if sha256(stock_resource) != V1_RESOURCE_SHA256:
        raise ValueError("source NAND does not contain the supported stock V1 resource")
    if output_nand.exists():
        raise FileExistsError(output_nand)

    temporary = output_nand.with_name(output_nand.name + ".flying-video.tmp")
    if temporary.exists():
        temporary.unlink()
    output_nand.parent.mkdir(parents=True, exist_ok=True)
    try:
        path_installer.deployment.copy_file(stock_nand, temporary)
        replacement_report = replace_file(
            temporary, PLAYER_PATH, player, helper, V1_PLAYER_SHA256
        )
        resource_report = path_installer.install(
            temporary,
            v2_resource,
            "/\u5e94\u7528",
            "\u6570\u636e",
            "play2.bin",
            "PLAY2.BIN",
            helper,
            reuse_directory=True,
            directory_short_alias="DATA",
        )
        sample_report = None
        if sample is not None:
            sample_data = sample.read_bytes()
            if not sample_data.startswith(b"EEBBKBMD"):
                raise ValueError("sample does not have the encrypted EEBBKBMD header")
            sample_report = path_installer.install(
                temporary,
                sample,
                "/",
                SAMPLE_DIRECTORY,
                SAMPLE_NAME,
                "TEST.AVI",
                helper,
                reuse_directory=True,
                directory_short_alias="FLYVIDEO",
            )

        checked_player, _ = inspect_file(temporary, PLAYER_PATH)
        checked_v1_resource, _ = inspect_file(temporary, V1_RESOURCE_PATH)
        checked_v2_resource, _ = inspect_file(temporary, V2_RESOURCE_PATH)
        if checked_player != player or checked_v2_resource != resource:
            raise IOError("final NAND player/resource verification failed")
        if sha256(checked_v1_resource) != V1_RESOURCE_SHA256:
            raise IOError("stock V1 player.bin was modified")
        os.replace(temporary, output_nand)
    except BaseException:
        if temporary.exists():
            temporary.unlink()
        raise

    report: dict[str, object] = {
        "format": "bbk-h1-v1-flying-video-compat-install-v1",
        "source_nand_name": stock_nand.name,
        "output_nand_name": output_nand.name,
        "player": replacement_report,
        "v2_resource": compact_install_report(resource_report),
        "v1_resource_preserved_sha256": V1_RESOURCE_SHA256,
        "all_readbacks_verified": True,
    }
    if sample_report is not None:
        report["encrypted_sample"] = compact_install_report(sample_report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stock-nand", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--compat-bda",
        type=Path,
        default=REPOSITORY / "work" / "analysis" / "v1-v2-flying-video-compat.bda",
    )
    parser.add_argument(
        "--v2-resource",
        type=Path,
        default=REPOSITORY / "work" / "analysis" / "v2-player-resource.bin",
    )
    parser.add_argument("--sample", type=Path)
    parser.add_argument(
        "--ecc-helper", type=Path, default=default_ecc_helper(REPOSITORY)
    )
    parser.add_argument(
        "--python-ecc",
        action="store_true",
        help="use the checked Python/NumPy ECC encoder instead of a native helper",
    )
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    required = [args.stock_nand, args.compat_bda, args.v2_resource]
    if not args.python_ecc:
        required.append(args.ecc_helper)
    for path in required:
        if not path.is_file():
            raise FileNotFoundError(path)
    if args.sample is not None and not args.sample.is_file():
        raise FileNotFoundError(args.sample)
    report = install_compatibility_nand(
        args.stock_nand.resolve(),
        args.output.resolve(),
        args.compat_bda.resolve(),
        args.v2_resource.resolve(),
        None if args.python_ecc else args.ecc_helper.resolve(),
        args.sample.resolve() if args.sample is not None else None,
    )
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered, encoding="utf-8", newline="\n")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
