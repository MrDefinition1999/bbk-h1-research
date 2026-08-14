#!/usr/bin/env python3
"""Build the combined owner-authorized BBK H1 real-hardware game package."""

from __future__ import annotations

import argparse
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
GAME_BDA_BUILDER = WORKSPACE_ROOT / "scripts" / "build_all_h1_game_bdas.py"
RESOURCE_PATH_AUDITOR = (
    WORKSPACE_ROOT / "scripts" / "audit_h1_game_resource_paths.py"
)
KOV_TOOL = SDK_ROOT / "ports" / "kov_pgm" / "tools" / "prepare_rom_pack.py"
KOV_PACK = WORKSPACE_ROOT / "work" / "private" / "kov" / "KOVH1.PAK"
KOV_PACK_SIZE = 58_785_792
KOV_PACK_SHA256 = "6A3E5EF41212AA47A242689D904374DF0CBFEF4E34313053B2D7C1755642DB53"
DELIVERABLES_ROOT = WORKSPACE_ROOT / "deliverables"
CS_ROOT = WORKSPACE_ROOT / "references" / "CS15-Lite-for9588"
CS_BDA = "H1CS15Lite.bda"
CS_BDA_PATH = CS_ROOT / "build" / "h1" / CS_BDA
CS_BDA_SIZE = 981_364
CS_BDA_SHA256 = "37E94249C215DA8E33E3CF0AB537F5963B22101BF26A75DC7851A2EAEAF491FF"
CS_PACK = WORKSPACE_ROOT / "work" / "private" / "cs15" / "CS15.C15PAK"
CS_PACK_SIZE = 12_552_216
CS_PACK_SHA256 = "37555033D9EFEA51B5B11FF25895EA4FCE2D3EF35C27F70C02F85B7C9CE33A42"
CS_PACK_TOOL = CS_ROOT / "tools" / "assetc.py"
CS_SOURCE_ARCHIVE = DELIVERABLES_ROOT / "CS15-Lite-H1-2026-07-31-source.zip"
CS_SOURCE_SHA256 = "A30B7EA7F88E832662E0C4F391BDBF3FF127D930C740D2E3E536F2E2BC34D0C8"
SOURCE_RELEASE = DELIVERABLES_ROOT / "H1-real-hardware-test-2026-07-29"
RELEASE_NAME = "H1-all-games-real-hardware-2026-08-02"
DEFAULT_STAGE = DELIVERABLES_ROOT / RELEASE_NAME
DEFAULT_ARCHIVE = DEFAULT_STAGE.with_suffix(".zip")
PROGRAM_DIRECTORY = Path("应用") / "程序"
DATA_DIRECTORY = Path("应用") / "数据"
KOV_BDA = "H1KOVPlus.bda"
ZIP_TIMESTAMP = (2026, 8, 2, 0, 0, 0)

