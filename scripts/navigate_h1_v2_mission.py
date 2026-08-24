#!/usr/bin/env python3
"""Navigate a running V2 emulator to Mission using only fixed input events."""

from __future__ import annotations

import argparse
import json
import re
import time

from h1_runtime_control import key, request, status, tap, wait_for_calibration


KEYBOARD_ENTER = 25
KEYBOARD_ESCAPE = 24
ACTION_CONFIRM = 39
ACTION_BACK = 41
MORE_BUTTON = (420, 258)
OTHER_CATEGORY = (380, 258)
OTHER_CATEGORY_FALLBACK = (390, 258)
TOOLS_CATEGORY = (430, 258)
TOOLS_CATEGORY_FALLBACK = (440, 258)
TOOLS_NEXT_PAGE = (455, 216)
MISSION_SLOT = (402, 61)
CATEGORY_HOLD_MS = 550
PAGE_HOLD_MS = 550
MISSION_HOLD_MS = 600
MIN_BOOT_UPTIME = 15.0
MISSION_TRACE_PHYSICAL = 0x03F0E000
MISSION_TRACE_WORDS = 8
MISSION_TRACE_MAGIC = 0x56545231
TRACE_GAME_START = 0x47315331
TRACE_GAME_RETURN = 0x47315231
TRACE_PHASE_NAMES = {
    0x53544730: "stage-start",
    0x53544731: "stage-tables",
    TRACE_GAME_START: "game-start",
    TRACE_GAME_RETURN: "game-return",
}
WORD_RE = re.compile(r"0x([0-9a-fA-F]{8})")


def wait_for_stable_frame(base_url: str, timeout_seconds: float) -> dict[str, object]:
    """Wait for the boot UI without inspecting or saving screenshots."""
    deadline = time.monotonic() + timeout_seconds
    last: dict[str, object] = {}
    while time.monotonic() < deadline:
        last = status(base_url)
        frame = last.get("frame") or {}
        if (
            last.get("running")
            and float(last.get("uptime") or 0) >= MIN_BOOT_UPTIME
            and int(frame.get("count") or 0) >= 1
        ):
            return last
        time.sleep(0.25)
    raise TimeoutError(f"H1 V2 boot UI did not stabilize: {last}")


def parse_debug_words(payload: bytes, expected: int) -> list[int]:
    value = json.loads(payload)
    memory = value.get("memory") if isinstance(value, dict) else None
    if not isinstance(memory, str):
        raise RuntimeError(f"debug memory response has no payload: {value!r}")
    words = [int(item, 16) for item in WORD_RE.findall(memory)]
    if len(words) != expected:
        raise RuntimeError(
            f"debug memory returned {len(words)} words, expected {expected}: {memory!r}"
        )
    return words


def mission_stage_state(base_url: str) -> dict[str, object]:
    payload = request(
        base_url,
        f"/api/debug/memory?address=0x{MISSION_TRACE_PHYSICAL:08X}"
        f"&count={MISSION_TRACE_WORDS}",
    )
    words = parse_debug_words(payload, MISSION_TRACE_WORDS)
    if words[0] == MISSION_TRACE_MAGIC:
        phase = words[5]
        return {
            "format": "persistent-trace-v1",
            "present": True,
            "phase": phase,
            "phase_name": TRACE_PHASE_NAMES.get(phase, f"0x{phase:08X}"),
            "generation": words[6],
            "event_count": words[3],
        }
    # The currently deployed probe writes only its phase word.  Supporting it
    # keeps the private image testable while rebuilt wrappers migrate to the
    # persistent header above.  A transition is still required, so stale data
    # can never satisfy launch verification.
    if words[0] in TRACE_PHASE_NAMES:
        return {
            "format": "legacy-phase-v1",
            "present": True,
            "phase": words[0],
            "phase_name": TRACE_PHASE_NAMES[words[0]],
            "generation": None,
            "event_count": None,
        }
    return {
        "format": "none",
        "present": False,
        "phase": None,
        "phase_name": "none",
        "generation": None,
        "event_count": None,
    }


def wait_for_mission_entry(
    base_url: str,
    baseline: dict[str, object],
    timeout_seconds: float,
) -> dict[str, object]:
    deadline = time.monotonic() + timeout_seconds
    last = baseline
    while time.monotonic() < deadline:
        current_status = status(base_url)
        if not current_status.get("running"):
            raise RuntimeError("emulator stopped before Mission entered its game payload")
        if current_status.get("last_error"):
            raise RuntimeError(f"emulator error: {current_status['last_error']}")
        last = mission_stage_state(base_url)
        if last["format"] == "persistent-trace-v1":
            new_generation = last["generation"] != baseline.get("generation")
            if new_generation and last["phase"] in {
                TRACE_GAME_START,
                TRACE_GAME_RETURN,
            }:
                return last
        elif (
            last["format"] == "legacy-phase-v1"
            and last["phase"] in {TRACE_GAME_START, TRACE_GAME_RETURN}
            and last["phase"] != baseline.get("phase")
        ):
            return last
        time.sleep(0.25)
    raise TimeoutError(
        "Mission loader signature did not reach a game-entry transition; "
        f"last state was {last}"
    )


