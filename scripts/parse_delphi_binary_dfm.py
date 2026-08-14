#!/usr/bin/env python3
"""Parse a Delphi TPF0 binary form embedded in a file.

The parser is intentionally read-only and bounded.  Large binary properties
are represented by their size and SHA-256 rather than copied into the report.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path


VALUE_NAMES = {
    0: "null",
    1: "list",
    2: "int8",
    3: "int16",
    4: "int32",
    5: "extended",
    6: "string",
    7: "ident",
    8: "false",
    9: "true",
    10: "binary",
    11: "set",
    12: "long_string",
    13: "nil",
    14: "collection",
    15: "single",
    16: "currency",
    17: "date",
    18: "wide_string",
    19: "int64",
    20: "utf8_string",
    21: "unicode_string",
    22: "double",
}


class DfmReader:
    def __init__(self, data: bytes, start: int, limit: int | None = None) -> None:
        self.data = data
        self.start = start
        self.pos = start
        self.limit = len(data) if limit is None else min(len(data), start + limit)

    def require(self, size: int) -> None:
        if size < 0 or self.pos + size > self.limit:
            raise ValueError(f"truncated DFM at file offset 0x{self.pos:x}")

    def take(self, size: int) -> bytes:
        self.require(size)
        result = self.data[self.pos : self.pos + size]
        self.pos += size
        return result

    def u8(self) -> int:
        return self.take(1)[0]

    def i8(self) -> int:
        return struct.unpack("<b", self.take(1))[0]

    def i16(self) -> int:
        return struct.unpack("<h", self.take(2))[0]

    def i32(self) -> int:
        return struct.unpack("<i", self.take(4))[0]

    def u32(self) -> int:
        return struct.unpack("<I", self.take(4))[0]

    def i64(self) -> int:
        return struct.unpack("<q", self.take(8))[0]

    def short_bytes(self) -> bytes:
        return self.take(self.u8())

    @staticmethod
    def decode_ansi(raw: bytes) -> str:
        for encoding in ("gbk", "cp1252"):
            try:
                return raw.decode(encoding)
            except UnicodeDecodeError:
                pass
        return raw.decode("latin1")

    def short_string(self) -> str:
        return self.decode_ansi(self.short_bytes())

    def sized_bytes(self) -> bytes:
        return self.take(self.u32())

    def parse_value(self) -> object:
        offset = self.pos
        kind = self.u8()
        if kind == 0:
            return None
        if kind == 1:
            values = []
            while self.data[self.pos] != 0:
                values.append(self.parse_value())
            self.pos += 1
            return values
        if kind == 2:
            return self.i8()
        if kind == 3:
            return self.i16()
        if kind == 4:
            return self.i32()
        if kind == 5:
            return {"extended_hex": self.take(10).hex()}
        if kind in (6, 7):
            return self.short_string()
        if kind == 8:
            return False
        if kind == 9:
            return True
        if kind == 10:
            raw = self.sized_bytes()
            return {"binary_size": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
        if kind == 11:
            values = []
            while True:
                value = self.short_string()
                if not value:
                    return values
                values.append(value)
        if kind in (12, 20):
            raw = self.sized_bytes()
            encoding = "utf-8" if kind == 20 else "gbk"
            return raw.decode(encoding, "replace")
        if kind == 13:
            return {"ident": "nil"}
        if kind == 14:
            return self.parse_collection()
        if kind == 15:
            return struct.unpack("<f", self.take(4))[0]
        if kind in (16, 17):
            return {VALUE_NAMES[kind] + "_hex": self.take(8).hex()}
        if kind == 18:
            raw = self.take(self.u32() * 2)
            return raw.decode("utf-16le", "replace")
        if kind == 19:
            return self.i64()
        if kind == 21:
            raw = self.take(self.u32() * 2)
            return raw.decode("utf-16le", "replace")
        if kind == 22:
            return struct.unpack("<d", self.take(8))[0]
        raise ValueError(f"unknown DFM value type {kind} at file offset 0x{offset:x}")

    def parse_collection(self) -> list[dict[str, object]]:
        items = []
        while self.data[self.pos] != 0:
            order = None
            if self.data[self.pos] in (2, 3, 4):
                order = self.parse_value()
            marker = self.u8()
            if marker != 1:
                raise ValueError(f"invalid collection item marker {marker} at 0x{self.pos - 1:x}")
            properties = self.parse_properties()
            item: dict[str, object] = {"properties": properties}
            if order is not None:
                item["order"] = order
            items.append(item)
        self.pos += 1
        return items

    def parse_properties(self) -> dict[str, object]:
        properties: dict[str, object] = {}
        while self.data[self.pos] != 0:
            name = self.short_string()
            properties[name] = self.parse_value()
        self.pos += 1
        return properties

    def parse_component(self) -> dict[str, object]:
        offset = self.pos
        prefix = None
        child_position = None
        if self.data[self.pos] & 0xF0 == 0xF0:
            prefix = self.u8()
            # Delphi TFilerFlags: ffInherited=bit 0, ffChildPos=bit 1,
            # ffInline=bit 2.  A child position is encoded as an integer value.
            if prefix & 0x02:
                child_position = self.parse_value()
        class_name = self.short_string()
        name = self.short_string()
        if not class_name:
            raise ValueError(f"empty component class at file offset 0x{offset:x}")
        properties = self.parse_properties()
        children = []
        while self.data[self.pos] != 0:
            children.append(self.parse_component())
        self.pos += 1
        result: dict[str, object] = {
            "file_offset": offset,
            "class": class_name,
            "name": name,
            "properties": properties,
            "children": children,
        }
        if prefix is not None:
            result["prefix"] = prefix
        if child_position is not None:
            result["child_position"] = child_position
        return result

    def parse(self) -> dict[str, object]:
        if self.take(4) != b"TPF0":
            raise ValueError(f"missing TPF0 signature at file offset 0x{self.start:x}")
        root = self.parse_component()
        return {
            "source_offset": self.start,
            "end_offset": self.pos,
            "encoded_size": self.pos - self.start,
            "root": root,
        }


def parse_offset(value: str) -> int:
    return int(value, 0)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--offset", type=parse_offset, required=True)
    parser.add_argument("--limit", type=parse_offset)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()
    report = DfmReader(args.input.read_bytes(), args.offset, args.limit).parse()
    rendered = json.dumps(report, ensure_ascii=True, indent=2) + "\n"
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
