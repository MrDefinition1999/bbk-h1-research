#!/usr/bin/env python3
"""Wrap a raw little-endian MIPS32 image in a minimal ELF32 container."""

from __future__ import annotations

import argparse
import struct
from pathlib import Path


ELF_HEADER_SIZE = 52
PROGRAM_HEADER_SIZE = 32
PAYLOAD_OFFSET = 0x1000
EM_MIPS = 8
EF_MIPS_NOREORDER = 0x00000001
EF_MIPS_ABI_O32 = 0x00001000
EF_MIPS_ARCH_32 = 0x50000000


def parse_int(value: str) -> int:
    return int(value, 0)


def build_elf(payload: bytes, base: int, entry: int, physical: int, flags: int) -> bytes:
    ident = b"\x7fELF" + bytes((1, 1, 1, 0, 0)) + bytes(7)
    elf_header = struct.pack(
        "<16sHHIIIIIHHHHHH",
        ident,
        2,
        EM_MIPS,
        1,
        entry,
        ELF_HEADER_SIZE,
        0,
        EF_MIPS_NOREORDER | EF_MIPS_ABI_O32 | EF_MIPS_ARCH_32,
        ELF_HEADER_SIZE,
        PROGRAM_HEADER_SIZE,
        1,
        0,
        0,
        0,
    )
    program_header = struct.pack(
        "<IIIIIIII",
        1,
        PAYLOAD_OFFSET,
        base,
        physical,
        len(payload),
        len(payload),
        flags,
        0x1000,
    )
    padding = bytes(PAYLOAD_OFFSET - len(elf_header) - len(program_header))
    return elf_header + program_header + padding + payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="raw binary input")
    parser.add_argument("output", type=Path, help="ELF output")
    parser.add_argument("--base", type=parse_int, required=True, help="virtual load address")
    parser.add_argument("--entry", type=parse_int, help="entry address (default: base)")
    parser.add_argument(
        "--physical",
        type=parse_int,
        help="physical load address (default: virtual base masked to 512 MiB)",
    )
    parser.add_argument(
        "--segment-flags",
        type=parse_int,
        default=7,
        help="ELF PF_R/PF_W/PF_X mask (default: 7, rwx)",
    )
    args = parser.parse_args()

    payload = args.input.read_bytes()
    entry = args.entry if args.entry is not None else args.base
    physical = args.physical if args.physical is not None else args.base & 0x1FFFFFFF
    output = build_elf(payload, args.base, entry, physical, args.segment_flags)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(output)
    print(
        f"wrote {args.output}: payload={len(payload)} bytes, "
        f"base=0x{args.base:08x}, entry=0x{entry:08x}, physical=0x{physical:08x}"
    )


if __name__ == "__main__":
    main()
