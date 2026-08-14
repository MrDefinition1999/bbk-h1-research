#!/usr/bin/env python3
"""Build and verify a raw @ibox H1 boot NAND image."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from jz4740_ecc import jz4740_page_oob_ecc

PAGE_SIZE = 2048
SPARE_SIZE = 64
PAGE_STRIDE = PAGE_SIZE + SPARE_SIZE
PAGES_PER_BLOCK = 128
LOADER_PAGE = 0
LOADER_PROGRAM_BYTES = 0x1800
UBOOT_PAGE = 0x80
UBOOT_PROGRAM_BYTES = 0x70800
PROJECT_PAGE = 0x400
PROJECT_MAX_BYTES = 0x600000
PROJECT_RESERVED_END_BLOCK = 0x3E
ECC_OOB_OFFSET = 6


@dataclass(frozen=True)
class Segment:
    name: str
    path: Path
    start_page: int
    payload: bytes
    program_bytes: int

    @property
    def pages(self) -> int:
        return self.program_bytes // PAGE_SIZE

    @property
    def end_page(self) -> int:
        return self.start_page + self.pages

    def page_data(self, index: int) -> bytes:
        start = index * PAGE_SIZE
        chunk = self.payload[start : start + PAGE_SIZE]
        return chunk + b"\xff" * (PAGE_SIZE - len(chunk))


def align_up(value: int, alignment: int) -> int:
    return (value + alignment - 1) // alignment * alignment


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest().upper()


def page_oob(data: bytes) -> bytes:
    parity = jz4740_page_oob_ecc(data, offset=ECC_OOB_OFFSET)
    if len(parity) > SPARE_SIZE:
        raise ValueError("JZ4740 parity does not fit in the H1 spare area")
    oob = bytearray(b"\xff" * SPARE_SIZE)
    oob[ECC_OOB_OFFSET : len(parity)] = parity[ECC_OOB_OFFSET:]
    oob[2:5] = b"\x00\x00\x00"
    return bytes(oob)


def write_erased_image(output, size: int) -> None:
    chunk = b"\xff" * (1024 * 1024)
    remaining = size
    while remaining:
        count = min(remaining, len(chunk))
        output.write(chunk[:count])
        remaining -= count


def write_segment(output, segment: Segment) -> None:
    for index in range(segment.pages):
        data = segment.page_data(index)
        output.seek((segment.start_page + index) * PAGE_STRIDE)
        output.write(data)
        output.write(page_oob(data))


def verify_segment(image, segment: Segment) -> None:
    for index in range(segment.pages):
        page = segment.start_page + index
        image.seek(page * PAGE_STRIDE)
        actual_data = image.read(PAGE_SIZE)
        actual_oob = image.read(SPARE_SIZE)
        expected_data = segment.page_data(index)
        if actual_data != expected_data:
            raise ValueError(f"{segment.name}: data mismatch at page 0x{page:x}")
        if actual_oob != page_oob(expected_data):
            raise ValueError(f"{segment.name}: OOB/ECC mismatch at page 0x{page:x}")


def verify_erased_pages(image, pages: set[int], page_count: int) -> None:
    erased = b"\xff" * PAGE_STRIDE
    for page in sorted(page for page in pages if 0 <= page < page_count):
        image.seek(page * PAGE_STRIDE)
        if image.read(PAGE_STRIDE) != erased:
            raise ValueError(f"expected erased page at 0x{page:x}")


def load_segments(loader_path: Path, uboot_path: Path, project_path: Path) -> list[Segment]:
    loader = loader_path.read_bytes()
    uboot = uboot_path.read_bytes()
    project = project_path.read_bytes()
    if len(loader) > LOADER_PROGRAM_BYTES:
        raise ValueError("loader does not fit in the three pages written by H1 recovery")
    if len(uboot) > UBOOT_PROGRAM_BYTES:
        raise ValueError("U-Boot exceeds the 0x70800-byte H1 recovery write span")
    if len(project) > PROJECT_MAX_BYTES:
        raise ValueError("project image exceeds U-Boot's 0x600000-byte load limit")
    return [
        Segment("loader", loader_path, LOADER_PAGE, loader, LOADER_PROGRAM_BYTES),
        Segment("u-boot", uboot_path, UBOOT_PAGE, uboot, UBOOT_PROGRAM_BYTES),
        Segment("project", project_path, PROJECT_PAGE, project, align_up(len(project), PAGE_SIZE)),
    ]


def validate_layout(segments: list[Segment], physical_blocks: int) -> int:
    for previous, current in zip(segments, segments[1:]):
        if previous.end_page > current.start_page:
            raise ValueError(f"{previous.name} overlaps {current.name}")
    required_pages = max(segment.end_page for segment in segments)
    physical_pages = physical_blocks * PAGES_PER_BLOCK
    if physical_pages < required_pages:
        raise ValueError(
            f"image needs 0x{required_pages:x} pages, but {physical_blocks} blocks provide 0x{physical_pages:x}"
        )
    return physical_pages


def manifest(output: Path, segments: list[Segment], physical_blocks: int) -> dict:
    return {
        "format": "bbk-h1-raw-nand-v1",
        "output": str(output.resolve()),
        "geometry": {
            "page_size": PAGE_SIZE,
            "spare_size": SPARE_SIZE,
            "pages_per_block": PAGES_PER_BLOCK,
            "physical_blocks": physical_blocks,
        },
        "oob": {
            "programmed_prefix_hex": "ffff000000ff",
            "ecc_offset": ECC_OOB_OFFSET,
            "ecc": "JZ4740 RS(511,503), 9 bytes per 512-byte chunk",
        },
        "segments": [
            {
                "name": segment.name,
                "source": str(segment.path.resolve()),
                "source_bytes": len(segment.payload),
                "source_sha256": sha256(segment.payload),
                "start_page": segment.start_page,
                "pages": segment.pages,
                "program_bytes": segment.program_bytes,
            }
            for segment in segments
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--loader", type=Path, required=True)
    parser.add_argument("--uboot", type=Path, required=True)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument(
        "--physical-blocks",
        type=lambda value: int(value, 0),
        default=PROJECT_RESERVED_END_BLOCK,
        help="physical block count (default: 0x3E, the H1 recovery boot-area reservation)",
    )
    parser.add_argument("--no-verify", action="store_true")
    args = parser.parse_args()

    if args.physical_blocks <= 0:
        parser.error("--physical-blocks must be positive")
    segments = load_segments(args.loader, args.uboot, args.project)
    physical_pages = validate_layout(segments, args.physical_blocks)
    output_size = physical_pages * PAGE_STRIDE
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w+b") as output:
        write_erased_image(output, output_size)
        for segment in segments:
            write_segment(output, segment)
        if not args.no_verify:
            for segment in segments:
                verify_segment(output, segment)
            boundary_pages = {0, physical_pages - 1}
            for segment in segments:
                boundary_pages.update({segment.start_page - 1, segment.end_page})
            programmed = {
                page
                for segment in segments
                for page in range(segment.start_page, segment.end_page)
            }
            verify_erased_pages(output, boundary_pages - programmed, physical_pages)

    report = manifest(args.output, segments, args.physical_blocks)
    report["output_bytes"] = output_size
    report["output_sha256"] = sha256_file(args.output)
    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.manifest:
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        args.manifest.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
