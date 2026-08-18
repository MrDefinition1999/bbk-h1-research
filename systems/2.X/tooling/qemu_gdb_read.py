#!/usr/bin/env python3
"""Read registers and memory from an already stopped local QEMU guest."""

from __future__ import annotations

import argparse
import json

from qemu_gdb_break import REGISTERS, parse_memory_range, read_memory
from qemu_gdb_watch import RspClient, read_register


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument(
        "--memory",
        type=parse_memory_range,
        action="append",
        default=[],
        help="read ADDRESS:SIZE bytes; repeat as needed",
    )
    parser.add_argument("--continue-after", action="store_true")
    args = parser.parse_args()

    client = RspClient(args.host, args.port)
    try:
        values = {name: read_register(client, number) for name, number in REGISTERS.items()}
        print(
            "registers="
            + " ".join(
                f"{name}=" + ("unknown" if value is None else f"0x{value:08x}")
                for name, value in values.items()
            )
        )
        for address, size in args.memory:
            raw = read_memory(client, address, size)
            print(
                "memory="
                + json.dumps(
                    {
                        "address": f"0x{address:08x}",
                        "requested_size": size,
                        "read_size": len(raw),
                        "raw_hex": raw.hex().upper(),
                    },
                    separators=(",", ":"),
                )
            )
        if args.continue_after:
            client.sock.sendall(client._packet("c"))
            client._wait_for_ack()
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
