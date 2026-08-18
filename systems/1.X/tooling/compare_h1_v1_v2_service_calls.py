#!/usr/bin/env python3
"""Compare service-table calls used by one V1 BDA with native V2 BDAs."""

from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCANNER_DIR = ROOT / "h1-bda-sdk" / "reverse" / "tools"
if str(SCANNER_DIR) not in sys.path:
    sys.path.insert(0, str(SCANNER_DIR))

from scan_service_calls import scan_file  # noqa: E402


ApiKey = tuple[str, int]


def collect(path: Path) -> tuple[dict[ApiKey, int], dict[ApiKey, set[str]], list[dict[str, object]]]:
    files = [path] if path.is_file() else sorted(path.rglob("*.bda"))
    totals: collections.Counter[ApiKey] = collections.Counter()
    users: dict[ApiKey, set[str]] = collections.defaultdict(set)
    reports: list[dict[str, object]] = []
    for candidate in files:
        try:
            report = scan_file(candidate)
        except ValueError:
            continue
        calls = report["calls"]
        if not calls:
            continue
        reports.append(report)
        relative = candidate.name if path.is_file() else str(candidate.relative_to(path))
        for call in calls:
            key = (str(call["table"]), int(call["api_offset"]))
            totals[key] += 1
            users[key].add(relative)
    return dict(totals), users, reports


def build_report(v1_bda: Path, v2_root: Path) -> dict[str, object]:
    v1_totals, _v1_users, v1_reports = collect(v1_bda)
    v2_totals, v2_users, v2_reports = collect(v2_root)
    rows = []
    for table, offset in sorted(v1_totals):
        key = (table, offset)
        rows.append(
            {
                "table": table,
                "offset": offset,
                "offset_hex": f"0x{offset:03X}",
                "v1_calls": v1_totals[key],
                "v2_calls": v2_totals.get(key, 0),
                "v2_app_count": len(v2_users.get(key, set())),
                "v2_apps": sorted(v2_users.get(key, set())),
            }
        )
    overlap = sum(1 for row in rows if row["v2_calls"])
    return {
        "v1_bda": v1_bda.name,
        "v1_payload_offset": v1_reports[0]["payload_offset"] if v1_reports else None,
        "v1_distinct_calls": len(v1_totals),
        "v2_root": v2_root.name,
        "v2_bdas_with_calls": len(v2_reports),
        "v2_payload_offsets": sorted({int(report["payload_offset"]) for report in v2_reports}),
        "v2_distinct_calls": len(v2_totals),
        "covered_v1_calls": overlap,
        "uncovered_v1_calls": len(rows) - overlap,
        "rows": rows,
    }


def render_markdown(report: dict[str, object]) -> str:
    lines = [
        "# H1 V1/V2 Service-Call Compatibility",
        "",
        f"- V1 application: `{report['v1_bda']}`",
        f"- V1 distinct service offsets: {report['v1_distinct_calls']}",
        f"- V2 native BDAs with detected calls: {report['v2_bdas_with_calls']}",
        f"- V2 distinct service offsets: {report['v2_distinct_calls']}",
        f"- V1 offsets observed in V2: {report['covered_v1_calls']}",
        f"- V1 offsets not observed in V2: {report['uncovered_v1_calls']}",
        "",
        "Static overlap proves only that the same table-relative slot is called.",
        "Signatures and semantics still require firmware or dynamic validation.",
        "",
        "| Table | Offset | V1 calls | V2 calls | V2 apps | Evidence |",
        "| --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in report["rows"]:
        apps = row["v2_apps"]
        evidence = ", ".join(f"`{app}`" for app in apps[:3]) if apps else "not observed"
        if len(apps) > 3:
            evidence += f" (+{len(apps) - 3} more)"
        lines.append(
            f"| {row['table']} | `+{row['offset_hex']}` | {row['v1_calls']} | "
            f"{row['v2_calls']} | {row['v2_app_count']} | {evidence} |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("v1_bda", type=Path)
    parser.add_argument("v2_root", type=Path)
    parser.add_argument("--json", type=Path)
    parser.add_argument("--markdown", type=Path)
    args = parser.parse_args()

    report = build_report(args.v1_bda, args.v2_root)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    if args.markdown:
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        args.markdown.write_text(render_markdown(report), encoding="utf-8", newline="\n")

    print(
        "v1_distinct={v1_distinct_calls} v2_distinct={v2_distinct_calls} "
        "covered={covered_v1_calls} uncovered={uncovered_v1_calls}".format(**report)
    )
    for row in report["rows"]:
        if row["v2_calls"] == 0:
            print(f"uncovered {row['table']}+{row['offset_hex']} v1_calls={row['v1_calls']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
