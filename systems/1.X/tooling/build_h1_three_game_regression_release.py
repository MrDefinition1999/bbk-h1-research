#!/usr/bin/env python3
"""Build the reproducible three-game H1 real-hardware regression package."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
SDK_ROOT = WORKSPACE_ROOT / "h1-bda-sdk"
DELIVERABLES_ROOT = WORKSPACE_ROOT / "deliverables"
SOURCE_RELEASE = DELIVERABLES_ROOT / "H1-all-games-real-hardware-2026-08-02"
RELEASE_NAME = "H1-three-game-hardware-regression-2026-08-02"
STAGE = DELIVERABLES_ROOT / RELEASE_NAME
ARCHIVE = STAGE.with_suffix(".zip")
ZIP_TIMESTAMP = (2026, 8, 2, 0, 0, 0)
PROGRAM_DIRECTORY = Path("A-root") / "应用" / "程序"
DATA_DIRECTORY = Path("A-root") / "应用" / "数据"
GAMES = {
    "H1Doudizhu.bda": (
        "DOUDIZHU.APP",
        "873E8A2107594829F0175AB85A16D6D0E3EA56604D6F6140F2EB18F72BDCF28B",
    ),
    "H1PAL.bda": (
        "PAL.APP",
        "B48A1DECF861E6292DC8C402DFDA838A1D91D59BBA7311F034A43B3AE01A7A36",
    ),
    "H1Zhaoyun.bda": (
        "ZHAOYUN.APP",
        "BEC4E7A5193B08B33F95629A29931B6DCA3B7FBF6B832D6207488B4E19FF737F",
    ),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest().upper()


def generated_target(path: Path) -> Path:
    target = path.resolve()
    root = DELIVERABLES_ROOT.resolve()
    if target == root or root not in target.parents:
        raise SystemExit(f"refusing generated output outside deliverables: {target}")
    return target


def run(command: list[str]) -> None:
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment.setdefault("SOURCE_DATE_EPOCH", "1785542400")
    subprocess.run(
        command,
        cwd=WORKSPACE_ROOT,
        env=environment,
        check=True,
    )


def build_bdas() -> None:
    run(
        [
            sys.executable,
            str(WORKSPACE_ROOT / "scripts" / "build_all_h1_game_bdas.py"),
            "--only",
            "doudizhu",
            "--only",
            "pal",
            "--only",
            "zhaoyun",
        ]
    )
    for name, (_resource, expected_hash) in GAMES.items():
        path = SDK_ROOT / "build" / name
        actual_hash = sha256(path)
        if actual_hash != expected_hash:
            raise SystemExit(
                f"{name} no longer matches the 2026-08-01 hardware baseline: "
                f"{actual_hash}"
            )


def reset_stage() -> None:
    target = generated_target(STAGE)
    if target.exists():
        shutil.rmtree(target)
    (target / PROGRAM_DIRECTORY).mkdir(parents=True)
    (target / DATA_DIRECTORY).mkdir(parents=True)


def stage_files() -> None:
    source_data = SOURCE_RELEASE / "A-root" / "应用" / "数据"
    for bda_name, (resource_name, _expected_hash) in GAMES.items():
        bda = SDK_ROOT / "build" / bda_name
        resource = source_data / resource_name
        if not resource.is_file():
            raise SystemExit(f"missing packaged game resource: {resource_name}")
        expected_path = f"A:\\应用\\数据\\{resource_name}".encode("gbk")
        if expected_path not in bda.read_bytes():
            raise SystemExit(f"{bda_name} does not reference {resource_name} below A:\\应用\\数据")
        shutil.copyfile(bda, STAGE / PROGRAM_DIRECTORY / bda_name)
        shutil.copyfile(resource, STAGE / DATA_DIRECTORY / resource_name)

    (STAGE / "游戏说明.txt").write_text(
        "H1 三款实机回归测试说明\n"
        "=======================\n\n"
        "注意：先备份机器内同名 BDA，再将 A-root 的内容合并到 A: 盘。\n"
        "本包用于确认仙剑奇侠传、赵云传和斗地主的画面与稳定性恢复。\n\n"
        "仙剑奇侠传\n"
        "方向键移动和选择；确认键/Enter/J 对话、调查和确认；返回键/K\n"
        "打开或关闭菜单；Esc 退出到桌面。请重点测试进入剧情、行走、菜单和战斗。\n\n"
        "赵云传\n"
        "方向键移动；确认键对话、调查和确认；返回键取消或返回菜单；\n"
        "Esc 退出到桌面。请重点测试进入地图、移动、战斗和退出。\n\n"
        "斗地主\n"
        "方向键在手牌、按钮和菜单间移动；确认键选牌和执行操作；返回键\n"
        "撤销选择或返回；Esc 退出到桌面。请重点测试完整一局和返回桌面。\n",
        encoding="utf-8",
    )


def audit_icons_and_privacy() -> None:
    with tempfile.TemporaryDirectory(prefix="h1-regression-icon-audit-") as temporary:
        report = Path(temporary) / "icons.json"
        run(
            [
                sys.executable,
                str(SDK_ROOT / "scripts" / "audit_release_icons.py"),
                str(STAGE / PROGRAM_DIRECTORY),
                "--expected-count",
                str(len(GAMES)),
                "--output",
                str(report),
            ]
        )
    run(
        [
            sys.executable,
            str(WORKSPACE_ROOT / "scripts" / "audit_release_secrets.py"),
            str(STAGE),
        ]
    )


def build_archive() -> None:
    target = generated_target(ARCHIVE)
    with tempfile.NamedTemporaryFile(
        prefix=target.name + ".",
        suffix=".tmp",
        dir=target.parent,
        delete=False,
    ) as stream:
        temporary = Path(stream.name)
    try:
        paths = sorted(
            (path for path in STAGE.rglob("*") if path.is_file()),
            key=lambda path: path.relative_to(STAGE).as_posix().casefold(),
        )
        with zipfile.ZipFile(
            temporary,
            "w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=9,
        ) as output:
            for path in paths:
                relative = path.relative_to(STAGE).as_posix()
                info = zipfile.ZipInfo(relative, ZIP_TIMESTAMP)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                output.writestr(info, path.read_bytes(), compresslevel=9)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    run(
        [
            sys.executable,
            str(WORKSPACE_ROOT / "scripts" / "audit_release_secrets.py"),
            str(target),
        ]
    )


def main() -> int:
    build_bdas()
    reset_stage()
    stage_files()
    audit_icons_and_privacy()
    build_archive()
    print(f"stage={STAGE.name} files={sum(path.is_file() for path in STAGE.rglob('*'))}")
    print(f"archive={ARCHIVE.name} size={ARCHIVE.stat().st_size} sha256={sha256(ARCHIVE)}")
    for name in sorted(GAMES):
        print(f"{name} sha256={sha256(STAGE / PROGRAM_DIRECTORY / name)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
