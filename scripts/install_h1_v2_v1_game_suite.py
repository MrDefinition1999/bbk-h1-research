#!/usr/bin/env python3
"""Install six V1 games with B-resident resources on a copied V2 NAND."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import struct
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SDK_ROOT = next(
    (path for path in (ROOT / "h1-bda-sdk", ROOT / "sdk") if path.is_dir()),
    ROOT / "h1-bda-sdk",
)
if str(SDK_ROOT) not in sys.path:
    sys.path.insert(0, str(SDK_ROOT))

from h1_bda.header import (  # noqa: E402
    HeaderFields,
    decode_header,
    encode_header,
    read_c_string,
)
from h1_bda.validate import validate_bda  # noqa: E402

from add_h1_v1_game_assets_to_nand import (  # noqa: E402
    FatEntry,
    FatTree,
    LogicalVolume,
    default_ecc_helper,
    lfn_entries,
    read_v1_file,
    short_entry,
)
from h1_ftl import RAW_ERASE_BLOCK_SIZE  # noqa: E402
from verify_h1_v2_game_compat_coverage import build_report  # noqa: E402


PAYLOAD_OFFSET = 0x785C
V1_ENTRY_VA = 0x83C00020
COMPATIBILITY_BASE = 0x83E00000
SAFE_WRAPPER_SHA256 = "154B601539E1B865A08D658B2C2038093C5BCA4E1C34935183977B5008E93C2C"
OLD_EXTERNAL_PATH = b"A:\\V1GAME.BIN"
OLD_GAME_SIZE = 0x79374
OLD_SIZE_SEQUENCE = struct.pack("<II", 0x3C010007, 0x34339374)
OLD_CACHE_END = 0x83C793A0
OLD_CACHE_SEQUENCE = struct.pack("<II", 0x3C0183C7, 0x342293A0)
RESOURCE_ROOT_A = "A:\\应用\\数据\\游戏\\".encode("gbk")
RESOURCE_ROOT_B = "B:\\应用\\数据\\游戏\\".encode("gbk")
PROGRAM_DIRECTORY = "应用\\程序"
GAME_DATA_DIRECTORY = "应用\\数据\\游戏"


@dataclass(frozen=True)
class GameSpec:
    name: str
    payload_name: str
    resources: tuple[str, ...]
    expected_absolute_paths: int

    @property
    def guest_payload_path(self) -> str:
        return "A:\\" + self.payload_name

    @property
    def guest_wrapper_path(self) -> str:
        return f"A:\\{PROGRAM_DIRECTORY}\\{self.name}.bda"

    @property
    def guest_resource_paths(self) -> tuple[str, ...]:
        return tuple(
            f"B:\\{GAME_DATA_DIRECTORY}\\{resource}"
            for resource in self.resources
        )


GAMES = (
    GameSpec("中国象棋", "CHESS1.BIN", ("cheRes.lib", "CheSnd.lib"), 2),
    GameSpec("俄罗斯", "TETRIS.BIN", ("els.lib", "elssound.lib"), 1),
    GameSpec("宠物泡泡", "PETPOP.BIN", ("popo.lib", "posnd.lib"), 3),
    GameSpec("猫狗大战", "CATDOG.BIN", ("dvc.lib", "dvcsnd.lib"), 2),
    GameSpec(
        "雷霆战机",
        "FLYJET.BIN",
        (
            "flydata.lib",
            "flydata1.lib",
            "flydata2.lib",
            "flydata3.lib",
            "flydata4.lib",
            "FlySound.lib",
        ),
        1,
    ),
    GameSpec("黑白子", "BWGAME.BIN", ("black.lib", "blacksound.lib"), 1),
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
            count = 16 * 1024 * 1024 if remaining is None else min(remaining, 16 * 1024 * 1024)
            chunk = stream.read(count)
            if not chunk:
                break
            value.update(chunk)
            if remaining is not None:
                remaining -= len(chunk)
        if remaining not in (None, 0):
            raise IOError(f"short region read from {path.name}")
    return value.hexdigest().upper()


def _replace_once(data: bytes, old: bytes, new: bytes, label: str) -> bytes:
    count = data.count(old)
    if count != 1:
        raise ValueError(f"safe wrapper must contain one {label}, found {count}")
    return data.replace(old, new, 1)


def size_sequence(size: int) -> bytes:
    if not 0 < size < COMPATIBILITY_BASE - V1_ENTRY_VA:
        raise ValueError("V1 game payload size exceeds the compatibility arena")
    return struct.pack(
        "<II",
        0x3C010000 | ((size >> 16) & 0xFFFF),
        0x34330000 | (size & 0xFFFF),
    )


def cache_sequence(size: int) -> bytes:
    end = (V1_ENTRY_VA + size + 15) & ~15
    return struct.pack(
        "<II",
        0x3C010000 | ((end >> 16) & 0xFFFF),
        0x34220000 | (end & 0xFFFF),
    )


def patch_external_payload(template: bytes, guest_path: str, game_size: int) -> bytes:
    encoded_path = guest_path.encode("ascii")
    if len(encoded_path) != len(OLD_EXTERNAL_PATH):
        raise ValueError(
            f"external path must be exactly {len(OLD_EXTERNAL_PATH)} ASCII bytes"
        )
    patched = _replace_once(template, OLD_EXTERNAL_PATH, encoded_path, "external path")
    patched = _replace_once(
        patched,
        OLD_SIZE_SEQUENCE,
        size_sequence(game_size),
        "compiled game-size sequence",
    )
    patched = _replace_once(
        patched,
        OLD_CACHE_SEQUENCE,
        cache_sequence(game_size),
        "compiled cache-end sequence",
    )
    return patched


def patch_game_resource_drive(
    payload: bytes, expected_paths: int
) -> tuple[bytes, list[int], list[str]]:
    """Rewrite only verified absolute game-data roots from A: to B:."""
    offsets: list[int] = []
    paths: list[str] = []
    start = 0
    while True:
        offset = payload.find(RESOURCE_ROOT_A, start)
        if offset < 0:
            break
        offsets.append(offset)
        end = payload.find(b"\0", offset, min(len(payload), offset + 256))
        if end < 0:
            raise ValueError(f"unterminated resource path at payload offset 0x{offset:X}")
        paths.append(payload[offset:end].decode("gbk"))
        start = offset + len(RESOURCE_ROOT_A)
    if len(offsets) != expected_paths:
        raise ValueError(
            f"expected {expected_paths} absolute A: game-data paths, found {len(offsets)}"
        )
    patched = payload.replace(RESOURCE_ROOT_A, RESOURCE_ROOT_B)
    if len(patched) != len(payload):
        raise AssertionError("resource-drive rewrite changed payload size")
    if RESOURCE_ROOT_A in patched:
        raise AssertionError("an A: game-data root remains after rewriting")
    changed = [index for index, pair in enumerate(zip(payload, patched)) if pair[0] != pair[1]]
    if changed != offsets:
        raise AssertionError("resource-drive rewrite changed bytes outside drive letters")
    return patched, offsets, paths


def build_wrapper(
    source_bda: bytes,
    safe_wrapper: bytes,
    guest_path: str,
    output: Path,
    game_payload: bytes | None = None,
) -> dict[str, object]:
    source_header = decode_header(source_bda)
    source_words = struct.unpack_from("<11I", source_header)
    source_payload_offset = source_words[5]
    resource_offset = source_words[6]
    if source_payload_offset != PAYLOAD_OFFSET or not 0x88 <= resource_offset <= PAYLOAD_OFFSET:
        raise ValueError("V1 game does not use the shared 0x785C payload layout")
    source_game_payload = source_bda[source_payload_offset:]
    if game_payload is None:
        game_payload = source_game_payload
    if len(game_payload) != len(source_game_payload):
        raise ValueError("patched V1 game payload changed size")
    if V1_ENTRY_VA + len(game_payload) > COMPATIBILITY_BASE:
        raise ValueError("V1 game payload overlaps the compatibility-table arena")

    wrapper_header = decode_header(safe_wrapper)
    wrapper_payload_offset = int.from_bytes(wrapper_header[0x14:0x18], "little")
    if wrapper_payload_offset != PAYLOAD_OFFSET:
        raise ValueError("safe wrapper does not use the expected payload offset")
    wrapper_payload = patch_external_payload(
        safe_wrapper[wrapper_payload_offset:], guest_path, len(game_payload)
    )
    total_size = PAYLOAD_OFFSET + len(wrapper_payload)
    padding = (-total_size) & 3
    fields = HeaderFields(
        category=source_words[3],
        file_size_minus_4=total_size + padding - 4,
        payload_offset=PAYLOAD_OFFSET,
        resource_offset=resource_offset,
        resource_sizes=tuple(source_words[7:11]),
        version=source_words[2],
    )
    header = encode_header(
        fields,
        title=read_c_string(source_header[0x2C:0x3C]),
        build_time=read_c_string(source_header[0x3C:0x50]),
        description="H1 V2 V1 compat",
    )
    resources = source_bda[resource_offset:PAYLOAD_OFFSET]
    if len(header) + len(resources) != PAYLOAD_OFFSET:
        raise ValueError("V1 resource envelope does not end at 0x785C")
    wrapper = header + resources + wrapper_payload + bytes(padding)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(wrapper)
    validation = validate_bda(output)
    if not validation["ok"]:
        output.unlink(missing_ok=True)
        raise ValueError("generated wrapper failed validation: " + "; ".join(validation["errors"]))
    return {
        "bytes": len(wrapper),
        "sha256": sha256_bytes(wrapper),
        "payload_bytes": len(game_payload),
        "payload_sha256": sha256_bytes(game_payload),
        "guest_payload_path": guest_path,
    }


def short_ascii(name: str) -> bytes:
    stem, suffix = name.split(".", 1)
    if not 1 <= len(stem) <= 8 or not 1 <= len(suffix) <= 3:
        raise ValueError(f"not an 8.3 filename: {name}")
    return (stem.upper().ljust(8) + suffix.upper().ljust(3)).encode("ascii")


def add_file(
    tree: FatTree,
    free_clusters: list[int],
    parent_cluster: int | None,
    long_name: str | None,
    short_raw: bytes,
    payload: bytes,
) -> list[int]:
    count = max(1, (len(payload) + tree.cluster_size - 1) // tree.cluster_size)
    chain = tree.allocate_chain(free_clusters, count)
    entries = lfn_entries(long_name, short_raw) if long_name else []
    entries.append(short_entry(short_raw, 0x20, chain[0], len(payload)))
    tree.put_entries(parent_cluster, entries)
    tree.write_chain(chain, payload)
    return chain


def install_suite(
    template: Path,
    output: Path,
    v1_image: Path,
    wrapper_template: Path,
    manifest_path: Path,
    scan_start_block: int,
    scan_end_block: int,
    b_scan_end_block: int,
    v1_scan_start_block: int,
    ecc_helper: Path | None,
) -> dict[str, object]:
    if output.exists():
        raise FileExistsError(f"refusing to overwrite existing output: {output}")
    safe_wrapper = wrapper_template.read_bytes()
    wrapper_sha = sha256_bytes(safe_wrapper)
    if wrapper_sha != SAFE_WRAPPER_SHA256:
        raise ValueError(
            f"wrapper template is not the verified stage-arena build: {wrapper_sha}"
        )

    source_games: dict[str, tuple[bytes, FatEntry]] = {}
    resource_files: dict[str, tuple[bytes, FatEntry]] = {}
    for spec in GAMES:
        source_games[spec.name] = read_v1_file(
            v1_image, f"应用\\程序\\{spec.name}.bda", v1_scan_start_block
        )
        for resource in spec.resources:
            if resource not in resource_files:
                resource_files[resource] = read_v1_file(
                    v1_image,
                    f"应用\\数据\\游戏\\{resource}",
                    v1_scan_start_block,
                )

    if not scan_start_block < scan_end_block < b_scan_end_block:
        raise ValueError("A/B scan windows must be ordered and non-empty")

    with tempfile.TemporaryDirectory(prefix="h1-v2-v1-suite-") as temporary:
        stage = Path(temporary)
        source_paths = []
        wrappers: dict[str, tuple[bytes, dict[str, object]]] = {}
        patched_payloads: dict[str, bytes] = {}
        path_rewrites: dict[str, dict[str, object]] = {}
        for spec in GAMES:
            source_data, _ = source_games[spec.name]
            source_path = stage / f"{spec.name}.bda"
            source_path.write_bytes(source_data)
            source_paths.append(source_path)
            original_payload = source_data[PAYLOAD_OFFSET:]
            patched_payload, offsets, original_paths = patch_game_resource_drive(
                original_payload, spec.expected_absolute_paths
            )
            patched_payloads[spec.name] = patched_payload
            path_rewrites[spec.name] = {
                "count": len(offsets),
                "payload_offsets": [f"0x{offset:X}" for offset in offsets],
                "old_paths": original_paths,
                "new_paths": ["B:" + path[2:] for path in original_paths],
            }
            wrapper_path = stage / "wrappers" / f"{spec.name}.bda"
            wrapper_report = build_wrapper(
                source_data,
                safe_wrapper,
                spec.guest_payload_path,
                wrapper_path,
                patched_payload,
            )
            wrappers[spec.name] = (wrapper_path.read_bytes(), wrapper_report)
        coverage = build_report(source_paths)
        if coverage["unmapped"]:
            raise ValueError(
                f"compatibility coverage has {len(coverage['unmapped'])} unmapped services"
            )

        a_offset = scan_start_block * RAW_ERASE_BLOCK_SIZE
        b_offset = scan_end_block * RAW_ERASE_BLOCK_SIZE
        template_boot = hash_region(template, 0, a_offset)
        template_b = hash_region(template, b_offset)
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(template, output)
        chains: dict[str, dict[str, int]] = {}

        expected_a: dict[str, bytes] = {}
        a_volume = LogicalVolume(
            output,
            scan_start_block,
            writable=True,
            scan_end_block=scan_end_block,
        )
        try:
            a_tree = FatTree(a_volume)
            a_free = a_tree.free_clusters()
            a_free_before = len(a_free)
            program_cluster = a_tree.resolve(PROGRAM_DIRECTORY).first_cluster
            for spec in GAMES:
                source_entry = source_games[spec.name][1]
                payload = patched_payloads[spec.name]
                payload_internal = spec.payload_name
                try:
                    a_tree.resolve(payload_internal)
                    raise FileExistsError(spec.guest_payload_path)
                except FileNotFoundError:
                    pass
                chain = add_file(
                    a_tree,
                    a_free,
                    None,
                    None,
                    short_ascii(payload_internal),
                    payload,
                )
                expected_a[payload_internal] = payload
                chains[spec.guest_payload_path] = {
                    "first": chain[0],
                    "clusters": len(chain),
                }

                wrapper_name = f"{spec.name}.bda"
                wrapper_internal = f"{PROGRAM_DIRECTORY}\\{wrapper_name}"
                try:
                    a_tree.resolve(wrapper_internal)
                    raise FileExistsError(spec.guest_wrapper_path)
                except FileNotFoundError:
                    pass
                wrapper_data = wrappers[spec.name][0]
                chain = add_file(
                    a_tree,
                    a_free,
                    program_cluster,
                    source_entry.long_name or wrapper_name,
                    source_entry.short_raw,
                    wrapper_data,
                )
                expected_a[wrapper_internal] = wrapper_data
                chains[spec.guest_wrapper_path] = {
                    "first": chain[0],
                    "clusters": len(chain),
                }
            a_tree.write_fat()
            sequences = [
                record.sequence or 0 for record in a_volume.result.mapping.values()
            ]
            sequence = ((max(sequences) if sequences else 0) + 1) & 0xFFFF or 1
            a_write_report = a_volume.flush(ecc_helper, sequence)
            a_free_after = len(a_free)
        except Exception:
            a_volume.close()
            output.unlink(missing_ok=True)
            raise

        checked_a = LogicalVolume(
            output,
            scan_start_block,
            writable=False,
            scan_end_block=scan_end_block,
        )
        try:
            checked_a_tree = FatTree(checked_a)
            a_readback: dict[str, dict[str, object]] = {}
            for path, wanted in expected_a.items():
                entry = checked_a_tree.resolve(path)
                observed = checked_a_tree.read_file(entry)
                if observed != wanted:
                    raise IOError(f"A: readback mismatch for {path}")
                full_path = f"A:\\{path}"
                a_readback[full_path] = {
                    "bytes": len(observed),
                    "sha256": sha256_bytes(observed),
                    "first_cluster": entry.first_cluster,
                }
            a_mapped_after = len(checked_a.result.mapping)
        finally:
            checked_a.close()

        if hash_region(output, 0, a_offset) != template_boot:
            output.unlink(missing_ok=True)
            raise IOError("boot prefix changed while adding A-volume executables")
        post_a_prefix = hash_region(output, 0, b_offset)
        if hash_region(output, b_offset) != template_b:
            output.unlink(missing_ok=True)
            raise IOError("B partition changed while adding A-volume executables")

        expected_b: dict[str, bytes] = {}
        b_volume = LogicalVolume(
            output,
            scan_end_block,
            writable=True,
            scan_end_block=b_scan_end_block,
        )
        try:
            b_tree = FatTree(b_volume)
            b_free = b_tree.free_clusters()
            b_free_before = len(b_free)
            game_cluster = b_tree.resolve(GAME_DATA_DIRECTORY).first_cluster
            for resource, (payload, source_entry) in resource_files.items():
                target_name = source_entry.long_name or resource
                target = f"{GAME_DATA_DIRECTORY}\\{target_name}"
                try:
                    b_tree.resolve(target)
                    raise FileExistsError(f"B:\\{target}")
                except FileNotFoundError:
                    pass
                chain = add_file(
                    b_tree,
                    b_free,
                    game_cluster,
                    target_name,
                    source_entry.short_raw,
                    payload,
                )
                expected_b[target] = payload
                chains[f"B:\\{target}"] = {
                    "first": chain[0],
                    "clusters": len(chain),
                }
            b_tree.write_fat()
            sequences = [
                record.sequence or 0 for record in b_volume.result.mapping.values()
            ]
            sequence = ((max(sequences) if sequences else 0) + 1) & 0xFFFF or 1
            b_write_report = b_volume.flush(ecc_helper, sequence)
            b_free_after = len(b_free)
        except Exception:
            b_volume.close()
            output.unlink(missing_ok=True)
            raise

        checked_b = LogicalVolume(
            output,
            scan_end_block,
            writable=False,
            scan_end_block=b_scan_end_block,
        )
        try:
            checked_b_tree = FatTree(checked_b)
            b_readback: dict[str, dict[str, object]] = {}
            for path, wanted in expected_b.items():
                entry = checked_b_tree.resolve(path)
                observed = checked_b_tree.read_file(entry)
                if observed != wanted:
                    raise IOError(f"B: readback mismatch for {path}")
                full_path = f"B:\\{path}"
                b_readback[full_path] = {
                    "bytes": len(observed),
                    "sha256": sha256_bytes(observed),
                    "first_cluster": entry.first_cluster,
                }
            b_mapped_after = len(checked_b.result.mapping)
        finally:
            checked_b.close()

    if hash_region(output, 0, b_offset) != post_a_prefix:
        output.unlink(missing_ok=True)
        raise IOError("boot/A byte range changed while adding B-volume resources")
    output_b = hash_region(output, b_offset)
    if output_b == template_b:
        output.unlink(missing_ok=True)
        raise IOError("B partition did not change while adding game resources")

    installed_files = {**a_readback, **b_readback}
    resource_full_paths = {
        resource: next(
            path for path in b_readback if path.casefold().endswith(("\\" + resource).casefold())
        )
        for resource in resource_files
    }
    report = {
        "format": "h1-v2-v1-game-suite-v2",
        "template_name": template.name,
        "template_sha256": sha256_file(template),
        "output_name": output.name,
        "output_bytes": output.stat().st_size,
        "output_sha256": sha256_file(output),
        "v1_image_name": v1_image.name,
        "v1_image_sha256": sha256_file(v1_image),
        "safe_wrapper_sha256": wrapper_sha,
        "scan_window": {
            "A:": {
                "start_block": scan_start_block,
                "end_block_exclusive": scan_end_block,
            },
            "B:": {
                "start_block": scan_end_block,
                "end_block_exclusive": b_scan_end_block,
            },
        },
        "coverage": {
            "games": len(coverage["games"]),
            "unique_services": coverage["unique_services"],
            "unmapped": len(coverage["unmapped"]),
            "action_counts": coverage["action_counts"],
        },
        "games": [
            {
                "name": spec.name,
                **wrappers[spec.name][1],
                "wrapper_path": spec.guest_wrapper_path,
                "payload_path": spec.guest_payload_path,
                "resource_paths": [
                    resource_full_paths[resource] for resource in spec.resources
                ],
                "absolute_path_rewrites": path_rewrites[spec.name],
            }
            for spec in GAMES
        ],
        "installed_files": installed_files,
        "chains": chains,
        "volumes": {
            "A:": {
                "role": "launchers-and-executable-payloads",
                "fat_free_clusters_before": a_free_before,
                "fat_free_clusters_after": a_free_after,
                "ftl_mapped_logical_units_after": a_mapped_after,
                "write": a_write_report,
                "sha256": hash_region(output, a_offset, b_offset - a_offset),
            },
            "B:": {
                "role": "all-game-resources",
                "fat_free_clusters_before": b_free_before,
                "fat_free_clusters_after": b_free_after,
                "ftl_mapped_logical_units_after": b_mapped_after,
                "write": b_write_report,
                "sha256": output_b,
            },
        },
        "boot_prefix_sha256": template_boot,
        "template_b_partition_sha256": template_b,
        "resource_policy": "all packaged game resources are B:-resident",
        "mission_install_preserved": True,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--v1-image", type=Path, required=True)
    parser.add_argument("--wrapper-template", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--scan-start-block", type=lambda value: int(value, 0), default=0x40)
    parser.add_argument("--scan-end-block", type=lambda value: int(value, 0), default=0x6F4)
    parser.add_argument("--b-scan-end-block", type=lambda value: int(value, 0), default=0x1000)
    parser.add_argument("--v1-scan-start-block", type=lambda value: int(value, 0), default=0x40)
    parser.add_argument("--ecc-helper", type=Path, default=default_ecc_helper())
    parser.add_argument("--python-ecc", action="store_true")
    args = parser.parse_args()
    report = install_suite(
        args.template.resolve(strict=True),
        args.output.resolve(),
        args.v1_image.resolve(strict=True),
        args.wrapper_template.resolve(strict=True),
        args.manifest.resolve(),
        args.scan_start_block,
        args.scan_end_block,
        args.b_scan_end_block,
        args.v1_scan_start_block,
        None if args.python_ecc else args.ecc_helper.resolve(strict=True),
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
