#!/usr/bin/env python3
"""Build the owner-authorized BBK H1 KOV Plus real-hardware package."""

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


ROOT = Path(__file__).resolve().parents[1]
SDK = ROOT / "h1-bda-sdk"
PORT = SDK / "ports" / "kov_pgm"
PACK = ROOT / "work" / "private" / "kov" / "KOVH1.PAK"
PACK_SIZE = 58_785_792
PACK_SHA256 = "6A3E5EF41212AA47A242689D904374DF0CBFEF4E34313053B2D7C1755642DB53"
DELIVERABLES = ROOT / "deliverables"
RELEASE_NAME = "H1-KOV-Plus-real-hardware-2026-08-04"
DEFAULT_STAGE = DELIVERABLES / RELEASE_NAME
DEFAULT_ARCHIVE = DEFAULT_STAGE.with_suffix(".zip")
SOURCE_DATE_EPOCH = "1785456000"
ZIP_TIMESTAMP = (2026, 8, 4, 0, 0, 0)
BDA_NAME = "H1KOVPlus.bda"
PROGRAM = Path("A-root") / "应用" / "程序"
DATA = Path("A-root") / "应用" / "数据"
EXPECTED_FILES = {
    PROGRAM / BDA_NAME,
    DATA / "KOVH1" / "KOVH1.PAK",
    Path("游戏说明.txt"),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest().upper()


def output_path(path: Path) -> Path:
    resolved = path.resolve()
    root = DELIVERABLES.resolve()
    if resolved == root or root not in resolved.parents:
        raise SystemExit(f"refusing generated output outside deliverables: {resolved}")
    return resolved


def environment() -> dict[str, str]:
    child = os.environ.copy()
    child["PYTHONDONTWRITEBYTECODE"] = "1"
    child["SOURCE_DATE_EPOCH"] = SOURCE_DATE_EPOCH
    pillow = ROOT / "work" / "rebuild" / "python-deps" / "pillow"
    child["PYTHONPATH"] = os.pathsep.join(
        str(path) for path in (SDK, pillow, Path(child.get("PYTHONPATH", ""))) if str(path)
    )
    return child


def run(command: list[str], *, quiet: bool = False) -> None:
    completed = subprocess.run(
        command,
        cwd=ROOT,
        env=environment(),
        stdout=subprocess.PIPE if quiet else None,
        stderr=subprocess.STDOUT if quiet else None,
        text=True if quiet else False,
        check=False,
    )
    if completed.returncode:
        if quiet and completed.stdout:
            print(completed.stdout, file=sys.stderr, end="")
        raise subprocess.CalledProcessError(completed.returncode, command)


def build_bda(destination: Path) -> None:
    run(
        [
            sys.executable,
            str(PORT / "build_port.py"),
            "--output",
            str(destination),
        ],
        quiet=True,
    )


def build_reproducible_bda(destination: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="h1-kov-owner-bda-") as temporary:
        first = Path(temporary) / "first.bda"
        second = Path(temporary) / "second.bda"
        build_bda(first)
        build_bda(second)
        if first.read_bytes() != second.read_bytes():
            raise SystemExit("KOV BDA is not reproducible")
        shutil.copyfile(first, destination)


def verify_inputs(bda: Path) -> None:
    if not PACK.is_file() or PACK.stat().st_size != PACK_SIZE or sha256(PACK) != PACK_SHA256:
        raise SystemExit("owner-authorized KOVH1.PAK failed size/SHA-256 validation")
    run([sys.executable, str(PORT / "tools" / "prepare_rom_pack.py"), "verify", str(PACK), "--pages"], quiet=True)
    sys.path.insert(0, str(SDK))
    from h1_bda.validate import validate_bda

    report = validate_bda(bda)
    if not report["ok"]:
        raise SystemExit("invalid KOV BDA: " + "; ".join(report["errors"]))
    if bda.stat().st_size != 703_812 or sha256(bda) != "8526C198CF0AD1058DF9E5F745E87122E46A7291E12B58C52A83E883B4B9FD80":
        raise SystemExit("rebuilt KOV BDA differs from the validated H1KOVPlus build")


def reset_stage(stage: Path) -> None:
    target = output_path(stage)
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)


def write_instructions(stage: Path) -> None:
    (stage / "游戏说明.txt").write_text(
        "三国战纪：风云再起\n\n"
        "操作方法\n"
        "方向键或 W/A/S/D：移动\n"
        "J/K/U/I：四个街机动作键\n"
        "确认键或 Enter：开始和确认\n"
        "Space：投币\n"
        "P：暂停/继续\n"
        "返回键或 Esc：长按约 2 秒退出到 H1 桌面\n\n"
        "注意事项\n"
        "将 A-root 文件夹内的内容合并复制到存储卡 A: 根目录。\n"
        "程序文件必须位于 A:\\应用\\程序\\H1KOVPlus.bda。\n"
        "数据文件必须位于 A:\\应用\\数据\\KOVH1\\KOVH1.PAK。\n"
        "本包按 H1 原生 448x224 比例显示，周围黑边是正常现象。\n",
        encoding="utf-8",
        newline="\n",
    )


def verify_stage(stage: Path) -> None:
    actual = {path.relative_to(stage) for path in stage.rglob("*") if path.is_file()}
    if actual != EXPECTED_FILES:
        raise SystemExit(f"unexpected KOV stage files: {sorted(map(str, actual))}")
    staged_pack = stage / DATA / "KOVH1" / "KOVH1.PAK"
    if staged_pack.stat().st_size != PACK_SIZE or sha256(staged_pack) != PACK_SHA256:
        raise SystemExit("staged KOVH1.PAK failed validation")


def audit(*targets: Path) -> None:
    run([sys.executable, str(ROOT / "scripts" / "audit_release_secrets.py"), *map(str, targets)])


def archive(stage: Path, target: Path) -> None:
    target = output_path(target)
    with tempfile.NamedTemporaryFile(prefix=target.name + ".", suffix=".tmp", dir=target.parent, delete=False) as stream:
        temporary = Path(stream.name)
    try:
        files = sorted(
            (path for path in stage.rglob("*") if path.is_file()),
            key=lambda path: path.relative_to(stage).as_posix().casefold(),
        )
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as output:
            for path in files:
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
    stage = output_path(args.stage)
    target = output_path(args.archive)
    with tempfile.TemporaryDirectory(prefix="h1-kov-owner-build-") as temporary:
        bda = Path(temporary) / BDA_NAME
        build_reproducible_bda(bda)
        verify_inputs(bda)
        reset_stage(stage)
        destination_bda = stage / PROGRAM / BDA_NAME
        destination_bda.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(bda, destination_bda)
    destination_pack = stage / DATA / "KOVH1" / "KOVH1.PAK"
    destination_pack.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(PACK, destination_pack)
    write_instructions(stage)
    verify_stage(stage)
    audit(stage)
    archive(stage, target)
    audit(target)
    print(f"stage={stage}")
    print(f"archive={target} size={target.stat().st_size} sha256={sha256(target)}")
    print(f"bda_sha256={sha256(stage / PROGRAM / BDA_NAME)}")
    print(f"pack_sha256={sha256(destination_pack)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