def navigate_to_mission(
    base_url: str,
    *,
    reset: bool,
    slot_x: int,
    slot_y: int,
    timeout_seconds: float,
    launch_wait_seconds: float,
    settle_wait_seconds: float,
) -> dict[str, object]:
    current = status(base_url)
    if reset:
        endpoint = "/api/reset" if current.get("running") else "/api/start"
        request(base_url, endpoint, {})
    wait_for_calibration(base_url, timeout_seconds)
    wait_for_stable_frame(base_url, timeout_seconds)
    time.sleep(0.5)

    # The V2 image reaches a deterministic sequence of clock, low-space, and
    # Time-app states after reset.  Clear it with permanent keys, then use the
    # launcher's fixed category and slot coordinates.  No frame is captured or
    # interpreted anywhere in this navigation path.
    key(base_url, KEYBOARD_ESCAPE)
    time.sleep(3.0)
    key(base_url, KEYBOARD_ENTER)
    time.sleep(2.0)
    key(base_url, KEYBOARD_ESCAPE)
    time.sleep(1.0)
    # V2 can restore the previously active native application after the boot
    # prompts.  The first hardware Return exits that application to its last
    # category page; the second exits the category page to the subject desktop.
    # Subsequent navigation coordinates are valid only from that desktop.
    key(base_url, ACTION_BACK)
    time.sleep(1.2)
    key(base_url, ACTION_BACK)
    time.sleep(1.2)
    # Enter the subject application's category view through the center of the
    # desktop More button.  The former x=400 point was close to its left edge,
    # and the category transition can still be animating after only 1.2 s.
    tap(base_url, *MORE_BUTTON, hold_ms=500)
    time.sleep(2.5)
    # Tools/Entertainment is the clipped rightmost tab and ignores a direct
    # hit while the remembered leftmost category is selected.  Selecting its
    # adjacent Other tab first makes the same fixed center reliable.
    tap(base_url, *OTHER_CATEGORY, hold_ms=CATEGORY_HOLD_MS)
    time.sleep(0.8)
    tap(base_url, *OTHER_CATEGORY_FALLBACK, hold_ms=CATEGORY_HOLD_MS)
    time.sleep(1.5)
    # In-memory frame comparisons found these inner hit points more reliable
    # than the visually centered but clipped right edge.
    tap(base_url, *TOOLS_CATEGORY, hold_ms=CATEGORY_HOLD_MS)
    time.sleep(0.8)
    tap(base_url, *TOOLS_CATEGORY_FALLBACK, hold_ms=CATEGORY_HOLD_MS)
    time.sleep(1.5)
    # V2's Page Up/Page Down keys cycle subject categories.  The actual second
    # Tools/Entertainment page is opened by its on-screen down arrow and has a
    # dedicated Mission icon at the final fixed slot below.
    tap(base_url, *TOOLS_NEXT_PAGE, hold_ms=PAGE_HOLD_MS)
    time.sleep(1.0)
    # V2 can drop the first pen event during the page transition.  Retrying the
    # same point is safe because it is blank on page two.
    tap(base_url, *TOOLS_NEXT_PAGE, hold_ms=PAGE_HOLD_MS)
    time.sleep(2.5)
    baseline = mission_stage_state(base_url)
    if baseline["phase"] == TRACE_GAME_START:
        raise RuntimeError(
            "Mission was already running before the launcher slot was selected; "
            "the navigation state is not normalized"
        )
    # A touch selects the V2 grid icon but does not consistently activate it.
    # The permanent Confirm key deterministically launches the selected BDA.
    tap(base_url, slot_x, slot_y, hold_ms=MISSION_HOLD_MS)
    time.sleep(1.0)
    key(base_url, ACTION_CONFIRM)
    mission_state = wait_for_mission_entry(
        base_url, baseline, launch_wait_seconds
    )
    time.sleep(settle_wait_seconds)

    result = status(base_url)
    return {
        "state": "mission-wrapper-confirmed",
        "verified": True,
        "navigation": "fixed-input-only",
        "screenshots_used": False,
        "other_category": [list(OTHER_CATEGORY), list(OTHER_CATEGORY_FALLBACK)],
        "tools_category": [list(TOOLS_CATEGORY), list(TOOLS_CATEGORY_FALLBACK)],
        "page_navigation": {
            "method": "tools-down-arrow",
            "target": list(TOOLS_NEXT_PAGE),
            "attempts": 2,
            "page": 2,
        },
        "slot": [slot_x, slot_y],
        "slot_activation": "touch-select-then-hardware-confirm",
        "reset_requested": reset,
        "mission_stage": mission_state,
        "entry_outcome": (
            "active-entry"
            if mission_state["phase"] == TRACE_GAME_START
            else "returned-to-dispatcher"
        ),
        "settle_wait_seconds": settle_wait_seconds,
        "pid": result.get("pid"),
        "uptime": result.get("uptime"),
        "input_count": result.get("input_count"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8796")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="restart QEMU before navigating; normally start the frontend once and omit this",
    )
    parser.add_argument("--slot-x", type=int, default=MISSION_SLOT[0])
    parser.add_argument("--slot-y", type=int, default=MISSION_SLOT[1])
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument(
        "--launch-wait",
        type=float,
        default=30.0,
        help="timeout for the Mission loader's persistent game-entry signature",
    )
    parser.add_argument(
        "--settle-wait",
        type=float,
        default=20.0,
        help="fixed wait after the verified loader transition",
    )
    args = parser.parse_args()
    if args.launch_wait <= 0 or args.settle_wait < 0:
        parser.error("--launch-wait must be positive and --settle-wait non-negative")

    result = navigate_to_mission(
        args.url.rstrip("/"),
        reset=args.reset,
        slot_x=args.slot_x,
        slot_y=args.slot_y,
        timeout_seconds=args.timeout,
        launch_wait_seconds=args.launch_wait,
        settle_wait_seconds=args.settle_wait,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
