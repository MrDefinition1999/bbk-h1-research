#!/usr/bin/env python3
"""Build the reproducible owner-authorized KOV overclock/profile test package."""

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
DEFAULT_RELEASE_PREFIX = "H1-KOV"
SOURCE_DATE_EPOCH = "1785715200"
ZIP_TIMESTAMP = (2026, 8, 3, 0, 0, 0)
BDA_NAME = "H1KOVPERF.bda"
TITLE = "\u4e09\u56fd\u6027\u80fd"
PROGRAM_DIRECTORY = Path("\u5e94\u7528") / "\u7a0b\u5e8f"
DATA_DIRECTORY = Path("\u5e94\u7528") / "\u6570\u636e"
GUIDE_NAME = "\u6e38\u620f\u8bf4\u660e.txt"
EXPECTED_PACK_PATH = (
    b"A:\\" + "\u5e94\u7528\\\u6570\u636e\\KOVH1\\KOVH1.PAK".encode("gbk")
)
OLD_PACK_PATH = b"A:\\KOVH1\\KOVH1.PAK"
PROFILE_MARKERS = (
    b"KOVJOURNAL3:CLOCK_PLAN,CLOCK_RESULT,STAGE,LIVE,FINAL_REPORT,RPLUS_SEEK_END",
    b"KOVPERF.TXT",
    b"record=FINAL_REPORT",
)
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


def build_bda(output: Path, target_hz: int) -> None:
    run(
        [
            sys.executable,
            str(BUILD_TOOL),
            "--hardware-profile",
            "--clock-target-hz",
            str(target_hz),
            "--title",
            TITLE,
            "--output",
            str(output),
        ],
        quiet=True,
    )


def verify_reproducible_bda(destination: Path, target_hz: int) -> None:
    with tempfile.TemporaryDirectory(prefix="kov-profile-repro-") as temporary:
        root = Path(temporary)
        first = root / "first.bda"
        second = root / "second.bda"
        build_bda(first, target_hz)
        build_bda(second, target_hz)
        if first.read_bytes() != second.read_bytes():
            raise SystemExit("KOV profile BDA is not reproducible across two builds")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(first, destination)


def verify_bda(bda: Path) -> None:
    sys.path.insert(0, str(SDK_ROOT))
    from h1_bda.validate import validate_bda

    report = validate_bda(bda)
    if not report["ok"]:
        raise SystemExit("invalid KOV profile BDA: " + "; ".join(report["errors"]))
    if report["title"] != TITLE:
        raise SystemExit(f"unexpected KOV profile title: {report['title']!r}")
    payload = bda.read_bytes()
    if EXPECTED_PACK_PATH not in payload or OLD_PACK_PATH in payload:
        raise SystemExit("KOV profile BDA contains an invalid resource path")
    missing = [marker.decode("ascii") for marker in PROFILE_MARKERS if marker not in payload]
    if missing:
        raise SystemExit("KOV profile instrumentation is missing: " + ", ".join(missing))


def audit_icon(bda: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="kov-profile-icon-") as temporary:
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


def write_instructions(stage: Path, target_hz: int) -> None:
    (stage / GUIDE_NAME).write_text(
        "三国战纪：风云再起 H1 超频性能测试版\n"
        "===================================\n\n"
        "操作方法\n"
        "--------\n"
        "方向键或 W/A/S/D：移动\n"
        "J/K/U/I：四个街机动作键\n"
        "确认键或 Enter：Start\n"
        "Space：投币\n"
        "P：暂停/继续\n"
        "长按 Esc 或返回键约 0.75 秒：正常退出到 H1 桌面\n\n"
        "注意事项\n"
        "--------\n"
        "将 A-root 内的内容合并复制到存储卡 A: 根目录。应用名称为“三国性能”。\n"
        "本版会在兼容的 H1 上临时尝试 408 MHz CPU 时钟；不会刷写固件，正常退出时恢复原时钟。\n"
        "内存、总线、LCD、存储和音频时钟不会高于启动前实测值，且不会修改 SDRAM 时序。\n"
        "先连续测试 10 至 15 分钟；若出现异常发热、花屏、无声或卡死，请立即按 RESET 重启。\n"
        "自适应跳帧仅跳过画面绘制，游戏逻辑、按键和音频仍逐帧运行，最多连续跳过 9 帧。\n"
        "日志会在超频前创建，启动阶段及运行中约每秒增量写入并立即关闭文件；异常重启后也应保留最后一条完整记录。\n"
        "日志位于 A:\\应用\\数据\\KOVH1\\KOVPERF.TXT；请在重启后先将该文件复制出来再重新运行游戏，新一次启动会清空旧日志。\n",
        encoding="utf-8",
    )
    guide_path = stage / GUIDE_NAME
    guide = guide_path.read_text(encoding="utf-8")
    guide_path.write_text(
        guide.replace("408 MHz", f"{target_hz // 1_000_000} MHz"),
        encoding="utf-8",
    )


def verify_stage(stage: Path) -> None:
    files = sorted(
        path.relative_to(stage).as_posix()
        for path in stage.rglob("*")
        if path.is_file()
    )
    expected = sorted(
        [
            (Path("A-root") / PROGRAM_DIRECTORY / BDA_NAME).as_posix(),
            (Path("A-root") / DATA_DIRECTORY / "KOVH1" / "KOVH1.PAK").as_posix(),
            GUIDE_NAME,
        ]
    )
    if files != expected:
        raise SystemExit(f"unexpected KOV profile stage contents: {files}")
    rejected = [name for name in files if Path(name).suffix.casefold() in PROHIBITED_SUFFIXES]
    if rejected:
        raise SystemExit("private/debug file entered KOV profile stage: " + ", ".join(rejected))


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
    parser.add_argument(
        "--target-hz", type=int, choices=(336000000, 384000000),
        default=384000000,
        help="profile CPU target in Hz (default: 384000000)",
    )
    parser.add_argument("--release-name")
    parser.add_argument("--stage", type=Path)
    parser.add_argument("--archive", type=Path)
    args = parser.parse_args()
    release_name = args.release_name or (
        f"{DEFAULT_RELEASE_PREFIX}-{args.target_hz // 1_000_000}MHz-profile-2026-08-03"
    )
    default_stage = DELIVERABLES_ROOT / release_name
    stage = ensure_generated_target(args.stage or default_stage)
    archive = ensure_generated_target(args.archive or stage.with_suffix(".zip"))
    built_bda = SDK_ROOT / "build" / BDA_NAME

    verify_reproducible_bda(built_bda, args.target_hz)
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
    write_instructions(stage, args.target_hz)
    verify_stage(stage)
    audit_secrets(stage)
    build_archive(stage, archive)
    audit_secrets(archive)

    print(f"target_hz={args.target_hz}")
    print(f"bda={built_bda.name} size={built_bda.stat().st_size} sha256={sha256(built_bda)}")
    print(f"archive={archive.name} size={archive.stat().st_size} sha256={sha256(archive)}")
    print(f"top_level=A-root,{GUIDE_NAME}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
