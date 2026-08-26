#!/usr/bin/env python3
"""Rank H2 V2.2L services against the proven H1 V2 Mission map."""

from __future__ import annotations

import argparse
import difflib
import json
import struct
from dataclasses import dataclass
from pathlib import Path


H2_TABLES = {
    "GUI": 0x80651EF0,
    "FS": 0x800CA950,
    "SYS": 0x800CA830,
    "MEM": 0x800CAE44,
    "RES": 0x8095AB80,
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
        result = image.read(address, size)
        if result is not None:
            return result
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


def similarity(left: list[int], right: list[int]) -> tuple[float, float, float, int]:
    left_fine = [fine_token(word) for word in left]
    right_fine = [fine_token(word) for word in right]
    left_coarse = [coarse_token(word) for word in left]
    right_coarse = [coarse_token(word) for word in right]
    fine = difflib.SequenceMatcher(a=left_fine, b=right_fine, autojunk=False).ratio()
    coarse = difflib.SequenceMatcher(a=left_coarse, b=right_coarse, autojunk=False).ratio()
    prefix = prefix_equal(left_fine, right_fine)
    score = min(fine * 0.7 + coarse * 0.3 + min(prefix, 8) * 0.0125, 1.0)
    return score, fine, coarse, prefix


def candidates(images: list[Image], table: str) -> list[tuple[int, int]]:
    output: list[tuple[int, int]] = []
    for offset in range(0, TABLE_SCAN_LIMITS[table], 4):
        pointer = read_u32(images, H2_TABLES[table] + offset)
        if pointer is not None and read_virtual(images, pointer, 4) is not None:
            output.append((offset, pointer))
    return output


def confidence(score: float) -> str:
    if score >= 0.9:
        return "strong_fingerprint"
    if score >= 0.78:
        return "probable_fingerprint"
    if score >= 0.65:
        return "weak_candidate"
    return "unresolved"


def render_markdown(report: dict[str, object]) -> str:
    summary = report["summary"]
    lines = [
        "# Mission on H2 V2.2L: static compatibility report",
        "",
        "This report compares H2's native service tables with the already proven",
        "H1 V2 Mission compatibility map. A fingerprint is evidence for code",
        "lineage, not a signature or runtime-semantics proof.",
        "",
        f"- forwarded Mission services: {summary['forwarded_services']}",
        f"- strong fingerprints: {summary['strong_fingerprints']}",
        f"- probable fingerprints: {summary['probable_fingerprints']}",
        f"- unresolved/weak services: {summary['weak_or_unresolved']}",
        f"- local shims retained: {summary['local_shims']}",
        f"- forwarded targets used by native H2 applications: "
        f"{summary['native_h2_evidence']}",
        "- H2 native prefix: `0x81C30000`; wrapper entry: `0x81C30040`",
        "- H1 Mission prefix/code: `0x83C00000/+0x20`, aliased by 32 MiB SDRAM",
        "  to `0x81C00000/+0x20`",
        "",
        "| Service | H1 V2 target | H2 best target | Score | Confidence | Same offset |",
        "| --- | --- | --- | ---: | --- | --- |",
    ]
    for row in report["rows"]:
        if row["action"] != "forward":
            lines.append(
                f"| `{row['table']}+{row['v1_offset_hex']}` | local shim | "
                f"local shim | - | `{row['action']}` | - |"
            )
            continue
        best = row["best_h2"]
        lines.append(
            f"| `{row['table']}+{row['v1_offset_hex']}` | "
            f"`+{row['h1_v2_offset_hex']}` | `+{best['offset_hex']}` / "
            f"`{best['pointer']}` | {best['score']:.3f} | "
            f"{best['confidence']} | {best['same_offset']} |"
        )
    lines.extend(
        [
            "",
            "## Weak/unresolved services and native H2 evidence",
            "",
            "A native call at the mapped slot proves that the slot is live on H2; it",
            "does not by itself prove that the H1 argument and return-value contract is",
            "identical. Those calls narrow the dynamic work needed for the wrapper.",
            "",
            "| Service | Mapped H2 slot | Mission calls | H2 native calls | H2 apps |",
            "| --- | --- | ---: | ---: | ---: |",
        ]
    )
    for row in report["rows"]:
        if row["action"] != "forward" or row["best_h2"]["confidence"] in {
            "strong_fingerprint",
            "probable_fingerprint",
        }:
            continue
        evidence = row.get("native_h2_evidence", {"calls": 0, "app_count": 0})
        lines.append(
            f"| `{row['table']}+{row['v1_offset_hex']}` | "
            f"`+{row['h1_v2_offset_hex']}` | {row['v1_calls']} | "
            f"{evidence['calls']} | {evidence['app_count']} |"
        )
    lines.extend(
        [
            "",
            "## Porting boundary",
            "",
            "The H1 V2 wrapper cannot be copied unchanged. It reads the native prefix",
            "at `0x83C00000`, while H2 publishes it at `0x81C30000`",
            "(`0x83C30000` through SDRAM wrapping). An H2 stage must save the native",
            "prefix there, build a V1-shaped prefix at aliased `0x81C00000`, then load",
            "the unmodified Mission payload at `0x81C00020`.",
            "",
            "The physical H2 has only Left, Right, Confirm, Return, Volume-/+, and",
            "Power. Mission therefore also needs a touchscreen control overlay for",
            "Up/Down and any game actions not expressible with those keys. Multiplayer",
            "or link features must be disabled because H2 has no link chip.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("compatibility_json", type=Path)
    parser.add_argument("--h1-v2-os", type=Path, required=True)
    parser.add_argument("--h1-v2-extos1", type=Path, required=True)
    parser.add_argument("--h1-v2-extos2", type=Path, required=True)
    parser.add_argument("--h2-kernel", type=Path, required=True)
    parser.add_argument("--h2-classic-os", type=Path, required=True)
    parser.add_argument("--h2-cartoon-os", type=Path, required=True)
    parser.add_argument(
        "--h2-native-services",
        type=Path,
        help="optional output from scan_h2_packet_bda_services.py",
    )
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--markdown", type=Path, required=True)
    args = parser.parse_args()

    h1_images = [
        Image("H1 V2 OS", 0x80004000, args.h1_v2_os.read_bytes()),
        Image("H1 V2 ExtOs1", 0x80600000, args.h1_v2_extos1.read_bytes()),
        Image("H1 V2 ExtOs2", 0x809F0000, args.h1_v2_extos2.read_bytes()),
    ]
    h2_images = [
        Image("H2 kernel", 0x80004000, args.h2_kernel.read_bytes()),
        Image("H2 classic OS", 0x804AF000, args.h2_classic_os.read_bytes()),
        Image("H2 cartoon OS", 0x8086B000, args.h2_cartoon_os.read_bytes()),
    ]
    source = json.loads(args.compatibility_json.read_text(encoding="utf-8"))
    native_services: dict[tuple[str, int], dict[str, object]] = {}
    if args.h2_native_services:
        native_report = json.loads(args.h2_native_services.read_text(encoding="utf-8"))
        native_services = {
            (str(item["table"]), int(item["offset"])): item
            for item in native_report["rows"]
        }
    table_candidates = {table: candidates(h2_images, table) for table in H2_TABLES}
    rows: list[dict[str, object]] = []
    for item in source["rows"]:
        row: dict[str, object] = {
            "table": item["table"],
            "v1_offset": item["v1_offset"],
            "v1_offset_hex": item["v1_offset_hex"],
            "v1_calls": item["v1_calls"],
            "action": item["action"],
        }
        if item["action"] != "forward":
            rows.append(row)
            continue
        table = str(item["table"])
        h1_pointer = int(str(item["v2_pointer"]), 0)
        h1_words = instruction_words(h1_images, h1_pointer)
        ranked: list[dict[str, object]] = []
        target_offset = int(item["v2_offset"])
        for offset, pointer in table_candidates[table]:
            score, fine, coarse, prefix = similarity(
                h1_words, instruction_words(h2_images, pointer)
            )
            ranked.append(
                {
                    "offset": offset,
                    "offset_hex": f"0x{offset:03X}",
                    "pointer": f"0x{pointer:08X}",
                    "score": round(score, 6),
                    "fine": round(fine, 6),
                    "coarse": round(coarse, 6),
                    "normalized_prefix_words": prefix,
                    "same_offset": offset == target_offset,
                    "confidence": confidence(score),
                }
            )
        ranked.sort(
            key=lambda value: (
                value["score"],
                value["normalized_prefix_words"],
                value["same_offset"],
            ),
            reverse=True,
        )
        row.update(
            {
                "h1_v2_offset": target_offset,
                "h1_v2_offset_hex": f"0x{target_offset:03X}",
                "h1_v2_pointer": f"0x{h1_pointer:08X}",
                "best_h2": ranked[0],
                "top_h2": ranked[:5],
                "native_h2_evidence": {
                    "calls": int(native_services.get((table, target_offset), {}).get("calls", 0)),
                    "app_count": int(
                        native_services.get((table, target_offset), {}).get("app_count", 0)
                    ),
                },
            }
        )
        rows.append(row)

    forwarded = [row for row in rows if row["action"] == "forward"]
    strong = sum(row["best_h2"]["confidence"] == "strong_fingerprint" for row in forwarded)
    probable = sum(row["best_h2"]["confidence"] == "probable_fingerprint" for row in forwarded)
    report = {
        "format": "h2-v2.2l-mission-static-compat-v1",
        "h2_runtime_prefix": [
            "0x00000000", "0x80651EF0", "0x800CA950", "0x800CA830",
            "0x800CAE44", "0x8095AB80", "0x800CA9F4", "0x00000000",
            "0x00000000", "0x00000000", "0x800AF484", "0x800AF60C",
            "0x8095AA20", "0x80663FF0", "0x00000000", "0x00000000",
        ],
        "h2_tables": {key: f"0x{value:08X}" for key, value in H2_TABLES.items()},
        "table_executable_candidates": {
            key: len(value) for key, value in table_candidates.items()
        },
        "summary": {
            "mission_services": len(rows),
            "forwarded_services": len(forwarded),
            "strong_fingerprints": strong,
            "probable_fingerprints": probable,
            "weak_or_unresolved": len(forwarded) - strong - probable,
            "local_shims": len(rows) - len(forwarded),
            "native_h2_evidence": sum(
                int(row.get("native_h2_evidence", {}).get("calls", 0)) > 0
                for row in forwarded
            ),
            "same_offset_best_matches": sum(
                bool(row["best_h2"]["same_offset"]) for row in forwarded
            ),
        },
        "rows": rows,
    }
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    args.markdown.parent.mkdir(parents=True, exist_ok=True)
    args.markdown.write_text(render_markdown(report), encoding="utf-8", newline="\n")
    print(json.dumps(report["summary"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
