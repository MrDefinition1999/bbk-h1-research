#!/usr/bin/env python3
"""Regression tests for the BBK PC DAT XOR decoder."""

from __future__ import annotations

import unittest

from decode_bbk_pc_dat import HEADER_SIZE, KEY_PERIOD, MAGIC, decode, derive_key


class DecodeBbkPcDatTests(unittest.TestCase):
    def test_round_trip_and_period_validation(self) -> None:
        key = bytes((index * 29 + 7) & 0xFF for index in range(KEY_PERIOD))
        plain = bytes((index * 17 + 3) & 0xFF for index in range(KEY_PERIOD * 2 + 91))
        cipher = bytes(value ^ key[index % KEY_PERIOD] for index, value in enumerate(plain))
        dat = MAGIC + b"\0" * (HEADER_SIZE - len(MAGIC)) + cipher
        derived = derive_key(dat, plain)
        self.assertEqual(derived, key)
        self.assertEqual(decode(dat, derived), plain)

    def test_rejects_bad_magic(self) -> None:
        with self.assertRaisesRegex(ValueError, "missing"):
            derive_key(b"BAD!" + b"\0" * (HEADER_SIZE + KEY_PERIOD), b"\0" * KEY_PERIOD)

    def test_rejects_nonperiodic_pair(self) -> None:
        plain = b"\0" * (KEY_PERIOD + 1)
        dat = MAGIC + b"\0" * (HEADER_SIZE - len(MAGIC)) + b"\x01" * KEY_PERIOD + b"\x02"
        with self.assertRaisesRegex(ValueError, "offset"):
            derive_key(dat, plain)


if __name__ == "__main__":
    unittest.main()
