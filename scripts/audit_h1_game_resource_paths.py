#!/usr/bin/env python3
"""Verify that release BDAs open their packaged data below A:\\应用\\数据."""

from __future__ import annotations

import argparse
from pathlib import Path


RESOURCE_PATHS = {
    "H17Days.bda": r"A:\应用\数据\7DAYS.APP",
    "H1Alibaba.bda": r"A:\应用\数据\ALIBABA.APP",
    "H1Brick.bda": r"A:\应用\数据\BRICK.APP",
    "H1Bubble.bda": r"A:\应用\数据\BUBBLE.APP",
    "H1BWFighter.bda": r"A:\应用\数据\BWFIGHTER.APP",
    "H1Candy.bda": r"A:\应用\数据\CANDY.APP",
    "H1Doom.bda": r"A:\应用\数据\DOOM1.WAD",
    "H1Doudizhu.bda": r"A:\应用\数据\DOUDIZHU.APP",
    "H1Drift.bda": r"A:\应用\数据\DRIFT.APP",
    "H1LinkLink.bda": r"A:\应用\数据\LINKLINK.APP",
    "H1LubiLubi.bda": r"A:\应用\数据\LUBILUBI.APP",
    "H1PAL.bda": r"A:\应用\数据\PAL.APP",
    "H1Snake.bda": r"A:\应用\数据\SNAKE.APP",
    "H1TD1.bda": r"A:\应用\数据\TD1.APP",
    "H1TD2.bda": r"A:\应用\数据\TD2.APP",
    "H1Tetris.bda": r"A:\应用\数据\TETRIS.APP",
    "H1Xingtian.bda": r"A:\应用\数据\XINGTIAN.APP",
    "H1Zhaoyun.bda": r"A:\应用\数据\ZHAOYUN.APP",
    "H1CS15Lite.bda": r"A:\应用\数据\CS15LITE\CS15.C15PAK",
    "H1KOVPlus.bda": r"A:\应用\数据\KOVH1\KOVH1.PAK",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    errors: list[str] = []
    for name, expected_path in RESOURCE_PATHS.items():
        bda = args.directory / name
        if not bda.is_file():
            errors.append(f"missing BDA: {name}")
            continue
        data = bda.read_bytes()
        expected = expected_path.encode("gbk")
        if expected not in data:
            errors.append(f"{name}: missing GBK resource path {expected_path}")
        basename = expected_path.rsplit("\\", 1)[-1]
        old_root_path = f"A:\\{basename}".encode("ascii")
        if old_root_path in data:
            errors.append(f"{name}: still contains root resource path A:\\{basename}")
    old_kov = rb"A:\KOVH1\KOVH1.PAK"
    kov = args.directory / "H1KOVPlus.bda"
    if kov.is_file() and old_kov in kov.read_bytes():
        errors.append("H1KOVPlus.bda: still contains root KOV pack path")
    if errors:
        raise SystemExit("resource path audit failed:\n- " + "\n- ".join(errors))
    print(f"resource_path_audit=ok bda_count={len(RESOURCE_PATHS)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
