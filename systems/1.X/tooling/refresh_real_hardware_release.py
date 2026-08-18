#!/usr/bin/env python3
"""Refresh the complete H1 real-hardware game package from verified builds."""

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
DEFAULT_RELEASE_DIR = (
    WORKSPACE_ROOT / "deliverables" / "H1-real-hardware-test-2026-07-29"
)
DEFAULT_ARCHIVE = DEFAULT_RELEASE_DIR.with_suffix(".zip")
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
ZIP_TIMESTAMP = (2026, 7, 30, 0, 0, 0)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest().upper()


def validate_release_inputs(release_dir: Path) -> tuple[Path, Path]:
    root = release_dir / "A-root"
    apps = root / "apps"
    readme = release_dir / "README-实机测试.txt"
    missing = [name for name in RUNTIME_NAMES if not (root / name).is_file()]
    missing.extend(name for name in BDA_NAMES if not (WORKSPACE_ROOT / "h1-bda-sdk" / "build" / name).is_file())
    if not readme.is_file():
        missing.append(readme.name)
    if missing:
        raise SystemExit("missing release inputs: " + ", ".join(missing))
    apps.mkdir(parents=True, exist_ok=True)
    return root, apps


def sync_bda_files(apps: Path) -> None:
    source_dir = WORKSPACE_ROOT / "h1-bda-sdk" / "build"
    for name in BDA_NAMES:
        source = source_dir / name
        destination = apps / name
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        shutil.copyfile(source, temporary)
        os.replace(temporary, destination)


def write_checksums(release_dir: Path, root: Path) -> int:
    paths = sorted(
        (path for path in root.rglob("*") if path.is_file()),
        key=lambda path: path.relative_to(release_dir).as_posix().casefold(),
    )
    lines = [
        f"{sha256(path)}  {path.relative_to(release_dir).as_posix()}"
        for path in paths
    ]
    output = release_dir / "CHECKSUMS.sha256"
    output.write_text("\n".join(lines) + "\n", encoding="ascii")
    return len(paths)


def build_archive(release_dir: Path, archive: Path) -> None:
    archive.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        prefix=archive.name + ".",
        suffix=".tmp",
        dir=archive.parent,
        delete=False,
    ) as temporary_stream:
        temporary = Path(temporary_stream.name)
    try:
        paths = sorted(
            (path for path in release_dir.rglob("*") if path.is_file()),
            key=lambda path: path.relative_to(release_dir).as_posix().casefold(),
        )
        with zipfile.ZipFile(
            temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
        ) as output:
            for path in paths:
                relative = path.relative_to(release_dir).as_posix()
                info = zipfile.ZipInfo(relative, ZIP_TIMESTAMP)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                output.writestr(info, path.read_bytes(), compresslevel=9)
        os.replace(temporary, archive)
    finally:
        temporary.unlink(missing_ok=True)


def audit(*targets: Path) -> None:
    command = [
        sys.executable,
        str(WORKSPACE_ROOT / "scripts" / "audit_release_secrets.py"),
        *map(str, targets),
    ]
    subprocess.run(command, cwd=WORKSPACE_ROOT, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-dir", type=Path, default=DEFAULT_RELEASE_DIR)
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    args = parser.parse_args()

    release_dir = args.release_dir.resolve()
    archive = args.archive.resolve()
    root, apps = validate_release_inputs(release_dir)
    sync_bda_files(apps)
    checksum_entries = write_checksums(release_dir, root)
    audit(release_dir)
    build_archive(release_dir, archive)
    audit(archive)

    report = {
        "format": "h1-real-hardware-release-v1",
        "games": len(BDA_NAMES),
        "checksum_entries": checksum_entries,
        "archive": archive.name,
        "archive_size": archive.stat().st_size,
        "archive_sha256": sha256(archive),
    }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
