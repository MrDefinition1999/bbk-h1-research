#!/usr/bin/env python3
"""Unit tests for signature-verified V2 Mission navigation."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import navigate_h1_v2_mission as navigator


def memory_payload(*words: int) -> bytes:
    rows = []
    for offset in range(0, len(words), 4):
        values = " ".join(f"0x{word:08x}" for word in words[offset : offset + 4])
        rows.append(f"03f0e0{offset * 4:02x}: {values}")
    return json.dumps({"memory": "\n".join(rows) + "\n(qemu) "}).encode()


class MissionNavigationTests(unittest.TestCase):
    def test_fixed_v2_hit_targets_use_verified_centers(self) -> None:
        self.assertEqual(navigator.MORE_BUTTON, (420, 258))
        self.assertEqual(navigator.OTHER_CATEGORY, (380, 258))
        self.assertEqual(navigator.OTHER_CATEGORY_FALLBACK, (390, 258))
        self.assertEqual(navigator.TOOLS_CATEGORY, (430, 258))
        self.assertEqual(navigator.TOOLS_CATEGORY_FALLBACK, (440, 258))
        self.assertEqual(navigator.TOOLS_NEXT_PAGE, (455, 216))
        self.assertEqual(navigator.MISSION_SLOT, (402, 61))
        self.assertEqual(navigator.CATEGORY_HOLD_MS, 550)
        self.assertEqual(navigator.PAGE_HOLD_MS, 550)
        self.assertEqual(navigator.MISSION_HOLD_MS, 600)

    def test_parse_debug_words_ignores_physical_address(self) -> None:
        payload = memory_payload(1, 2, 3, 4, 5, 6, 7, 8)
        self.assertEqual(navigator.parse_debug_words(payload, 8), list(range(1, 9)))

    @mock.patch.object(navigator, "request")
    def test_persistent_trace_state(self, request: mock.Mock) -> None:
        request.return_value = memory_payload(
            navigator.MISSION_TRACE_MAGIC,
            1,
            4,
            9,
            navigator.TRACE_GAME_START,
            navigator.TRACE_GAME_START,
            3,
            0,
        )
        state = navigator.mission_stage_state("http://127.0.0.1:8796")
        self.assertEqual(state["format"], "persistent-trace-v1")
        self.assertEqual(state["phase_name"], "game-start")
        self.assertEqual(state["generation"], 3)

    @mock.patch.object(navigator, "request")
    def test_legacy_phase_state(self, request: mock.Mock) -> None:
        request.return_value = memory_payload(
            navigator.TRACE_GAME_START, 0, 0, 0, 0, 0, 0, 0
        )
        state = navigator.mission_stage_state("http://127.0.0.1:8796")
        self.assertEqual(state["format"], "legacy-phase-v1")
        self.assertEqual(state["phase_name"], "game-start")

    @mock.patch.object(navigator, "mission_stage_state")
    @mock.patch.object(navigator, "status")
    def test_wait_requires_new_generation(
        self, status: mock.Mock, stage_state: mock.Mock
    ) -> None:
        status.return_value = {"running": True, "last_error": None}
        stage_state.side_effect = [
            {
                "format": "persistent-trace-v1",
                "phase": navigator.TRACE_GAME_START,
                "generation": 4,
            },
            {
                "format": "persistent-trace-v1",
                "phase": navigator.TRACE_GAME_START,
                "generation": 5,
            },
        ]
        baseline = {
            "format": "persistent-trace-v1",
            "phase": navigator.TRACE_GAME_RETURN,
            "generation": 4,
        }
        with mock.patch.object(navigator.time, "sleep", return_value=None):
            result = navigator.wait_for_mission_entry(
                "http://127.0.0.1:8796", baseline, 1.0
            )
        self.assertEqual(result["generation"], 5)
        self.assertEqual(stage_state.call_count, 2)


if __name__ == "__main__":
    unittest.main()
