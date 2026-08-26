#!/usr/bin/env python3
"""Build the H2-native wrapper for the original H1 V1 Mission payload."""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SDK_ROOT = REPOSITORY_ROOT / "h1-bda-sdk"
sys.path.insert(0, str(SDK_ROOT))

from h1_bda.header import HeaderFields, decode_header, encode_header  # noqa: E402
from h1_bda.validate import validate_bda  # noqa: E402


H2_ENTRY_VA = 0x81C30040
STAGE_VA = 0x83F00000
EMBEDDED_GAME_SIZE = 0x79374
H2_GAME_SHA256 = (
    "5D505D6C68ED6C4B93977B057937A625803B9F67801A2A7E43B5A1F8BA1AAEA6"
)
EXTERNAL_PATH = "A:\\V1GAME.BIN"


def _temporary_root() -> Path:
    root = REPOSITORY_ROOT / "work" / "h2" / "build-temp"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def _find_zig() -> Path:
    configured = os.environ.get("H2_ZIG")
    candidates = [
        Path(configured) if configured else Path("__not_configured__"),
        REPOSITORY_ROOT
        / "work"
        / "h2"
        / "toolchain-temp"
        / "zig-aarch64-windows-0.16.0"
        / "zig.exe",
    ]
    located = shutil.which("zig") or shutil.which("zig.exe")
    if located:
        candidates.append(Path(located))
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise SystemExit("cannot find Zig; set H2_ZIG to an ARM64 Zig executable")


def _find_objcopy() -> Path:
    configured = os.environ.get("H2_LLVM_OBJCOPY")
    candidates = [
        Path(configured) if configured else Path("__not_configured__"),
        REPOSITORY_ROOT
        / "work"
        / "h2"
        / "toolchain-temp"
        / "llvm-mingw-20240518-ucrt-aarch64"
        / "bin"
        / "llvm-objcopy.exe",
    ]
    located = shutil.which("llvm-objcopy") or shutil.which("llvm-objcopy.exe")
    if located:
        candidates.append(Path(located))
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise SystemExit("cannot find llvm-objcopy; set H2_LLVM_OBJCOPY")


def _run(command: list[str], label: str, attempts: int = 1) -> None:
    completed: subprocess.CompletedProcess[bytes] | None = None
    for _attempt in range(attempts):
        completed = subprocess.run(command, check=False)
        if completed.returncode == 0:
            return
    assert completed is not None
    raise SystemExit(f"{label} failed with exit code {completed.returncode}")


def _compile_sources(
    sources: Sequence[Path],
    entry_va: int,
    defines: Sequence[str] = (),
    debug_elf: Path | None = None,
) -> bytes:
    zig = _find_zig()
    objcopy = _find_objcopy()
    # Keep Zig's output below the already prefix-mapped repository root.  The
    # ARM64 Windows build otherwise crashes after writing an object below the
    # user-profile TEMP directory when that profile is prefix-mapped.
    with tempfile.TemporaryDirectory(
        prefix="h2-mips-", dir=_temporary_root()
    ) as temporary:
        work = Path(temporary)
        linker = work / "h2-mission.ld"
        output_elf = work / "app.elf"
        output_bin = work / "app.bin"
        objects: list[Path] = []
        linker.write_text(
            f"""ENTRY(h1_bda_main)
SECTIONS
{{
  . = 0x{entry_va:08x};
  .text : {{ *(.text.h1_bda_entry) *(.text*) }}
  .rodata : {{ *(.rodata*) }}
  .data : {{ *(.data*) *(.sdata*) *(.bss*) *(COMMON) }}
  .got : {{ *(.got*) }}
  /DISCARD/ : {{ *(.comment*) *(.note*) *(.MIPS.abiflags*) *(.reginfo*) }}
}}
""",
            encoding="ascii",
            newline="\n",
        )
        privacy_flags: list[str] = ["-g0"]
        mapped_roots: list[Path] = []
        for source, target in (
            (REPOSITORY_ROOT, "h2-source"),
            (Path.home(), "user-home"),
            (work, "h2-build"),
        ):
            resolved = source.resolve()
            if any(resolved == root or resolved.is_relative_to(root) for root in mapped_roots):
                continue
            mapped_roots.append(resolved)
            prefix = str(resolved)
            privacy_flags.extend(
                [
                    f"-ffile-prefix-map={prefix}={target}",
                    f"-fmacro-prefix-map={prefix}={target}",
                    f"-fdebug-prefix-map={prefix}={target}",
                ]
            )
        for index, source in enumerate(sources):
            output_object = work / f"{index:03d}-{source.stem}.o"
            _run(
                [
                    str(zig),
                    "cc",
                    "-target",
                    "mipsel-freestanding",
                    "-march=mips32",
                    "-mabi=32",
                    "-mno-abicalls",
                    "-fno-pic",
                    "-G0",
                    # Zig 0.16's ARM64-hosted MIPS backend crashes in one
                    # size-optimization pass at -Os for the H2 input shim.
                    # -Oz produces equivalent freestanding code and a smaller
                    # stage without invoking that faulty pass.
                    "-Oz",
                    "-ffreestanding",
                    "-fno-builtin",
                    "-fno-stack-protector",
                    "-ffunction-sections",
                    "-fdata-sections",
                    *privacy_flags,
                    *[item for value in defines for item in ("-D", value)],
                    "-c",
                    str(source),
                    "-o",
                    str(output_object),
                ],
                f"MIPS compilation of {source.name}",
                attempts=3,
            )
            objects.append(output_object)
        _run(
            [
                str(zig),
                "ld.lld",
                "-m",
                "elf32ltsmip",
                "-T",
                str(linker),
                "--build-id=none",
                "--gc-sections",
                *map(str, objects),
                "-o",
                str(output_elf),
            ],
            "MIPS linking",
        )
        _run(
            [str(objcopy), "-O", "binary", str(output_elf), str(output_bin)],
            "flat binary export",
        )
        if debug_elf is not None:
            debug_elf.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(output_elf, debug_elf)
        return output_bin.read_bytes()


