#!/usr/bin/env python3
"""Rebuild every H1 game BDA whose source is maintained in this workspace."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
SDK_ROOT = WORKSPACE_ROOT / "h1-bda-sdk"
A320_BUILDER = SDK_ROOT / "ports/dingoo_a320/tools/build_game_port.py"
A320_ASSETS = SDK_ROOT / "ports/dingoo_a320/assets"
BUILD_ROOT = SDK_ROOT / "build"

GAME_RECIPES = (
    {"slug": "alibaba", "prepared": "alibaba", "output": "H1Alibaba", "runtime": "ALIBABA.APP", "status": "ALISTAT.BIN", "title": "阿里巴巴", "app_main": "ALIBABA.APP"},
    {"slug": "brick", "prepared": "brick", "output": "H1Brick", "runtime": "BRICK.APP", "status": "BRKSTAT.BIN", "title": "打砖块", "rotate": True, "filesystem_only": ("brick.bin",)},
    {"slug": "bubble", "prepared": "bubble", "output": "H1Bubble", "runtime": "BUBBLE.APP", "status": "BUBSTAT.BIN", "title": "泡泡龙", "app_main": "BUBBLE.APP", "rotate": True},
    {"slug": "bwfighter", "prepared": "bwfighter", "output": "H1BWFighter", "runtime": "BWFIGHTER.APP", "status": "BWFSTAT.BIN", "title": "霸王战机", "key_event": "0x80A21D34", "patches": ("0x80A0C108=0x24020001",)},
    {"slug": "candy", "prepared": "candyhouse", "output": "H1Candy", "runtime": "CANDY.APP", "status": "CNDSTAT.BIN", "title": "糖果屋"},
    {"slug": "doudizhu", "prepared": "doudizhu", "output": "H1Doudizhu", "runtime": "DOUDIZHU.APP", "status": "DDZSTAT.BIN", "title": "斗地主"},
    {"slug": "drift", "prepared": "drift", "output": "H1Drift", "runtime": "DRIFT.APP", "status": "DRFSTAT.BIN", "title": "极限漂移", "app_main": "DRIFT.APP"},
    {"slug": "linklink", "prepared": "linklink", "output": "H1LinkLink", "runtime": "LINKLINK.APP", "status": "LINKSTAT.BIN", "title": "连连看", "app_main": "LINKLINK.APP"},
    {"slug": "lubilubi", "prepared": "lubilubi", "output": "H1LubiLubi", "runtime": "LUBILUBI.APP", "status": "LUBISTAT.BIN", "title": "卢比卢比"},
    {"slug": "pal", "prepared": "pal", "output": "H1PAL", "runtime": "PAL.APP", "status": "PALSTAT.BIN", "title": "仙剑奇侠传", "app_main": "?????.app"},
    {"slug": "snake", "prepared": "snake", "output": "H1Snake", "runtime": "SNAKE.APP", "status": "SNAKSTAT.BIN", "title": "迪克蛇", "app_main": "SNAKE.APP"},
    {"slug": "td1", "prepared": "td1", "output": "H1TD1", "runtime": "TD1.APP", "status": "TD1STAT.BIN", "title": "天地道", "app_main": "A:\\TD1.APP"},
    {"slug": "td2", "prepared": "td2", "output": "H1TD2", "runtime": "TD2.APP", "status": "TD2STAT.BIN", "title": "天地道II", "app_main": "TD2.APP", "patches": ("0x80B05158=0x24020001",)},
    {"slug": "tetris", "prepared": "tetris", "output": "H1Tetris", "runtime": "TETRIS.APP", "status": "TETSTAT.BIN", "title": "俄罗斯方块", "app_main": "TETRIS.APP", "rotate": True},
    {"slug": "xingtian", "prepared": "xingtian", "output": "H1Xingtian", "runtime": "XINGTIAN.APP", "status": "XINSTAT.BIN", "title": "战神刑天", "app_main": "XINGTIAN.APP"},
    {"slug": "zhaoyun", "prepared": "zhaoyun", "output": "H1Zhaoyun", "runtime": "ZHAOYUN.APP", "status": "ZHASTAT.BIN", "title": "赵云传", "app_main": "ZHAOYUN.APP"},
)


def child_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment.setdefault("SOURCE_DATE_EPOCH", "1785542400")
    return environment


def run(command: list[str]) -> None:
    subprocess.run(
        command,
        cwd=WORKSPACE_ROOT,
        env=child_environment(),
        check=True,
    )


def build_a320(recipe: dict[str, object], emulator: bool = False) -> None:
    slug = str(recipe["slug"])
    output_stem = str(recipe["output"])
    output_suffix = "-emulator" if emulator else ""
    report_target = "emulator" if emulator else "hardware"
    command = [
        sys.executable,
        str(A320_BUILDER),
        str(WORKSPACE_ROOT / "work/analysis/dingoo" / f"{recipe['prepared']}-prepared.json"),
        "--title", str(recipe["title"]),
        "--runtime-name", str(recipe["runtime"]),
        "--status-name", str(recipe["status"]),
        "--message-title", str(recipe["title"]),
        "--icon", str(A320_ASSETS / f"{slug}-icon.png"),
        "--output", str(BUILD_ROOT / f"{output_stem}{output_suffix}.bda"),
        "--elf", str(BUILD_ROOT / f"{output_stem}{output_suffix}.elf"),
        "--report", str(BUILD_ROOT / f"{slug}-{report_target}-build.json"),
    ]
    if emulator:
        command.append("--emulator")
    if recipe.get("app_main"):
        command.extend(["--app-main-name", str(recipe["app_main"])])
    if recipe.get("rotate"):
        command.append("--rotate-counterclockwise")
    if recipe.get("key_event"):
        command.extend(["--key-event-wrapper-address", str(recipe["key_event"])])
    for name in recipe.get("filesystem_only", ()):
        command.extend(["--filesystem-only-name", str(name)])
    for patch in recipe.get("patches", ()):
        command.extend(["--patch-word", str(patch)])
    run(command)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--only",
        action="append",
        default=[],
        help="build only a recipe slug, or one of: 7days, doom, kov",
    )
    parser.add_argument(
        "--emulator",
        action="store_true",
        help="build emulator-bridge variants instead of real-hardware variants",
    )
    args = parser.parse_args()
    selected = {value.casefold() for value in args.only}

    for recipe in GAME_RECIPES:
        if not selected or str(recipe["slug"]).casefold() in selected:
            build_a320(recipe, emulator=args.emulator)
    standalone = (
        ("7days", SDK_ROOT / "ports/dingoo_a320/7days/build_port.py"),
        ("doom", SDK_ROOT / "ports/doom/build_port.py"),
        ("kov", SDK_ROOT / "ports/kov_pgm/build_port.py"),
    )
    for name, builder in standalone:
        if not selected or name in selected:
            if args.emulator and name == "7days":
                run([
                    sys.executable,
                    str(builder),
                    "--emulator",
                    "--output", str(BUILD_ROOT / "H17Days-emulator.bda"),
                    "--elf", str(BUILD_ROOT / "H17Days-emulator.elf"),
                ])
            elif args.emulator and name == "kov":
                run([
                    sys.executable,
                    str(builder),
                    "--emulator-bridge",
                    "--emulator-host-yield",
                    "--output", str(BUILD_ROOT / "H1KOVPlus-emulator.bda"),
                    "--elf", str(BUILD_ROOT / "H1KOVPlus-emulator.elf"),
                ])
            elif not args.emulator:
                run([sys.executable, str(builder)])
    unknown = selected - {
        *(str(recipe["slug"]).casefold() for recipe in GAME_RECIPES),
        *(name for name, _builder in standalone),
    }
    if unknown:
        raise SystemExit("unknown build target(s): " + ", ".join(sorted(unknown)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
