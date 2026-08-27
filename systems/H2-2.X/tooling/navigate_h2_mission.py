#!/usr/bin/env python3
"""Navigate H2 to Mission and verify the wrapper transition without screenshots."""

from __future__ import annotations

import argparse
import json
import time
from urllib.request import Request, urlopen

from probe_h2_mission import read_trace


MORE_BUTTON = (420, 258)
OTHER_CATEGORY = ((380, 258), (390, 258))
TOOLS_CATEGORY = ((430, 258), (440, 258))
TOOLS_NEXT_PAGE = (455, 216)
MISSION_SLOT = (402, 61)
TOOLS_PAGE_ADVANCES = 1
NORMALIZE_BACK_PRESSES = 5
MIN_BOOT_UPTIME = 35.0
POST_BOOT_INPUT_GUARD_SECONDS = 6.0
TRACE_GAME_START = "game-start"
TRACE_GAME_RETURN = "game-return"


def request_json(
    base_url: str,
    path: str,
    body: dict[str, object] | None = None,
) -> dict[str, object]:
    payload = None if body is None else json.dumps(body).encode("ascii")
    request = Request(
        base_url + path,
        data=payload,
        headers={"Content-Type": "application/json"} if payload is not None else {},
    )
    with urlopen(request, timeout=10.0) as response:
        result = json.loads(response.read())
    if not isinstance(result, dict):
        raise RuntimeError(f"unexpected response from {path}: {result!r}")
    if result.get("error"):
        raise RuntimeError(str(result["error"]))
    return result


def status(base_url: str) -> dict[str, object]:
    return request_json(base_url, "/api/status")


def key(base_url: str, name: str, duration_ms: int = 150) -> None:
    request_json(
        base_url,
        "/api/key",
        {"key": name, "duration": duration_ms},
    )


def tap(base_url: str, point: tuple[int, int], hold_ms: int = 550) -> None:
    request_json(
        base_url,
        "/api/tap",
        {"x": point[0], "y": point[1], "hold": hold_ms},
    )


def wait_for_desktop(base_url: str, timeout_seconds: float) -> dict[str, object]:
    deadline = time.monotonic() + timeout_seconds
    last: dict[str, object] = {}
    while time.monotonic() < deadline:
        last = status(base_url)
        if (
            last.get("running")
            and float(last.get("uptimeSeconds") or 0) >= MIN_BOOT_UPTIME
        ):
            return last
        if last.get("lastError"):
            raise RuntimeError(f"H2 runtime error: {last['lastError']}")
        time.sleep(0.25)
    raise TimeoutError(f"H2 desktop did not become ready: {last}")


def wait_for_mission_entry(
    base_url: str,
    baseline: dict[str, object],
    timeout_seconds: float,
) -> dict[str, object]:
    deadline = time.monotonic() + timeout_seconds
    last = baseline
    while time.monotonic() < deadline:
        current = status(base_url)
        if not current.get("running"):
            raise RuntimeError("H2 stopped before Mission entered its payload")
        if current.get("lastError"):
            raise RuntimeError(f"H2 runtime error: {current['lastError']}")
        last = read_trace(base_url)
        if (
            last.get("present")
            and last.get("generation") != baseline.get("generation")
            and last.get("phase") in {TRACE_GAME_START, TRACE_GAME_RETURN}
        ):
            return last
        time.sleep(0.25)
    raise TimeoutError(
        "Mission wrapper did not report a new game-entry transition; "
        f"last trace was {last}"
    )


def navigate_to_mission(
    base_url: str,
    *,
    timeout_seconds: float,
    launch_wait_seconds: float,
    settle_wait_seconds: float,
) -> dict[str, object]:
    wait_for_desktop(base_url, timeout_seconds)

    # The H2 launcher can already be visible while its first post-boot task is
    # still blocking touch dispatch for roughly five seconds.  Do not send the
    # More-button tap during that known dead interval.
    time.sleep(POST_BOOT_INPUT_GUARD_SECONDS)

    # The stock image can restore a native application with more than one
    # nested screen.  Back is a no-op once the desktop is reached, so a fixed
    # bounded sequence safely normalizes every observed boot state without
    # interpreting frames or relying on the previously active application.
    for _press in range(NORMALIZE_BACK_PRESSES):
        key(base_url, "esc")
        time.sleep(1.2)

    tap(base_url, MORE_BUTTON, 500)
    time.sleep(2.5)
    for point in OTHER_CATEGORY:
        tap(base_url, point)
        time.sleep(0.8)
    time.sleep(0.7)
    for point in TOOLS_CATEGORY:
        tap(base_url, point)
        time.sleep(0.8)
    # H2 Tools/Entertainment contains two launcher pages.  Re-selecting the
    # category above normalizes it to page one; Mission occupies the final
    # clock slot on page two.  Let the page finish loading before advancing so
    # a busy launcher cannot swallow the fixed selection/Confirm pair.
    time.sleep(2.5)
    for _page in range(TOOLS_PAGE_ADVANCES):
        # The arrow is a focusable launcher item: touch only selects it, just
        # as it does for an application icon.  Confirm performs the actual
        # page transition.  A touch-only sequence silently remained on page
        # one even though every coordinate was correct.
        tap(base_url, TOOLS_NEXT_PAGE, 150)
        time.sleep(0.3)
        key(base_url, "ret")
        time.sleep(3.0)

    baseline = read_trace(base_url)
    tap(base_url, MISSION_SLOT, 600)
    time.sleep(1.0)
    # Touch selects a grid item; the real Confirm key is the deterministic
    # activation mechanism used by the proven H1 V2 navigator.
    key(base_url, "ret")
    mission = wait_for_mission_entry(base_url, baseline, launch_wait_seconds)
    time.sleep(settle_wait_seconds)
    return {
        "state": "mission-wrapper-confirmed",
        "verified": True,
        "navigation": "fixed-input-plus-trace-verification",
        "screenshots_used": False,
        "post_boot_input_guard_seconds": POST_BOOT_INPUT_GUARD_SECONDS,
        "more_button": list(MORE_BUTTON),
        "other_category": [list(point) for point in OTHER_CATEGORY],
        "tools_category": [list(point) for point in TOOLS_CATEGORY],
        "page_navigation": {
            "method": "tools-down-arrow-select-plus-hardware-confirm",
            "target": list(TOOLS_NEXT_PAGE),
            "attempts": TOOLS_PAGE_ADVANCES,
            "page": 2,
        },
        "slot": list(MISSION_SLOT),
        "slot_activation": "touch-select-then-hardware-confirm",
        "mission_stage": mission,
        "entry_outcome": (
            "active-entry"
            if mission.get("phase") == TRACE_GAME_START
            else "returned-to-dispatcher"
        ),
        "runtime": status(base_url),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8797")
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--launch-wait", type=float, default=30.0)
    parser.add_argument("--settle-wait", type=float, default=2.0)
    args = parser.parse_args()
    if args.timeout <= 0 or args.launch_wait <= 0 or args.settle_wait < 0:
        parser.error("timeouts must be positive and settle wait non-negative")
    result = navigate_to_mission(
        args.url.rstrip("/"),
        timeout_seconds=args.timeout,
        launch_wait_seconds=args.launch_wait,
        settle_wait_seconds=args.settle_wait,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