BDA_NAMES = (
    "H17Days.bda",
    "H1Alibaba.bda",
    "H1Brick.bda",
    "H1Bubble.bda",
    "H1BWFighter.bda",
    "H1Candy.bda",
    "H1Doom.bda",
    "H1Doudizhu.bda",
    "H1Drift.bda",
    "H1LinkLink.bda",
    "H1LubiLubi.bda",
    "H1PAL.bda",
    "H1Snake.bda",
    "H1TD1.bda",
    "H1TD2.bda",
    "H1Tetris.bda",
    "H1Xingtian.bda",
    "H1Zhaoyun.bda",
    CS_BDA,
    KOV_BDA,
)
RUNTIME_NAMES = (
    "7DAYS.APP",
    "ALIBABA.APP",
    "BRICK.APP",
    "BUBBLE.APP",
    "BWFIGHTER.APP",
    "CANDY.APP",
    "DOOM1.WAD",
    "DOUDIZHU.APP",
    "DRIFT.APP",
    "LINKLINK.APP",
    "LUBILUBI.APP",
    "PAL.APP",
    "SNAKE.APP",
    "TD1.APP",
    "TD2.APP",
    "TETRIS.APP",
    "XINGTIAN.APP",
    "ZHAOYUN.APP",
)
PROHIBITED_SUFFIXES = {".elf", ".json", ".log", ".png", ".pyc", ".rom"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest().upper()


def ensure_generated_target(path: Path) -> Path:
    resolved = path.resolve()
    root = DELIVERABLES_ROOT.resolve()
    if resolved == root or root not in resolved.parents:
        raise SystemExit(f"refusing generated output outside deliverables: {resolved}")
    return resolved


def child_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return environment


def run(command: list[str]) -> None:
    subprocess.run(
        command,
        cwd=WORKSPACE_ROOT,
        env=child_environment(),
        check=True,
    )


def run_quiet(command: list[str]) -> None:
    completed = subprocess.run(
        command,
        cwd=WORKSPACE_ROOT,
        env=child_environment(),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    if completed.returncode:
        print(completed.stdout, file=sys.stderr, end="")
        raise subprocess.CalledProcessError(completed.returncode, command)


def validate_source(source_release: Path) -> Path:
    source_root = source_release / "A-root"
    required: list[Path] = []
    required.extend(source_root / name for name in RUNTIME_NAMES)
    required.extend(
        SDK_ROOT / "build" / name for name in BDA_NAMES
        if name not in {KOV_BDA, CS_BDA}
    )
    missing = [str(path.relative_to(source_release)) for path in required if not path.is_file()]
    if missing:
        raise SystemExit("missing source-release inputs: " + ", ".join(missing))
    kov_bda = SDK_ROOT / "build" / KOV_BDA
    if not kov_bda.is_file():
        raise SystemExit(f"missing current KOV BDA: {kov_bda}")
    if not KOV_PACK.is_file():
        raise SystemExit(f"missing owner-authorized KOV pack: {KOV_PACK}")
    if KOV_PACK.stat().st_size != KOV_PACK_SIZE or sha256(KOV_PACK) != KOV_PACK_SHA256:
        raise SystemExit("owner-authorized KOVH1.PAK failed size/SHA-256 validation")
    run([sys.executable, str(KOV_TOOL), "verify", str(KOV_PACK), "--pages"])
    if not CS_BDA_PATH.is_file():
        raise SystemExit(f"missing emulator-accepted CS15 BDA: {CS_BDA_PATH}")
    if CS_BDA_PATH.stat().st_size != CS_BDA_SIZE or sha256(CS_BDA_PATH) != CS_BDA_SHA256:
        raise SystemExit("CS15 BDA failed size/SHA-256 validation")
    if not CS_PACK.is_file():
        raise SystemExit(f"missing emulator-accepted CS15 pack: {CS_PACK}")
    if CS_PACK.stat().st_size != CS_PACK_SIZE or sha256(CS_PACK) != CS_PACK_SHA256:
        raise SystemExit("CS15.C15PAK failed size/SHA-256 validation")
    run_quiet([sys.executable, str(CS_PACK_TOOL), "inspect", str(CS_PACK)])
    if not CS_SOURCE_ARCHIVE.is_file() or sha256(CS_SOURCE_ARCHIVE) != CS_SOURCE_SHA256:
        raise SystemExit("CS15 corresponding-source archive is missing or invalid")
    return source_root


def reset_stage(stage: Path) -> None:
    target = ensure_generated_target(stage)
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)


def copy_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)


def sync_game_files(source_root: Path, stage: Path) -> None:
    destination_root = stage / "A-root"
    destination_data = destination_root / DATA_DIRECTORY
    for name in RUNTIME_NAMES:
        copy_file(source_root / name, destination_data / name)
    destination_apps = destination_root / PROGRAM_DIRECTORY
    for name in BDA_NAMES:
        if name == KOV_BDA:
            source = SDK_ROOT / "build" / name
        elif name == CS_BDA:
            source = CS_BDA_PATH
        else:
            source = SDK_ROOT / "build" / name
        copy_file(source, destination_apps / name)
    copy_file(KOV_PACK, destination_data / "KOVH1" / "KOVH1.PAK")
    copy_file(CS_PACK, destination_data / "CS15LITE" / CS_PACK.name)


