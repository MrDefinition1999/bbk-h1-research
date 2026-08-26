#!/usr/bin/env python3
"""Summarize a BBK guest heap from its five-word allocator metadata."""

from __future__ import annotations

import argparse
import json
import struct

from qemu_gdb_break import read_memory
from qemu_gdb_watch import RspClient, read_words


def hex32(value: int) -> str:
    return f"0x{value:08x}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument(
        "--metadata-address",
        type=lambda value: int(value, 0),
        required=True,
        help="address of end,start,record_bottom,count,cursor words",
    )
    parser.add_argument("--continue-after", action="store_true")
    args = parser.parse_args()

    client = RspClient(args.host, args.port)
    try:
        metadata = read_words(client, args.metadata_address, 5)
        if len(metadata) != 5:
            raise RuntimeError("could not read allocator metadata")
        heap_end, heap_start, record_bottom, record_count, cursor = metadata

        if heap_end < heap_start:
            raise RuntimeError("heap end precedes heap start")
        if record_count > 0x100000:
            raise RuntimeError(f"implausible record count: {record_count}")
        expected_bottom = heap_end - record_count * 8
        if record_bottom != expected_bottom:
            raise RuntimeError(
                "record bottom does not match end - count*8: "
                f"{hex32(record_bottom)} != {hex32(expected_bottom)}"
            )
        if not heap_start <= cursor <= record_bottom <= heap_end:
            raise RuntimeError("allocator pointers are outside the heap")

        raw = read_memory(client, record_bottom, record_count * 8)
        if len(raw) != record_count * 8:
            raise RuntimeError("could not read allocator records")

        allocated_sizes: list[int] = []
        free_sizes: list[int] = []
        invalid_records: list[dict[str, str]] = []
        for address, size_flags in struct.iter_unpack("<II", raw):
            size = size_flags & ~1
            if not heap_start <= address <= heap_end or address + size > heap_end:
                invalid_records.append(
                    {
                        "address": hex32(address),
                        "size_flags": hex32(size_flags),
                    }
                )
            (allocated_sizes if size_flags & 1 else free_sizes).append(size)

        tail_bytes = record_bottom - cursor
        summary = {
            "metadata_address": hex32(args.metadata_address),
            "heap_start": hex32(heap_start),
            "heap_end": hex32(heap_end),
            "capacity_bytes": heap_end - heap_start,
            "cursor": hex32(cursor),
            "record_bottom": hex32(record_bottom),
            "record_count": record_count,
            "allocated_count": len(allocated_sizes),
            "allocated_bytes": sum(allocated_sizes),
            "free_record_count": len(free_sizes),
            "free_record_bytes": sum(free_sizes),
            "tail_bytes": tail_bytes,
            "largest_free_record_bytes": max(free_sizes, default=0),
            "largest_immediate_allocation_bytes": max(
                max(free_sizes, default=0), max(0, tail_bytes - 8)
            ),
            "invalid_record_count": len(invalid_records),
        }
        if invalid_records:
            summary["invalid_records"] = invalid_records[:16]
        print(json.dumps(summary, ensure_ascii=True, separators=(",", ":")))

        if args.continue_after:
            client.sock.sendall(client._packet("c"))
            client._wait_for_ack()
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
