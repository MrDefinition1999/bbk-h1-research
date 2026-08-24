#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import struct
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("build_h1_v1_flying_video_compat.py")
SPEC = importlib.util.spec_from_file_location("flying_video_compat", SCRIPT)
assert SPEC and SPEC.loader
compat = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(compat)


class FlyingVideoCompatTests(unittest.TestCase):
    def test_jump_encoding(self) -> None:
        self.assertEqual(compat.encode_j(0x83F41000), 0x08FD0400)

    def test_entry_initializer_installs_all_tables(self) -> None:
        code = compat.make_init_code()
        values = struct.unpack(f"<{len(code) // 4}I", code)
        self.assertEqual(values[0], compat.encode_i(0x0F, 0, 8, 0x83C0))
        self.assertEqual(values[-2], compat.encode_j(compat.V2_ENTRY))
        self.assertEqual(values[-1], 0)
        for offset in (0x04, 0x0C, 0x18, 0x30):
            self.assertIn(compat.encode_i(0x2B, 8, 9, offset), values)

    def test_framebuffer_getter_reads_lcd_descriptor(self) -> None:
        code = compat.make_framebuffer_getter()
        values = struct.unpack(f"<{len(code) // 4}I", code)
        self.assertEqual(values[0], compat.encode_i(0x0F, 0, 2, 0xB305))
        self.assertIn(compat.encode_i(0x23, 2, 2, 0x0040), values)
        self.assertIn(compat.encode_i(0x23, 2, 2, 0x0004), values)
        self.assertEqual(values.count(0x00431025), 2)

    def test_fixed_string_patch_is_size_preserving(self) -> None:
        original = bytearray("A:\\应用\\数据\\player.cfg".encode("gbk") + b"tail")
        size = len(original)
        compat.replace_fixed_string(
            original,
            "A:\\应用\\数据\\player.cfg",
            "A:\\应用\\数据\\play2.cfg",
            1,
        )
        self.assertEqual(len(original), size)
        self.assertTrue(original.startswith("A:\\应用\\数据\\play2.cfg".encode("gbk") + b"\0"))


if __name__ == "__main__":
    unittest.main()
