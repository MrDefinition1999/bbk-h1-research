#!/usr/bin/env python3
"""Open the first AVI in the V2 Flying Video app using fixed input only."""

from __future__ import annotations

import argparse
import json
import time

from h1_runtime_control import status, tap
from navigate_h1_v2_mission import (
    CATEGORY_HOLD_MS,
    MORE_BUTTON,
    OTHER_CATEGORY,
    OTHER_CATEGORY_FALLBACK,
    TOOLS_CATEGORY,
    TOOLS_CATEGORY_FALLBACK,
)
from prepare_h1_v2_desktop import prepare


FLYING_VIDEO_SLOT = (70, 65)
FILE_SELECTOR_BUTTON = (30, 250)
FIRST_RESULT_CHECKBOX = (22, 105)
# The visible button spans the lower-right corner, but V2 accepts the inner
# point below reliably while edge-near (455, 258) presses can be dropped.
OPEN_BUTTON = (450, 250)


def counter(snapshot: dict[str, object], section: str, field: str) -> int:
    value = snapshot.get(section) or {}
    return int(value.get(field) or 0) if isinstance(value, dict) else 0


def navigate_and_launch(base_url: str, timeout: float) -> dict[str, object]:
    desktop = prepare(base_url, timeout, restart=False)

    tap(base_url, *MORE_BUTTON, hold_ms=500)
    time.sleep(2.5)
    tap(base_url, *OTHER_CATEGORY, hold_ms=CATEGORY_HOLD_MS)
    time.sleep(0.8)
    tap(base_url, *OTHER_CATEGORY_FALLBACK, hold_ms=CATEGORY_HOLD_MS)
    time.sleep(1.5)
    tap(base_url, *TOOLS_CATEGORY, hold_ms=CATEGORY_HOLD_MS)
    time.sleep(0.8)
    tap(base_url, *TOOLS_CATEGORY_FALLBACK, hold_ms=CATEGORY_HOLD_MS)
    time.sleep(2.0)

    tap(base_url, *FLYING_VIDEO_SLOT, hold_ms=600)
    time.sleep(4.0)
    tap(base_url, *FILE_SELECTOR_BUTTON, hold_ms=600)
    # Flying Video searches B: recursively when its file selector opens.
    time.sleep(6.0)
    # Merely highlighting the row is insufficient: the first result's box
    # must be checked before the Open button is pressed.
    tap(base_url, *FIRST_RESULT_CHECKBOX, hold_ms=350)
    time.sleep(1.0)

    before = status(base_url)
    tap(base_url, *OPEN_BUTTON, hold_ms=600)
    time.sleep(8.0)
    after = status(base_url)

    frame_delta = counter(after, "frame", "sequence") - counter(
        before, "frame", "sequence"
    )
    audio_delta = counter(after, "audio", "packets") - counter(
        before, "audio", "packets"
    )
    verified = bool(after.get("running")) and frame_delta > 0 and audio_delta > 0
    if not verified:
        raise RuntimeError(
            "Flying Video did not produce both video and audio after fixed launch "
            f"input (frame_delta={frame_delta}, audio_packet_delta={audio_delta})"
        )
    return {
        "state": "v2-flying-video-playing",
        "verified": True,
        "navigation": "fixed-input-only",
        "screenshots_used": False,
        "desktop": desktop,
        "file_selection": {
            "source": "B:-recursive-search",
            "result": 1,
            "checkbox": list(FIRST_RESULT_CHECKBOX),
            "open_button": list(OPEN_BUTTON),
        },
        "validation_seconds": 8.0,
        "frame_sequence_delta": frame_delta,
        "audio_packet_delta": audio_delta,
        "memory": after.get("memory"),
        "instruction_clock": after.get("instruction_clock"),
        "tcg_thread": after.get("tcg_thread"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8796")
    parser.add_argument("--timeout", type=float, default=120.0)
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    result = navigate_and_launch(args.url.rstrip("/"), args.timeout)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