def write_readme(_source_release: Path, stage: Path) -> None:
    (stage / "游戏说明.txt").write_text(
        "H1 移植游戏操作说明\n"
        "===================\n\n"
        "通用 A320 游戏键位\n"
        "------------------\n"
        "方向键或 W/A/S/D：移动、菜单导航\n"
        "确认键、Enter 或 J：A 键、确认、主要动作\n"
        "返回键或 K：B 键、取消、次要动作\n"
        "X / Y：A320 X / Y 键\n"
        "Q 或 Page Up：L 肩键\n"
        "E 或 Page Down：R 肩键\n"
        "Space：Start\n"
        "Shift：Select\n"
        "Esc：退出到 H1 桌面\n\n"
        "1. DOOM\n"
        "方向键用于菜单和前后移动；W/S 前进后退；A/D 左右平移；Q/E 转向。\n"
        "确认键或 Enter 确认；Space/J 开火；F 使用；Shift 奔跑；Z/X 或\n"
        "Page Up/Page Down 切换武器；C 打开地图；H 帮助；返回键/Esc 菜单。\n"
        "退出必须选择 Quit Game，出现提示后按实体 Y 键确认。\n\n"
        "2. 7 Days\n"
        "使用通用 A320 键位。首次语言提示用左右键选择，再按确认键。\n"
        "主菜单选择 New Game 或 Continue；Esc 可随时退出到桌面。\n\n"
        "3. 仙剑奇侠传\n"
        "方向键移动和选择；确认键/Enter/J 对话、调查和确认；返回键/K 打开\n"
        "或关闭菜单。存档、读档和退出均在游戏菜单的‘系统’项目中完成。\n\n"
        "4. 天地道\n"
        "使用通用 A320 键位。方向键移动；确认键攻击和确认；返回键取消。\n"
        "Space 打开或关闭武器选择；Esc 直接退出到桌面。\n\n"
        "5. 天地道 II\n"
        "使用通用 A320 键位。标题画面按确认键，菜单选择 NEW GAME。\n"
        "Space 为 Start；Esc 直接退出到桌面。\n\n"
        "6. 极限漂移\n"
        "左右键转向；确认键/Enter/J 加速和确认；返回键/K 制动或返回。\n"
        "Space 暂停；其余按键采用通用 A320 键位；Esc 退出。\n\n"
        "7. 战神刑天\n"
        "使用通用 A320 键位。方向键移动；确认键攻击；返回键取消或次要动作；\n"
        "Space 为 Start；Esc 退出。\n\n"
        "8. 赵云传\n"
        "使用通用 A320 键位。方向键移动；确认键对话、调查和确认；返回键\n"
        "取消或返回菜单；Esc 退出。\n\n"
        "9. 阿里巴巴\n"
        "使用通用 A320 键位。方向键用于菜单、地图和选项；确认键确认、跳跃\n"
        "或主要动作；返回键取消或返回；Esc 退出。\n\n"
        "10. 霸王战机\n"
        "使用通用 A320 键位。方向键移动战机；确认键为主要武器；返回键为\n"
        "次要武器；Space 开始或暂停；Esc 退出。\n\n"
        "11. 斗地主\n"
        "方向键在手牌、按钮和菜单间移动；确认键选牌和执行操作；返回键撤销\n"
        "选择或返回；其余使用通用 A320 键位；Esc 退出。\n\n"
        "12. 卢比卢比\n"
        "方向键导航菜单和移动；确认键选择图块；返回键取消；选择难度后再次\n"
        "按确认键进入棋盘；Esc 退出。\n\n"
        "13. 打砖块\n"
        "左右键移动挡板；确认键展开菜单并选择‘快速开始’；返回键取消。\n"
        "进入关卡后继续用左右键控制挡板；Esc 退出。\n\n"
        "14. 糖果屋\n"
        "方向键移动光标；确认键选择、交换或确认；返回键取消；采用通用\n"
        "A320 辅助键；Esc 退出。\n\n"
        "15. 泡泡龙\n"
        "左右键调整发射方向；确认键发射；返回键取消或返回菜单；Esc 退出。\n\n"
        "16. 俄罗斯方块\n"
        "左右键移动方块；下键加速下落；确认键旋转；Y 键反向旋转；\n"
        "返回键暂停或返回菜单；Esc 退出。\n\n"
        "17. 连连看\n"
        "方向键移动光标；确认键依次选择两个图块；返回键取消选择或返回；\n"
        "Esc 退出。\n\n"
        "18. 贪吃蛇\n"
        "方向键控制蛇移动；确认键选择菜单和地图；返回键返回上一层。\n"
        "开始游戏前在模式菜单选择游戏类型；Esc 退出。\n\n"
        "19. 三国战纪：风云再起\n"
        "方向键或 W/A/S/D 移动；J/K/U/I 为四个街机动作键；确认键或 Enter\n"
        "为 Start；Space 投币；P 暂停/继续。长按返回键或 Esc 约 0.75 秒\n"
        "退出到桌面。画面保持原始比例，四周黑边属于正常现象。\n\n"
        "20. CS15 Lite\n"
        "方向键或 W/A/S/D 移动；Q/E 水平观察；I/K 垂直观察；确认键、Enter\n"
        "或 J 确认和开火；F 使用、购买、安装/拆除或开始回合；R 换弹；\n"
        "短按 X 或 Page Down 切换武器，长按约 0.7 秒丢弃武器；Alt 使用\n"
        "瞄准镜、消音器、点射等副功能；Space 跳跃；C 蹲下。短按 Esc\n"
        "暂停/继续，长按约 0.8 秒紧急退出；H1 永久返回键立即退出。\n",
        encoding="utf-8",
    )


