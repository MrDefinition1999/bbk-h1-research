#!/usr/bin/env python3
"""Unit tests for the compiler-free V1 game wrapper specialization."""

from __future__ import annotations

import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from install_h1_v2_v1_game_suite import (
    GAME_DATA_DIRECTORY,
    OLD_CACHE_SEQUENCE,
    OLD_EXTERNAL_PATH,
    OLD_SIZE_SEQUENCE,
    RESOURCE_ROOT_A,
    RESOURCE_ROOT_B,
    cache_sequence,
    patch_game_resource_drive,
    patch_external_payload,
    size_sequence,
)


class GameSuiteWrapperTests(unittest.TestCase):
    def test_patches_path_size_and_cache_end_once(self) -> None:
        template = b"a" + OLD_EXTERNAL_PATH + b"b" + OLD_SIZE_SEQUENCE + b"c" + OLD_CACHE_SEQUENCE
        patched = patch_external_payload(template, r"A:\CHESS1.BIN", 0x12345)
        self.assertIn(b"A:\\CHESS1.BIN", patched)
        self.assertIn(size_sequence(0x12345), patched)
        self.assertIn(cache_sequence(0x12345), patched)
        self.assertNotIn(OLD_SIZE_SEQUENCE, patched)
        end_words = struct.unpack("<II", cache_sequence(0x12345))
        self.assertEqual(end_words, (0x3C0183C1, 0x34222370))

    def test_rejects_path_of_different_length(self) -> None:
        template = OLD_EXTERNAL_PATH + OLD_SIZE_SEQUENCE + OLD_CACHE_SEQUENCE
        with self.assertRaisesRegex(ValueError, "exactly 13"):
            patch_external_payload(template, r"A:\X.BIN", 1)

    def test_rejects_missing_compiled_sequence(self) -> None:
        with self.assertRaisesRegex(ValueError, "compiled game-size"):
            patch_external_payload(OLD_EXTERNAL_PATH + OLD_CACHE_SEQUENCE, r"A:\CHESS1.BIN", 1)

    def test_rewrites_only_resource_drive_bytes(self) -> None:
        first = RESOURCE_ROOT_A + b"one.lib\0"
        second = RESOURCE_ROOT_A + b"save.bin\0"
        original = b"prefix" + first + b"middle" + second + b"suffix"
        patched, offsets, paths = patch_game_resource_drive(original, 2)
        self.assertEqual(len(patched), len(original))
        self.assertEqual(offsets, [6, 6 + len(first) + 6])
        self.assertNotIn(RESOURCE_ROOT_A, patched)
        self.assertEqual(patched.count(RESOURCE_ROOT_B), 2)
        self.assertEqual(
            paths,
            [
                f"A:\\{GAME_DATA_DIRECTORY}\\one.lib",
                f"A:\\{GAME_DATA_DIRECTORY}\\save.bin",
            ],
        )

    def test_rejects_unexpected_resource_path_count(self) -> None:
        with self.assertRaisesRegex(ValueError, "expected 2"):
            patch_game_resource_drive(RESOURCE_ROOT_A + b"only.lib\0", 2)


if __name__ == "__main__":
    unittest.main()
