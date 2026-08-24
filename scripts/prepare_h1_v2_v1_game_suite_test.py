#!/usr/bin/env python3
"""Leave a healthy V2 guest on Tools/Entertainment for manual game testing."""

from __future__ import annotations

import argparse
import json
import time

from h1_runtime_control import key, status, tap, wait_for_calibration
from navigate_h1_v2_mission import (
    ACTION_BACK,
    CATEGORY_HOLD_MS,
    KEYBOARD_ENTER,
    KEYBOARD_ESCAPE,
    MIN_BOOT_UPTIME,
    MORE_BUTTON,
    OTHER_CATEGORY,
    OTHER_CATEGORY_FALLBACK,
    TOOLS_CATEGORY,
    TOOLS_CATEGORY_FALLBACK,
    wait_for_stable_frame,
)


GAMES = ("中国象棋", "俄罗斯", "宠物泡泡", "猫狗大战", "雷霆战机", "黑白子", "使命")


def prepare(base_url: str, timeout: float) -> dict[str, object]:
    current = status(base_url)
    if not current.get("running"):
        raise RuntimeError("emulator is not running")
    if current.get("instruction_clock") or current.get("tcg_thread") != "single":
        raise RuntimeError("manual test must use instruction_clock=false and single TCG")
    if current.get("memory") != "64 MiB":
        raise RuntimeError(f"manual test requires 64 MiB, got {current.get('memory')}")
    remaining = max(0.0, MIN_BOOT_UPTIME - float(current.get("uptime") or 0.0))
    if remaining:
        time.sleep(remaining)
    wait_for_stable_frame(base_url, timeout)
    wait_for_calibration(base_url, timeout_seconds=timeout)

    key(base_url, KEYBOARD_ENTER)
    time.sleep(1.0)
    key(base_url, KEYBOARD_ESCAPE)
    time.sleep(1.0)
    key(base_url, ACTION_BACK)
    time.sleep(1.2)
    key(base_url, ACTION_BACK)
    time.sleep(1.2)
    tap(base_url, *MORE_BUTTON, hold_ms=500)
    time.sleep(2.5)
    tap(base_url, *OTHER_CATEGORY, hold_ms=CATEGORY_HOLD_MS)
    time.sleep(0.8)
    tap(base_url, *OTHER_CATEGORY_FALLBACK, hold_ms=CATEGORY_HOLD_MS)
    time.sleep(1.5)
    tap(base_url, *TOOLS_CATEGORY, hold_ms=CATEGORY_HOLD_MS)
    time.sleep(0.8)
    tap(base_url, *TOOLS_CATEGORY_FALLBACK, hold_ms=CATEGORY_HOLD_MS)
    time.sleep(2.5)

    result = status(base_url)
    if not result.get("running") or result.get("last_error"):
        raise RuntimeError(f"guest failed while preparing manual test: {result}")
    return {
        "state": "tools-entertainment-ready-for-manual-test",
        "screenshots_used": False,
        "games": list(GAMES),
        "page_navigation": "use the on-screen up/down arrows",
        "memory": result.get("memory"),
        "instruction_clock": result.get("instruction_clock"),
        "tcg_thread": result.get("tcg_thread"),
        "guest_instructions": (result.get("performance") or {}).get("guest_instructions"),
        "audio_dma_completions": ((result.get("audio") or {}).get("diagnostics") or {}).get(
            "dma_completions"
        ),
        "input_count": result.get("input_count"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8796")
    parser.add_argument("--timeout", type=float, default=90.0)
    args = parser.parse_args()
    print(json.dumps(prepare(args.url.rstrip("/"), args.timeout), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
