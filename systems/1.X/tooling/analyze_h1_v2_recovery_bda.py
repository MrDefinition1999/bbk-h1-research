#!/usr/bin/env python3
"""Produce a conservative static report for the H1 V2 recovery BDA.

This is intentionally a scanner, not an emulator: it identifies MIPS control
flow and embedded strings without guessing function boundaries or executing
the update code.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import struct
from pathlib import Path


LOAD_ADDRESS = 0x83C00040


def load_decode_bda():
    module_path = Path(__file__).with_name("decode_bda.py")
    spec = importlib.util.spec_from_file_location("h1_decode_bda", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load decode_bda.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def reg_name(index: int) -> str:
    names = (
        "zero", "at", "v0", "v1", "a0", "a1", "a2", "a3",
        "t0", "t1", "t2", "t3", "t4", "t5", "t6", "t7",
        "s0", "s1", "s2", "s3", "s4", "s5", "s6", "s7",
        "t8", "t9", "k0", "k1", "gp", "sp", "fp", "ra",
    )
    return names[index & 31]


def mips_instruction(word: int, pc: int, base: int) -> dict[str, object]:
    op = word >> 26
    rs = (word >> 21) & 31
    rt = (word >> 16) & 31
    rd = (word >> 11) & 31
    imm = word & 0xFFFF
    simm = imm - 0x10000 if imm & 0x8000 else imm
    target: int | None = None
    mnemonic = "word"
    if op == 0:
        funct = word & 63
        if funct == 8:
            mnemonic = f"jr {reg_name(rs)}"
        elif funct == 9:
            mnemonic = f"jalr {reg_name(rd)},{reg_name(rs)}"
        elif funct == 12:
            mnemonic = "syscall"
        elif funct == 13:
            mnemonic = "break"
        else:
            mnemonic = f"special funct=0x{funct:02x}"
    elif op == 2:
        target = ((pc + 4) & 0xF0000000) | ((word & 0x03FFFFFF) << 2)
        mnemonic = f"j 0x{target:08x}"
    elif op == 3:
        target = ((pc + 4) & 0xF0000000) | ((word & 0x03FFFFFF) << 2)
        mnemonic = f"jal 0x{target:08x}"
    elif op in (4, 5, 6, 7, 20, 21, 22, 23):
        target = pc + 4 + (simm << 2)
        branch = {4: "beq", 5: "bne", 6: "blez", 7: "bgtz", 20: "beql", 21: "bnel", 22: "blezl", 23: "bgtzl"}[op]
        operands = f"{reg_name(rs)},{reg_name(rt)}" if op in (4, 5, 20, 21) else reg_name(rs)
        mnemonic = f"{branch} {operands},0x{target:08x}"
    elif op == 15:
        mnemonic = f"lui {reg_name(rt)},0x{imm:04x}"
    elif op in (9, 12, 13, 14, 10, 11):
        name = {9: "addiu", 12: "andi", 13: "ori", 14: "xori", 10: "slti", 11: "sltiu"}[op]
        mnemonic = f"{name} {reg_name(rt)},{reg_name(rs)},0x{imm:04x}"
    elif op in (32, 33, 35, 36, 37, 40, 41, 43, 44, 45):
        name = {32: "lb", 33: "lh", 35: "lw", 36: "lbu", 37: "lhu", 40: "sb", 41: "sh", 43: "sw", 44: "swr", 45: "swr"}[op]
        mnemonic = f"{name} {reg_name(rt)},{simm}({reg_name(rs)})"
    return {"offset": pc - base, "address": pc, "word": word, "mnemonic": mnemonic, "target": target}


def ascii_strings(data: bytes, minimum: int = 4) -> list[dict[str, object]]:
    return [
        {"offset": match.start(), "text": match.group().decode("ascii", "replace")}
        for match in re.finditer(rb"[ -~]{" + str(minimum).encode() + rb",}", data)
    ]


def utf16_strings(data: bytes, minimum: int = 4) -> list[dict[str, object]]:
    pattern = rb"(?:[ -~]\x00){" + str(minimum).encode() + rb",}"
    result: list[dict[str, object]] = []
    for match in re.finditer(pattern, data):
        raw = match.group()
        result.append({"offset": match.start(), "text": raw.decode("utf-16le", "replace")})
    return result


def analyze(path: Path) -> dict[str, object]:
    decoder = load_decode_bda()
    metadata, payload = decoder.inspect_bda(path, LOAD_ADDRESS)
    instructions: list[dict[str, object]] = []
    for offset in range(0, len(payload) - 3, 4):
        word = struct.unpack_from("<I", payload, offset)[0]
        instructions.append(mips_instruction(word, LOAD_ADDRESS + offset, LOAD_ADDRESS))
    jal = [item for item in instructions if str(item["mnemonic"]).startswith("jal ")]
    branches = [
        item for item in instructions
        if str(item["mnemonic"]).split(" ", 1)[0].startswith(("b", "j"))
    ]
    return {
        "input": path.name,
        "file_sha256": metadata["file_sha256"],
        "payload_size": len(payload),
        "payload_sha256": metadata["payload_sha256"],
        "load_address": f"0x{LOAD_ADDRESS:08x}",
        "entry_prologue": [mips_instruction(struct.unpack_from("<I", payload, i)[0], LOAD_ADDRESS + i, LOAD_ADDRESS) for i in range(0, min(64, len(payload)), 4)],
        "instruction_count": len(instructions),
        "jal_count": len(jal),
        "branch_count": len(branches),
        "syscall_offsets": [item["offset"] for item in instructions if item["mnemonic"] in ("syscall", "break")],
        "jal_targets": sorted({f"0x{int(item['target']):08x}" for item in jal if item["target"] is not None}),
        "ascii_strings": ascii_strings(payload),
        "utf16_strings": utf16_strings(payload),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()
    report = analyze(args.input)
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
