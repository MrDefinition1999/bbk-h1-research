#!/usr/bin/env python3
"""Build the seven V1 game wrappers and a sanitized local delivery manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from build_h1_v2_game_loader import build_game_loader
from verify_h1_v2_game_compat_coverage import build_report


DEFAULT_GAMES = (
    "中国象棋",
    "使命",
    "俄罗斯",
    "宠物泡泡",
    "猫狗大战",
    "雷霆战机",
    "黑白子",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v1-app-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--game", action="append", dest="games")
    parser.add_argument(
        "--mission-external-path",
        help="also build a small Mission wrapper using this H1 guest payload path",
    )
    args = parser.parse_args()

    names = tuple(args.games or DEFAULT_GAMES)
    sources = [args.v1_app_dir / f"{name}.bda" for name in names]
    missing = [path.name for path in sources if not path.is_file()]
    if missing:
        raise FileNotFoundError("missing V1 games: " + ", ".join(missing))

    coverage = build_report(sources)
    if coverage["unmapped"]:
        rendered = ", ".join(
            f"{row['table']}+{row['offset']}" for row in coverage["unmapped"]
        )
        raise ValueError("compatibility rules do not cover: " + rendered)

    games_dir = args.output_dir / "games"
    rows = []
    for name, source in zip(names, sources, strict=True):
        output = games_dir / f"{name}.bda"
        build_game_loader(source, output)
        rows.append(
            {
                "name": name,
                "source_sha256": sha256(source),
                "output": f"games/{output.name}",
                "output_bytes": output.stat().st_size,
                "output_sha256": sha256(output),
            }
        )

    external_row = None
    if args.mission_external_path:
        mission = args.v1_app_dir / "使命.bda"
        output = args.output_dir / "test" / "使命-外置兼容.bda"
        build_game_loader(mission, output, external_path=args.mission_external_path)
        external_row = {
            "output": f"test/{output.name}",
            "guest_payload_path": args.mission_external_path,
            "output_bytes": output.stat().st_size,
            "output_sha256": sha256(output),
        }

    manifest = {
        "format": "h1-v2-v1-game-compat-release-v1",
        "policy": {
            "v1_coin_system": "allow_without_charge",
            "v2_system_files_modified": False,
            "original_game_code_modified": False,
        },
        "coverage": {
            "games": len(coverage["games"]),
            "unique_services": coverage["unique_services"],
            "unmapped": len(coverage["unmapped"]),
            "action_counts": coverage["action_counts"],
        },
        "games": rows,
        "external_mission_test": external_row,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (args.output_dir / "coverage.json").write_text(
        json.dumps(coverage, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"output={args.output_dir}")
    print(f"games={len(rows)}")
    print(f"unique_services={coverage['unique_services']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
