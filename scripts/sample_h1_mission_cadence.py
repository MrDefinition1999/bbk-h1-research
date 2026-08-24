#!/usr/bin/env python3
"""Measure Mission frame cadence and guest progress without changing QEMU."""

from __future__ import annotations

import argparse
import json
import statistics
import time
import urllib.request
from pathlib import Path
from typing import Any


def fetch_status(base_url: str, timeout: float) -> dict[str, Any]:
    with urllib.request.urlopen(
        base_url.rstrip("/") + "/api/status", timeout=timeout
    ) as response:
        return json.load(response)


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, round((len(ordered) - 1) * fraction))
    return ordered[index]


def rounded(value: float | None, digits: int = 3) -> float | None:
    return None if value is None else round(value, digits)


def summarize(
    rows: list[dict[str, int | float]],
    base_url: str,
    duration: float,
    interval_ms: int,
    failures: int,
    configuration: dict[str, Any],
    mode: str,
) -> dict[str, Any]:
    if len(rows) < 2:
        raise RuntimeError("fewer than two status samples were captured")

    elapsed = (float(rows[-1]["time_ms"]) - float(rows[0]["time_ms"])) / 1000.0
    frame_events = [rows[0]]
    instruction_points = [rows[0]]
    for row in rows[1:]:
        if row["frame_sequence"] != frame_events[-1]["frame_sequence"]:
            frame_events.append(row)
        if row["guest_instructions"] != instruction_points[-1]["guest_instructions"]:
            instruction_points.append(row)

    frame_gaps_ms = [
        float(current["time_ms"]) - float(previous["time_ms"])
        for previous, current in zip(frame_events, frame_events[1:])
    ]
    instruction_rates: list[float] = []
    instruction_intervals: list[dict[str, float | int]] = []
    for previous, current in zip(instruction_points, instruction_points[1:]):
        interval = (float(current["time_ms"]) - float(previous["time_ms"])) / 1000.0
        delta = int(current["guest_instructions"]) - int(previous["guest_instructions"])
        if interval <= 0:
            continue
        rate = delta / interval
        instruction_rates.append(rate)
        instruction_intervals.append(
            {
                "end_time_ms": current["time_ms"],
                "elapsed_ms": round(interval * 1000.0, 3),
                "instruction_delta": delta,
                "instructions_per_second": round(rate, 3),
            }
        )

    frame_delta = int(rows[-1]["frame_sequence"]) - int(rows[0]["frame_sequence"])
    return {
        "format": "h1-mission-cadence-v1",
        "base_url": base_url.rstrip("/"),
        "mode": mode,
        "requested_duration_seconds": duration,
        "actual_duration_seconds": round(elapsed, 3),
        "sample_interval_ms": interval_ms,
        "samples": len(rows),
        "sample_failures": failures,
        "configuration": configuration,
        "frame": {
            "sequence_delta": frame_delta,
            "effective_changed_frames_per_second": rounded(frame_delta / elapsed),
            "observed_change_events": len(frame_events) - 1,
            "gap_ms_median": rounded(
                statistics.median(frame_gaps_ms) if frame_gaps_ms else None
            ),
            "gap_ms_p95": rounded(percentile(frame_gaps_ms, 0.95)),
            "gap_ms_max": rounded(max(frame_gaps_ms) if frame_gaps_ms else None),
        },
        "guest": {
            "instruction_delta": int(rows[-1]["guest_instructions"])
            - int(rows[0]["guest_instructions"]),
            "instructions_per_second_min": rounded(
                min(instruction_rates) if instruction_rates else None
            ),
            "instructions_per_second_median": rounded(
                statistics.median(instruction_rates) if instruction_rates else None
            ),
            "instructions_per_second_max": rounded(
                max(instruction_rates) if instruction_rates else None
            ),
            "one_second_intervals": instruction_intervals,
        },
        "audio": {
            "packet_delta": int(rows[-1]["audio_sequence"])
            - int(rows[0]["audio_sequence"]),
            "dma_completion_delta": int(rows[-1]["dma_completions"])
            - int(rows[0]["dma_completions"]),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8796")
    parser.add_argument("--duration", type=float, default=20.0)
    parser.add_argument("--interval-ms", type=int, default=40)
    parser.add_argument("--countdown", type=int, default=5)
    parser.add_argument(
        "--mode",
        choices=("idle",),
        default="idle",
        help="label the sample; only the reproducible default-standing method is accepted",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.duration <= 0 or not 20 <= args.interval_ms <= 1000 or args.countdown < 0:
        parser.error(
            "duration/countdown must be non-negative and interval-ms must be 20..1000"
        )
    initial_status = fetch_status(args.base_url, 2.0)
    if not initial_status.get("running"):
        raise SystemExit(f"emulator is not running at {args.base_url.rstrip('/')}")

    for remaining in range(args.countdown, 0, -1):
        print(f"sampling starts in {remaining}...", flush=True)
        time.sleep(1)
    print("IDLE_NOW: leave Mission untouched for the full sample", flush=True)

    rows: list[dict[str, int | float]] = []
    failures = 0
    configuration: dict[str, Any] = {}
    started = time.monotonic()
    next_sample = started
    while time.monotonic() - started < args.duration:
        try:
            status = fetch_status(
                args.base_url, max(1.0, args.interval_ms / 1000.0 * 4.0)
            )
            if not status.get("running"):
                raise RuntimeError("emulator is not running")
            if not configuration:
                configuration = {
                    "machine": status.get("machine"),
                    "memory": status.get("memory"),
                    "instruction_clock": status.get("instruction_clock"),
                    "tcg_thread": status.get("tcg_thread"),
                    "touch_profile": status.get("touch_profile"),
                }
            rows.append(
                {
                    "time_ms": round((time.monotonic() - started) * 1000.0, 3),
                    "frame_sequence": int(status["frame"]["sequence"]),
                    "frame_age": float(status["frame"]["age"]),
                    "guest_instructions": int(
                        status["performance"]["guest_instructions"]
                    ),
                    "qemu_realtime_ms": int(
                        status["performance"]["qemu_realtime_ms"]
                    ),
                    "audio_sequence": int(status["audio"]["sequence"]),
                    "dma_completions": int(
                        status["audio"]["diagnostics"]["dma_completions"]
                    ),
                }
            )
        except (OSError, KeyError, RuntimeError, TypeError, ValueError) as error:
            failures += 1
            if not rows:
                print(f"status warning: {type(error).__name__}: {error}", flush=True)
        next_sample += args.interval_ms / 1000.0
        time.sleep(max(0.0, next_sample - time.monotonic()))

    report = summarize(
        rows,
        args.base_url,
        args.duration,
        args.interval_ms,
        failures,
        configuration,
        args.mode,
    )
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
