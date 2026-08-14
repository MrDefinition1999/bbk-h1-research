#!/usr/bin/env python3
"""Build the reproducible ROM-free KOV Plus release for BBK H1."""

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
DELIVERABLES_ROOT = WORKSPACE_ROOT / "deliverables"
RELEASE_NAME = "KOV-Plus-H1-2026-08-01"
DEFAULT_STAGE = DELIVERABLES_ROOT / RELEASE_NAME
DEFAULT_ARCHIVE = DEFAULT_STAGE.with_suffix(".zip")
SOURCE_DATE_EPOCH = "1785456000"
ZIP_TIMESTAMP = (2026, 8, 1, 0, 0, 0)
BDA_NAME = "H1KOVPlus.bda"
PROGRAM_DIRECTORY = Path("应用") / "程序"
PROHIBITED_SUFFIXES = {
    ".elf", ".json", ".log", ".pak", ".png", ".pyc", ".rom",
}
PROHIBITED_NAMES = {
    ".git", "__pycache__", "kov.zip", "kovplus.zip", "kovh1.pak",
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


def run(command: list[str], *, env: dict[str, str] | None = None) -> None:
    child_env = os.environ.copy() if env is None else env.copy()
    child_env["PYTHONDONTWRITEBYTECODE"] = "1"
    subprocess.run(command, cwd=WORKSPACE_ROOT, env=child_env, check=True)


def build_bda(output: Path) -> None:
    env = os.environ.copy()
    env["SOURCE_DATE_EPOCH"] = SOURCE_DATE_EPOCH
    bundled_candidates = (
        WORKSPACE_ROOT
        / "work/rebuild/tools/msys2-20260611/msys64/ucrt64/bin",
        WORKSPACE_ROOT / "work/tools/msys64/clangarm64/bin",
    )
    if "H1_LLVM_BIN" not in env:
        bundled_llvm = next(
            (path for path in bundled_candidates if (path / "clang.exe").is_file()),
            None,
        )
        if bundled_llvm is not None:
            env["H1_LLVM_BIN"] = str(bundled_llvm)
    run(
        [sys.executable, str(PORT_ROOT / "build_port.py"), "-o", str(output)],
        env=env,
    )


def reset_stage(stage: Path) -> None:
    target = ensure_generated_target(stage)
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)


def write_readme(stage: Path) -> None:
    (stage / "README-H1.txt").write_text(
        "三国战纪：风云再起 V119 - 步步高 H1 原生移植\n"
        "===============================================\n\n"
        "本发布包不含游戏 ROM、PGM BIOS 或 KOVH1.PAK。请只使用自己合法\n"
        "持有的 kov.zip（父集）与 kovplus.zip（V119 克隆集）生成数据包。\n\n"
        "生成数据包\n"
        "------------\n"
        "在 PC 上安装 Python 3.10 或更高版本，然后在本目录执行：\n\n"
        "python tools\\prepare_rom_pack.py build ^\n"
        "  --parent <path-to-owned-roms>\\kov.zip ^\n"
        "  --clone <path-to-owned-roms>\\kovplus.zip ^\n"
        "  -o KOVH1.PAK\n\n"
        "可选完整校验：\n"
        "python tools\\prepare_rom_pack.py verify KOVH1.PAK --pages\n\n"
        "正确数据包大小：58,785,792 字节\n"
        "正确数据包 SHA-256：\n"
        "6A3E5EF41212AA47A242689D904374DF0CBFEF4E34313053B2D7C1755642DB53\n\n"
        "实机安装\n"
        "--------\n"
        "1. 将 应用\\程序\\H1KOVPlus.bda 复制到：\n"
        "   A:\\应用\\程序\\H1KOVPlus.bda\n"
        "2. 在 A: 根目录新建 KOVH1 文件夹，将生成的数据包复制到：\n"
        "   A:\\应用\\数据\\KOVH1\\KOVH1.PAK\n"
        "3. 在 H1 的‘其它’分类最后一项启动‘三国战纪+’。\n\n"
        "操作\n"
        "----\n"
        "方向键或 W/A/S/D：移动\n"
        "J/K/U/I：四个街机动作键\n"
        "确认键或 Enter：Start\n"
        "Space：投币\n"
        "P：暂停/继续\n"
        "长按返回键或 Esc 0.75 秒：退出到 H1 桌面\n\n"
        "显示为原生 448x224，居中且不拉伸。ARM64 主机上的 H1 模拟器已\n"
        "通过 300 秒压力测试；真实 H1 的性能与兼容性仍需实机确认。\n",
        encoding="utf-8",
    )


def write_checksums(stage: Path) -> None:
    output = stage / "CHECKSUMS.sha256"
    paths = sorted(
        (path for path in stage.rglob("*") if path.is_file() and path != output),
        key=lambda path: path.relative_to(stage).as_posix().casefold(),
    )
    lines = [f"{sha256(path)}  {path.relative_to(stage).as_posix()}" for path in paths]
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def reject_private_or_debug_files(stage: Path) -> None:
    rejected: list[str] = []
    for path in stage.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(stage).as_posix()
        lowered_parts = {part.casefold() for part in path.relative_to(stage).parts}
        if lowered_parts & PROHIBITED_NAMES or path.suffix.casefold() in PROHIBITED_SUFFIXES:
            rejected.append(relative)
    if rejected:
        raise SystemExit("private/debug file entered KOV release: " + ", ".join(rejected))


def audit_icon(bda: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="kov-icon-audit-") as temporary:
        report = Path(temporary) / "icon-audit.json"
        run(
            [
                sys.executable,
                str(SDK_ROOT / "scripts" / "audit_release_icons.py"),
                str(bda.parent),
                "--expected-count", "1",
                "--output", str(report),
            ]
        )


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
    parser.add_argument("--stage", type=Path, default=DEFAULT_STAGE)
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    args = parser.parse_args()
    stage = ensure_generated_target(args.stage)
    archive = ensure_generated_target(args.archive)
    built_bda = SDK_ROOT / "build" / BDA_NAME

    build_bda(built_bda)
    with tempfile.TemporaryDirectory(prefix="kov-bda-audit-") as temporary:
        isolated = Path(temporary) / BDA_NAME
        shutil.copyfile(built_bda, isolated)
        audit_icon(isolated)

    reset_stage(stage)
    destination = stage / PROGRAM_DIRECTORY / BDA_NAME
    destination.parent.mkdir(parents=True)
    shutil.copyfile(built_bda, destination)
    tools = stage / "tools"
    tools.mkdir()
    shutil.copyfile(PORT_ROOT / "tools" / "prepare_rom_pack.py", tools / "prepare_rom_pack.py")
    write_readme(stage)
    write_checksums(stage)
    reject_private_or_debug_files(stage)
    audit_secrets(stage)
    build_archive(stage, archive)
    audit_secrets(archive)

    print(f"bda={built_bda.name} size={built_bda.stat().st_size} sha256={sha256(built_bda)}")
    print(f"stage={stage.name} files={sum(path.is_file() for path in stage.rglob('*'))}")
    print(f"archive={archive.name} size={archive.stat().st_size} sha256={sha256(archive)}")
    print("roms_embedded=no")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
