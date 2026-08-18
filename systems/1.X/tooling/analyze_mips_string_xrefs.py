#!/usr/bin/env python3
"""Find MIPS32 little-endian code references to strings in a raw image."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from capstone import CS_ARCH_MIPS, CS_MODE_LITTLE_ENDIAN, CS_MODE_MIPS32, Cs


REGISTER = r"\$[a-z0-9]+"
LUI_RE = re.compile(rf"^({REGISTER}), (0x[0-9a-f]+|[0-9]+)$")
THREE_RE = re.compile(
    rf"^({REGISTER}), ({REGISTER}), (-?0x[0-9a-f]+|-?[0-9]+)$"
)
MOVE_RE = re.compile(rf"^({REGISTER}), ({REGISTER})$")


def parse_int(text: str) -> int:
    negative = text.startswith("-")
    body = text[1:] if negative else text
    value = int(body, 0)
    return -value if negative else value


def disassemble(data: bytes, base: int) -> list[dict[str, object]]:
    engine = Cs(CS_ARCH_MIPS, CS_MODE_MIPS32 | CS_MODE_LITTLE_ENDIAN)
    engine.skipdata = True
    return [
        {
            "address": instruction.address,
            "mnemonic": instruction.mnemonic,
            "operands": instruction.op_str,
        }
        for instruction in engine.disasm(data, base)
    ]


def evaluate_window(
    instructions: list[dict[str, object]], start: int, target: int, limit: int
) -> list[int]:
    constants: dict[str, int] = {}
    references: list[int] = []
    for item in instructions[start : start + limit]:
        mnemonic = str(item["mnemonic"])
        operands = str(item["operands"])
        address = int(item["address"])

        if mnemonic == "lui":
            match = LUI_RE.match(operands)
            if match:
                constants[match.group(1)] = (parse_int(match.group(2)) << 16) & 0xFFFFFFFF
            continue

        match = THREE_RE.match(operands)
        if mnemonic in {"addiu", "addi", "ori"} and match:
            destination, source, immediate_text = match.groups()
            if source in constants:
                immediate = parse_int(immediate_text)
                if mnemonic == "ori":
                    value = constants[source] | (immediate & 0xFFFF)
                else:
                    if immediate & 0x8000 and immediate >= 0:
                        immediate -= 0x10000
                    value = (constants[source] + immediate) & 0xFFFFFFFF
                constants[destination] = value
                if value == target:
                    references.append(address)
            else:
                constants.pop(destination, None)
            continue

        if mnemonic == "move":
            match = MOVE_RE.match(operands)
            if match:
                destination, source = match.groups()
                if source in constants:
                    constants[destination] = constants[source]
                    if constants[destination] == target:
                        references.append(address)
                else:
                    constants.pop(destination, None)
            continue

        if mnemonic in {"j", "jr", "jal", "jalr", "b", "bal"} or mnemonic.startswith("b"):
            break

        destination = operands.split(",", 1)[0]
        if re.fullmatch(REGISTER, destination):
            constants.pop(destination, None)
    return references


def find_references(
    instructions: list[dict[str, object]], target: int, window: int
) -> list[int]:
    upper_values = {target >> 16, ((target + 0x8000) & 0xFFFFFFFF) >> 16}
    references: set[int] = set()
    for index, item in enumerate(instructions):
        if item["mnemonic"] != "lui":
            continue
        match = LUI_RE.match(str(item["operands"]))
        if match and parse_int(match.group(2)) in upper_values:
            references.update(evaluate_window(instructions, index, target, window))
    return sorted(references)


def function_start(instructions: list[dict[str, object]], reference_index: int) -> int | None:
    lower = max(0, reference_index - 768)
    for index in range(reference_index, lower - 1, -1):
        item = instructions[index]
        if item["mnemonic"] not in {"addiu", "addi"}:
            continue
        match = THREE_RE.match(str(item["operands"]))
        if not match:
            continue
        destination, source, immediate_text = match.groups()
        if destination == "$sp" and source == "$sp" and parse_int(immediate_text) < 0:
            return int(item["address"])
    return None


def direct_callers(instructions: list[dict[str, object]], target: int) -> list[int]:
    result = []
    for item in instructions:
        if item["mnemonic"] not in {"jal", "bal"}:
            continue
        try:
            destination = int(str(item["operands"]), 0)
        except ValueError:
            continue
        if destination == target:
            result.append(int(item["address"]))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("text")
    parser.add_argument("--base", type=lambda value: int(value, 0), required=True)
    parser.add_argument("--encoding", default="gbk")
    parser.add_argument("--window", type=int, default=16)
    parser.add_argument("--context", type=int, default=8)
    args = parser.parse_args()

    data = args.image.read_bytes()
    needle = args.text.encode(args.encoding)
    string_offsets = []
    offset = 0
    while True:
        offset = data.find(needle, offset)
        if offset < 0:
            break
        string_offsets.append(offset)
        offset += 1

    instructions = disassemble(data, args.base)
    index_by_address = {
        int(item["address"]): index for index, item in enumerate(instructions)
    }
    report = []
    for string_offset in string_offsets:
        string_address = args.base + string_offset
        rows = []
        for reference in find_references(instructions, string_address, args.window):
            index = index_by_address[reference]
            start = function_start(instructions, index)
            rows.append(
                {
                    "reference": f"0x{reference:08X}",
                    "function": f"0x{start:08X}" if start is not None else None,
                    "callers": [
                        f"0x{address:08X}"
                        for address in direct_callers(instructions, start)
                    ]
                    if start is not None
                    else [],
                    "context": [
                        {
                            "address": f"0x{int(item['address']):08X}",
                            "mnemonic": item["mnemonic"],
                            "operands": item["operands"],
                        }
                        for item in instructions[
                            max(0, index - args.context) : index + args.context + 1
                        ]
                    ],
                }
            )
        report.append(
            {
                "string_offset": f"0x{string_offset:X}",
                "string_address": f"0x{string_address:08X}",
                "references": rows,
            }
        )

    print(json.dumps(report, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
