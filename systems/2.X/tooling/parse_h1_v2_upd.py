#!/usr/bin/env python3
"""Inspect and selectively extract the indexed files in an H1 V2 UPD image.

The V2 recovery image is an indexed container rather than a filesystem image.
Records are 0x100 bytes wide.  A record stores the file size and absolute
payload offset at path-8 and path-4, respectively; the GBK path itself starts
at record+0x100.  The parser deliberately does not extract the unindexed tail.
"""

from __future__ import annotations

import argparse
import json
import mmap
import posixpath
import struct
from dataclasses import asdict, dataclass
from pathlib import Path


RECORD_SIZE = 0x100
PATH_OFFSET = RECORD_SIZE
PATH_FIELD_SIZE = 0x100
MAX_PATH_BYTES = 0x100
DEFAULT_SCAN_LIMIT = 64 * 1024


@dataclass(frozen=True)
class Entry:
    index: int
    table_offset: int
    path: str
    size: int
    payload_offset: int


def decode_path(raw: bytes) -> str:
    value = raw.split(b"\0", 1)[0]
    # The official V2 image uses mainland GBK for the table, not UTF-8.
    return value.decode("gbk", errors="replace")


def looks_like_path(raw: bytes) -> bool:
    value = raw.split(b"\0", 1)[0]
    return value.startswith(b"A:\\") and len(value) > 3 and b"\0" in raw


def locate_table(stream: mmap.mmap) -> int:
    # The first record is aligned to a 0x100-byte boundary in the header area.
    # Search only the small metadata prefix so a payload string cannot win.
    for path in range(0, min(len(stream), DEFAULT_SCAN_LIMIT), 4):
        if not looks_like_path(stream[path : path + PATH_FIELD_SIZE]):
            continue
        candidate = path - PATH_OFFSET
        if candidate < 0:
            continue
        size = struct.unpack_from("<I", stream, candidate + 0xF8)[0]
        payload = struct.unpack_from("<I", stream, candidate + 0xFC)[0]
        if size <= len(stream) and payload <= len(stream) and payload + size <= len(stream):
            return candidate
    raise ValueError("could not locate an aligned V2 UPD table")


def parse_entries(stream: mmap.mmap, table_offset: int) -> list[Entry]:
    entries: list[Entry] = []
    offset = table_offset
    while offset + RECORD_SIZE + PATH_FIELD_SIZE <= len(stream):
        path_raw = stream[offset + PATH_OFFSET : offset + PATH_OFFSET + PATH_FIELD_SIZE]
        if not looks_like_path(path_raw):
            break
        size = struct.unpack_from("<I", stream, offset + 0xF8)[0]
        payload = struct.unpack_from("<I", stream, offset + 0xFC)[0]
        if payload > len(stream) or size > len(stream) - payload:
            raise ValueError(
                f"invalid entry {len(entries)} at 0x{offset:X}: "
                f"offset=0x{payload:X} size=0x{size:X}"
            )
        entries.append(
            Entry(
                index=len(entries),
                table_offset=offset,
                path=decode_path(path_raw),
                size=size,
                payload_offset=payload,
            )
        )
        offset += RECORD_SIZE
    if not entries:
        raise ValueError("UPD table contains no valid entries")
    return entries


def open_image(path: Path):
    handle = path.open("rb")
    image = mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ)
    return handle, image


def safe_relative_path(path: str) -> Path:
    # Convert the firmware's A:\ prefix into a relative host path and reject
    # traversal.  This also prevents an accidental extraction outside --out.
    normalized = path.replace("/", "\\")
    if not normalized.startswith("A:\\"):
        raise ValueError(f"unsupported UPD path: {path!r}")
    relative = normalized[3:].replace("\\", "/")
    if not relative or relative.startswith("/"):
        raise ValueError(f"empty/absolute UPD path: {path!r}")
    parts = [part for part in relative.split("/") if part not in ("", ".")]
    if any(part == ".." for part in parts):
        raise ValueError(f"traversal in UPD path: {path!r}")
    return Path(*parts)


def find_entries(entries: list[Entry], selectors: list[str]) -> list[Entry]:
    if not selectors:
        return entries
    lowered = [selector.lower().replace("/", "\\") for selector in selectors]
    selected: list[Entry] = []
    for entry in entries:
        candidate = entry.path.lower()
        if any(selector in candidate for selector in lowered):
            selected.append(entry)
    return selected


def command_list(args: argparse.Namespace) -> int:
    handle, image = open_image(args.image)
    try:
        table = locate_table(image)
        entries = parse_entries(image, table)
        selected = find_entries(entries, args.selector)
        result = {
            "image_size": len(image),
            "table_offset": table,
            "entry_count": len(entries),
            "indexed_end": max(entry.payload_offset + entry.size for entry in entries),
            "unindexed_tail": len(image) - max(entry.payload_offset + entry.size for entry in entries),
            "entries": [asdict(entry) for entry in selected],
        }
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"image_size={result['image_size']}")
            print(f"table_offset=0x{table:X} entry_count={len(entries)}")
            print(f"indexed_end=0x{result['indexed_end']:X} unindexed_tail={result['unindexed_tail']}")
            for entry in selected:
                print(
                    f"{entry.index:03d} size={entry.size:10d} "
                    f"payload=0x{entry.payload_offset:08X} {entry.path}"
                )
    finally:
        image.close()
        handle.close()
    return 0


def command_extract(args: argparse.Namespace) -> int:
    handle, image = open_image(args.image)
    try:
        table = locate_table(image)
        entries = find_entries(parse_entries(image, table), args.selector)
        if not entries:
            raise SystemExit("no UPD entries matched the selector")
        output = args.out.resolve()
        output.mkdir(parents=True, exist_ok=True)
        for entry in entries:
            relative = safe_relative_path(entry.path)
            destination = (output / relative).resolve()
            if output not in destination.parents:
                raise ValueError(f"refusing extraction outside output: {entry.path!r}")
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open("wb") as target:
                target.write(image[entry.payload_offset : entry.payload_offset + entry.size])
            print(f"extracted {entry.path} ({entry.size} bytes)")
    finally:
        image.close()
        handle.close()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path, help="official V2 .upd image")
    sub = parser.add_subparsers(dest="command", required=True)
    listing = sub.add_parser("list", help="print the indexed table")
    listing.add_argument("selector", nargs="*", help="case-insensitive path substrings")
    listing.add_argument("--json", action="store_true")
    listing.set_defaults(handler=command_list)
    extracting = sub.add_parser("extract", help="extract selected indexed files")
    extracting.add_argument("--out", required=True, type=Path)
    extracting.add_argument("selector", nargs="*", help="case-insensitive path substrings")
    extracting.set_defaults(handler=command_extract)
    args = parser.parse_args()
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
