#!/usr/bin/env python3
"""Read the H2 Mission stage trace and optionally probe its seven real keys."""

from __future__ import annotations

import argparse
import json
import re
import time
from urllib.request import Request, urlopen


TRACE_PHYSICAL = 0x01F0E000
TRACE_MAGIC = 0x56545231
TRACE_HEADER_WORDS = 8
TRACE_RECORD_WORDS = 6
TRACE_RECORD_COUNT = 32
TRACE_WORDS = TRACE_HEADER_WORDS + TRACE_RECORD_WORDS * TRACE_RECORD_COUNT
TRACE_PHASES = {
    0x53544730: "stage-start",
    0x53544731: "stage-tables",
    0x47315331: "game-start",
    0x47315231: "game-return",
}
KEYS = ("left", "right", "ret", "esc", "volumedown", "volumeup", "power")
MONITOR_ROW_RE = re.compile(
    r"^[0-9a-fA-F]+:\s*((?:0x[0-9a-fA-F]{8}(?:\s+|$))+)",
    re.MULTILINE,
)
WORD_RE = re.compile(r"0x([0-9a-fA-F]{8})")


def parse_monitor_words(memory: str) -> list[int]:
    """Parse only HMP ``xp`` result rows, excluding the echoed command."""

    words: list[int] = []
    for row in MONITOR_ROW_RE.findall(memory):
        words.extend(int(value, 16) for value in WORD_RE.findall(row))
    return words


def request_json(url: str, body: dict[str, object] | None = None) -> dict[str, object]:
    payload = None if body is None else json.dumps(body).encode("utf-8")
    request = Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"} if payload is not None else {},
    )
    with urlopen(request, timeout=5.0) as response:
        value = json.loads(response.read())
    if not isinstance(value, dict):
        raise RuntimeError(f"unexpected response from {url}: {value!r}")
    return value


def read_trace(base_url: str) -> dict[str, object]:
    response = request_json(
        f"{base_url}/api/debug/memory?address=0x{TRACE_PHYSICAL:08X}&count={TRACE_WORDS}"
    )
    memory = response.get("memory")
    if not isinstance(memory, str):
        raise RuntimeError(f"debug response has no memory text: {response!r}")
    words = parse_monitor_words(memory)
    if len(words) != TRACE_WORDS:
        raise RuntimeError(f"trace returned {len(words)} words, expected {TRACE_WORDS}")
    if words[0] != TRACE_MAGIC:
        return {
            "present": False,
            "magic": f"0x{words[0]:08X}",
            "phase": "none",
            "event_count": 0,
            "generation": 0,
            "records": [],
        }

    write_index = words[2] % TRACE_RECORD_COUNT
    total = words[3]
    available = min(total, TRACE_RECORD_COUNT)
    first = (write_index - available) % TRACE_RECORD_COUNT
    records: list[dict[str, object]] = []
    for sequence in range(available):
        slot = (first + sequence) % TRACE_RECORD_COUNT
        offset = TRACE_HEADER_WORDS + slot * TRACE_RECORD_WORDS
        record = words[offset : offset + TRACE_RECORD_WORDS]
        records.append(
            {
                "sequence": total - available + sequence,
                "event": f"0x{record[0]:08X}",
                "a0": f"0x{record[1]:08X}",
                "a1": f"0x{record[2]:08X}",
                "a2": f"0x{record[3]:08X}",
                "a3": f"0x{record[4]:08X}",
                "result": f"0x{record[5]:08X}",
            }
        )
    phase = words[5]
    return {
        "present": True,
        "phase": TRACE_PHASES.get(phase, f"0x{phase:08X}"),
        "last_event": f"0x{words[4]:08X}",
        "event_count": total,
        "generation": words[6],
        "records": records,
    }


def new_records(before: dict[str, object], after: dict[str, object]) -> list[dict[str, object]]:
    baseline = int(before.get("event_count", 0))
    return [
        record
        for record in after.get("records", [])
        if isinstance(record, dict) and int(record.get("sequence", -1)) >= baseline
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True, help="H2 frontend base URL")
    parser.add_argument("--keys", nargs="*", choices=KEYS)
    parser.add_argument("--duration", type=int, default=180)
    parser.add_argument("--settle", type=float, default=0.75)
    args = parser.parse_args()
    if not 80 <= args.duration <= 2000 or args.settle < 0:
        parser.error("--duration must be 80..2000 and --settle must be non-negative")

    base_url = args.url.rstrip("/")
    state = read_trace(base_url)
    if not args.keys:
        print(json.dumps(state, ensure_ascii=False, indent=2))
        return 0

    probes: list[dict[str, object]] = []
    for key in args.keys:
        before = state
        request_json(
            f"{base_url}/api/key", {"key": key, "duration": args.duration}
        )
        time.sleep(args.settle)
        state = read_trace(base_url)
        probes.append(
            {
                "key": key,
                "before_event_count": before.get("event_count", 0),
                "after_event_count": state.get("event_count", 0),
                "new_records": new_records(before, state),
            }
        )
    print(
        json.dumps(
            {
                "format": "bbk-h2-mission-key-probe-v1",
                "phase": state.get("phase"),
                "generation": state.get("generation"),
                "probes": probes,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
