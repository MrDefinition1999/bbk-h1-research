#!/usr/bin/env python3
"""Unit tests for trace-verified H2 Mission navigation."""

from __future__ import annotations

import unittest
from unittest import mock

import navigate_h2_mission as navigator


class NavigateH2MissionTests(unittest.TestCase):
    def test_wait_requires_new_generation(self) -> None:
        baseline = {
            "present": True,
            "phase": "game-start",
            "generation": 4,
        }
        states = iter(
            (
                baseline,
                {"present": True, "phase": "game-start", "generation": 5},
            )
        )
        with (
            mock.patch.object(
                navigator,
                "status",
                return_value={"running": True, "lastError": None},
            ),
            mock.patch.object(navigator, "read_trace", side_effect=lambda _url: next(states)),
            mock.patch.object(navigator.time, "sleep"),
        ):
            result = navigator.wait_for_mission_entry("http://h2", baseline, 1.0)
        self.assertEqual(result["generation"], 5)

    def test_navigation_uses_proven_h1_order(self) -> None:
        calls: list[tuple[str, object]] = []
        with (
            mock.patch.object(navigator, "wait_for_desktop"),
            mock.patch.object(navigator, "read_trace", return_value={"generation": 0}),
            mock.patch.object(
                navigator,
                "wait_for_mission_entry",
                return_value={"present": True, "phase": "game-start", "generation": 1},
            ),
            mock.patch.object(navigator, "status", return_value={"running": True}),
            mock.patch.object(
                navigator,
                "tap",
                side_effect=lambda _url, point, hold_ms=550: calls.append(("tap", point)),
            ),
            mock.patch.object(
                navigator,
                "key",
                side_effect=lambda _url, name, duration_ms=150: calls.append(("key", name)),
            ),
            mock.patch.object(navigator.time, "sleep"),
        ):
            result = navigator.navigate_to_mission(
                "http://h2",
                timeout_seconds=1.0,
                launch_wait_seconds=1.0,
                settle_wait_seconds=0.0,
            )
        self.assertEqual(
            calls,
            [
                ("key", "esc"),
                ("key", "esc"),
                ("key", "esc"),
                ("key", "esc"),
                ("key", "esc"),
                ("tap", navigator.MORE_BUTTON),
                ("tap", navigator.OTHER_CATEGORY[0]),
                ("tap", navigator.OTHER_CATEGORY[1]),
                ("tap", navigator.TOOLS_CATEGORY[0]),
                ("tap", navigator.TOOLS_CATEGORY[1]),
                ("tap", navigator.TOOLS_NEXT_PAGE),
                ("key", "ret"),
                ("tap", navigator.MISSION_SLOT),
                ("key", "ret"),
            ],
        )
        self.assertEqual(result["page_navigation"]["page"], 2)
        self.assertEqual(result["page_navigation"]["attempts"], 1)
        self.assertTrue(result["verified"])


if __name__ == "__main__":
    unittest.main()
