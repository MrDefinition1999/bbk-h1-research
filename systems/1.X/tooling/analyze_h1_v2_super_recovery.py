#!/usr/bin/env python3
"""Statically inventory the H1 V2 PC recovery PE and its overlay.

The executable is treated as untrusted data.  This script never loads or
executes it; it reports PE section/resource metadata and known container
signatures found in the overlay.
"""

from __future__ import annotations

import argparse
import bz2
import hashlib
import json
import mmap
import struct
from pathlib import Path


SECTION_SIZE = 40
DIRECTORY_NAMES = (
    "export", "import", "resource", "exception", "certificate", "reloc",
    "debug", "architecture", "global_ptr", "tls", "load_config", "bound_import",
    "iat", "delay_import", "com_descriptor", "reserved",
)


def u16(data: mmap.mmap, off: int) -> int:
    return struct.unpack_from("<H", data, off)[0]


def u32(data: mmap.mmap, off: int) -> int:
    return struct.unpack_from("<I", data, off)[0]


def cstr(data: mmap.mmap, off: int, size: int) -> str:
    return bytes(data[off : off + size]).split(b"\0", 1)[0].decode("ascii", "replace")


def rva_to_file(rva: int, sections: list[dict[str, int | str]]) -> int | None:
    for section in sections:
        start = int(section["virtual_address"])
        span = max(int(section["virtual_size"]), int(section["raw_size"]))
        if start <= rva < start + span:
            delta = rva - start
            if delta < int(section["raw_size"]):
                return int(section["raw_pointer"]) + delta
            return None
    return None


def parse_resources(
    data: mmap.mmap,
    resource_rva: int,
    resource_size: int,
    sections: list[dict[str, int | str]],
) -> list[dict[str, object]]:
    root = rva_to_file(resource_rva, sections)
    if root is None:
        return []
    resource_end = root + resource_size
    if resource_end > len(data):
        resource_end = len(data)
    result: list[dict[str, object]] = []

    def name_at(relative: int) -> str | int:
        off = root + relative
        if off + 2 > resource_end:
            return "<invalid>"
        length = u16(data, off)
        raw = bytes(data[off + 2 : off + 2 + length * 2])
        return raw.decode("utf-16le", "replace")

    def walk(relative: int, depth: int, labels: tuple[str | int, ...]) -> None:
        off = root + relative
        if off < root or off + 16 > resource_end or depth > 3:
            return
        # IMAGE_RESOURCE_DIRECTORY: NumberOfNamedEntries/Ids are at +0xC/+0xE.
        named = u16(data, off + 12)
        ids = u16(data, off + 14)
        count = named + ids
        entries = off + 16
        for index in range(count):
            entry = entries + index * 8
            if entry + 8 > resource_end:
                return
            name_field = u32(data, entry)
            id_label: str | int = (
                name_at(name_field & 0x7FFFFFFF)
                if name_field & 0x80000000
                else name_field
            )
            target = u32(data, entry + 4)
            child_labels = labels + (id_label,)
            if target & 0x80000000:
                walk(target & 0x7FFFFFFF, depth + 1, child_labels)
                continue
            data_entry = root + (target & 0x7FFFFFFF)
            if data_entry + 16 > resource_end:
                continue
            payload_rva = u32(data, data_entry)
            payload_size = u32(data, data_entry + 4)
            payload_file = rva_to_file(payload_rva, sections)
            result.append(
                {
                    "path": list(child_labels),
                    "payload_rva": payload_rva,
                    "payload_file_offset": payload_file,
                    "payload_size": payload_size,
                    "codepage": u32(data, data_entry + 8),
                }
            )

    walk(0, 0, ())
    return result


