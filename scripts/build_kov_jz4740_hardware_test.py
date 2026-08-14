#!/usr/bin/env python3
"""Build the reproducible owner-authorized JZ4740 KOV hardware test package."""

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
PORT_ROOT = SDK_ROOT / "ports" / "kov_pgm"
BUILD_TOOL = PORT_ROOT / "build_port.py"
PACK_TOOL = PORT_ROOT / "tools" / "prepare_rom_pack.py"
PACK = WORKSPACE_ROOT / "work" / "private" / "kov" / "KOVH1.PAK"
PACK_SIZE = 58_785_792
PACK_SHA256 = "6A3E5EF41212AA47A242689D904374DF0CBFEF4E34313053B2D7C1755642DB53"
DELIVERABLES_ROOT = WORKSPACE_ROOT / "deliverables"
RELEASE_NAME = "H1-KOV-JZ4740-hardware-test-2026-08-02"
DEFAULT_STAGE = DELIVERABLES_ROOT / RELEASE_NAME
DEFAULT_ARCHIVE = DEFAULT_STAGE.with_suffix(".zip")
SOURCE_DATE_EPOCH = "1785628800"
ZIP_TIMESTAMP = (2026, 8, 2, 0, 0, 0)
BDA_NAME = "H1KOVJZ4740.bda"
PROGRAM_DIRECTORY = Path("应用") / "程序"
DATA_DIRECTORY = Path("应用") / "数据"
EXPECTED_PACK_PATH = b"A:\\" + "应用\\数据\\KOVH1\\KOVH1.PAK".encode("gbk")
OLD_PACK_PATH = b"A:\\KOVH1\\KOVH1.PAK"
PROHIBITED_SUFFIXES = {
    ".elf", ".json", ".log", ".png", ".pyc", ".rom",
}


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
    environment["SOURCE_DATE_EPOCH"] = SOURCE_DATE_EPOCH
    bundled_candidates = (
        WORKSPACE_ROOT
        / "work/rebuild/tools/msys2-20260611/msys64/ucrt64/bin",
        WORKSPACE_ROOT / "work/tools/msys64/clangarm64/bin",
    )
    if "H1_LLVM_BIN" not in environment:
        bundled_llvm = next(
            (path for path in bundled_candidates if (path / "clang.exe").is_file()),
            None,
        )
        if bundled_llvm is not None:
            environment["H1_LLVM_BIN"] = str(bundled_llvm)
    return environment


def run(command: list[str], *, quiet: bool = False) -> None:
    options: dict[str, object] = {}
    if quiet:
        options.update(stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    completed = subprocess.run(
        command,
        cwd=WORKSPACE_ROOT,
        env=child_environment(),
        check=False,
        **options,
    )
    if completed.returncode:
        if quiet and completed.stdout:
            print(completed.stdout, file=sys.stderr, end="")
        raise subprocess.CalledProcessError(completed.returncode, command)


def build_bda(output: Path) -> None:
    run(
        [
            sys.executable,
            str(BUILD_TOOL),
            "--jz4740-hardware",
            "--title",
            "三国优化",
            "--output",
            str(output),
        ],
        quiet=True,
    )


def verify_reproducible_bda(destination: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="kov-jz4740-repro-") as temporary:
        root = Path(temporary)
        first = root / "first.bda"
        second = root / "second.bda"
        build_bda(first)
        build_bda(second)
        if first.read_bytes() != second.read_bytes():
            raise SystemExit("JZ4740 KOV BDA is not reproducible across two builds")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(first, destination)


def verify_bda(bda: Path) -> None:
    sys.path.insert(0, str(SDK_ROOT))
    from h1_bda.validate import validate_bda

    report = validate_bda(bda)
    if not report["ok"]:
        raise SystemExit("invalid JZ4740 KOV BDA: " + "; ".join(report["errors"]))
    if report["title"] != "三国优化":
        raise SystemExit(f"unexpected JZ4740 KOV title: {report['title']!r}")
    payload = bda.read_bytes()
    if EXPECTED_PACK_PATH not in payload or OLD_PACK_PATH in payload:
        raise SystemExit("JZ4740 KOV BDA contains an invalid resource path")


def audit_icon(bda: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="kov-jz4740-icon-") as temporary:
        isolated = Path(temporary) / BDA_NAME
        report = Path(temporary) / "icon-report.json"
        shutil.copyfile(bda, isolated)
        run(
            [
                sys.executable,
                str(SDK_ROOT / "scripts" / "audit_release_icons.py"),
                str(isolated.parent),
                "--expected-count",
                "1",
                "--output",
                str(report),
            ],
            quiet=True,
        )


def verify_pack() -> None:
    if not PACK.is_file():
        raise FileNotFoundError(PACK)
    if PACK.stat().st_size != PACK_SIZE or sha256(PACK) != PACK_SHA256:
        raise SystemExit("owner-authorized KOVH1.PAK failed size/SHA-256 validation")
    run([sys.executable, str(PACK_TOOL), "verify", str(PACK), "--pages"], quiet=True)


def reset_stage(stage: Path) -> None:
    target = ensure_generated_target(stage)
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)


