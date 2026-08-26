#!/usr/bin/env python3
"""Scan native H2 BDA service calls directly from packet1.dat."""

from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = REPOSITORY_ROOT / "scripts"
SCANNER = REPOSITORY_ROOT / "h1-bda-sdk" / "reverse" / "tools"
for directory in (SCRIPTS, SCANNER):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

from build_h2_v2_image import parse_packet  # noqa: E402
import scan_service_calls as scanner  # noqa: E402


H2_ENTRY_VA = 0x81C30040
H2_TABLE_SLOTS = {
    0x83C30004: "GUI",
    0x83C30008: "FS",
    0x83C3000C: "SYS",
    0x83C30010: "MEM",
    0x83C30014: "RES",
}


def render_markdown(report: dict[str, object]) -> str:
    lines = [
        "# H2 V2.2L native BDA service calls",
        "",
        "The scanner reads BDA payloads directly from `packet1.dat`; it does not",
        "expand the application tree. H2 applications use the prefix alias at",
        "`0x83C30000` and execute at `0x81C30040`.",
        "",
        f"- BDA files scanned: {report['bda_files']}",
        f"- BDA files with recognized calls: {report['files_with_calls']}",
        f"- distinct service offsets: {report['distinct_services']}",
        "",
        "| Service | Calls | Native H2 applications |",
        "| --- | ---: | ---: |",
    ]
    for row in report["rows"]:
        lines.append(
            f"| `{row['table']}+{row['offset_hex']}` | {row['calls']} | "
            f"{row['app_count']} |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("packet", type=Path)
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--markdown", type=Path, required=True)
    args = parser.parse_args()

    scanner.TABLE_SLOTS = H2_TABLE_SLOTS
    scanner.ENTRY_VA = H2_ENTRY_VA
    packet = parse_packet(args.packet)
    totals: collections.Counter[tuple[str, int]] = collections.Counter()
    users: dict[tuple[str, int], set[str]] = collections.defaultdict(set)
    file_reports: list[dict[str, object]] = []
    bda_count = 0
    with args.packet.open("rb") as stream:
        for entry in packet.entries:
            if not entry.path.lower().endswith(".bda"):
                continue
            bda_count += 1
            stream.seek(entry.packet_offset)
            data = stream.read(entry.size)
            if len(data) != entry.size:
                raise IOError(f"short packet read for {entry.path}")
            try:
                payload_offset, category = scanner._decode_header(Path(entry.path), data)
            except ValueError:
                continue
            calls = scanner.scan_payload(data, payload_offset)
            if not calls:
                continue
            file_reports.append(
                {
                    "path": entry.path,
                    "category": category,
                    "payload_offset": payload_offset,
                    "calls": calls,
                }
            )
            seen: set[tuple[str, int]] = set()
            for call in calls:
                key = (str(call["table"]), int(call["api_offset"]))
                totals[key] += 1
                seen.add(key)
            for key in seen:
                users[key].add(entry.path)

    rows = [
        {
            "table": table,
            "offset": offset,
            "offset_hex": f"0x{offset:03X}",
            "calls": count,
            "app_count": len(users[(table, offset)]),
            "applications": sorted(users[(table, offset)]),
        }
        for (table, offset), count in sorted(totals.items())
    ]
    report = {
        "format": "h2-v2.2l-native-bda-services-v1",
        "packet": args.packet.name,
        "entry_va": f"0x{H2_ENTRY_VA:08X}",
        "table_slots": {f"0x{key:08X}": value for key, value in H2_TABLE_SLOTS.items()},
        "bda_files": bda_count,
        "files_with_calls": len(file_reports),
        "distinct_services": len(rows),
        "rows": rows,
        "files": file_reports,
    }
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    args.markdown.parent.mkdir(parents=True, exist_ok=True)
    args.markdown.write_text(render_markdown(report), encoding="utf-8", newline="\n")
    print(
        f"bdas={bda_count} files_with_calls={len(file_reports)} "
        f"distinct_services={len(rows)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