def reject_private_files(stage: Path) -> None:
    rejected = [
        path.relative_to(stage).as_posix()
        for path in stage.rglob("*")
        if path.is_file() and path.suffix.casefold() in PROHIBITED_SUFFIXES
    ]
    if rejected:
        raise SystemExit("private/debug file entered combined release: " + ", ".join(rejected))
    pack_files = [
        path for path in stage.rglob("*")
        if path.is_file() and path.suffix.casefold() == ".pak"
    ]
    expected_pack = (
        stage / "A-root" / DATA_DIRECTORY / "KOVH1" / "KOVH1.PAK"
    )
    if len(pack_files) != 1 or pack_files[0] != expected_pack:
        raise SystemExit(
            "combined release must contain only "
            "A-root/应用/数据/KOVH1/KOVH1.PAK"
        )
    if expected_pack.stat().st_size != KOV_PACK_SIZE or sha256(expected_pack) != KOV_PACK_SHA256:
        raise SystemExit("staged KOVH1.PAK failed size/SHA-256 validation")
    cs_pack_files = [
        path for path in stage.rglob("*")
        if path.is_file() and path.suffix.casefold() == ".c15pak"
    ]
    expected_cs_pack = (
        stage / "A-root" / DATA_DIRECTORY / "CS15LITE" / "CS15.C15PAK"
    )
    if len(cs_pack_files) != 1 or cs_pack_files[0] != expected_cs_pack:
        raise SystemExit("combined release must contain the one matching CS15.C15PAK")
    if (
        expected_cs_pack.stat().st_size != CS_PACK_SIZE
        or sha256(expected_cs_pack) != CS_PACK_SHA256
    ):
        raise SystemExit("staged CS15.C15PAK failed size/SHA-256 validation")
    expected_runtime_files = {
        (stage / "A-root" / DATA_DIRECTORY / name).resolve()
        for name in RUNTIME_NAMES
    }
    staged_runtime_files = {
        path.resolve()
        for path in (stage / "A-root").rglob("*")
        if path.is_file() and path.suffix.casefold() in {".app", ".wad"}
    }
    if staged_runtime_files != expected_runtime_files:
        raise SystemExit("all APP/WAD resources must be under A-root/应用/数据")


def audit_icons(directory: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="h1-all-icon-audit-") as temporary:
        report = Path(temporary) / "icon-audit.json"
        run(
            [
                sys.executable,
                str(SDK_ROOT / "scripts" / "audit_release_icons.py"),
                str(directory),
                "--expected-count", str(len(BDA_NAMES)),
                "--output", str(report),
            ]
        )


def audit_resource_paths(directory: Path) -> None:
    run([sys.executable, str(RESOURCE_PATH_AUDITOR), str(directory)])


def audit_secrets(*targets: Path) -> None:
    run(
        [
            sys.executable,
            str(WORKSPACE_ROOT / "scripts" / "audit_release_secrets.py"),
            *map(str, targets),
        ]
    )


def build_archive(stage: Path, archive: Path) -> None:
    target = ensure_generated_target(archive)
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        prefix=target.name + ".", suffix=".tmp", dir=target.parent, delete=False
    ) as temporary_stream:
        temporary = Path(temporary_stream.name)
    try:
        paths = sorted(
            (path for path in stage.rglob("*") if path.is_file()),
            key=lambda path: path.relative_to(stage).as_posix().casefold(),
        )
        with zipfile.ZipFile(
            temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
        ) as output:
            for path in paths:
                relative = path.relative_to(stage).as_posix()
                info = zipfile.ZipInfo(relative, ZIP_TIMESTAMP)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                output.writestr(info, path.read_bytes(), compresslevel=9)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-release", type=Path, default=SOURCE_RELEASE)
    parser.add_argument("--stage", type=Path, default=DEFAULT_STAGE)
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    args = parser.parse_args()
    source_release = args.source_release.resolve()
    stage = ensure_generated_target(args.stage)
    archive = ensure_generated_target(args.archive)

    run([sys.executable, str(GAME_BDA_BUILDER)])
    run_quiet(
        [
            sys.executable,
            str(SDK_ROOT / "tests" / "test_a320_game_patches.py"),
        ]
    )
    source_root = validate_source(source_release)
    reset_stage(stage)
    sync_game_files(source_root, stage)
    write_readme(source_release, stage)
    reject_private_files(stage)
    audit_icons(stage / "A-root" / PROGRAM_DIRECTORY)
    audit_resource_paths(stage / "A-root" / PROGRAM_DIRECTORY)
    audit_secrets(stage)
    build_archive(stage, archive)
    audit_secrets(archive)

    print(f"release={stage.name}")
    print(f"bda_count={len(BDA_NAMES)}")
    print(f"stage_files={sum(path.is_file() for path in stage.rglob('*'))}")
    print(f"archive={archive.name} size={archive.stat().st_size} sha256={sha256(archive)}")
    print("kov_pack_included=owner-authorized")
    print("cs15_pack_included=emulator-accepted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
