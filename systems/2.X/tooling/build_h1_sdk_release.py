#!/usr/bin/env python3
"""Build a deterministic, privacy-audited release of the focused H1 SDK."""

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
DELIVERABLES_ROOT = WORKSPACE_ROOT / "deliverables"
DEFAULT_NAME = "BBK-H1-BDA-SDK-core-2026-08-04"
SOURCE_DATE_EPOCH = "1785801600"
ZIP_TIMESTAMP = (2026, 8, 4, 0, 0, 0)

ROOT_FILES = ("README.md", "pyproject.toml")
TREE_PATTERNS = {
    "h1_bda": ("*.py",),
    "sdk/include": ("*.h",),
    "examples/basic/hello_dialog": ("*.c",),
    "examples/system/memory": ("*.c",),
    "reverse/include": ("*.h",),
    "reverse/docs": ("*.md",),
    "docs/verified/assets": ("*.png",),
    "tests/fixtures": ("*.c",),
}
WORKSPACE_FILES = (
    "scripts/audit_release_secrets.py",
    "scripts/build_h1_system_nand.py",
    "scripts/h1_fat16.py",
    "scripts/h1_ftl.py",
    "scripts/jz4740_ecc.py",
    "scripts/make_h1_nand.py",
)
EXPLICIT_FILES = (
    "reverse/probes/filesystem_probe.c",
    "reverse/probes/graphics_probe.c",
    "reverse/probes/input_time_probe.c",
    "reverse/probes/memory_probe.c",
    "reverse/probes/message_box_probe.c",
    "reverse/tools/scan_service_calls.py",
    "docs/emulator_deployment.md",
    "docs/verified/custom_icon_build.md",
    "docs/verified/emulator_root_file_install.md",
    "docs/verified/filesystem_api.md",
    "docs/verified/game_slot_workflow.md",
    "docs/verified/graphics_api.md",
    "docs/verified/input_time_api.md",
    "docs/verified/memory_api.md",
    "docs/verified/message_box_api.md",
    "docs/verified/multi_source_build.md",
    "scripts/audit_release_icons.py",
    "scripts/capture_emulator_frame.py",
    "scripts/capture_probe_memory.py",
    "scripts/compare_emulator_nand.py",
    "scripts/deploy_emulator_bda.py",
    "scripts/extract_bda_icons.py",
    "scripts/extract_emulator_file.py",
    "scripts/install_emulator_file.py",
    "scripts/install_emulator_path.py",
    "scripts/profile_guest_pc.py",
    "scripts/qemu_mips_watch.py",
    "tests/test_build.py",
    "tests/test_deploy_growth.py",
    "tests/test_header.py",
    "tests/test_install_emulator_path.py",
    "tests/test_service_scan.py",
    "tests/test_validate.py",
)


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


def child_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["SOURCE_DATE_EPOCH"] = SOURCE_DATE_EPOCH
    if "H1_LLVM_BIN" not in environment:
        candidates = (
            WORKSPACE_ROOT
            / "work/rebuild/tools/msys2-20260611/msys64/ucrt64/bin",
            WORKSPACE_ROOT / "work/tools/msys64/clangarm64/bin",
        )
        selected = next(
            (path for path in candidates if (path / "clang.exe").is_file()), None
        )
        if selected is not None:
            environment["H1_LLVM_BIN"] = str(selected)
    return environment


def run(command: list[str], *, cwd: Path = WORKSPACE_ROOT) -> None:
    subprocess.run(command, cwd=cwd, env=child_environment(), check=True)


def reset_stage(stage: Path) -> None:
    target = ensure_generated_target(stage)
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)


def copy_source(stage: Path) -> None:
    source_root = stage / "h1-bda-sdk"
    for relative in ROOT_FILES:
        destination = source_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(SDK_ROOT / relative, destination)
    for relative_root, patterns in TREE_PATTERNS.items():
        source_directory = SDK_ROOT / relative_root
        for pattern in patterns:
            for source in sorted(source_directory.glob(pattern)):
                if not source.is_file():
                    continue
                destination = source_root / source.relative_to(SDK_ROOT)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, destination)
    for relative in EXPLICIT_FILES:
        source = SDK_ROOT / relative
        if not source.is_file():
            raise FileNotFoundError(source)
        destination = source_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    for relative in WORKSPACE_FILES:
        source = WORKSPACE_ROOT / relative
        if not source.is_file():
            raise FileNotFoundError(source)
        destination = stage / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)


