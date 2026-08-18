#!/usr/bin/env python3
"""Read H1 runtime service slots from a stopped QEMU guest."""

from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path

from qemu_gdb_break import read_memory
from qemu_gdb_watch import RspClient


PREFIX_ADDRESS = 0x83C00000
TABLE_PREFIX_SLOTS = {
    "GUI": 0x04,
    "FS": 0x08,
    "SYS": 0x0C,
    "MEM": 0x10,
    "RES": 0x14,
}
EXECUTABLE_RANGES = (
    (0x80004000, 0x800C6670, "OS"),
    (0x80600000, 0x80981908, "ExtOs1"),
    (0x809F0000, 0x80B08E90, "ExtOs2"),
)


def read_u32(client: RspClient, address: int) -> int | None:
    raw = read_memory(client, address, 4)
    return struct.unpack("<I", raw)[0] if len(raw) == 4 else None


def classify_pointer(pointer: int | None) -> str:
    if pointer is None:
        return "unreadable"
    if pointer == 0:
        return "null"
    for start, end, name in EXECUTABLE_RANGES:
        if start <= pointer < end:
            return name
    return "other"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("compatibility_json", type=Path)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()

    compatibility = json.loads(args.compatibility_json.read_text(encoding="utf-8"))
    client = RspClient(args.host, args.port)
    try:
        prefix = read_memory(client, PREFIX_ADDRESS, 0x40)
        if len(prefix) != 0x40:
            raise SystemExit("could not read the 64-byte H1 runtime prefix")
        words = list(struct.unpack("<16I", prefix))
        table_bases = {
            table: words[offset // 4] for table, offset in TABLE_PREFIX_SLOTS.items()
        }
        rows = []
        for source in compatibility["rows"]:
            table = str(source["table"])
            offset = int(source["offset"])
            base = table_bases[table]
            pointer = read_u32(client, base + offset)
            rows.append(
                {
                    "table": table,
                    "offset": offset,
                    "offset_hex": f"0x{offset:03X}",
                    "table_base": f"0x{base:08X}",
                    "entry_address": f"0x{base + offset:08X}",
                    "pointer": None if pointer is None else f"0x{pointer:08X}",
                    "classification": classify_pointer(pointer),
                    "v1_calls": int(source["v1_calls"]),
                    "v2_calls": int(source["v2_calls"]),
                }
            )
    finally:
        client.close()

    result = {
        "runtime_prefix_address": f"0x{PREFIX_ADDRESS:08X}",
        "runtime_prefix_words": [f"0x{word:08X}" for word in words],
        "table_bases": {table: f"0x{base:08X}" for table, base in table_bases.items()},
        "mission_slots": len(rows),
        "non_null_slots": sum(row["classification"] not in ("null", "unreadable") for row in rows),
        "executable_slots": sum(
            row["classification"] in {"OS", "ExtOs1", "ExtOs2"} for row in rows
        ),
        "rows": rows,
    }
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(rendered, encoding="utf-8")
    print(
        f"mission_slots={result['mission_slots']} non_null={result['non_null_slots']} "
        f"executable={result['executable_slots']}"
    )
    for row in rows:
        if row["classification"] not in {"OS", "ExtOs1", "ExtOs2"}:
            print(
                f"non_executable {row['table']}+{row['offset_hex']} "
                f"pointer={row['pointer']} classification={row['classification']}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
