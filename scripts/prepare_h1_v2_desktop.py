#!/usr/bin/env python3
"""Cold-start a V2 guest and normalize its restored application to the desktop."""

from __future__ import annotations

import argparse
import json
import time

from h1_runtime_control import key, request, status, wait_for_calibration
from navigate_h1_v2_mission import (
    ACTION_BACK,
    KEYBOARD_ENTER,
    KEYBOARD_ESCAPE,
    wait_for_stable_frame,
)


def prepare(
    base_url: str,
    timeout: float,
    *,
    restart: bool = False,
    boot_attempts: int = 3,
) -> dict[str, object]:
    if boot_attempts <= 0:
        raise ValueError("boot_attempts must be positive")
    current = status(base_url)
    if restart:
        endpoint = "/api/reset" if current.get("running") else "/api/start"
        request(base_url, endpoint, {})
    elif not current.get("running"):
        request(base_url, "/api/start", {})
    recovered_attempt = 1
    for attempt in range(1, boot_attempts + 1):
        wait_for_stable_frame(base_url, timeout)
        probe_before = status(base_url)
        instruction_before = int(
            ((probe_before.get("performance") or {}).get("guest_instructions") or 0)
        )
        time.sleep(0.75)
        probe_after = status(base_url)
        instruction_after = int(
            ((probe_after.get("performance") or {}).get("guest_instructions") or 0)
        )
        if instruction_after > instruction_before:
            recovered_attempt = attempt
            break
        if attempt == boot_attempts:
            raise RuntimeError(
                "V2 boot repeatedly entered the non-progressing exception state; "
                f"all {boot_attempts} fixed reset attempts were discarded"
            )
        request(base_url, "/api/reset", {})
    wait_for_calibration(base_url, timeout_seconds=timeout)
    time.sleep(0.5)

    # The V2 system restores its last native application after the clock and
    # low-space prompts.  This sequence is deliberately state-normalizing:
    # keyboard Esc/Enter clear those prompts, then two permanent Back events
    # leave a restored application and its category page for the subject
    # desktop.  Extra Back events at the desktop are harmless.
    key(base_url, KEYBOARD_ESCAPE)
    time.sleep(3.0)
    key(base_url, KEYBOARD_ENTER)
    time.sleep(2.0)
    key(base_url, KEYBOARD_ESCAPE)
    time.sleep(1.0)
    key(base_url, ACTION_BACK)
    time.sleep(1.2)
    key(base_url, ACTION_BACK)
    time.sleep(1.2)

    result = status(base_url)
    if not result.get("running") or result.get("last_error"):
        raise RuntimeError(f"guest failed while normalizing V2 desktop: {result}")
    instruction_before = int(
        ((result.get("performance") or {}).get("guest_instructions") or 0)
    )
    time.sleep(0.75)
    progress = status(base_url)
    instruction_after = int(
        ((progress.get("performance") or {}).get("guest_instructions") or 0)
    )
    if instruction_after <= instruction_before:
        raise RuntimeError(
            "V2 guest instruction counter is stalled after boot normalization; "
            "discard this boot and restart the complete frontend/QEMU process"
        )
    return {
        "state": "v2-desktop-normalized",
        "navigation": "fixed-input-only",
        "screenshots_used": False,
        "restart_requested": restart,
        "healthy_boot_attempt": recovered_attempt,
        "memory": result.get("memory"),
        "instruction_clock": result.get("instruction_clock"),
        "tcg_thread": result.get("tcg_thread"),
        "guest_instructions": instruction_after,
        "progress_probe_delta": instruction_after - instruction_before,
        "input_count": progress.get("input_count"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8796")
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument(
        "--restart",
        action="store_true",
        help="restart QEMU first; normally attach to the frontend's fresh process",
    )
    parser.add_argument("--boot-attempts", type=int, default=3)
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    print(
        json.dumps(
            prepare(
                args.url.rstrip("/"),
                args.timeout,
                restart=args.restart,
                boot_attempts=args.boot_attempts,
            ),
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
