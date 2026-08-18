#!/usr/bin/env python3
"""Navigate a running V2 emulator to Mission using only fixed input events."""

from __future__ import annotations

import argparse
import json
import time

from h1_runtime_control import key, request, status, tap, wait_for_calibration


KEYBOARD_ENTER = 25
KEYBOARD_ESCAPE = 24
KEYBOARD_PAGE_UP = 15
ACTION_BACK = 41
MORE_BUTTON = (400, 258)
TOOLS_CATEGORY = (462, 251)
MISSION_SLOT = (153, 207)
MIN_BOOT_UPTIME = 15.0


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


def navigate_to_mission(
    base_url: str,
    *,
    reset: bool,
    slot_x: int,
    slot_y: int,
    timeout_seconds: float,
    launch_wait_seconds: float,
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
    tap(base_url, *MORE_BUTTON, hold_ms=500)
    time.sleep(1.2)
    tap(base_url, *TOOLS_CATEGORY, hold_ms=400)
    time.sleep(1.2)
    # Mission reuses the native Time application's slot on the first
    # Tools/Entertainment page.  Page Up returns a remembered second page to
    # that first page and is ignored when the first page is already active.
    key(base_url, KEYBOARD_PAGE_UP)
    time.sleep(1.2)
    tap(base_url, slot_x, slot_y)
    time.sleep(launch_wait_seconds)

    result = status(base_url)
    return {
        "state": "mission-launch-inputs-sent",
        "navigation": "fixed-input-only",
        "screenshots_used": False,
        "tools_category": list(TOOLS_CATEGORY),
        "page_normalization": "keyboard-page-up",
        "slot": [slot_x, slot_y],
        "reset_requested": reset,
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
        help="wait for Mission to reach its first manually testable interface",
    )
    args = parser.parse_args()
    if args.launch_wait < 0:
        parser.error("--launch-wait must not be negative")

    result = navigate_to_mission(
        args.url.rstrip("/"),
        reset=args.reset,
        slot_x=args.slot_x,
        slot_y=args.slot_y,
        timeout_seconds=args.timeout,
        launch_wait_seconds=args.launch_wait,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
