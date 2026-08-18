from __future__ import annotations

import unittest

from patch_h1_v2_mission_resource_drive import (
    MISSION_DATA_ROOT_A,
    MISSION_DATA_ROOT_B,
    patch_payload,
)


class MissionResourceDriveTests(unittest.TestCase):
    def test_rewrites_only_drive_bytes(self) -> None:
        original = b"prefix" + MISSION_DATA_ROOT_A + b"one\0middle" + MISSION_DATA_ROOT_A + b"two\0"
        patched, offsets = patch_payload(original, 2)
        self.assertEqual(patched.count(MISSION_DATA_ROOT_B), 2)
        self.assertNotIn(MISSION_DATA_ROOT_A, patched)
        changed = [index for index, pair in enumerate(zip(original, patched)) if pair[0] != pair[1]]
        self.assertEqual(changed, offsets)

    def test_rejects_unexpected_path_count(self) -> None:
        with self.assertRaisesRegex(ValueError, "expected 2.*found 1"):
            patch_payload(MISSION_DATA_ROOT_A, 2)


if __name__ == "__main__":
    unittest.main()
