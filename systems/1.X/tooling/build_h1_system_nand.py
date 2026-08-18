#!/usr/bin/env python3
"""Stream the H1 recovery tree directly into a guest-compatible FAT16/FTL NAND."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import struct
import subprocess
import sys
import time
from dataclasses import asdict, replace
from pathlib import Path

if __package__:
    from .h1_fat16 import (
        LOGICAL_UNIT_SIZE,
        Extent,
        FatGeometry,
        FatPlan,
        build_plan,
        iter_logical_units,
    )
    from .h1_ftl import (
        DEFAULT_SCAN_START_BLOCK,
        PAGE_SIZE,
        PAGE_STRIDE,
        PAGES_PER_FTL_UNIT,
        SPARE_SIZE,
        FtlRecord,
        fat_geometry,
        read_logical_unit,
        read_oob,
        scan_image,
        sequence_is_newer,
    )
    from .jz4740_ecc import jz4740_page_oob_ecc
else:
    from h1_fat16 import (
        LOGICAL_UNIT_SIZE,
        Extent,
        FatGeometry,
        FatPlan,
        build_plan,
        iter_logical_units,
    )
    from h1_ftl import (
        DEFAULT_SCAN_START_BLOCK,
        PAGE_SIZE,
        PAGE_STRIDE,
        PAGES_PER_FTL_UNIT,
        SPARE_SIZE,
        FtlRecord,
        fat_geometry,
        read_logical_unit,
        read_oob,
        scan_image,
        sequence_is_newer,
    )
    from jz4740_ecc import jz4740_page_oob_ecc

DATA_ECC_OOB_OFFSET = 4
FTL_LOGICAL_HIGH_BITS = 0xFFFF0000
ECC_BYTES_PER_PAGE = 36
MAX_ECC_BATCH_PAGES = 64
ERASED_SLOT = b"\xFF" * (PAGE_STRIDE * PAGES_PER_FTL_UNIT)
COPY_CHUNK = 16 * 1024 * 1024
VERIFY_CHUNK = 1024 * 1024


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(COPY_CHUNK):
            digest.update(chunk)
    return digest.hexdigest().upper()


def apply_mapping_overrides(scan_result, values: list[str]) -> list[dict[str, int]]:
    applied: list[dict[str, int]] = []
    for value in values:
        logical_text, separator, location = value.partition("=")
        if not separator:
            raise ValueError(f"mapping override must be LOGICAL=BLOCK[:SLOT], got {value!r}")
        block_text, slot_separator, slot_text = location.partition(":")
        logical = int(logical_text, 0)
        physical_block = int(block_text, 0)
        slot = int(slot_text, 0) if slot_separator else 0
        matches = [
            record
            for record in scan_result.records
            if record.kind == "mapped"
            and record.logical == logical
            and record.physical_block == physical_block
            and record.slot == slot
        ]
        if len(matches) != 1:
            raise ValueError(
                f"mapping override {value!r} matched {len(matches)} committed records"
            )
        record = matches[0]
        scan_result.mapping[logical] = record
        applied.append(
            {
                "logical": logical,
                "physical_block": physical_block,
                "slot": slot,
                "sequence": int(record.sequence or 0),
            }
        )
    return applied


def read_exact(stream, size: int) -> bytes:
    output = bytearray()
    while len(output) < size:
        chunk = stream.read(size - len(output))
        if not chunk:
            raise IOError(f"ECC helper ended after {len(output)} of {size} bytes")
        output.extend(chunk)
    return bytes(output)


class EccEncoder:
    def __init__(self, helper: Path | None):
        self.helper = helper.resolve() if helper is not None else None
        self.process: subprocess.Popen | None = None

    def __enter__(self) -> "EccEncoder":
        if self.helper is not None:
            if not self.helper.is_file():
                raise FileNotFoundError(self.helper)
            self.process = subprocess.Popen(
                [str(self.helper)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        return self

    def encode_pages(self, pages: list[bytes]) -> list[bytes]:
        if not pages:
            return []
        if any(len(page) != PAGE_SIZE for page in pages):
            raise ValueError("ECC input pages must be exactly 2,048 bytes")
        if self.process is None:
            return [jz4740_page_oob_ecc(page, offset=DATA_ECC_OOB_OFFSET)[4:] for page in pages]
        assert self.process.stdin is not None and self.process.stdout is not None
        encoded: list[bytes] = []
        # Keep helper output below the Windows anonymous-pipe capacity while
        # the parent is still writing the corresponding page batch.
        for start in range(0, len(pages), MAX_ECC_BATCH_PAGES):
            batch = pages[start : start + MAX_ECC_BATCH_PAGES]
            self.process.stdin.write(b"".join(batch))
            self.process.stdin.flush()
            output = read_exact(self.process.stdout, len(batch) * ECC_BYTES_PER_PAGE)
            encoded.extend(
                output[index : index + ECC_BYTES_PER_PAGE]
                for index in range(0, len(output), ECC_BYTES_PER_PAGE)
            )
        return encoded

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        if self.process is None:
            return
        assert self.process.stdin is not None
        self.process.stdin.close()
        code = self.process.wait(timeout=30)
        stderr = b""
        if self.process.stderr is not None:
            stderr = self.process.stderr.read()
            self.process.stderr.close()
        if code and exc_type is None:
            raise RuntimeError(
                f"ECC helper exited with {code}: {stderr.decode(errors='replace').strip()}"
            )


def geometry_from_template(logical_zero: bytes) -> FatGeometry:
    parsed = fat_geometry(logical_zero)
    geometry = FatGeometry(
        boot_lba=int(parsed["boot_lba"]),
        bytes_per_sector=int(parsed["bytes_per_sector"]),
        sectors_per_cluster=int(parsed["sectors_per_cluster"]),
        reserved_sectors=int(parsed["reserved_sectors"]),
        fat_copies=int(parsed["fat_copies"]),
        root_entries=int(parsed["root_entries"]),
        sectors_per_fat=int(parsed["sectors_per_fat"]),
        hidden_sectors=int(parsed["hidden_sectors"]),
        total_sectors=int(parsed["total_sectors"]),
    )
    geometry.validate()
    return geometry


def patch_fat_boot_geometry(logical_zero: bytes, geometry: FatGeometry) -> bytes:
    patched = bytearray(logical_zero)
    boot = geometry.boot_lba * geometry.bytes_per_sector
    struct.pack_into("<H", patched, boot + 11, geometry.bytes_per_sector)
    patched[boot + 13] = geometry.sectors_per_cluster
    struct.pack_into("<H", patched, boot + 14, geometry.reserved_sectors)
    patched[boot + 16] = geometry.fat_copies
    struct.pack_into("<H", patched, boot + 17, geometry.root_entries)
    if geometry.total_sectors <= 0xFFFF:
        struct.pack_into("<H", patched, boot + 19, geometry.total_sectors)
        struct.pack_into("<I", patched, boot + 32, 0)
    else:
        struct.pack_into("<H", patched, boot + 19, 0)
        struct.pack_into("<I", patched, boot + 32, geometry.total_sectors)
    struct.pack_into("<H", patched, boot + 22, geometry.sectors_per_fat)
    struct.pack_into("<I", patched, boot + 28, geometry.hidden_sectors)
    return bytes(patched)


def root_volume_label_from_template(stream, template_result, geometry: FatGeometry) -> bytes:
    root_start = (
        geometry.boot_lba
        + geometry.reserved_sectors
        + geometry.fat_copies * geometry.sectors_per_fat
    ) * geometry.bytes_per_sector
    logical = root_start // LOGICAL_UNIT_SIZE
    within = root_start % LOGICAL_UNIT_SIZE
    unit = read_logical_unit(stream, template_result.mapping.get(logical))
    entry = unit[within : within + 32]
    if len(entry) != 32 or not entry[11] & 0x08 or entry[11] == 0x0F:
        raise ValueError("guest template root directory has no leading volume-label entry")
    return entry


def programmed_pages_from_template(template_result) -> dict[int, set[int]]:
    result: dict[int, set[int]] = {}
    with template_result.path.open("rb") as stream:
        for logical, record in template_result.mapping.items():
            expected_tail = (record.sequence or 0).to_bytes(2, "little") + (
                record.tail or 0
            ).to_bytes(4, "little")
            pages = {
                page
                for page in range(PAGES_PER_FTL_UNIT)
                if (oob := read_oob(stream, record.first_page + page))[1] != 0xFF
                and oob[-6:] == expected_tail
            }
            if pages:
                result[logical] = pages
    return result


def copy_template(source: Path, target: Path) -> None:
    with source.open("rb") as input_stream, target.open("xb") as output_stream:
        shutil.copyfileobj(input_stream, output_stream, COPY_CHUNK)
        output_stream.flush()
        os.fsync(output_stream.fileno())


def make_ftl_oob(parity: bytes, logical: int, sequence: int, last_valid: int) -> bytes:
    if len(parity) != ECC_BYTES_PER_PAGE:
        raise ValueError("unexpected JZ4740 page parity length")
    oob = bytearray(b"\xFF" * SPARE_SIZE)
    oob[1] = 0
    struct.pack_into("<H", oob, 2, last_valid)
    oob[DATA_ECC_OOB_OFFSET : DATA_ECC_OOB_OFFSET + len(parity)] = parity
    struct.pack_into("<H", oob, SPARE_SIZE - 6, sequence & 0xFFFF)
    struct.pack_into("<I", oob, SPARE_SIZE - 4, FTL_LOGICAL_HIGH_BITS | logical)
    return bytes(oob)


def write_mapped_unit(
    output,
    record: FtlRecord,
    logical: int,
    data: bytes,
    sequence: int,
    encoder: EccEncoder,
    required_pages: set[int] | None = None,
) -> int:
    if len(data) != LOGICAL_UNIT_SIZE:
        raise ValueError("logical FTL unit must be exactly 256 KiB")
    if not 0 <= logical <= 0xFFFF:
        raise ValueError(f"logical unit does not fit the H1 OOB tag: {logical}")
    # The H1 guest returns the NAND erase value for pages without a valid OOB
    # entry.  Program zero-filled pages too; otherwise black resource regions
    # become 0xFFFFFFFF even though an offline sparse reader reconstructs zero.
    valid = set(range(PAGES_PER_FTL_UNIT))
    valid.update(required_pages or ())
    valid = sorted(valid)
    last_valid = max(valid)
    pages = [data[page * PAGE_SIZE : (page + 1) * PAGE_SIZE] for page in valid]
    parity = encoder.encode_pages(pages)

    output.seek(record.first_page * PAGE_STRIDE)
    output.write(ERASED_SLOT)
    for page_index, page_data, page_parity in zip(valid, pages, parity):
        physical_page = record.first_page + page_index
        output.seek(physical_page * PAGE_STRIDE)
        output.write(page_data)
        output.write(make_ftl_oob(page_parity, logical, sequence, last_valid))
    return len(valid)


def plan_report(plan: FatPlan) -> dict[str, object]:
    return {
        "geometry": asdict(plan.geometry),
        "cluster_count": plan.geometry.cluster_count,
        "used_clusters": plan.used_clusters,
        "free_clusters": plan.free_clusters,
        "cluster_bytes": plan.geometry.cluster_size,
        "source_files": plan.source_files,
        "source_directories": plan.source_directories,
        "source_bytes": plan.source_bytes,
        "planned_extents": len(plan.extents),
        "disk_bytes": plan.geometry.disk_bytes,
    }


def stream_into_nand(
    template_result,
    plan: FatPlan,
    output_path: Path,
    helper: Path | None,
    sequence: int,
    map_zero_units_through_used: bool = False,
    template_programmed_pages: dict[int, set[int]] | None = None,
) -> dict[str, object]:
    bbt_records = [record for record in template_result.records if record.kind == "bbt"]
    selected_bbt: FtlRecord | None = None
    for record in bbt_records:
        if selected_bbt is None or sequence_is_newer(
            record.sequence or 0,
            selected_bbt.sequence or 0,
        ):
            selected_bbt = record
    if selected_bbt is None:
        raise ValueError("guest template contains no BBT slot")
    allocation_start = selected_bbt.physical_block
    free_records = iter(
        record
        for record in template_result.records
        if record.kind == "free" and record.physical_block >= allocation_start
    )
    selected: set[tuple[int, int]] = set()
    mapped_units = 0
    programmed_pages = 0
    started = time.perf_counter()
    with output_path.open("r+b", buffering=0) as output, EccEncoder(helper) as encoder:
        for logical, data in iter_logical_units(
            plan, map_zero_units_through_used=map_zero_units_through_used
        ):
            record = template_result.mapping.get(logical)
            if record is None:
                try:
                    record = next(free_records)
                except StopIteration as error:
                    raise ValueError(f"FTL has no free slot for logical unit {logical}") from error
            key = (record.physical_block, record.slot)
            if key in selected:
                raise ValueError(f"FTL allocator selected slot twice: {key}")
            selected.add(key)
            programmed_pages += write_mapped_unit(
                output,
                record,
                logical,
                data,
                sequence,
                encoder,
                (template_programmed_pages or {}).get(logical),
            )
            mapped_units += 1
            if mapped_units % 512 == 0:
                print(
                    f"mapped {mapped_units} units, {programmed_pages} pages",
                    file=sys.stderr,
                    flush=True,
                )

        # Erase every stale mapped or BBT record, not only the record selected
        # by the scanner. Runtime images can contain older copies and the guest
        # FTL is free to resolve equal generations differently from this
        # offline scanner.
        selected_bbt_key = (selected_bbt.physical_block, selected_bbt.slot)
        for record in template_result.records:
            if record.kind not in {"mapped", "bbt"}:
                continue
            key = (record.physical_block, record.slot)
            keep = key in selected or (record.kind == "bbt" and key == selected_bbt_key)
            if not keep:
                output.seek(record.first_page * PAGE_STRIDE)
                output.write(ERASED_SLOT)
        output.flush()
        os.fsync(output.fileno())
    return {
        "allocation_start_block": allocation_start,
        "bbt_slots_found": len(bbt_records),
        "bbt_slots_preserved": 1,
        "selected_bbt_block": selected_bbt.physical_block,
        "selected_bbt_sequence": selected_bbt.sequence,
        "mapped_logical_units": mapped_units,
        "programmed_pages": programmed_pages,
        "remaining_free_slots": sum(
            record.kind == "free" and record.physical_block >= allocation_start
            for record in template_result.records
        )
        - sum(key not in {(r.physical_block, r.slot) for r in template_result.mapping.values()} for key in selected),
        "sequence": sequence & 0xFFFF,
        "map_zero_units_through_used": map_zero_units_through_used,
        "template_programmed_pages_preserved": sum(
            len(pages) for pages in (template_programmed_pages or {}).values()
        ),
        "write_seconds": round(time.perf_counter() - started, 3),
    }


class LogicalReader:
    def __init__(self, path: Path, scan_result):
        self.stream = path.open("rb")
        self.mapping = scan_result.mapping
        self.cached_logical: int | None = None
        self.cached_data = b""

    def close(self) -> None:
        self.stream.close()

    def _unit(self, logical: int) -> bytes:
        if logical != self.cached_logical:
            self.cached_data = read_logical_unit(self.stream, self.mapping.get(logical))
            self.cached_logical = logical
        return self.cached_data

    def read(self, offset: int, size: int) -> bytes:
        output = bytearray()
        while size:
            logical = offset // LOGICAL_UNIT_SIZE
            within = offset % LOGICAL_UNIT_SIZE
            count = min(size, LOGICAL_UNIT_SIZE - within)
            output.extend(self._unit(logical)[within : within + count])
            offset += count
            size -= count
        return bytes(output)


def verify_extent(reader: LogicalReader, extent: Extent, system_root: Path) -> dict[str, object]:
    expected_digest = hashlib.sha256()
    actual_digest = hashlib.sha256()
    remaining = extent.length
    offset = 0
    source_stream = extent.source.open("rb") if extent.source is not None else None
    try:
        while remaining:
            count = min(remaining, VERIFY_CHUNK)
            if extent.data is not None:
                expected = extent.data[offset : offset + count]
            else:
                assert source_stream is not None
                expected = source_stream.read(count)
            actual = reader.read(extent.start + offset, count)
            if len(expected) != count or len(actual) != count:
                raise IOError(f"short verification read for {extent.name}")
            expected_digest.update(expected)
            actual_digest.update(actual)
            if expected != actual:
                raise ValueError(f"FTL verification mismatch in {extent.name} at +0x{offset:x}")
            remaining -= count
            offset += count
    finally:
        if source_stream is not None:
            source_stream.close()
    source_name = None
    if extent.source is not None:
        try:
            source_name = str(extent.source.resolve().relative_to(system_root.resolve()))
        except ValueError:
            source_name = str(extent.source.resolve())
    return {
        "name": extent.name,
        "source": source_name,
        "bytes": extent.length,
        "sha256": actual_digest.hexdigest().upper(),
        "match": actual_digest.digest() == expected_digest.digest(),
    }


def verify_output(
    path: Path,
    plan: FatPlan,
    system_root: Path,
    scan_start_block: int,
) -> dict[str, object]:
    started = time.perf_counter()
    result = scan_image(path, scan_start_block)
    if any(record.kind in {"bad", "invalid", "torn"} for record in result.records):
        raise ValueError("output FTL scan contains bad, invalid, or torn slots")
    mapped_records: dict[int, list[FtlRecord]] = {}
    for record in result.records:
        if record.kind == "mapped" and record.logical is not None:
            mapped_records.setdefault(record.logical, []).append(record)
    duplicates = {
        logical: records
        for logical, records in mapped_records.items()
        if len(records) != 1
    }
    if duplicates:
        raise ValueError(
            "output FTL contains duplicate logical mappings: "
            + ", ".join(str(logical) for logical in sorted(duplicates)[:16])
        )
    bbt_records = [record for record in result.records if record.kind == "bbt"]
    if len(bbt_records) != 1:
        raise ValueError(f"output FTL must contain one BBT slot, found {len(bbt_records)}")
    reader = LogicalReader(path, result)
    try:
        extents = [verify_extent(reader, extent, system_root) for extent in plan.extents]
        logical_zero = reader.read(0, LOGICAL_UNIT_SIZE)
    finally:
        reader.close()
    parsed_geometry = fat_geometry(logical_zero)
    expected_geometry = asdict(plan.geometry)
    for key, value in expected_geometry.items():
        if key in parsed_geometry and parsed_geometry[key] != value:
            raise ValueError(
                f"FAT geometry mismatch for {key}: {parsed_geometry[key]} != {value}"
            )
    return {
        "mapped_logical_units": len(result.mapping),
        "duplicate_logical_mappings": len(duplicates),
        "scan_start_block": result.scan_start_block,
        "free_slots": sum(record.kind == "free" for record in result.records),
        "bbt_slots": len(bbt_records),
        "invalid_or_torn_slots": sum(
            record.kind in {"invalid", "torn"} for record in result.records
        ),
        "verified_extents": len(extents),
        "verified_files": sum(extent["source"] is not None for extent in extents),
        "verified_bytes": sum(int(extent["bytes"]) for extent in extents),
        "seconds": round(time.perf_counter() - started, 3),
        "files": [extent for extent in extents if extent["source"] is not None],
    }


def main() -> int:
    repository = Path(__file__).resolve().parents[1]
    default_helper = repository / "work" / "tools" / "jz4740-ecc-x86_64.exe"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--system-data", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--ecc-helper", type=Path, default=default_helper)
    parser.add_argument("--python-ecc", action="store_true")
    parser.add_argument("--sequence", type=lambda value: int(value, 0), default=1)
    parser.add_argument(
        "--root-volume-label-entry-hex",
        help="verified 32-byte FAT root volume-label entry, encoded as hex",
    )
    parser.add_argument(
        "--mapping-override",
        action="append",
        default=[],
        metavar="LOGICAL=BLOCK[:SLOT]",
        help="select a verified template record when generic sequence ordering is ambiguous",
    )
    parser.add_argument(
        "--scan-start-block",
        type=lambda value: int(value, 0),
        default=DEFAULT_SCAN_START_BLOCK,
        help="first physical FTL block (default: 0x3e for H1 V1; H1 V2 uses 0x40)",
    )
    parser.add_argument(
        "--emulator-expanded",
        action="store_true",
        help="allow an emulator-only NAND larger than the 4,096-block production device",
    )
    parser.add_argument(
        "--sectors-per-cluster",
        type=int,
        choices=(32, 64),
        help="override FAT sectors per cluster for an expanded emulator image",
    )
    parser.add_argument(
        "--total-sectors",
        type=int,
        help="override FAT total sectors for an expanded emulator image",
    )
    parser.add_argument(
        "--map-zero-units-through-used",
        action="store_true",
        help="map every logical unit through the last used FAT extent",
    )
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--no-verify", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    template = args.template.resolve()
    system_root = args.system_data.resolve()
    template_result = scan_image(template, args.scan_start_block)
    mapping_overrides = apply_mapping_overrides(template_result, args.mapping_override)
    if template_result.physical_blocks != 4096 and not args.emulator_expanded:
        raise ValueError(
            f"H1 production template must have 4,096 physical blocks, got {template_result.physical_blocks}"
        )
    if (args.sectors_per_cluster or args.total_sectors) and not args.emulator_expanded:
        raise ValueError("FAT geometry overrides require --emulator-expanded")
    with template.open("rb") as stream:
        logical_zero = read_logical_unit(stream, template_result.mapping.get(0))
    template_programmed_pages = programmed_pages_from_template(template_result)
    geometry = geometry_from_template(logical_zero)
    geometry = replace(
        geometry,
        sectors_per_cluster=args.sectors_per_cluster or geometry.sectors_per_cluster,
        total_sectors=args.total_sectors or geometry.total_sectors,
    )
    geometry.validate()
    if args.root_volume_label_entry_hex:
        try:
            root_volume_label = bytes.fromhex(args.root_volume_label_entry_hex)
        except ValueError as error:
            raise ValueError("root volume-label entry is not valid hexadecimal") from error
        if len(root_volume_label) != 32:
            raise ValueError("root volume-label entry must decode to exactly 32 bytes")
        attributes = root_volume_label[11]
        if not attributes & 0x08 or attributes == 0x0F:
            raise ValueError("root volume-label override is not a FAT volume-label entry")
        root_volume_label_source = "explicit"
    else:
        with template.open("rb") as stream:
            root_volume_label = root_volume_label_from_template(
                stream, template_result, geometry_from_template(logical_zero)
            )
        root_volume_label_source = "template"
    logical_zero = patch_fat_boot_geometry(logical_zero, geometry)
    plan = build_plan(
        system_root,
        logical_zero,
        geometry,
        root_volume_label_entry=root_volume_label,
    )
    report: dict[str, object] = {
        "format": "bbk-h1-system-nand-v1",
        "template": str(template),
        "system_data": str(system_root),
        "root_volume_label_entry_hex": root_volume_label.hex().upper(),
        "root_volume_label_source": root_volume_label_source,
        "mapping_overrides": mapping_overrides,
        "plan": plan_report(plan),
    }
    if args.plan_only:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    if args.output is None:
        parser.error("--output is required unless --plan-only is used")

    output = args.output.resolve()
    temporary = output.with_name(output.name + ".tmp")
    if output == template:
        raise ValueError("output must not overwrite the guest-created template")
    for target in (output, temporary):
        if target.exists():
            if not args.force:
                raise FileExistsError(f"refusing to overwrite {target}; pass --force")
            target.unlink()
    output.parent.mkdir(parents=True, exist_ok=True)
    helper = None if args.python_ecc else args.ecc_helper
    try:
        copy_template(template, temporary)
        report["ftl_write"] = stream_into_nand(
            template_result,
            plan,
            temporary,
            helper,
            args.sequence,
            args.map_zero_units_through_used,
            template_programmed_pages,
        )
        if not args.no_verify:
            report["verification"] = verify_output(
                temporary,
                plan,
                system_root,
                args.scan_start_block,
            )
        report["output"] = str(output)
        report["output_bytes"] = temporary.stat().st_size
        report["output_sha256"] = sha256_file(temporary)
        report["ecc"] = {
            "implementation": "python" if helper is None else str(helper.resolve()),
            "helper_sha256": None if helper is None else sha256_file(helper.resolve()),
            "oob_offset": DATA_ECC_OOB_OFFSET,
        }
        os.replace(temporary, output)
    except BaseException:
        if temporary.exists():
            temporary.unlink()
        raise

    manifest = args.manifest or output.with_suffix(output.suffix + ".json")
    manifest.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    manifest.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
