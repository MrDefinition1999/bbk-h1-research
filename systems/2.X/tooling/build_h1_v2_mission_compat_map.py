#!/usr/bin/env python3
"""Build the explicit V1 Mission to H1 V2 service compatibility map."""

from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path


V1_GUI_TABLE = 0x802AA110
V2_TABLES = {
    "GUI": (0x80790BA0, 0x80600000, "v2-decoded-12.bin"),
    "FS": (0x800A50A0, 0x80004000, "v2-decoded-11.bin"),
    "SYS": (0x800A4FD0, 0x80004000, "v2-decoded-11.bin"),
    "RES": (0x80AE55C0, 0x809F0000, "v2-decoded-13.bin"),
}

V1_RES094_ADDRESS = 0x80004C88
V1_RES094_WORDS = (
    0x00001021,  # move v0, zero
    0xAFA50004,  # sw a1, 4(sp)
    0xAFA60008,  # sw a2, 8(sp)
    0x03E00008,  # jr ra
    0xAFA7000C,  # sw a3, 0xc(sp)
)


def read_u32(data: bytes, offset: int) -> int:
    if offset < 0 or offset + 4 > len(data):
        raise ValueError(f"read outside image at offset 0x{offset:X}")
    return struct.unpack_from("<I", data, offset)[0]


def map_gui_offset(offset: int) -> tuple[str, int | None, str, str]:
    if offset == 0x2B8:
        return "forward", 0x2B0, "function_fingerprint", "confirmed"
    if offset == 0x6A8:
        return "shim_game_mode_allow", None, "v1_game_mode_gate_removed", "confirmed"
    if offset == 0x6E0:
        return "forward", 0x9E4, "function_semantics_and_call_signature", "confirmed"
    if offset == 0x84C:
        return "shim_state_bridge", 0x738, "v1_v2_gui_init_return_contract", "confirmed"
    if 0x850 <= offset <= 0x9F4:
        return "forward", offset - 0x114, "table_rebase_and_fingerprint", "confirmed"
    if offset in (0xAA4, 0xAA8):
        return "shim_allow_without_charge", None, "v1_coin_service_removed", "confirmed_policy"
    if offset == 0xAD8:
        return "forward", 0x95C, "function_fingerprint", "confirmed"
    if offset == 0xADC:
        return "forward", 0x960, "function_fingerprint", "confirmed"
    raise ValueError(f"unmapped GUI offset 0x{offset:03X}")


def build_map(
    compatibility: dict[str, object],
    project: bytes,
    v2_images: dict[str, bytes],
) -> dict[str, object]:
    v1_words = tuple(
        read_u32(project, V1_RES094_ADDRESS - 0x80004000 + index * 4)
        for index in range(len(V1_RES094_WORDS))
    )
    if v1_words != V1_RES094_WORDS:
        rendered = ", ".join(f"0x{word:08X}" for word in v1_words)
        raise ValueError(f"unexpected V1 RES+0x094 implementation: {rendered}")

    output_rows = []
    for source in compatibility["rows"]:
        table = str(source["table"])
        offset = int(source["offset"])
        if table == "GUI":
            action, target, evidence, confidence = map_gui_offset(offset)
        elif table == "RES" and offset == 0x094:
            action = "shim_return_zero"
            target = None
            evidence = "v1_five_instruction_noop"
            confidence = "confirmed"
        elif table == "FS" and offset == 0x048:
            action = "shim_storage_geometry"
            target = None
            evidence = "v1_storage_geometry_abi_and_v2_slot_invalid"
            confidence = "confirmed"
        elif table == "SYS":
            action = "forward"
            target = offset
            evidence = "same_slot_native_v2_calls_and_fingerprint"
            confidence = "confirmed"
        else:
            raise ValueError(f"unmapped service {table}+0x{offset:03X}")

        pointer = None
        if target is not None:
            table_base, image_base, image_name = V2_TABLES[table]
            pointer = read_u32(
                v2_images[image_name], table_base - image_base + target
            )
            if not 0x80000000 <= pointer < 0x84000000:
                raise ValueError(
                    f"mapped pointer is not executable SDRAM: "
                    f"{table}+0x{offset:03X} -> 0x{pointer:08X}"
                )

        output_rows.append(
            {
                "table": table,
                "v1_offset": offset,
                "v1_offset_hex": f"0x{offset:03X}",
                "v1_calls": int(source["v1_calls"]),
                "action": action,
                "v2_offset": target,
                "v2_offset_hex": None if target is None else f"0x{target:03X}",
                "v2_pointer": None if pointer is None else f"0x{pointer:08X}",
                "evidence": evidence,
                "confidence": confidence,
            }
        )

    if len(output_rows) != 70:
        raise ValueError(f"expected 70 Mission slots, got {len(output_rows)}")
    identities = {(row["table"], row["v1_offset"]) for row in output_rows}
    if len(identities) != len(output_rows):
        raise ValueError("duplicate Mission service mapping")

    return {
        "format": "h1-v2-mission-compat-map-v1",
        "mission_slots": len(output_rows),
        "v1_entry": "0x83C00020",
        "v2_loader_entry": "0x83C00040",
        "gui_table_strategy": "compatibility_copy",
        "res_0x094": {
            "v1_pointer": "0x80004C88",
            "semantics": "return_zero_without_side_effects",
            "mission_call_count": 6,
        },
        "rows": output_rows,
    }


