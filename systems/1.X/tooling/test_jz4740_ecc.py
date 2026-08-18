from __future__ import annotations

import random
import unittest

from jz4740_ecc import jz4740_block_ecc, jz4740_page_oob_ecc


class Jz4740EccTests(unittest.TestCase):
    def test_erased_block_matches_recovery_vector(self) -> None:
        self.assertEqual(
            jz4740_block_ecc(b"\xFF" * 512).hex().upper(),
            "CD9D9058F48BFFB76F",
        )

    def test_page_contains_four_independent_parity_fields(self) -> None:
        randomizer = random.Random(0x4740)
        page = bytes(randomizer.randrange(256) for _ in range(2048))
        encoded = jz4740_page_oob_ecc(page, offset=4)
        self.assertEqual(encoded[:4], b"\xFF" * 4)
        self.assertEqual(len(encoded), 40)
        for index in range(4):
            start = index * 512
            self.assertEqual(
                encoded[4 + index * 9 : 4 + (index + 1) * 9],
                jz4740_block_ecc(page[start : start + 512]),
            )

    def test_rejects_invalid_sizes_and_offset(self) -> None:
        with self.assertRaises(ValueError):
            jz4740_block_ecc(b"\x00" * 511)
        with self.assertRaises(ValueError):
            jz4740_page_oob_ecc(b"\x00" * 2047)
        with self.assertRaises(ValueError):
            jz4740_page_oob_ecc(b"\x00" * 2048, offset=-1)


if __name__ == "__main__":
    unittest.main()
