#!/usr/bin/env python3
"""Rank V2 service-table functions as candidates for V1 Mission services."""

from __future__ import annotations

import argparse
import difflib
import json
import struct
from dataclasses import dataclass
from pathlib import Path


V1_TABLES = {
    "GUI": 0x802AA110,
    "FS": 0x802AA080,
    "SYS": 0x802A9EF0,
    "MEM": 0x802AAC4C,
    "RES": 0x802A9FD0,
}
V2_TABLES = {
    "GUI": 0x80790BA0,
    "FS": 0x800A50A0,
    "SYS": 0x800A4FD0,
    "MEM": 0x800A5554,
    "RES": 0x80AE55C0,
}
TABLE_SCAN_LIMITS = {
    "GUI": 0xB00,
    "FS": 0x100,
    "SYS": 0x100,
    "MEM": 0x40,
    "RES": 0x100,
}


@dataclass(frozen=True)
class Image:
    name: str
    base: int
    data: bytes

    @property
    def end(self) -> int:
        return self.base + len(self.data)

    def read(self, address: int, size: int) -> bytes | None:
        if not self.base <= address < self.end:
            return None
        offset = address - self.base
        return self.data[offset : min(len(self.data), offset + size)]


def read_virtual(images: list[Image], address: int, size: int) -> bytes | None:
    for image in images:
        value = image.read(address, size)
        if value is not None:
            return value
    return None


def read_u32(images: list[Image], address: int) -> int | None:
    raw = read_virtual(images, address, 4)
    return struct.unpack("<I", raw)[0] if raw is not None and len(raw) == 4 else None


def fine_token(word: int) -> int:
    opcode = word >> 26
    if opcode == 0:
        return word
    if opcode in (2, 3):
        return word & 0xFC000000
    return word & 0xFFFF0000


def coarse_token(word: int) -> int:
    opcode = word >> 26
    return (opcode << 6) | ((word & 0x3F) if opcode == 0 else 0)


def instruction_words(images: list[Image], address: int, count: int = 64) -> list[int]:
    raw = read_virtual(images, address, count * 4)
    if raw is None:
        return []
    return list(struct.unpack(f"<{len(raw) // 4}I", raw[: len(raw) & ~3]))


def prefix_equal(left: list[int], right: list[int]) -> int:
    result = 0
    for a, b in zip(left, right):
        if a != b:
            break
        result += 1
    return result


def similarity(v1_words: list[int], v2_words: list[int]) -> tuple[float, float, float, int]:
    v1_fine = [fine_token(word) for word in v1_words]
    v2_fine = [fine_token(word) for word in v2_words]
    v1_coarse = [coarse_token(word) for word in v1_words]
    v2_coarse = [coarse_token(word) for word in v2_words]
    fine = difflib.SequenceMatcher(a=v1_fine, b=v2_fine, autojunk=False).ratio()
    coarse = difflib.SequenceMatcher(a=v1_coarse, b=v2_coarse, autojunk=False).ratio()
    prefix = prefix_equal(v1_fine, v2_fine)
    score = fine * 0.7 + coarse * 0.3 + min(prefix, 8) * 0.0125
    return min(score, 1.0), fine, coarse, prefix


def executable_pointer(images: list[Image], pointer: int | None) -> bool:
    return pointer is not None and read_virtual(images, pointer, 4) is not None


def candidates_for_table(images: list[Image], table: str) -> list[tuple[int, int]]:
    base = V2_TABLES[table]
    output = []
    for offset in range(0, TABLE_SCAN_LIMITS[table], 4):
        pointer = read_u32(images, base + offset)
        if executable_pointer(images, pointer):
            assert pointer is not None
            output.append((offset, pointer))
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("compatibility_json", type=Path)
    parser.add_argument("--v1-project", type=Path, required=True)
    parser.add_argument("--v2-os", type=Path, required=True)
    parser.add_argument("--v2-extos1", type=Path, required=True)
    parser.add_argument("--v2-extos2", type=Path, required=True)
    parser.add_argument("--json", type=Path)
    parser.add_argument("--top", type=int, default=5)
    args = parser.parse_args()

    v1_images = [Image("V1", 0x80004000, args.v1_project.read_bytes())]
    v2_images = [
        Image("V2 OS", 0x80004000, args.v2_os.read_bytes()),
        Image("V2 ExtOs1", 0x80600000, args.v2_extos1.read_bytes()),
        Image("V2 ExtOs2", 0x809F0000, args.v2_extos2.read_bytes()),
    ]
    compatibility = json.loads(args.compatibility_json.read_text(encoding="utf-8"))
    table_candidates = {
        table: candidates_for_table(v2_images, table) for table in V1_TABLES
    }
    rows = []
    for source in compatibility["rows"]:
        table = str(source["table"])
        offset = int(source["offset"])
        v1_pointer = read_u32(v1_images, V1_TABLES[table] + offset)
        v1_words = instruction_words(v1_images, v1_pointer or 0)
        ranked = []
        for candidate_offset, candidate_pointer in table_candidates[table]:
            score, fine, coarse, prefix = similarity(
                v1_words, instruction_words(v2_images, candidate_pointer)
            )
            ranked.append(
                {
                    "offset": candidate_offset,
                    "offset_hex": f"0x{candidate_offset:03X}",
                    "pointer": f"0x{candidate_pointer:08X}",
                    "score": round(score, 6),
                    "fine": round(fine, 6),
                    "coarse": round(coarse, 6),
                    "normalized_prefix_words": prefix,
                    "same_offset": candidate_offset == offset,
                }
            )
        ranked.sort(
            key=lambda item: (
                item["score"],
                item["normalized_prefix_words"],
                item["same_offset"],
            ),
            reverse=True,
        )
        rows.append(
            {
                "table": table,
                "v1_offset": offset,
                "v1_offset_hex": f"0x{offset:03X}",
                "v1_pointer": None if v1_pointer is None else f"0x{v1_pointer:08X}",
                "v1_calls": int(source["v1_calls"]),
                "native_v2_calls_at_same_offset": int(source["v2_calls"]),
                "candidates": ranked[: max(1, args.top)],
            }
        )

    result = {
        "format": "h1-v1-v2-service-function-match-v1",
        "instruction_words": 64,
        "tables": {
            table: {
                "v1_base": f"0x{V1_TABLES[table]:08X}",
                "v2_base": f"0x{V2_TABLES[table]:08X}",
                "v2_executable_candidates": len(table_candidates[table]),
            }
            for table in V1_TABLES
        },
        "rows": rows,
    }
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(rendered, encoding="utf-8")

    for row in rows:
        if row["native_v2_calls_at_same_offset"]:
            continue
        best = row["candidates"][0]
        print(
            f"{row['table']}+{row['v1_offset_hex']} -> +{best['offset_hex']} "
            f"score={best['score']:.3f} pointer={best['pointer']} "
            f"same={best['same_offset']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
