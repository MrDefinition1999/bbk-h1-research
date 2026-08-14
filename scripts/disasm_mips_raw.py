#!/usr/bin/env python3
"""Disassemble an address range from a raw MIPS32 little-endian image."""

from __future__ import annotations

import argparse
from pathlib import Path

from capstone import CS_ARCH_MIPS, CS_MODE_LITTLE_ENDIAN, CS_MODE_MIPS32, Cs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("--base", type=lambda value: int(value, 0), required=True)
    parser.add_argument("--start", type=lambda value: int(value, 0), required=True)
    parser.add_argument("--stop", type=lambda value: int(value, 0), required=True)
    args = parser.parse_args()

    if args.start < args.base or args.stop <= args.start:
        raise SystemExit("invalid address range")
    data = args.image.read_bytes()
    begin = args.start - args.base
    end = args.stop - args.base
    if begin < 0 or end > len(data):
        raise SystemExit("address range is outside the image")

    engine = Cs(CS_ARCH_MIPS, CS_MODE_MIPS32 | CS_MODE_LITTLE_ENDIAN)
    engine.skipdata = True
    for instruction in engine.disasm(data[begin:end], args.start):
        print(
            f"0x{instruction.address:08X}: "
            f"{instruction.mnemonic:<8} {instruction.op_str}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
