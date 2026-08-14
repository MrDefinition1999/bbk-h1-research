#!/usr/bin/env python3
"""Disassemble bounded snippets around selected MZP tool string references."""

from __future__ import annotations

import argparse
import json
import mmap
import struct
from pathlib import Path

from capstone import Cs, CS_ARCH_X86, CS_MODE_32


def u16(data: mmap.mmap, offset: int) -> int:
    return struct.unpack_from("<H", data, offset)[0]


def u32(data: mmap.mmap, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def sections(data: mmap.mmap) -> tuple[int, list[dict[str, int | str]]]:
    pe = u32(data, 0x3C)
    coff = pe + 4
    count = u16(data, coff + 2)
    optional_size = u16(data, coff + 16)
    optional = coff + 20
    base = u32(data, optional + 28)
    table = optional + optional_size
    result = []
    for index in range(count):
        offset = table + index * 40
        result.append(
            {
                "name": bytes(data[offset : offset + 8]).split(b"\0", 1)[0].decode("ascii", "replace"),
                "rva": u32(data, offset + 12),
                "raw_pointer": u32(data, offset + 20),
                "raw_size": u32(data, offset + 16),
            }
        )
    return base, result


def va_to_file(va: int, base: int, pe_sections: list[dict[str, int | str]]) -> int | None:
    rva = va - base
    for section in pe_sections:
        start = int(section["rva"])
        if start <= rva < start + int(section["raw_size"]):
            return int(section["raw_pointer"]) + rva - start
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("analysis", type=Path)
    parser.add_argument("--contains", action="append", default=["Burn", "FileSize", "PcFileName", "FS_", "ERROR_"])
    parser.add_argument("--radius", type=int, default=48)
    args = parser.parse_args()
    wanted = [value.lower() for value in args.contains]
    report = json.loads(args.analysis.read_text(encoding="utf-8"))
    with args.input.open("rb") as handle, mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ) as data:
        base, pe_sections = sections(data)
        disassembler = Cs(CS_ARCH_X86, CS_MODE_32)
        disassembler.skipdata = True
        rows = []
        for reference in report["string_references"]:
            if not any(token in str(reference["text"]).lower() for token in wanted):
                continue
            for address_text in reference["instruction_addresses"][:1]:
                address = int(address_text, 16)
                file_offset = va_to_file(address, base, pe_sections)
                if file_offset is None:
                    continue
                start = max(0, file_offset - args.radius)
                block = bytes(data[start : file_offset + args.radius])
                instructions = [
                    {"address": f"0x{item.address:08x}", "mnemonic": item.mnemonic, "op_str": item.op_str}
                    for item in disassembler.disasm(block, base + (start - int(pe_sections[0]["raw_pointer"])) + int(pe_sections[0]["rva"]))
                ]
                rows.append({"text": reference["text"], "address": address_text, "file_offset": file_offset, "instructions": instructions})
        print(json.dumps(rows, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
