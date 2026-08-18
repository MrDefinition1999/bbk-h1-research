#!/usr/bin/env python3
"""Build the two-stage V2 loader that runs the original V1 Mission payload."""

from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

from h1_bda.build import compile_sources
from h1_bda.header import HeaderFields, decode_header, encode_header, read_c_string
from h1_bda.validate import validate_bda


ROOT = Path(__file__).resolve().parents[1]
ENTRY_VA = 0x83C00040
STAGE_VA = 0x83F00000
PAYLOAD_OFFSET = 0x785C


def build_loader(
    mission_bda: Path,
    mission_payload: Path,
    output: Path,
    debug_dir: Path | None,
    external_path: str | None,
    category_override: int | None = None,
    title_override: str | None = None,
    description: str = "H1 V2 Mission V2",
    template_bda: Path | None = None,
) -> None:
    original = mission_bda.read_bytes()
    decoded = decode_header(original)
    payload = mission_payload.read_bytes()
    original_payload_offset = int.from_bytes(decoded[0x14:0x18], "little")
    original_payload = original[original_payload_offset:]
    if original_payload != payload:
        raise ValueError("mission payload does not match mission-original.bda")
    if original_payload_offset != PAYLOAD_OFFSET:
        raise ValueError(f"unexpected Mission payload offset 0x{original_payload_offset:X}")

    with tempfile.TemporaryDirectory(prefix="h1-v2-mission-") as temporary:
        temp = Path(temporary)
        stage_source = ROOT / "h1-bda-sdk" / "examples" / "v2" / "mission_stage.c"
        template_name = "mission_entry_external.S" if external_path else "mission_entry.S"
        entry_template = ROOT / "h1-bda-sdk" / "examples" / "v2" / template_name
        stage_elf = (debug_dir / "mission-stage.elf") if debug_dir else None
        stage = compile_sources([stage_source], [], debug_elf=stage_elf, entry_va=STAGE_VA)
        if len(stage) & 3:
            stage += bytes((-len(stage)) & 3)
        stage_path = temp / "stage.bin"
        stage_path.write_bytes(stage)
        entry_source = temp / "mission_entry.S"
        source = entry_template.read_text(encoding="ascii").replace(
            '"stage.bin"', '"' + stage_path.as_posix() + '"'
        )
        if external_path:
            path_file = temp / "mission-path.bin"
            path_file.write_bytes(external_path.encode("gbk") + b"\0")
            source = source.replace(
                '"mission-path.bin"', '"' + path_file.as_posix() + '"'
            )
        else:
            mission_path = temp / "mission-payload.bin"
            mission_path.write_bytes(payload)
            source = source.replace(
                '"mission-payload.bin"', '"' + mission_path.as_posix() + '"'
            )
        entry_source.write_text(source, encoding="ascii")
        entry_elf = (debug_dir / "mission-entry.elf") if debug_dir else None
        entry = compile_sources([entry_source], [], debug_elf=entry_elf, entry_va=ENTRY_VA)

    template = decode_header(template_bda.read_bytes()) if template_bda else decoded
    resource_offset = int.from_bytes(template[0x18:0x1C], "little")
    payload_offset = int.from_bytes(template[0x14:0x18], "little")
    resource_sizes = tuple(
        int.from_bytes(template[offset : offset + 4], "little")
        for offset in (0x1C, 0x20, 0x24, 0x28)
    )
    category = (
        int.from_bytes(template[0x0C:0x10], "little")
        if category_override is None
        else category_override
    )
    title = title_override or read_c_string(template[0x2C:0x3C]) or "Mission V2"
    template_source = template_bda.read_bytes() if template_bda else original
    if resource_offset < 0x88 or payload_offset < resource_offset:
        raise ValueError("template BDA has invalid resource/payload offsets")
    total_size = payload_offset + len(entry)
    padding = (-total_size) & 3
    fields = HeaderFields(
        category=category,
        file_size_minus_4=total_size + padding - 4,
        payload_offset=payload_offset,
        resource_offset=resource_offset,
        resource_sizes=resource_sizes,
    )
    header = encode_header(
        fields,
        title=title,
        build_time="2026-08-05 00:00:00",
        description=description,
    )
    resources = template_source[resource_offset:payload_offset]
    if len(resources) != payload_offset - resource_offset:
        raise ValueError("template BDA does not contain its complete resource area")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(header + resources + entry + bytes(padding))
    report = validate_bda(output)
    template_resource_only_errors = bool(template_bda) and report["errors"] and all(
        error.startswith("resource ") for error in report["errors"]
    )
    if not report["ok"] and not template_resource_only_errors:
        output.unlink(missing_ok=True)
        raise ValueError("built loader failed validation: " + "; ".join(report["errors"]))
    print(f"output={output}")
    print(f"size=0x{output.stat().st_size:X}")
    print(f"entry_payload=0x{len(entry):X}")
    print(f"mission_payload=0x{len(payload):X}")
    print(f"payload_mode={'external' if external_path else 'embedded'}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mission-bda", type=Path, required=True)
    parser.add_argument("--mission-payload", type=Path, required=True)
    parser.add_argument("-o", "--output", type=Path, required=True)
    parser.add_argument("--debug-dir", type=Path)
    parser.add_argument(
        "--external-path",
        help="guest path containing the raw Mission payload; omits it from the BDA",
    )
    parser.add_argument("--category", type=lambda value: int(value, 0))
    parser.add_argument("--title")
    parser.add_argument("--description", default="H1 V2 Mission V2")
    parser.add_argument(
        "--template-bda",
        type=Path,
        help="V2 BDA whose resources, category and payload offset are reused",
    )
    args = parser.parse_args()
    build_loader(
        args.mission_bda,
        args.mission_payload,
        args.output,
        args.debug_dir,
        args.external_path,
        args.category,
        args.title,
        args.description,
        args.template_bda,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