def write_instructions(stage: Path) -> None:
    (stage / "游戏说明.txt").write_text(
        "三国战纪：风云再起 JZ4740 实机优化测试版\n"
        "====================================\n\n"
        "操作方法\n"
        "--------\n"
        "方向键或 W/A/S/D：移动\n"
        "J/K/U/I：四个街机动作键\n"
        "确认键或 Enter：Start\n"
        "Space：投币\n"
        "P：暂停/继续\n"
        "长按 Esc 约 0.75 秒：退出到 H1 桌面\n\n"
        "注意事项\n"
        "--------\n"
        "将 A-root 的内容合并复制到存储卡 A: 根目录。\n"
        "应用名称为“三国优化”，可与旧版“三国战纪+”同时保留。\n"
        "测试时请在相同关卡、相同人数和相近敌人数量下与旧版比较。\n"
        "本版不超频、不修改街机 CPU 周期、不固定跳帧；实机帧率结果以 H1 测试为准。\n",
        encoding="utf-8",
    )


def verify_stage(stage: Path) -> None:
    files = sorted(path.relative_to(stage).as_posix() for path in stage.rglob("*") if path.is_file())
    expected = sorted(
        [
            (Path("A-root") / PROGRAM_DIRECTORY / BDA_NAME).as_posix(),
            (Path("A-root") / DATA_DIRECTORY / "KOVH1" / "KOVH1.PAK").as_posix(),
            "游戏说明.txt",
        ]
    )
    if files != expected:
        raise SystemExit(f"unexpected hardware-test stage contents: {files}")
    rejected = [name for name in files if Path(name).suffix.casefold() in PROHIBITED_SUFFIXES]
    if rejected:
        raise SystemExit("private/debug file entered hardware-test stage: " + ", ".join(rejected))


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
    ) as stream:
        temporary = Path(stream.name)
    try:
        paths = sorted(
            (path for path in stage.rglob("*") if path.is_file()),
            key=lambda path: path.relative_to(stage).as_posix().casefold(),
        )
        with zipfile.ZipFile(
            temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
        ) as output:
            for path in paths:
                info = zipfile.ZipInfo(path.relative_to(stage).as_posix(), ZIP_TIMESTAMP)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                output.writestr(info, path.read_bytes(), compresslevel=9)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", type=Path, default=DEFAULT_STAGE)
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    args = parser.parse_args()
    stage = ensure_generated_target(args.stage)
    archive = ensure_generated_target(args.archive)
    built_bda = SDK_ROOT / "build" / BDA_NAME

    verify_reproducible_bda(built_bda)
    verify_bda(built_bda)
    audit_icon(built_bda)
    verify_pack()
    reset_stage(stage)
    destination_bda = stage / "A-root" / PROGRAM_DIRECTORY / BDA_NAME
    destination_pack = stage / "A-root" / DATA_DIRECTORY / "KOVH1" / "KOVH1.PAK"
    destination_bda.parent.mkdir(parents=True)
    destination_pack.parent.mkdir(parents=True)
    shutil.copyfile(built_bda, destination_bda)
    shutil.copyfile(PACK, destination_pack)
    write_instructions(stage)
    verify_stage(stage)
    audit_secrets(stage)
    build_archive(stage, archive)
    audit_secrets(archive)

    print(f"bda={built_bda.name} size={built_bda.stat().st_size} sha256={sha256(built_bda)}")
    print(f"archive={archive.name} size={archive.stat().st_size} sha256={sha256(archive)}")
    print("top_level=A-root,游戏说明.txt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