def inventory_bzip_streams(data: mmap.mmap, start: int) -> list[dict[str, object]]:
    """Decode concatenated BZh streams without materializing the full overlay."""
    streams: list[dict[str, object]] = []
    cursor = start
    # Decode the first stream for a stable fingerprint.  Later chunks can be
    # hundreds of megabytes and are left for an explicit extractor command.
    while cursor < len(data) and len(streams) < 1:
        # The super-recovery format prefixes each stream with ``zlb\x1a``.
        # Requiring that framing avoids treating random compressed bytes as a
        # new stream and keeps analysis bounded on a 462 MB overlay.
        marker = cursor + (4 if data[cursor : cursor + 4] == b"zlb\x1a" else 0)
        if data[marker : marker + 3] != b"BZh":
            break
        decoder = bz2.BZ2Decompressor()
        try:
            output_parts: list[bytes] = []
            position = marker
            while position < len(data) and not decoder.eof:
                chunk = data[position : position + 1024 * 1024]
                output_parts.append(decoder.decompress(chunk))
                position += len(chunk)
        except OSError:
            cursor = marker + 3
            continue
        if not decoder.eof:
            break
        end = position - len(decoder.unused_data)
        output = b"".join(output_parts)
        streams.append(
            {
                "compressed_offset": marker,
                "compressed_size": end - marker,
                "output_size": len(output),
                "output_sha256": hashlib.sha256(output).hexdigest(),
                "output_magic": output[:16].hex(),
            }
        )
        cursor = end
    return streams


def inventory(path: Path) -> dict[str, object]:
    with path.open("rb") as handle, mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ) as data:
        if bytes(data[:2]) != b"MZ":
            raise ValueError("missing MZ signature")
        pe_offset = u32(data, 0x3C)
        if bytes(data[pe_offset : pe_offset + 4]) != b"PE\0\0":
            raise ValueError("missing PE signature")
        coff = pe_offset + 4
        machine = u16(data, coff)
        section_count = u16(data, coff + 2)
        optional_size = u16(data, coff + 16)
        optional = coff + 20
        optional_magic = u16(data, optional)
        is_pe32_plus = optional_magic == 0x20B
        image_base = struct.unpack_from("<Q" if is_pe32_plus else "<I", data, optional + (24 if is_pe32_plus else 28))[0]
        entry_rva = u32(data, optional + 16)
        directory_count_offset = optional + (108 if is_pe32_plus else 92)
        directory_count = u32(data, directory_count_offset)
        directory_table = directory_count_offset + 4
        directories: dict[str, dict[str, int]] = {}
        for index, name in enumerate(DIRECTORY_NAMES):
            if index >= directory_count or directory_table + index * 8 + 8 > len(data):
                break
            directories[name] = {
                "rva": u32(data, directory_table + index * 8),
                "size": u32(data, directory_table + index * 8 + 4),
            }

        section_table = optional + optional_size
        sections: list[dict[str, int | str]] = []
        overlay_start = section_table + section_count * SECTION_SIZE
        for index in range(section_count):
            off = section_table + index * SECTION_SIZE
            raw_pointer = u32(data, off + 20)
            raw_size = u32(data, off + 16)
            sections.append(
                {
                    "index": index,
                    "name": cstr(data, off, 8),
                    "virtual_size": u32(data, off + 8),
                    "virtual_address": u32(data, off + 12),
                    "raw_size": raw_size,
                    "raw_pointer": raw_pointer,
                    "characteristics": u32(data, off + 36),
                }
            )
            overlay_start = max(overlay_start, raw_pointer + raw_size)

        signatures = (
            ("UPD bbk", b"bbk."),
            ("DLX", b"DLX"),
            ("bzip2", b"BZh"),
            ("RAR", b"Rar!"),
            ("7z", b"7z\xBC\xAF\x27\x1C"),
            ("ZIP", b"PK\x03\x04"),
            ("bda", b"BBK\0"),
        )
        signature_hits: list[dict[str, object]] = []
        for label, marker in signatures:
            cursor = overlay_start
            while True:
                found = data.find(marker, cursor)
                if found < 0:
                    break
                signature_hits.append({"name": label, "offset": found})
                cursor = found + 1
                if len(signature_hits) >= 5000:
                    break

        resource = directories.get("resource", {"rva": 0, "size": 0})
        return {
            "path": path.name,
            "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "pe_offset": pe_offset,
            "machine": f"0x{machine:04x}",
            "section_count": section_count,
            "optional_magic": f"0x{optional_magic:04x}",
            "image_base": f"0x{image_base:x}",
            "entry_rva": f"0x{entry_rva:x}",
            "directories": directories,
            "sections": sections,
            "overlay_start": overlay_start,
            "overlay_size": max(0, len(data) - overlay_start),
            "overlay_signatures": signature_hits,
            "overlay_bzip_streams": inventory_bzip_streams(data, overlay_start),
            "resources": parse_resources(data, resource["rva"], resource["size"], sections),
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--json", type=Path, help="write JSON report")
    args = parser.parse_args()
    report = inventory(args.input)
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
