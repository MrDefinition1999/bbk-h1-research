#!/usr/bin/env python3
"""Build a V2-native wrapper for an unmodified H1 V1 game payload."""

from __future__ import annotations

import argparse
import struct
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SDK_ROOT = ROOT / "h1-bda-sdk"
if str(SDK_ROOT) not in sys.path:
    sys.path.insert(0, str(SDK_ROOT))

from h1_bda.build import compile_sources  # noqa: E402
from h1_bda.header import (  # noqa: E402
    HeaderFields,
    MAGIC,
    decode_header,
    encode_header,
    read_c_string,
)
from h1_bda.validate import validate_bda  # noqa: E402


ENTRY_VA = 0x83C00040
STAGE_VA = 0x83F00000
V1_ENTRY_VA = 0x83C00020
COMPATIBILITY_BASE = 0x83E00000
NORMAL_PAYLOAD_OFFSET = 0x785C


def _read_game(game_bda: Path) -> tuple[bytes, bytes, tuple[int, ...]]:
    original = game_bda.read_bytes()
    decoded = decode_header(original)
    words = struct.unpack_from("<11I", decoded)
    if words[0] != MAGIC:
        raise ValueError("input is not an H1 BDA")
    payload_offset = words[5]
    resource_offset = words[6]
    if payload_offset != NORMAL_PAYLOAD_OFFSET:
        raise ValueError(
            f"V1 game payload offset must be 0x{NORMAL_PAYLOAD_OFFSET:X}, "
            f"got 0x{payload_offset:X}"
        )
    if not 0x88 <= resource_offset <= payload_offset <= len(original):
        raise ValueError("invalid H1 BDA resource/payload bounds")
    payload = original[payload_offset:]
    if V1_ENTRY_VA + len(payload) > COMPATIBILITY_BASE:
        raise ValueError("V1 payload overlaps the compatibility-table arena")
    return original, decoded, words


def build_game_loader(
    game_bda: Path,
    output: Path,
    debug_dir: Path | None = None,
    external_path: str | None = None,
    title_override: str | None = None,
) -> None:
    original, decoded, words = _read_game(game_bda)
    payload_offset = words[5]
    resource_offset = words[6]
    payload = original[payload_offset:]

    if external_path is not None and not external_path.upper().startswith("A:\\"):
        raise ValueError("external path must be an H1 guest path below A:\\")

    with tempfile.TemporaryDirectory(prefix="h1-v2-v1-game-") as temporary:
        temp = Path(temporary)
        stage_source = ROOT / "h1-bda-sdk" / "examples" / "v2" / "v1_game_stage.c"
        entry_name = "v1_game_entry_external.S" if external_path else "v1_game_entry.S"
        entry_template = ROOT / "h1-bda-sdk" / "examples" / "v2" / entry_name
        stage_elf = (debug_dir / "v1-game-stage.elf") if debug_dir else None
        stage = compile_sources(
            [stage_source],
            [],
            defines=[f"H1_GAME_SIZE=0x{len(payload):X}u"],
            debug_elf=stage_elf,
            entry_va=STAGE_VA,
        )
        if len(stage) & 3:
            stage += bytes((-len(stage)) & 3)
        stage_path = temp / "stage.bin"
        stage_path.write_bytes(stage)

        entry_source = temp / "v1_game_entry.S"
        source = entry_template.read_text(encoding="ascii").replace(
            '"stage.bin"', '"' + stage_path.as_posix() + '"'
        )
        if external_path:
            guest_path = temp / "game-path.bin"
            guest_path.write_bytes(external_path.encode("gbk") + b"\0")
            source = source.replace(
                '"game-path.bin"', '"' + guest_path.as_posix() + '"'
            )
        else:
            game_payload = temp / "game-payload.bin"
            game_payload.write_bytes(payload)
            source = source.replace(
                '"game-payload.bin"', '"' + game_payload.as_posix() + '"'
            )
        entry_source.write_text(source, encoding="ascii")
        entry_elf = (debug_dir / "v1-game-entry.elf") if debug_dir else None
        entry = compile_sources([entry_source], [], debug_elf=entry_elf, entry_va=ENTRY_VA)

    resource_sizes = tuple(words[7:11])
    title = title_override or read_c_string(decoded[0x2C:0x3C]) or game_bda.stem
    build_time = read_c_string(decoded[0x3C:0x50])
    total_size = payload_offset + len(entry)
    padding = (-total_size) & 3
    fields = HeaderFields(
        category=words[3],
        file_size_minus_4=total_size + padding - 4,
        payload_offset=payload_offset,
        resource_offset=resource_offset,
        resource_sizes=resource_sizes,
        version=words[2],
    )
    header = encode_header(
        fields,
        title=title,
        build_time=build_time,
        description="H1 V2 V1 compat",
    )
    resources = original[resource_offset:payload_offset]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(header + resources + entry + bytes(padding))
    report = validate_bda(output)
    if not report["ok"]:
        output.unlink(missing_ok=True)
        raise ValueError("built loader failed validation: " + "; ".join(report["errors"]))
    print(f"output={output}")
    print(f"size=0x{output.stat().st_size:X}")
    print(f"original_payload=0x{len(payload):X}")
    print(f"payload_mode={'external' if external_path else 'embedded'}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-bda", type=Path, required=True)
    parser.add_argument("-o", "--output", type=Path, required=True)
    parser.add_argument("--debug-dir", type=Path)
    parser.add_argument(
        "--external-path",
        help="H1 guest path containing the raw V1 payload; omits it from the wrapper",
    )
    parser.add_argument(
        "--title",
        dest="title_override",
        help="override the launcher title stored in the wrapper header",
    )
    args = parser.parse_args()
    build_game_loader(
        args.game_bda,
        args.output,
        args.debug_dir,
        args.external_path,
        args.title_override,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
