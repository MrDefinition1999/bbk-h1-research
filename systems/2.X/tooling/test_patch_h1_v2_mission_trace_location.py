#!/usr/bin/env python3
"""Unit tests for the legacy Mission trace relocation patch."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from patch_h1_v2_mission_trace_location import (
    PATCHES,
    load_sdk_validation,
    patch_trace_location,
)


class MissionTracePatchTests(unittest.TestCase):
    def test_exact_two_sequences_are_relocated(self) -> None:
        prefix = bytes(0x88)
        payload = b"before" + PATCHES[0][0] + b"middle" + PATCHES[1][0] + b"after"
        patched, changes = patch_trace_location(prefix + payload, len(prefix))
        self.assertEqual(len(changes), 2)
        self.assertNotIn(PATCHES[0][0], patched[len(prefix) :])
        self.assertNotIn(PATCHES[1][0], patched[len(prefix) :])
        self.assertIn(PATCHES[0][1], patched[len(prefix) :])
        self.assertIn(PATCHES[1][1], patched[len(prefix) :])

    def test_missing_sequence_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "expected one"):
            patch_trace_location(bytes(0x100), 0x88)

    def test_duplicate_sequence_is_rejected(self) -> None:
        data = bytes(0x88) + PATCHES[0][0] * 2 + PATCHES[1][0]
        with self.assertRaisesRegex(ValueError, "found 2"):
            patch_trace_location(data, 0x88)

    def test_standalone_import_does_not_require_sdk(self) -> None:
        self.assertTrue(callable(load_sdk_validation))


if __name__ == "__main__":
    unittest.main()