def build_example(source: Path, title: str, destination: Path) -> None:
    run(
        [
            sys.executable,
            "-B",
            "-m",
            "h1_bda.build",
            str(source),
            "--title",
            title,
            "-o",
            str(destination),
        ]
    )


def build_reproducible_examples(stage: Path) -> None:
    examples = (
        (
            SDK_ROOT / "examples/basic/hello_dialog/hello_dialog.c",
            "H1 Hello",
            "H1Hello.bda",
        ),
        (
            SDK_ROOT / "examples/system/memory/memory_demo.c",
            "H1 Memory",
            "H1Memory.bda",
        ),
    )
    output = stage / "examples" / "build"
    output.mkdir(parents=True)
    with tempfile.TemporaryDirectory(prefix="h1-sdk-repro-") as temporary:
        check_root = Path(temporary)
        for source, title, name in examples:
            first = check_root / ("first-" + name)
            second = check_root / ("second-" + name)
            build_example(source, title, first)
            build_example(source, title, second)
            if first.read_bytes() != second.read_bytes():
                raise SystemExit(f"SDK example is not reproducible: {name}")
            shutil.copyfile(first, output / name)


def write_release_readme(stage: Path) -> None:
    (stage / "README.txt").write_text(
        "BBK H1 native BDA SDK\n"
        "=====================\n\n"
        "This focused package contains only the H1-native SDK, verified H1 API\n"
        "evidence, generic deployment tools, and two reproducible examples.\n"
        "Dingoo A320 ports, DOOM, GTA, CS, private firmware, ROMs, caches, and\n"
        "debug logs are intentionally excluded.\n\n"
        "Install Python 3.10+ and Pillow, then install h1-bda-sdk/ with pip. A MIPS\n"
        "little-endian LLVM toolchain is required; set H1_LLVM_BIN to its bin\n"
        "directory. See h1-bda-sdk/README.md for API evidence and usage.\n",
        encoding="utf-8",
    )


def reject_unexpected(stage: Path) -> None:
    forbidden_parts = {".git", "__pycache__", "ports", "third_party"}
    forbidden_suffixes = {".elf", ".log", ".pyc", ".pyo", ".wav"}
    problems: list[str] = []
    for path in stage.rglob("*"):
        relative = path.relative_to(stage)
        lowered = {part.casefold() for part in relative.parts}
        if lowered & forbidden_parts:
            problems.append(relative.as_posix())
        if path.is_file() and path.suffix.casefold() in forbidden_suffixes:
            problems.append(relative.as_posix())
    if problems:
        raise SystemExit("forbidden SDK release content: " + ", ".join(problems))


def write_checksums(stage: Path) -> None:
    checksum_file = stage / "CHECKSUMS.sha256"
    files = sorted(
        (path for path in stage.rglob("*") if path.is_file() and path != checksum_file),
        key=lambda path: path.relative_to(stage).as_posix().casefold(),
    )
    checksum_file.write_text(
        "".join(
            f"{sha256(path)}  {path.relative_to(stage).as_posix()}\n"
            for path in files
        ),
        encoding="utf-8",
    )


def audit(*targets: Path) -> None:
    run(
        [
            sys.executable,
            "-B",
            str(WORKSPACE_ROOT / "scripts/audit_release_secrets.py"),
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
        files = sorted(
            (path for path in stage.rglob("*") if path.is_file()),
            key=lambda path: path.relative_to(stage).as_posix().casefold(),
        )
        with zipfile.ZipFile(
            temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
        ) as output:
            for path in files:
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
    copy_source(stage)
    build_reproducible_examples(stage)
    write_release_readme(stage)
    reject_unexpected(stage)
    write_checksums(stage)
    audit(stage)
    build_archive(stage, archive)
    audit(archive)
    print(f"stage={stage.name} files={sum(path.is_file() for path in stage.rglob('*'))}")
    print(f"archive={archive.name} size={archive.stat().st_size} sha256={sha256(archive)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
