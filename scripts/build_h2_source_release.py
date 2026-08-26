#!/usr/bin/env python3
"""Build the deterministic H2 V2.2L ARM64 source-only release."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DELIVERABLES_ROOT = REPOSITORY_ROOT / "deliverables"
RELEASE_NAME = "bbk-h2-v2.2l-arm64-source-20260826"
ZIP_TIMESTAMP = (2026, 8, 26, 0, 0, 0)

# This is deliberately an allowlist.  In particular, it does not contain the
# official recovery package, derived eMMC image, game data, QEMU binaries,
# compiler cache, debug ELF files, logs, journals, or any H1 emulator runtime.
SOURCE_TREES = (
    Path("systems/H2-2.X"),
    Path("h1-bda-sdk/h1_bda"),
)
SOURCE_FILES = (
    Path("scripts/build_h2_v2_image.py"),
    Path("scripts/verify_h2_v2_image.py"),
    Path("scripts/build_h2_source_release.py"),
    Path("h1-bda-sdk/examples/v2/v1_game_stage.c"),
)
FORBIDDEN_PARTS = {".git", ".local", "__pycache__", "build", "dist"}
FORBIDDEN_SUFFIXES = {
    ".bin",
    ".dll",
    ".elf",
    ".exe",
    ".gz",
    ".log",
    ".pyc",
    ".pyo",
    ".rar",
    ".raw",
    ".zip",
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
        raise SystemExit(f"refusing generated target outside deliverables: {target}")
    return target


def allowed_source(path: Path) -> bool:
    relative = path.relative_to(REPOSITORY_ROOT)
    lowered_parts = {part.casefold() for part in relative.parts}
    return not (lowered_parts & FORBIDDEN_PARTS) and (
        not path.is_file() or path.suffix.casefold() not in FORBIDDEN_SUFFIXES
    )


def copy_file(source: Path, stage: Path) -> None:
    if not source.is_file():
        raise FileNotFoundError(source)
    if not allowed_source(source):
        raise SystemExit(f"refusing forbidden source: {source}")
    relative = source.relative_to(REPOSITORY_ROOT)
    destination = stage / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)


def stage_sources(stage: Path) -> None:
    target = generated_target(stage)
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    for relative_tree in SOURCE_TREES:
        source_root = REPOSITORY_ROOT / relative_tree
        for source in sorted(source_root.rglob("*")):
            if source.is_file() and allowed_source(source):
                copy_file(source, target)
    for relative_file in SOURCE_FILES:
        copy_file(REPOSITORY_ROOT / relative_file, target)


def reject_unexpected(stage: Path) -> None:
    problems: list[str] = []
    for path in stage.rglob("*"):
        relative = path.relative_to(stage)
        lowered_parts = {part.casefold() for part in relative.parts}
        if lowered_parts & FORBIDDEN_PARTS:
            problems.append(relative.as_posix())
        if path.is_file() and path.suffix.casefold() in FORBIDDEN_SUFFIXES:
            problems.append(relative.as_posix())
    if problems:
        raise SystemExit("unexpected release content: " + ", ".join(problems))


def write_checksums(stage: Path) -> None:
    output = stage / "CHECKSUMS.sha256"
    paths = sorted(
        (path for path in stage.rglob("*") if path.is_file() and path != output),
        key=lambda path: path.relative_to(stage).as_posix().casefold(),
    )
    output.write_text(
        "".join(
            f"{sha256(path)}  {path.relative_to(stage).as_posix()}\n"
            for path in paths
        ),
        encoding="utf-8",
        newline="\n",
    )


def audit(*targets: Path) -> None:
    subprocess.run(
        [
            sys.executable,
            "-B",
            str(REPOSITORY_ROOT / "scripts/audit_release_secrets.py"),
            *map(str, targets),
        ],
        cwd=REPOSITORY_ROOT,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        check=True,
    )


def build_archive(stage: Path, archive: Path) -> None:
    target = generated_target(archive)
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
                info = zipfile.ZipInfo(
                    path.relative_to(stage).as_posix(), ZIP_TIMESTAMP
                )
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                output.writestr(info, path.read_bytes(), compresslevel=9)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> int:
    stage = generated_target(DELIVERABLES_ROOT / RELEASE_NAME)
    archive = generated_target(DELIVERABLES_ROOT / f"{RELEASE_NAME}.zip")
    stage_sources(stage)
    reject_unexpected(stage)
    write_checksums(stage)
    audit(stage)
    build_archive(stage, archive)
    audit(archive)
    print(f"stage={stage.name}")
    print(f"files={sum(path.is_file() for path in stage.rglob('*'))}")
    print(f"archive={archive.name}")
    print(f"bytes={archive.stat().st_size}")
    print(f"sha256={sha256(archive)}")
    print("official_firmware_included=no")
    print("game_data_included=no")
    print("h1_emulator_runtime_included=no")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
