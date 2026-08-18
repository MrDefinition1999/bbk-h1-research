#!/usr/bin/env python3
"""Capture a local QEMU MIPS breakpoint with registers and stack words."""

from __future__ import annotations

import argparse
import json

from qemu_gdb_watch import RspClient, read_register, read_words


REGISTERS = {
    "v0": 2,
    "v1": 3,
    "a0": 4,
    "a1": 5,
    "a2": 6,
    "a3": 7,
    "s0": 16,
    "s1": 17,
    "s2": 18,
    "s3": 19,
    "s4": 20,
    "s5": 21,
    "s6": 22,
    "s7": 23,
    "gp": 28,
    "sp": 29,
    "fp": 30,
    "ra": 31,
    "pc": 37,
}


def read_memory(client: RspClient, address: int, size: int) -> bytes:
    payload = client.command(f"m{address:x},{size:x}")
    try:
        raw = bytes.fromhex(payload)
    except ValueError:
        return b""
    return raw if len(raw) == size else b""


def read_c_string(client: RspClient, address: int, limit: int) -> bytes:
    raw = read_memory(client, address, limit)
    return raw.split(b"\0", 1)[0]


def parse_memory_range(value: str) -> tuple[int, int]:
    try:
        address_text, size_text = value.split(":", 1)
        address = int(address_text, 0)
        size = int(size_text, 0)
    except (TypeError, ValueError) as error:
        raise argparse.ArgumentTypeError("memory range must be ADDRESS:SIZE") from error
    if not 0 <= address <= 0xFFFFFFFF:
        raise argparse.ArgumentTypeError("memory address must fit in 32 bits")
    if size <= 0 or size > 0x10000:
        raise argparse.ArgumentTypeError("memory size must be between 1 and 65536")
    return address, size


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument(
        "--address",
        type=lambda value: int(value, 0),
        action="append",
        required=True,
        help="breakpoint address; repeat to stop at the first of several addresses",
    )
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--stack-words", type=int, default=64)
    parser.add_argument(
        "--string-register",
        action="append",
        choices=tuple(REGISTERS),
        default=[],
        help="decode a bounded NUL-terminated string from this register",
    )
    parser.add_argument("--string-bytes", type=int, default=256)
    parser.add_argument(
        "--memory",
        type=parse_memory_range,
        action="append",
        default=[],
        help="read ADDRESS:SIZE bytes at the breakpoint; repeat as needed",
    )
    parser.add_argument("--continue-after", action="store_true")
    args = parser.parse_args()

    client = RspClient(args.host, args.port)
    breakpoints: list[tuple[int, str]] = []
    try:
        supported = client.command("qSupported:multiprocess+;swbreak+;hwbreak+")
        for address in args.address:
            breakpoint_kind = "Z0"
            result = client.command(f"{breakpoint_kind},{address:x},4")
            if result != "OK":
                breakpoint_kind = "Z1"
                result = client.command(f"{breakpoint_kind},{address:x},4")
            if result != "OK":
                raise SystemExit(
                    f"QEMU rejected breakpoint at 0x{address:08x}: {result}"
                )
            breakpoints.append((address, breakpoint_kind))
        print(
            "breakpoints="
            + ",".join(
                f"0x{address:08x}:{kind}" for address, kind in breakpoints
            )
            + " "
            f"supported={supported}",
            flush=True,
        )
        stop, interrupted = client.resume_until_stop("c", args.timeout)
        removed = []
        for address, breakpoint_kind in breakpoints:
            remove_kind = "z" + breakpoint_kind[1:]
            removed.append(
                (address, client.command(f"{remove_kind},{address:x},4"))
            )
        values = {name: read_register(client, number) for name, number in REGISTERS.items()}
        print(
            f"stop={stop} interrupted={interrupted} removed="
            + ",".join(f"0x{address:08x}:{result}" for address, result in removed)
        )
        print(
            "registers="
            + " ".join(
                f"{name}=" + ("unknown" if value is None else f"0x{value:08x}")
                for name, value in values.items()
            )
        )
        sp = values["sp"]
        if sp is not None and args.stack_words:
            words = read_words(client, sp, args.stack_words)
            print("stack=" + " ".join(f"{word:08x}" for word in words))
        for name in args.string_register:
            address = values[name]
            if address is None:
                print(f"string[{name}]=unknown")
                continue
            raw = read_c_string(client, address, max(1, args.string_bytes))
            decoded = {
                "register": name,
                "address": f"0x{address:08x}",
                "raw_hex": raw.hex().upper(),
                "ascii": raw.decode("ascii", errors="replace"),
                "gbk": raw.decode("gbk", errors="replace"),
            }
            print("string=" + json.dumps(decoded, ensure_ascii=True))
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
