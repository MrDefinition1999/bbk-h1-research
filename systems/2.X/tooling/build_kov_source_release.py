#!/usr/bin/env python3
"""Build and verify the sanitized, ROM-free H1 KOV source release."""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
DELIVERABLES_ROOT = WORKSPACE_ROOT / "deliverables"
RELEASE_NAME = "KOV-Plus-H1-source-ROM-free-2026-08-04"
DEFAULT_STAGE = DELIVERABLES_ROOT / RELEASE_NAME
DEFAULT_ARCHIVE = DEFAULT_STAGE.with_suffix(".zip")
ZIP_TIMESTAMP = (2026, 8, 4, 0, 0, 0)
SOURCE_DATE_EPOCH = "1785715200"
EXPECTED_TESTS = 16

CZ80_FILES = (
    "cz80.c",
    "cz80.h",
    "cz80_op.c",
    "cz80_opCB.c",
    "cz80_opED.c",
    "cz80_opXY.c",
    "cz80_opXYCB.c",
    "cz80jmp.c",
    "readme.txt",
)
PROHIBITED_PARTS = {".git", "__pycache__", ".pytest_cache"}
PROHIBITED_SUFFIXES = {".elf", ".log", ".pak", ".pyc", ".pyo", ".zip"}
PROFILES = (
    "H1KOVPlus-base.bda",
    "H1KOVPlus-336MHz.bda",
    "H1KOVPlus-336MHz-30FPS.bda",
    "H1KOVPlus-384MHz.bda",
    "H1KOVPlus-384MHz-30FPS.bda",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest().upper()


def ensure_deliverable_target(path: Path) -> Path:
    resolved = path.resolve()
    root = DELIVERABLES_ROOT.resolve()
    if resolved == root or root not in resolved.parents:
        raise SystemExit(f"refusing generated output outside deliverables: {resolved}")
    return resolved


def allowed_source(path: Path) -> bool:
    return (
        not any(part.casefold() in PROHIBITED_PARTS for part in path.parts)
        and path.suffix.casefold() not in PROHIBITED_SUFFIXES
    )


def copy_tree(source: Path, destination: Path) -> None:
    for path in sorted(source.rglob("*"), key=lambda item: item.as_posix().casefold()):
        relative = path.relative_to(source)
        if path.is_file() and allowed_source(relative):
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)


