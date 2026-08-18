#!/usr/bin/env python3
"""Remove generated caches, runtime logs, and development-only reports."""

from __future__ import annotations

import argparse
import ctypes
import os
from pathlib import Path
from ctypes import wintypes


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
RELEASE_SCAN_ROOTS = (
    REPOSITORY_ROOT / "deliverables",
    REPOSITORY_ROOT / "docs",
    REPOSITORY_ROOT / "scripts",
    REPOSITORY_ROOT / "emulator",
    REPOSITORY_ROOT / "h1-bda-sdk",
)
DEVELOPMENT_REPORT_PATTERNS = (
    "*-deployment.json",
    "*-install.json",
    "*-ab.json",
)
TRANSIENT_DIRECTORIES = (
    REPOSITORY_ROOT / "work" / "tmp",
)
OBSOLETE_RELEASE_TARGETS = (
    REPOSITORY_ROOT / "deliverables" / "H1-all-games-real-hardware-2026-08-01",
    REPOSITORY_ROOT / "deliverables" / "H1-all-games-real-hardware-2026-08-01.zip",
)
REBUILDABLE_BUILD_PATTERNS = ("*.elf", "*.wav")

FO_DELETE = 3
FOF_SILENT = 0x0004
FOF_NOCONFIRMATION = 0x0010
FOF_ALLOWUNDO = 0x0040
FOF_NOERRORUI = 0x0400


class SHFileOperation(ctypes.Structure):
    _fields_ = (
        ("hwnd", wintypes.HWND),
        ("wFunc", wintypes.UINT),
        ("pFrom", wintypes.LPCWSTR),
        ("pTo", wintypes.LPCWSTR),
        ("fFlags", wintypes.WORD),
        ("fAnyOperationsAborted", wintypes.BOOL),
        ("hNameMappings", wintypes.LPVOID),
        ("lpszProgressTitle", wintypes.LPCWSTR),
    )


def assert_within_repository(path: Path) -> Path:
    resolved = path.resolve()
    if not resolved.is_relative_to(REPOSITORY_ROOT):
        raise ValueError(f"cleanup target escaped repository: {resolved}")
    return resolved


def send_to_recycle_bin(path: Path) -> None:
    if os.name != "nt":
        raise RuntimeError("cleanup requires the Windows Recycle Bin")
    source = f"{path}\0\0"
    operation = SHFileOperation(
        wFunc=FO_DELETE,
        pFrom=source,
        fFlags=FOF_SILENT | FOF_NOCONFIRMATION | FOF_ALLOWUNDO | FOF_NOERRORUI,
    )
    result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(operation))
    if result != 0 or operation.fAnyOperationsAborted:
        raise OSError(result, f"could not recycle {path}")


def collect_targets() -> tuple[list[Path], list[Path]]:
    directories: set[Path] = set()
    files: set[Path] = set()
    for root in RELEASE_SCAN_ROOTS:
        if not root.is_dir():
            continue
        for directory in root.rglob("__pycache__"):
            if directory.is_dir() and directory.name == "__pycache__":
                directories.add(assert_within_repository(directory))
        for suffix in ("*.pyc", "*.pyo"):
            for path in root.rglob(suffix):
                if path.is_file():
                    files.add(assert_within_repository(path))

    runtime = REPOSITORY_ROOT / "emulator" / "windows-x86_64" / "runtime"
    if runtime.is_dir():
        for path in runtime.glob("*.log"):
            if path.is_file():
                files.add(assert_within_repository(path))

    build = REPOSITORY_ROOT / "h1-bda-sdk" / "build"
    if build.is_dir():
        for pattern in DEVELOPMENT_REPORT_PATTERNS:
            for path in build.glob(pattern):
                if path.is_file():
                    files.add(assert_within_repository(path))
        for pattern in REBUILDABLE_BUILD_PATTERNS:
            for path in build.glob(pattern):
                if path.is_file():
                    files.add(assert_within_repository(path))

    for directory in TRANSIENT_DIRECTORIES:
        if directory.is_dir():
            directories.add(assert_within_repository(directory))

    for path in OBSOLETE_RELEASE_TARGETS:
        if path.is_dir():
            directories.add(assert_within_repository(path))
        elif path.is_file():
            files.add(assert_within_repository(path))

    files = {
        path
        for path in files
        if not any(path.is_relative_to(directory) for directory in directories)
    }
    ordered_directories = sorted(directories, key=lambda item: (-len(item.parts), str(item)))
    return ordered_directories, sorted(files)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    directories, files = collect_targets()
    removed_bytes = sum(path.stat().st_size for path in files if path.exists())
    for directory in directories:
        removed_bytes += sum(
            path.stat().st_size for path in directory.rglob("*") if path.is_file()
        )

    if not args.dry_run:
        for path in files:
            if path.exists():
                send_to_recycle_bin(path)
        for directory in directories:
            if directory.exists():
                send_to_recycle_bin(directory)

    action = "would_remove" if args.dry_run else "removed"
    print(
        f"{action}_files={len(files)} {action}_cache_dirs={len(directories)} "
        f"bytes={removed_bytes}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
