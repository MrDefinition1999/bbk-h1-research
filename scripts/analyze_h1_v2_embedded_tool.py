#!/usr/bin/env python3
"""Statically inspect the MZP/PE tool embedded in the V2 super updater.

The tool is treated as data.  This report parses sections and imports, then
uses Capstone to find x86 instructions that load selected string addresses.
It never executes the updater or its drivers.
"""

from __future__ import annotations

import argparse
import json
import mmap
import re
import struct
from pathlib import Path

from capstone import Cs, CS_ARCH_X86, CS_MODE_32


def u16(data: mmap.mmap, offset: int) -> int:
    return struct.unpack_from("<H", data, offset)[0]


def u32(data: mmap.mmap, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def rva_to_file(rva: int, sections: list[dict[str, int | str]]) -> int | None:
    for section in sections:
        start = int(section["rva"])
        span = max(int(section["virtual_size"]), int(section["raw_size"]))
        if start <= rva < start + span:
            delta = rva - start
            if delta < int(section["raw_size"]):
                return int(section["raw_pointer"]) + delta
    return None


def parse_pe(data: mmap.mmap) -> tuple[int, list[dict[str, int | str]], int, int]:
    pe = u32(data, 0x3C)
    if bytes(data[pe : pe + 4]) != b"PE\0\0":
        raise ValueError("missing PE signature")
    coff = pe + 4
    section_count = u16(data, coff + 2)
    optional_size = u16(data, coff + 16)
    optional = coff + 20
    image_base = u32(data, optional + 28)
    entry_rva = u32(data, optional + 16)
    table = optional + optional_size
    sections = []
    for index in range(section_count):
        offset = table + index * 40
        name = bytes(data[offset : offset + 8]).split(b"\0", 1)[0].decode("ascii", "replace")
        sections.append(
            {
                "index": index,
                "name": name,
                "virtual_size": u32(data, offset + 8),
                "rva": u32(data, offset + 12),
                "raw_size": u32(data, offset + 16),
                "raw_pointer": u32(data, offset + 20),
                "characteristics": u32(data, offset + 36),
            }
        )
    return image_base, sections, entry_rva, optional


def ascii_strings(data: mmap.mmap, sections: list[dict[str, int | str]]) -> list[dict[str, object]]:
    result = []
    for section in sections:
        start = int(section["raw_pointer"])
        end = min(len(data), start + int(section["raw_size"]))
        block = bytes(data[start:end])
        for match in re.finditer(rb"[ -~]{6,}", block):
            text = match.group().decode("ascii", "replace")
            if any(keyword in text.lower() for keyword in ("burn", "nand", "usb", "file", "upd", "loader", "system", "project", "sys")):
                result.append({"section": section["name"], "file_offset": start + match.start(), "text": text[:240]})
    return result


def analyze(path: Path) -> dict[str, object]:
    with path.open("rb") as handle, mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ) as data:
        image_base, sections, entry_rva, optional = parse_pe(data)
        code = next((section for section in sections if str(section["name"]).lower() in (".text", "code")), sections[0])
        code_start = int(code["raw_pointer"])
        code_end = min(len(data), code_start + int(code["raw_size"]))
        code_bytes = bytes(data[code_start:code_end])
        md = Cs(CS_ARCH_X86, CS_MODE_32)
        md.detail = False
        md.skipdata = True
        instructions = list(md.disasm(code_bytes, image_base + int(code["rva"])))
        interesting = ascii_strings(data, sections)
        refs = []
        for item in interesting:
            rva = int(item["file_offset"]) - int(next(section for section in sections if section["name"] == item["section"])["raw_pointer"])
            section = next(section for section in sections if section["name"] == item["section"])
            va = image_base + int(section["rva"]) + rva
            matching = [ins for ins in instructions if ins.bytes.find(struct.pack("<I", va)) >= 0]
            if matching:
                refs.append(
                    {
                        "text": item["text"],
                        "section": item["section"],
                        "file_offset": item["file_offset"],
                        "virtual_address": f"0x{va:08x}",
                        "instruction_addresses": [f"0x{ins.address:08x}" for ins in matching[:20]],
                    }
                )
        return {
            "path": path.name,
            "size": len(data),
            "image_base": f"0x{image_base:08x}",
            "entry_rva": f"0x{entry_rva:08x}",
            "entry_va": f"0x{image_base + entry_rva:08x}",
            "sections": sections,
            "interesting_strings": interesting,
            "string_references": refs,
            "instruction_count": len(instructions),
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()
    rendered = json.dumps(analyze(args.input), ensure_ascii=True, indent=2) + "\n"
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
