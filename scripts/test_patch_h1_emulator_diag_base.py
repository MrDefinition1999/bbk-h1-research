from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).with_name("patch_h1_emulator_diag_base.py")
SPEC = importlib.util.spec_from_file_location("h1_diag_base_patch", SCRIPT)
assert SPEC and SPEC.loader
patcher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(patcher)


class DiagnosticBasePatchTests(unittest.TestCase):
    @staticmethod
    def synthetic_binary() -> bytes:
        pieces = [b"verified-test-binary"]
        for value, count in patcher.PATCH_VALUES.items():
            pieces.extend(value.to_bytes(4, "little") + b"separator" for _ in range(count))
        return b"".join(pieces)

    def test_relocates_every_verified_occurrence(self) -> None:
        source = self.synthetic_binary()
        with mock.patch.object(patcher, "SUPPORTED_SHA256", patcher.sha256(source)):
            output = patcher.patch(source)
        delta = patcher.NEW_BASE - patcher.OLD_BASE
        for old_value, count in patcher.PATCH_VALUES.items():
            self.assertEqual(output.count(old_value.to_bytes(4, "little")), 0)
            self.assertEqual(
                output.count((old_value + delta).to_bytes(4, "little")), count
            )
        self.assertEqual(len(output), len(source))

    def test_rejects_unverified_binary(self) -> None:
        with self.assertRaisesRegex(ValueError, "verified H1 x86-64 QEMU"):
            patcher.patch(b"not the supported executable")

    def test_rejects_changed_occurrence_count(self) -> None:
        source = self.synthetic_binary() + (0x03E00018).to_bytes(4, "little")
        with mock.patch.object(patcher, "SUPPORTED_SHA256", patcher.sha256(source)):
            with self.assertRaisesRegex(ValueError, "occurrence count"):
                patcher.patch(source)


if __name__ == "__main__":
    unittest.main()
