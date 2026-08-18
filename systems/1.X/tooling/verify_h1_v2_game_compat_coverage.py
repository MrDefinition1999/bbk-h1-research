#!/usr/bin/env python3
"""Verify that V2 compatibility rules cover every service used by V1 games."""

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

from h1_v2_game_compat_rules import classify_service  # noqa: E402


def build_report(games: list[Path]) -> dict[str, object]:
    usage: collections.Counter[tuple[str, int]] = collections.Counter()
    game_rows = []
    for game in games:
        report = scan_file(game)
        calls = report["calls"]
        services = {(str(call["table"]), int(call["api_offset"])) for call in calls}
        usage.update((str(call["table"]), int(call["api_offset"])) for call in calls)
        game_rows.append({"name": game.name, "services": len(services), "calls": len(calls)})

    rows = []
    unmapped = []
    counts: collections.Counter[str] = collections.Counter()
    for table, offset in sorted(usage):
        rule = classify_service(table, offset)
        row = {
            "table": table,
            "offset": f"0x{offset:03X}",
            "calls": usage[(table, offset)],
            "action": rule.action if rule else "unmapped",
            "target": None if rule is None or rule.target is None else f"0x{rule.target:03X}",
        }
        rows.append(row)
        if rule is None:
            unmapped.append(row)
        else:
            counts[rule.action] += 1

    return {
        "format": "h1-v2-v1-game-compat-coverage-v1",
        "games": game_rows,
        "unique_services": len(rows),
        "action_counts": dict(sorted(counts.items())),
        "unmapped": unmapped,
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("games", nargs="+", type=Path)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()
    report = build_report(args.games)
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    print(
        f"games={len(report['games'])} unique={report['unique_services']} "
        f"unmapped={len(report['unmapped'])}",
        file=sys.stderr,
    )
    return 1 if report["unmapped"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