def _verify_mission_payload(mission_payload: Path) -> bytes:
    payload = mission_payload.read_bytes()
    if len(payload) != EMBEDDED_GAME_SIZE or _sha256(payload) != H2_GAME_SHA256:
        raise ValueError("H2-retargeted Mission payload hash mismatch")
    return payload


def _compile_h2_entry(payload_size: int, debug_dir: Path | None) -> bytes:
    stage_source = (
        REPOSITORY_ROOT / "systems" / "H2-2.X" / "mission" / "h2_mission_stage.c"
    )
    entry_template = (
        REPOSITORY_ROOT
        / "systems"
        / "H2-2.X"
        / "mission"
        / "h2_mission_entry_external.S"
    )
    if not stage_source.is_file() or not entry_template.is_file():
        raise FileNotFoundError("H2 Mission runtime source is incomplete")

    if debug_dir is not None:
        debug_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="h2-mission-", dir=_temporary_root()
    ) as temporary:
        work = Path(temporary)
        stage = _compile_sources(
            [stage_source],
            STAGE_VA,
            defines=[f"H1_GAME_SIZE=0x{payload_size:X}u"],
            debug_elf=(debug_dir / "h2-mission-stage.elf") if debug_dir else None,
        )
        if len(stage) & 3:
            stage += bytes((-len(stage)) & 3)
        stage_path = work / "stage.bin"
        stage_path.write_bytes(stage)
        guest_path = work / "mission-path.bin"
        guest_path.write_bytes(EXTERNAL_PATH.encode("ascii") + b"\0")

        entry_source = work / "h2_mission_entry_external.S"
        source = entry_template.read_text(encoding="ascii")
        source = source.replace('"stage.bin"', '"' + stage_path.as_posix() + '"')
        source = source.replace(
            '"mission-path.bin"', '"' + guest_path.as_posix() + '"'
        )
        entry_source.write_text(source, encoding="ascii", newline="\n")
        return _compile_sources(
            [entry_source],
            H2_ENTRY_VA,
            debug_elf=(debug_dir / "h2-mission-entry.elf") if debug_dir else None,
        )


def build_loader(
    mission_payload: Path,
    template_bda: Path,
    output: Path,
    debug_dir: Path | None = None,
) -> None:
    payload = _verify_mission_payload(mission_payload)
    entry = _compile_h2_entry(len(payload), debug_dir)

    template_source = template_bda.read_bytes()
    template = decode_header(template_source)
    resource_offset = int.from_bytes(template[0x18:0x1C], "little")
    payload_offset = int.from_bytes(template[0x14:0x18], "little")
    if resource_offset < 0x88 or payload_offset < resource_offset:
        raise ValueError("H2 template BDA has invalid resource offsets")

    resource_sizes = tuple(
        int.from_bytes(template[offset : offset + 4], "little")
        for offset in (0x1C, 0x20, 0x24, 0x28)
    )
    category = int.from_bytes(template[0x0C:0x10], "little")
    total_size = payload_offset + len(entry)
    padding = (-total_size) & 3
    fields = HeaderFields(
        category=category,
        file_size_minus_4=total_size + padding - 4,
        payload_offset=payload_offset,
        resource_offset=resource_offset,
        resource_sizes=resource_sizes,
        version=int.from_bytes(template[0x08:0x0C], "little"),
    )
    header = encode_header(
        fields,
        title="浣垮懡",
        build_time="2026-08-25 00:00:00",
        description="H2 Mission compat",
    )
    resources = template_source[resource_offset:payload_offset]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(header + resources + entry + bytes(padding))
    report = validate_bda(output)
    non_resource_errors = [
        error for error in report["errors"] if not error.startswith("resource ")
    ]
    if non_resource_errors:
        output.unlink(missing_ok=True)
        raise ValueError("built H2 loader failed validation: " + "; ".join(non_resource_errors))

    print(f"output={output}")
    print(f"size=0x{output.stat().st_size:X}")
    print(f"entry_va=0x{H2_ENTRY_VA:08X}")
    print(f"stage_va=0x{STAGE_VA:08X}")
    print(f"entry_payload=0x{len(entry):X}")
    print(f"mission_payload=0x{len(payload):X}")
    print(f"external_path={EXTERNAL_PATH}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mission-payload", type=Path, required=True)
    parser.add_argument("--template-bda", type=Path, required=True)
    parser.add_argument("--debug-dir", type=Path)
    parser.add_argument("-o", "--output", type=Path, required=True)
    args = parser.parse_args()
    build_loader(
        args.mission_payload,
        args.template_bda,
        args.output,
        args.debug_dir,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
