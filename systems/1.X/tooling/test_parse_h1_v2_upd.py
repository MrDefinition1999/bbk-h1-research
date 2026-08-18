#!/usr/bin/env python3
"""Focused regression tests for the V2 UPD table parser."""

from __future__ import annotations

import mmap
import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from parse_h1_v2_upd import (
    RECORD_SIZE,
    locate_table,
    parse_entries,
    safe_relative_path,
)


class V2UpdParserTests(unittest.TestCase):
    def test_locates_unaligned_table_and_decodes_gbk(self) -> None:
        table = 0x708
        image = bytearray(0x708 + RECORD_SIZE * 2 + 0x100)
        records = [
            ("A:\\应用\\数据\\player.bin", 7, 0x900),
            ("A:\\系统\\数据\\shell\\touchpanel.dlx", 11, 0x910),
        ]
        for index, (path, size, payload) in enumerate(records):
            offset = table + index * RECORD_SIZE
            encoded = path.encode("gbk") + b"\0"
            image[offset + 0xF8 : offset + 0xFC] = struct.pack("<I", size)
            image[offset + 0xFC : offset + 0x100] = struct.pack("<I", payload)
            image[offset + 0x100 : offset + 0x100 + len(encoded)] = encoded
        with tempfile.TemporaryDirectory() as directory:
            image_path = Path(directory) / "synthetic.upd"
            image_path.write_bytes(image)
            with image_path.open("rb") as handle, mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ) as mapped:
                self.assertEqual(locate_table(mapped), table)
                entries = parse_entries(mapped, table)
        self.assertEqual([entry.path for entry in entries], [item[0] for item in records])
        self.assertEqual([entry.size for entry in entries], [7, 11])

    def test_rejects_traversal(self) -> None:
        with self.assertRaises(ValueError):
            safe_relative_path("A:\\应用\\数据\\..\\outside.bin")

    def test_real_v2_image_shape_when_present(self) -> None:
        image = next(
            Path("references/official/h1-v2").rglob("*.upd"),
            None,
        )
        if image is None:
            self.skipTest("official V2 UPD is not present")
        with image.open("rb") as handle, mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ) as mapped:
            table = locate_table(mapped)
            entries = parse_entries(mapped, table)
            self.assertEqual(table, 1800)
            self.assertEqual(len(entries), 307)
            self.assertEqual(entries[17].size, 1513956)
            self.assertEqual(entries[17].payload_offset, 0x872E2E)


if __name__ == "__main__":
    unittest.main()
