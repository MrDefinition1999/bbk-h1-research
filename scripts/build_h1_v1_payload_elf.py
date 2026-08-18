#!/usr/bin/env python3
"""Create an IDA-loadable ELF view of an H1 V1 raw game payload.

This is a research helper only. It emits a private analysis ELF and never
copies the payload into a release tree.
"""

from __future__ import annotations

import argparse
import struct
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SDK_ROOT = ROOT / "h1-bda-sdk"

import sys

if str(SDK_ROOT) not in sys.path:
    sys.path.insert(0, str(SDK_ROOT))

from h1_bda.build import compile_sources  # noqa: E402


ENTRY_VA = 0x83C00020


def _normalize_mips_physical_addresses(path: Path) -> None:
    """Match the physical-address convention used by H1 ELF loaders."""
    raw = bytearray(path.read_bytes())
    if raw[:4] != b"\x7fELF" or raw[4] != 1 or raw[5] != 1:
        raise ValueError("unexpected ELF format")
    phoff = struct.unpack_from("<I", raw, 28)[0]
    phentsize = struct.unpack_from("<H", raw, 42)[0]
    phnum = struct.unpack_from("<H", raw, 44)[0]
    if phentsize != 32:
        raise ValueError("unexpected ELF32 program-header size")
    for index in range(phnum):
        offset = phoff + index * phentsize
        p_type, p_offset, p_vaddr = struct.unpack_from("<III", raw, offset)
        if p_type == 1:
            struct.pack_into("<I", raw, offset + 12, p_vaddr & 0x0FFFFFFF)
    path.write_bytes(raw)


def build_payload_elf(payload: Path, output: Path) -> None:
    if not payload.is_file():
        raise FileNotFoundError(payload)
    data = payload.read_bytes()
    if not data or len(data) & 3:
        raise ValueError("payload must be non-empty and 4-byte aligned")

    with tempfile.TemporaryDirectory(prefix="h1-v1-payload-") as temporary:
        work = Path(temporary)
        blob = work / "payload.bin"
        blob.write_bytes(data)
        source = work / "payload.S"
        source.write_text(
            ".set noreorder\n"
            ".set noat\n"
            '.section .text.h1_bda_entry,"ax",@progbits\n'
            ".globl h1_bda_main\n"
            ".globl h1_v1_payload_entry\n"
            ".ent h1_bda_main\n"
            "h1_bda_main:\n"
            "h1_v1_payload_entry:\n"
            f'    .incbin "{blob.as_posix()}"\n'
            ".end h1_bda_main\n",
            encoding="ascii",
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        compile_sources(
            [source],
            [],
            debug_elf=output,
            entry_va=ENTRY_VA,
        )
        _normalize_mips_physical_addresses(output)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("payload", type=Path)
    parser.add_argument("-o", "--output", type=Path, required=True)
    args = parser.parse_args()
    build_payload_elf(args.payload, args.output)
    print(f"output={args.output}")
    print(f"payload_size=0x{args.payload.stat().st_size:X}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
