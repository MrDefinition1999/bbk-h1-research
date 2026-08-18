#!/usr/bin/env python3
"""Build the deterministic x86-64 H1 emulator runtime without private firmware."""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
EMULATOR_ROOT = WORKSPACE_ROOT / "emulator"
RUNTIME_ROOT = EMULATOR_ROOT / "windows-x86_64"
DELIVERABLES_ROOT = WORKSPACE_ROOT / "deliverables"
DEFAULT_NAME = "BBK-H1-emulator-x86_64-runtime-only-2026-08-04"
ZIP_TIMESTAMP = (2026, 8, 4, 0, 0, 0)
QEMU_SHA256 = "71D262B5ABEA05E96F98C7B379677C820A540EF54922EAB9AF4354409D3E3302"
PROJECT_SHA256 = "D05786E442F9AAD62A8D0A0CB4F6D786BDC7C2FA353A7A2B152C9ED9F01B40EF"
NAND_SHA256 = "9D5DD297B51A628570C550EEB98B0A7462B7EDD5DD50EEEABE353A48D46F434F"
NAND_BYTES = 1_107_296_256
PE_X86_64 = 0x8664


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest().upper()


def ensure_generated_target(path: Path) -> Path:
    target = path.resolve()
    root = DELIVERABLES_ROOT.resolve()
    if target == root or root not in target.parents:
        raise SystemExit(f"refusing generated output outside deliverables: {target}")
    return target


def reset_stage(stage: Path) -> None:
    target = ensure_generated_target(stage)
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)


def copy_tree(source: Path, destination: Path) -> None:
    for path in sorted(source.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(source)
        lowered_parts = {part.casefold() for part in relative.parts}
        if "__pycache__" in lowered_parts or path.suffix.casefold() in {
            ".pyc",
            ".pyo",
        }:
            continue
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)


def copy_runtime(stage: Path) -> None:
    copy_tree(RUNTIME_ROOT / "bin", stage / "bin")
    copy_tree(RUNTIME_ROOT / "python", stage / "python")
    copy_tree(RUNTIME_ROOT / "web", stage / "web")
    for name in ("h1_emulator.py", "README.md", "start-h1.cmd", "start-h1.ps1"):
        shutil.copyfile(RUNTIME_ROOT / name, stage / name)
    shutil.copyfile(EMULATOR_ROOT / "COPYING", stage / "COPYING")
    shutil.copyfile(EMULATOR_ROOT / "COPYING.LIB", stage / "COPYING.LIB")
    firmware = stage / "firmware"
    firmware.mkdir()
    (firmware / "REQUIRED.txt").write_text(
        "Private H1 firmware is intentionally not included.\n\n"
        "Place the original V1.41 project.bin here:\n"
        f"  bytes: 5729640\n  SHA-256: {PROJECT_SHA256}\n\n"
        "Place the verified full-page baseline NAND here as h1-system.raw:\n"
        f"  bytes: {NAND_BYTES}\n  SHA-256: {NAND_SHA256}\n\n"
        "Both inputs must come from the same trusted H1 recovery set. Do not\n"
        "substitute the known-corrupted post-incident workspace copies.\n",
        encoding="utf-8",
    )


def pe_machine(path: Path) -> int:
    data = path.read_bytes()
    if len(data) < 0x40 or data[:2] != b"MZ":
        raise ValueError(f"not a PE file: {path}")
    pe_offset = struct.unpack_from("<I", data, 0x3C)[0]
    if pe_offset + 6 > len(data) or data[pe_offset : pe_offset + 4] != b"PE\0\0":
        raise ValueError(f"invalid PE header: {path}")
    return struct.unpack_from("<H", data, pe_offset + 4)[0]


def verify_runtime(stage: Path) -> None:
    qemu = stage / "bin/qemu-system-mipsel.exe"
    if sha256(qemu) != QEMU_SHA256:
        raise SystemExit("staged QEMU hash does not match the finalized x86-64 build")
    pe_files = [
        *sorted((stage / "bin").glob("*.exe")),
        *sorted((stage / "bin").glob("*.dll")),
        *sorted((stage / "python").glob("*.exe")),
        *sorted((stage / "python").glob("*.dll")),
    ]
    wrong = [path for path in pe_files if pe_machine(path) != PE_X86_64]
    if wrong:
        raise SystemExit("non-x86-64 PE in runtime: " + ", ".join(map(str, wrong)))

    environment = os.environ.copy()
    environment["PATH"] = str(Path(os.environ["SystemRoot"]) / "System32")
    version = subprocess.run(
        [str(qemu), "--version"],
        cwd=qemu.parent,
        env=environment,
        check=True,
        text=True,
        capture_output=True,
    ).stdout
    machines = subprocess.run(
        [str(qemu), "-machine", "help"],
        cwd=qemu.parent,
        env=environment,
        check=True,
        text=True,
        capture_output=True,
    ).stdout
    if "QEMU emulator version 11.0.0" not in version:
        raise SystemExit("unexpected QEMU version")
    if not any(line.startswith("bbkh1 ") for line in machines.splitlines()):
        raise SystemExit("finalized QEMU does not expose bbkh1")

    python = stage / "python/python.exe"
    subprocess.run(
        [str(python), "-B", str(stage / "h1_emulator.py"), "--help"],
        cwd=stage,
        env={**environment, "PYTHONDONTWRITEBYTECODE": "1"},
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )


def reject_unexpected(stage: Path) -> None:
    forbidden_parts = {"__pycache__", "assets", ".git"}
    forbidden_suffixes = {".bin", ".log", ".pak", ".pyc", ".pyo", ".raw"}
    problems: list[str] = []
    for path in stage.rglob("*"):
        relative = path.relative_to(stage)
        lowered = {part.casefold() for part in relative.parts}
        if lowered & forbidden_parts:
            problems.append(relative.as_posix())
        if path.is_file() and path.suffix.casefold() in forbidden_suffixes:
            problems.append(relative.as_posix())
    if problems:
        raise SystemExit(
            "private, abandoned, or transient emulator content: "
            + ", ".join(problems)
        )


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
    )


def audit(*targets: Path) -> None:
    subprocess.run(
        [
            sys.executable,
            "-B",
            str(WORKSPACE_ROOT / "scripts/audit_release_secrets.py"),
            *map(str, targets),
        ],
        cwd=WORKSPACE_ROOT,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        check=True,
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", type=Path)
    parser.add_argument("--archive", type=Path)
    args = parser.parse_args()
    default_stage = DELIVERABLES_ROOT / DEFAULT_NAME
    stage = ensure_generated_target(args.stage or default_stage)
    archive = ensure_generated_target(args.archive or stage.with_suffix(".zip"))

    reset_stage(stage)
    copy_runtime(stage)
    reject_unexpected(stage)
    verify_runtime(stage)
    write_checksums(stage)
    audit(stage)
    build_archive(stage, archive)
    audit(archive)
    print(f"stage={stage.name} files={sum(path.is_file() for path in stage.rglob('*'))}")
    print(f"archive={archive.name} size={archive.stat().st_size} sha256={sha256(archive)}")
    print("firmware_included=no")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
