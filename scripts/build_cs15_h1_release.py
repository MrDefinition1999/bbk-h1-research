#!/usr/bin/env python3
"""Build reproducible public CS15 Lite H1 binary and source archives."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
ENGINE_ROOT = WORKSPACE_ROOT / "references" / "CS15-Lite-for9588"
SDK_ROOT = WORKSPACE_ROOT / "h1-bda-sdk"
DELIVERABLES_ROOT = WORKSPACE_ROOT / "deliverables"
RELEASE_NAME = "CS15-Lite-H1-2026-07-31"
DEFAULT_BINARY_STAGE = DELIVERABLES_ROOT / RELEASE_NAME
DEFAULT_SOURCE_STAGE = DELIVERABLES_ROOT / f"{RELEASE_NAME}-source"
DEFAULT_BINARY_ARCHIVE = DEFAULT_BINARY_STAGE.with_suffix(".zip")
DEFAULT_SOURCE_ARCHIVE = DEFAULT_SOURCE_STAGE.with_suffix(".zip")
SOURCE_DATE_EPOCH = "1785456000"
ZIP_TIMESTAMP = (2026, 7, 31, 0, 0, 0)
BDA_NAME = "H1CS15Lite.bda"
PROGRAM_DIRECTORY = Path("\u5e94\u7528") / "\u7a0b\u5e8f"

ENGINE_FILES = (
    "LICENSE",
    "NOTICE.md",
    "README.md",
    "RESOURCE_PACK.md",
)
ENGINE_DIRECTORIES = ("assets", "ports/h1", "src", "tests", "tools")
SDK_FILES = ("README.md", "pyproject.toml")
SDK_DIRECTORIES = ("h1_bda", "sdk/include", "reverse/include")
EXCLUDED_NAMES = {".git", "__pycache__", "build", ".deps", "content"}
EXCLUDED_SUFFIXES = {".pyc", ".c15pak", ".bsp", ".mdl", ".wad", ".wav"}


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


def reset_directory(path: Path) -> None:
    target = ensure_generated_target(path)
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)


def ignored_source(path: Path) -> bool:
    lowered_parts = {part.casefold() for part in path.parts}
    if lowered_parts & {item.casefold() for item in EXCLUDED_NAMES}:
        return True
    return path.suffix.casefold() in EXCLUDED_SUFFIXES


def copy_source_item(source: Path, destination: Path) -> None:
    if source.is_file():
        if not ignored_source(source):
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
        return
    for path in sorted(source.rglob("*"), key=lambda item: item.as_posix().casefold()):
        if not path.is_file() or ignored_source(path.relative_to(source)):
            continue
        relative = path.relative_to(source)
        output = destination / relative
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, output)


def run(command: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> None:
    subprocess.run(command, cwd=cwd, env=env, check=True)


def build_bda(output: Path) -> None:
    env = os.environ.copy()
    env["SOURCE_DATE_EPOCH"] = SOURCE_DATE_EPOCH
    env["H1_SDK_ROOT"] = str(SDK_ROOT)
    bundled_llvm = WORKSPACE_ROOT / "work" / "tools" / "msys64" / "clangarm64" / "bin"
    if "H1_LLVM_BIN" not in env and (bundled_llvm / "clang.exe").is_file():
        env["H1_LLVM_BIN"] = str(bundled_llvm)
    run(
        [
            sys.executable,
            str(ENGINE_ROOT / "ports" / "h1" / "build_port.py"),
            "--output",
            str(output),
        ],
        cwd=ENGINE_ROOT,
        env=env,
    )


def audit_icons(directory: Path, report: Path) -> None:
    run(
        [
            sys.executable,
            str(SDK_ROOT / "scripts" / "audit_release_icons.py"),
            str(directory),
            "--expected-count",
            "1",
            "--output",
            str(report),
        ],
        cwd=WORKSPACE_ROOT,
    )


def audit_secrets(*targets: Path) -> None:
    run(
        [
            sys.executable,
            str(WORKSPACE_ROOT / "scripts" / "audit_release_secrets.py"),
            *map(str, targets),
        ],
        cwd=WORKSPACE_ROOT,
    )


def write_checksums(root: Path) -> int:
    output = root / "CHECKSUMS.sha256"
    paths = sorted(
        (path for path in root.rglob("*") if path.is_file() and path != output),
        key=lambda path: path.relative_to(root).as_posix().casefold(),
    )
    lines = [f"{sha256(path)}  {path.relative_to(root).as_posix()}" for path in paths]
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(paths)


def build_archive(source: Path, archive: Path) -> None:
    archive = ensure_generated_target(archive)
    archive.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        prefix=archive.name + ".", suffix=".tmp", dir=archive.parent, delete=False
    ) as temporary_stream:
        temporary = Path(temporary_stream.name)
    try:
        paths = sorted(
            (path for path in source.rglob("*") if path.is_file()),
            key=lambda path: path.relative_to(source).as_posix().casefold(),
        )
        with zipfile.ZipFile(
            temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
        ) as output:
            for path in paths:
                relative = path.relative_to(source).as_posix()
                info = zipfile.ZipInfo(relative, ZIP_TIMESTAMP)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                output.writestr(info, path.read_bytes(), compresslevel=9)
        os.replace(temporary, archive)
    finally:
        temporary.unlink(missing_ok=True)


def stage_binary(stage: Path, built_bda: Path) -> None:
    reset_directory(stage)
    destination = stage / PROGRAM_DIRECTORY / BDA_NAME
    destination.parent.mkdir(parents=True)
    shutil.copyfile(built_bda, destination)
    (stage / "README-H1.txt").write_text(
        "CS15 Lite for BBK H1\n"
        "=======================\n\n"
        "Copy the contents of this package to the root of the H1 A: drive.\n"
        "The BDA is installed at A:\\\u5e94\u7528\\\u7a0b\u5e8f\\H1CS15Lite.bda.\n\n"
        "CS15.C15PAK is intentionally not included. Create it only from assets\n"
        "you legally possess, then copy it to:\n"
        "A:\\\u5e94\u7528\\\u6570\u636e\\CS15LITE\\CS15.C15PAK\n\n"
        "The required pack is version 2 for the matching CS15 Lite v0.3.4 data.\n"
        "Do not rename CS15.C15PAK.\n\n"
        "Controls\n"
        "--------\n"
        "Arrows or W/A/S/D: move and strafe\n"
        "Q/E and I/K: horizontal and vertical look\n"
        "Confirm, Enter, or J: menu confirm and fire\n"
        "F: use, buy, plant/defuse, or start from the buy screen\n"
        "R: reload\n"
        "Tap X or Page Down: next weapon; hold 0.7 s: drop weapon\n"
        "Left or right Alt: weapon alternate action\n"
        "Space: jump; C: crouch\n"
        "Short Esc: pause/resume; hold Esc 0.8 s: emergency exit\n"
        "Permanent H1 Back key: immediate exit\n",
        encoding="utf-8",
    )
    write_checksums(stage)


def stage_source(stage: Path) -> None:
    reset_directory(stage)
    engine_destination = stage / "CS15-Lite-for9588"
    sdk_destination = stage / "h1-bda-sdk"
    for relative in ENGINE_FILES:
        copy_source_item(ENGINE_ROOT / relative, engine_destination / relative)
    for relative in ENGINE_DIRECTORIES:
        copy_source_item(ENGINE_ROOT / relative, engine_destination / relative)
    for relative in SDK_FILES:
        copy_source_item(SDK_ROOT / relative, sdk_destination / relative)
    for relative in SDK_DIRECTORIES:
        copy_source_item(SDK_ROOT / relative, sdk_destination / relative)
    shutil.copyfile(ENGINE_ROOT / "LICENSE", sdk_destination / "COPYING.GPL-2.0-or-later")
    (stage / "REBUILD.txt").write_text(
        "Rebuild H1CS15Lite.bda\n"
        "=======================\n\n"
        "Requirements: Python 3.10+, Pillow, and LLVM tools with a MIPS target:\n"
        "clang, ld.lld, and llvm-objcopy. Set H1_LLVM_BIN to their directory.\n\n"
        "From this source package root on Windows PowerShell:\n"
        "$env:SOURCE_DATE_EPOCH='1785456000'\n"
        "$env:H1_SDK_ROOT=(Resolve-Path .\\h1-bda-sdk)\n"
        "python -m pip install Pillow\n"
        "python .\\CS15-Lite-for9588\\ports\\h1\\build_port.py `\n"
        "  --output .\\H1CS15Lite.bda\n\n"
        "Commercial Counter-Strike/Half-Life resources are not source code and\n"
        "are not included. See CS15-Lite-for9588\\RESOURCE_PACK.md.\n\n"
        "The H1 build-support subset in this corresponding-source package is\n"
        "distributed under GPL-2.0-or-later for rebuilding this program.\n",
        encoding="ascii",
    )
    prohibited = [
        path
        for path in stage.rglob("*")
        if path.is_file() and path.suffix.casefold() == ".c15pak"
    ]
    if prohibited:
        raise SystemExit("private resource pack entered source staging")
    write_checksums(stage)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary-stage", type=Path, default=DEFAULT_BINARY_STAGE)
    parser.add_argument("--source-stage", type=Path, default=DEFAULT_SOURCE_STAGE)
    parser.add_argument("--binary-archive", type=Path, default=DEFAULT_BINARY_ARCHIVE)
    parser.add_argument("--source-archive", type=Path, default=DEFAULT_SOURCE_ARCHIVE)
    args = parser.parse_args()

    binary_stage = ensure_generated_target(args.binary_stage)
    source_stage = ensure_generated_target(args.source_stage)
    binary_archive = ensure_generated_target(args.binary_archive)
    source_archive = ensure_generated_target(args.source_archive)
    build_output = ENGINE_ROOT / "build" / "h1" / BDA_NAME

    build_bda(build_output)
    audit_icons(build_output.parent, SDK_ROOT / "build" / "cs15-release-icon-audit.json")
    stage_binary(binary_stage, build_output)
    stage_source(source_stage)
    audit_secrets(binary_stage, source_stage)
    build_archive(binary_stage, binary_archive)
    build_archive(source_stage, source_archive)
    audit_secrets(binary_archive, source_archive)

    report = {
        "format": "h1-cs15-public-release-v1",
        "source_date_epoch": int(SOURCE_DATE_EPOCH),
        "bda": {
            "size": build_output.stat().st_size,
            "sha256": sha256(build_output),
        },
        "binary_archive": {
            "file": binary_archive.name,
            "size": binary_archive.stat().st_size,
            "sha256": sha256(binary_archive),
        },
        "source_archive": {
            "file": source_archive.name,
            "size": source_archive.stat().st_size,
            "sha256": sha256(source_archive),
        },
    }
    report_path = DELIVERABLES_ROOT / f"{RELEASE_NAME}-release.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="ascii")
    audit_secrets(report_path)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
