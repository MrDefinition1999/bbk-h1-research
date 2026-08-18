#!/usr/bin/env python3
"""Build an isolated H1 V2 NAND from decoded boot images and V2 files."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from decode_bda import HEADER_SIZE
from make_h1_nand import PAGE_SIZE, PAGE_STRIDE, PAGES_PER_BLOCK, page_oob
from validate_h1_v2_bda_sources import validate_header


SPARE_SIZE = PAGE_STRIDE - PAGE_SIZE
BOOT_BLOCKS = 64
ERASE_BLOCK_BYTES = PAGE_STRIDE * PAGES_PER_BLOCK
ERASE_BLOCK_DATA_BYTES = PAGE_SIZE * PAGES_PER_BLOCK
ERASED_CHUNK = b"\xff" * (1024 * 1024)
NATIVE_ROOT_VOLUME_LABEL_ENTRY_HEX = (
    "4831202020202020202020080000000000000000000000000000000000000000"
)
NATIVE_TEMPLATE_SHA256 = "7E3FE874C6221B58EC638A41938A465D7697FF1CDA324BAAB764B0E1F582A0C3"
EXPECTED_V2_BDA_COUNT = 61


@dataclass(frozen=True)
class Segment:
    name: str
    source: Path
    start_block: int
    partition_blocks: int
    fixed_program_bytes: int | None = None

    @property
    def payload(self) -> bytes:
        return self.source.read_bytes()

    @property
    def program_bytes(self) -> int:
        size = len(self.payload) if self.fixed_program_bytes is None else self.fixed_program_bytes
        alignment = PAGE_SIZE if self.fixed_program_bytes is not None else ERASE_BLOCK_DATA_BYTES
        return (size + alignment - 1) // alignment * alignment

    @property
    def pages(self) -> int:
        return self.program_bytes // PAGE_SIZE

    @property
    def start_page(self) -> int:
        return self.start_block * PAGES_PER_BLOCK


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(16 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest().upper()


def validate_segments(segments: list[Segment]) -> None:
    for segment in segments:
        payload_size = segment.source.stat().st_size
        if segment.fixed_program_bytes is not None and payload_size > segment.fixed_program_bytes:
            raise ValueError(f"{segment.name} exceeds its confirmed recovery write span")
        if segment.pages > segment.partition_blocks * PAGES_PER_BLOCK:
            raise ValueError(f"{segment.name} exceeds its V2 partition")
    ordered = sorted(segments, key=lambda item: item.start_block)
    for left, right in zip(ordered, ordered[1:]):
        if left.start_block + left.partition_blocks > right.start_block:
            raise ValueError(f"V2 partitions overlap: {left.name} and {right.name}")
    if ordered[-1].start_block + ordered[-1].partition_blocks > BOOT_BLOCKS:
        raise ValueError("V2 boot partitions exceed block 63")


def validate_system_data(system_data: Path) -> dict[str, object]:
    bda_files = sorted(
        (path for path in system_data.rglob("*") if path.is_file() and path.suffix.lower() == ".bda"),
        key=lambda path: str(path.relative_to(system_data)).casefold(),
    )
    if len(bda_files) != EXPECTED_V2_BDA_COUNT:
        raise ValueError(
            f"V2 filesystem must contain {EXPECTED_V2_BDA_COUNT} BDA files; "
            f"found {len(bda_files)}"
        )
    for path in bda_files:
        with path.open("rb") as stream:
            header = stream.read(HEADER_SIZE)
        valid, reason = validate_header(header, path.stat().st_size)
        if not valid:
            relative = path.relative_to(system_data)
            raise ValueError(f"V2 filesystem contains transformed/invalid BDA {relative}: {reason}")
    return {"bda_count": len(bda_files), "bda_headers_valid": len(bda_files)}


def erase_boot_region(stream) -> None:
    stream.seek(0)
    remaining = BOOT_BLOCKS * ERASE_BLOCK_BYTES
    while remaining:
        size = min(remaining, len(ERASED_CHUNK))
        stream.write(ERASED_CHUNK[:size])
        remaining -= size


def page_data(payload: bytes, offset: int) -> bytes:
    chunk = payload[offset : offset + PAGE_SIZE]
    return chunk + b"\xff" * (PAGE_SIZE - len(chunk))


def program_segment(stream, segment: Segment) -> None:
    payload = segment.payload
    for page_index in range(segment.pages):
        data = page_data(payload, page_index * PAGE_SIZE)
        stream.seek((segment.start_page + page_index) * PAGE_STRIDE)
        stream.write(data)
        stream.write(page_oob(data))


def verify_segment(stream, segment: Segment) -> None:
    payload = segment.payload
    for page_index in range(segment.pages):
        page = segment.start_page + page_index
        expected_data = page_data(payload, page_index * PAGE_SIZE)
        expected_oob = page_oob(expected_data)
        stream.seek(page * PAGE_STRIDE)
        actual_data = stream.read(PAGE_SIZE)
        actual_oob = stream.read(SPARE_SIZE)
        if actual_data != expected_data:
            raise ValueError(f"{segment.name} data verification failed at page 0x{page:x}")
        if actual_oob != expected_oob:
            raise ValueError(f"{segment.name} ECC/OOB verification failed at page 0x{page:x}")


def segment_report(segment: Segment) -> dict[str, object]:
    return {
        "name": segment.name,
        "source_name": segment.source.name,
        "source_bytes": segment.source.stat().st_size,
        "source_sha256": sha256_file(segment.source),
        "start_block": segment.start_block,
        "partition_blocks": segment.partition_blocks,
        "programmed_pages": segment.pages,
        "programmed_bytes": segment.program_bytes,
    }


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
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--system-data", type=Path, required=True)
    parser.add_argument("--loader", type=Path, required=True)
    parser.add_argument("--uboot", type=Path, required=True)
    parser.add_argument("--os", dest="base_os", type=Path, required=True)
    parser.add_argument("--extos1", type=Path, required=True)
    parser.add_argument("--extos2", type=Path, required=True)
    parser.add_argument("--ecc-helper", type=Path, default=default_ecc_helper(repository))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    segments = [
        Segment("loader", args.loader.resolve(), 0, 1, 0x1800),
        Segment("u-boot", args.uboot.resolve(), 1, 5, 0x70800),
        Segment("os", args.base_os.resolve(), 6, 10),
        Segment("extos1", args.extos1.resolve(), 16, 34),
        Segment("extos2", args.extos2.resolve(), 50, 12),
    ]
    for source in (args.template, args.system_data, args.ecc_helper, *(item.source for item in segments)):
        if not source.exists():
            raise FileNotFoundError(source)
    validate_segments(segments)
    system_data_validation = validate_system_data(args.system_data.resolve())
    template_sha256 = sha256_file(args.template.resolve())
    if template_sha256 != NATIVE_TEMPLATE_SHA256:
        raise ValueError(
            "V2 native template hash mismatch: "
            f"expected {NATIVE_TEMPLATE_SHA256}, got {template_sha256}"
        )

    report: dict[str, object] = {
        "format": "bbk-h1-v2-nand-v1",
        "geometry": {
            "page_size": PAGE_SIZE,
            "spare_size": SPARE_SIZE,
            "pages_per_block": PAGES_PER_BLOCK,
            "ftl_start_block": BOOT_BLOCKS,
        },
        "native_template_sha256": template_sha256,
        "system_data_validation": system_data_validation,
        "segments": [segment_report(segment) for segment in segments],
    }
    if args.plan_only:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    output = args.output.resolve()
    temporary = output.with_name(output.name + ".building")
    ftl_manifest = output.with_name(output.name + ".ftl-building.json")
    if output.exists():
        if not args.force:
            raise FileExistsError(f"refusing to overwrite {output}; pass --force")
        # A raw H1 NAND is about 1 GiB. Drop a known-stale forced output before
        # allocating its replacement so rebuilds do not temporarily need a
        # third complete image.
        output.unlink()
    output.parent.mkdir(parents=True, exist_ok=True)
    for stale in (temporary, ftl_manifest):
        if stale.exists():
            stale.unlink()

    command = [
        sys.executable,
        str(repository / "scripts" / "build_h1_system_nand.py"),
        "--template",
        str(args.template.resolve()),
        "--system-data",
        str(args.system_data.resolve()),
        "--scan-start-block",
        "0x40",
        "--sequence",
        "8",
        "--root-volume-label-entry-hex",
        NATIVE_ROOT_VOLUME_LABEL_ENTRY_HEX,
        "--mapping-override",
        "3=146:0",
        "--ecc-helper",
        str(args.ecc_helper.resolve()),
        "--output",
        str(temporary),
        "--manifest",
        str(ftl_manifest),
    ]
    try:
        completed = subprocess.run(command, check=True, capture_output=True, text=True)
        ftl_report = json.loads(completed.stdout)
        with temporary.open("r+b", buffering=0) as stream:
            erase_boot_region(stream)
            for segment in segments:
                program_segment(stream, segment)
            stream.flush()
            os.fsync(stream.fileno())
            for segment in segments:
                verify_segment(stream, segment)
        report["ftl_plan"] = ftl_report["plan"]
        report["ftl_write"] = ftl_report["ftl_write"]
        report["ftl_verification"] = ftl_report["verification"]
        report["ecc_helper_sha256"] = sha256_file(args.ecc_helper.resolve())
        report["output_bytes"] = temporary.stat().st_size
        report["output_sha256"] = sha256_file(temporary)
        if output.exists():
            output.unlink()
        os.replace(temporary, output)
    except BaseException:
        if temporary.exists():
            temporary.unlink()
        raise
    finally:
        if ftl_manifest.exists():
            ftl_manifest.unlink()

    manifest = args.manifest or output.with_suffix(output.suffix + ".json")
    manifest.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    manifest.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