def render_markdown(report: dict[str, object]) -> str:
    rows = report["rows"]
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["action"]] = counts.get(row["action"], 0) + 1
    lines = [
        "# H1 V2 Mission compatibility map",
        "",
        f"- Mission service slots: {report['mission_slots']}",
        f"- V1 entry: `{report['v1_entry']}`",
        f"- V2 loader entry: `{report['v2_loader_entry']}`",
        f"- direct V2 forwards: {counts.get('forward', 0)}",
        f"- confirmed return-zero shims: {counts.get('shim_return_zero', 0)}",
        f"- storage-geometry shims: {counts.get('shim_storage_geometry', 0)}",
        f"- game-mode compatibility shims: {counts.get('shim_game_mode_allow', 0)}",
        f"- GUI state-bridge shims: {counts.get('shim_state_bridge', 0)}",
        f"- no-charge policy shims: {counts.get('shim_allow_without_charge', 0)}",
        "",
        "`RES+0x094` is not forwarded. Its V1 implementation is a five-instruction",
        "leaf that returns zero; the V2 same-offset function has unrelated resource",
        "initialization behavior.",
        "",
        "| V1 service | Calls | Action | V2 target | Confidence | Evidence |",
        "| --- | ---: | --- | --- | --- | --- |",
    ]
    for row in rows:
        target = row["v2_offset_hex"] or "local shim"
        lines.append(
            f"| `{row['table']}+{row['v1_offset_hex']}` | {row['v1_calls']} | "
            f"`{row['action']}` | `{target}` | {row['confidence']} | "
            f"{row['evidence']} |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("compatibility_json", type=Path)
    parser.add_argument("--v1-project", type=Path, required=True)
    parser.add_argument("--v2-os", type=Path, required=True)
    parser.add_argument("--v2-extos1", type=Path, required=True)
    parser.add_argument("--v2-extos2", type=Path, required=True)
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--markdown", type=Path, required=True)
    args = parser.parse_args()

    compatibility = json.loads(args.compatibility_json.read_text(encoding="utf-8"))
    report = build_map(
        compatibility,
        args.v1_project.read_bytes(),
        {
            "v2-decoded-11.bin": args.v2_os.read_bytes(),
            "v2-decoded-12.bin": args.v2_extos1.read_bytes(),
            "v2-decoded-13.bin": args.v2_extos2.read_bytes(),
        },
    )
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.markdown.parent.mkdir(parents=True, exist_ok=True)
    args.markdown.write_text(render_markdown(report), encoding="utf-8", newline="\n")
    print(f"mapped={report['mission_slots']}")
    print(f"json={args.json}")
    print(f"markdown={args.markdown}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