def copy_file(source: Path, destination: Path) -> None:
    if not source.is_file():
        raise SystemExit(f"missing release source: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)


def stage_sources(stage: Path) -> None:
    source_sdk = WORKSPACE_ROOT / "h1-bda-sdk"
    staged_sdk = stage / "h1-bda-sdk"
    copy_tree(source_sdk / "ports" / "kov_pgm", staged_sdk / "ports" / "kov_pgm")
    copy_tree(source_sdk / "h1_bda", staged_sdk / "h1_bda")
    copy_tree(source_sdk / "sdk" / "include", staged_sdk / "sdk" / "include")
    copy_file(source_sdk / "pyproject.toml", staged_sdk / "pyproject.toml")

    upstream = WORKSPACE_ROOT / "references" / "fba-a320"
    staged_upstream = stage / "references" / "fba-a320"
    copy_file(upstream / "readme.txt", staged_upstream / "readme.txt")
    copy_file(
        upstream / "src" / "cpu" / "a68k" / "mips32r1" / "fba_make68k.c",
        staged_upstream
        / "src"
        / "cpu"
        / "a68k"
        / "mips32r1"
        / "fba_make68k.c",
    )
    for name in CZ80_FILES:
        copy_file(
            upstream / "src" / "cpu" / "cz80" / name,
            staged_upstream / "src" / "cpu" / "cz80" / name,
        )


def write_release_documents(stage: Path) -> None:
    (stage / "README.txt").write_text(
        "BBK H1 KOV Plus V119 source release (ROM-free)\n"
        "================================================\n\n"
        "Scope\n"
        "-----\n"
        "This package contains only the native H1 KOV port, the minimum H1 BDA\n"
        "SDK components needed to build it, and the reviewed A68K/CZ80 sources.\n"
        "It does not contain arcade ROMs, PGM BIOS data, KOVH1.PAK, firmware,\n"
        "A320 game ports, CS, DOOM, compiler binaries, caches, logs, or Git data.\n\n"
        "Prerequisites\n"
        "-------------\n"
        "- Python 3.10 or newer\n"
        "- Pillow 10 or newer\n"
        "- LLVM tools with MIPS support: clang, ld.lld, llvm-objcopy\n"
        "- A native host C compiler available as clang or gcc\n\n"
        "Set H1_LLVM_BIN to the LLVM bin directory, then run:\n\n"
        "  python -m unittest discover -s h1-bda-sdk/ports/kov_pgm/tests -p test_*.py -v\n"
        "  python h1-bda-sdk/ports/kov_pgm/build_profiles.py --verify-reproducible\n\n"
        "Profiles\n"
        "--------\n"
        "H1KOVPlus-base.bda: no clock change and no live profile journal.\n"
        "H1KOVPlus-336MHz.bda: nominal-clock live profiling and adaptive frameskip.\n"
        "H1KOVPlus-336MHz-30FPS.bda: nominal clock and fixed alternate-frame rendering.\n"
        "H1KOVPlus-384MHz.bda: experimental overclock profiling and adaptive frameskip.\n"
        "H1KOVPlus-384MHz-30FPS.bda: 384 MHz and fixed alternate-frame rendering.\n"
        "Do not use 408 MHz: real H1 testing repeatedly rebooted within seconds.\n\n"
        "Runtime data\n"
        "------------\n"
        "The BDA expects a separately generated, legally owned ROM data pack at:\n"
        "  A:\\应用\\数据\\KOVH1\\KOVH1.PAK\n"
        "Expected pack size: 58,785,792 bytes\n"
        "Expected SHA-256:\n"
        "  6A3E5EF41212AA47A242689D904374DF0CBFEF4E34313053B2D7C1755642DB53\n",
        encoding="utf-8",
    )
    (stage / "THIRD_PARTY_NOTICES.txt").write_text(
        "Third-party notices and use restrictions\n"
        "========================================\n\n"
        "This package has no blanket license grant that overrides the terms of its\n"
        "individual components. Preserve all copyright headers and notices.\n\n"
        "A68K MIPS32r1 generator\n"
        "-----------------------\n"
        "Source: https://github.com/dmitrysmagin/fba-a320\n"
        "Reviewed revision: 68af7cc0065757c688595adc409f5d47977793ae\n"
        "Copyright notices in fba_make68k.c credit Mike Coates, Darren Olafson,\n"
        "Manuel Geran, and Dmitry Smagin. The reviewed upstream tree does not carry\n"
        "a separate license file for this generator; consult the copyright holders\n"
        "and upstream project before redistribution beyond private research.\n\n"
        "CZ80 0.91\n"
        "---------\n"
        "Copyright 2004-2005 Stephane Dallongeville. Its bundled readme permits free\n"
        "distribution and use only for non-commercial projects with credit. That\n"
        "restriction applies to builds containing CZ80. See:\n"
        "  references/fba-a320/src/cpu/cz80/readme.txt\n\n"
        "ROM and firmware notice\n"
        "-----------------------\n"
        "No game ROM or BBK firmware is included. Users must supply legally owned\n"
        "inputs. Do not distribute copyrighted ROM data without permission.\n",
        encoding="utf-8",
    )


def run(
    command: list[str], *, cwd: Path, env: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    print(completed.stdout, end="")
    if completed.returncode:
        raise SystemExit(
            f"command failed ({completed.returncode}): {' '.join(command)}"
        )
    return completed


def llvm_bin() -> Path:
    configured = os.environ.get("H1_LLVM_BIN")
    candidates = [
        Path(configured) if configured else Path("__missing__"),
        WORKSPACE_ROOT
        / "work"
        / "rebuild"
        / "tools"
        / "msys2-20260611"
        / "msys64"
        / "ucrt64"
        / "bin",
        WORKSPACE_ROOT / "work" / "tools" / "msys64" / "clangarm64" / "bin",
    ]
    for candidate in candidates:
        required = ("clang.exe", "ld.lld.exe", "llvm-objcopy.exe")
        if all((candidate / name).is_file() for name in required):
            return candidate.resolve()
    raise SystemExit("cannot find the MIPS-capable LLVM toolchain")


def build_environment() -> dict[str, str]:
    tools = llvm_bin()
    environment = os.environ.copy()
    environment["H1_LLVM_BIN"] = str(tools)
    environment["PATH"] = str(tools) + os.pathsep + environment.get("PATH", "")
    environment["SOURCE_DATE_EPOCH"] = SOURCE_DATE_EPOCH
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return environment


def verify_source_tree(root: Path, output: Path) -> None:
    environment = build_environment()
    tests = run(
        [
            sys.executable,
            "-m",
            "unittest",
            "discover",
            "-s",
            "h1-bda-sdk/ports/kov_pgm/tests",
            "-p",
            "test_*.py",
            "-v",
        ],
        cwd=root,
        env=environment,
    )
    match = re.search(r"Ran (\d+) tests?", tests.stdout)
    if match is None or int(match.group(1)) != EXPECTED_TESTS:
        raise SystemExit(f"expected {EXPECTED_TESTS} KOV tests")
    if "skipped=" in tests.stdout:
        raise SystemExit("KOV source verification must not skip tests")

    run(
        [
            sys.executable,
            "h1-bda-sdk/ports/kov_pgm/build_profiles.py",
            "--verify-reproducible",
            "-o",
            str(output),
        ],
        cwd=root,
        env=environment,
    )


def write_checksums(stage: Path) -> None:
    checksum_path = stage / "CHECKSUMS.sha256"
    files = sorted(
        (
            path
            for path in stage.rglob("*")
            if path.is_file() and path != checksum_path
        ),
        key=lambda path: path.relative_to(stage).as_posix().casefold(),
    )
    checksum_path.write_text(
        "".join(
            f"{sha256(path)}  {path.relative_to(stage).as_posix()}\n"
            for path in files
        ),
        encoding="utf-8",
    )


def reject_transients(stage: Path) -> None:
    rejected: list[str] = []
    for path in stage.rglob("*"):
        relative = path.relative_to(stage)
        if any(part.casefold() in PROHIBITED_PARTS for part in relative.parts):
            rejected.append(relative.as_posix())
        elif path.is_file() and path.suffix.casefold() in PROHIBITED_SUFFIXES:
            rejected.append(relative.as_posix())
    if rejected:
        raise SystemExit(
            "prohibited source release entries: " + ", ".join(sorted(rejected))
        )


def create_zip(stage: Path, archive: Path) -> None:
    archive.parent.mkdir(parents=True, exist_ok=True)
    archive.unlink(missing_ok=True)
    with zipfile.ZipFile(
        archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
    ) as output:
        paths = sorted(
            stage.rglob("*"),
            key=lambda item: item.relative_to(stage).as_posix().casefold(),
        )
        for path in paths:
            if not path.is_file():
                continue
            relative = Path(RELEASE_NAME) / path.relative_to(stage)
            info = zipfile.ZipInfo(relative.as_posix(), ZIP_TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            output.writestr(
                info,
                path.read_bytes(),
                compress_type=zipfile.ZIP_DEFLATED,
                compresslevel=9,
            )


def audit(*targets: Path) -> None:
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    run(
        [
            sys.executable,
            str(WORKSPACE_ROOT / "scripts" / "audit_release_secrets.py"),
            *map(str, targets),
        ],
        cwd=WORKSPACE_ROOT,
        env=environment,
    )


def compare_profiles(expected: Path, actual: Path) -> None:
    for name in PROFILES:
        if sha256(expected / name) != sha256(actual / name):
            raise SystemExit(f"unpacked profile differs: {name}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", type=Path, default=DEFAULT_STAGE)
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    args = parser.parse_args()

    stage = ensure_deliverable_target(args.stage)
    archive = ensure_deliverable_target(args.archive)
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)

    stage_sources(stage)
    write_release_documents(stage)
    prebuilt = stage / "prebuilt"
    verify_source_tree(stage, prebuilt)
    reject_transients(stage)
    write_checksums(stage)
    audit(stage)
    create_zip(stage, archive)
    audit(archive)

    with tempfile.TemporaryDirectory(
        prefix="kov-source-release-", ignore_cleanup_errors=True
    ) as temporary:
        extraction = Path(temporary)
        with zipfile.ZipFile(archive) as packaged:
            packaged.extractall(extraction)
        unpacked = extraction / RELEASE_NAME
        rebuilt = extraction / "rebuilt"
        verify_source_tree(unpacked, rebuilt)
        compare_profiles(unpacked / "prebuilt", rebuilt)

    print(f"release={archive}")
    print(f"size={archive.stat().st_size}")
    print(f"sha256={sha256(archive)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
