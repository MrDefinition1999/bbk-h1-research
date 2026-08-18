#!/usr/bin/env python3
"""Verify KOV guest progress through its exported counters and local GDB."""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

from qemu_gdb_watch import RspClient


COUNTER_WORDS = 8


def api(server: str) -> dict[str, object]:
    with urllib.request.urlopen(server.rstrip("/") + "/api/status", timeout=10) as response:
        value = json.load(response)
    if not isinstance(value, dict):
        raise ValueError("unexpected emulator status")
    return value


def read_counter_words(port: int, address: int) -> list[int]:
    client = RspClient("127.0.0.1", port)
    try:
        payload = client.command(f"m{address:x},{COUNTER_WORDS * 4:x}")
        raw = bytes.fromhex(payload)
        if len(raw) != COUNTER_WORDS * 4:
            raise RuntimeError("GDB returned a short KOV counter block")
        values = [int.from_bytes(raw[offset : offset + 4], "little")
                  for offset in range(0, len(raw), 4)]
        client.sock.sendall(client._packet("c"))
        client._wait_for_ack()
        return values
    finally:
        client.close()


def sample(server: str, gdb_port: int, counter_address: int, elapsed: float) -> dict[str, object]:
    status = api(server)
    values = read_counter_words(gdb_port, counter_address)
    audio = status.get("audio") or {}
    diagnostics = audio.get("diagnostics") or {}
    return {
        "elapsed": round(elapsed, 3),
        "running": bool(status.get("running")),
        "pid": status.get("pid"),
        "logic_frames": values[0],
        "rendered_frames": values[1],
        "skipped_frames": values[2],
        "timer_ms": values[3],
        "raw_ticks": values[4],
        "phase": values[5],
        "phase_sequence": values[6],
        "clock_hz": values[7],
        "guest_instructions": int((status.get("performance") or {}).get("guest_instructions") or 0),
        "audio_frames": int(audio.get("frames") or 0),
        "audio_output_frames": int(diagnostics.get("output_frames") or 0),
        "audio_underruns": int(diagnostics.get("underruns") or 0),
        "audio_overruns": int(diagnostics.get("overruns") or 0),
        "audio_dma_completions": int(diagnostics.get("dma_completions") or 0),
        "audio_dma_rearms": int(diagnostics.get("dma_rearms") or 0),
        "last_error": status.get("last_error"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server", default="http://127.0.0.1:8793")
    parser.add_argument("--gdb-port", type=int, default=1234)
    parser.add_argument("--counter-address", type=lambda value: int(value, 0), required=True)
    parser.add_argument("--duration", type=float, default=300.0)
    parser.add_argument("--sample-interval", type=float, default=5.0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.duration <= 0 or args.sample_interval <= 0:
        parser.error("duration and sample interval must be positive")

    started = time.monotonic()
    samples = [sample(args.server, args.gdb_port, args.counter_address, 0.0)]
    deadline = started + args.duration
    while time.monotonic() < deadline:
        time.sleep(min(args.sample_interval, max(0.0, deadline - time.monotonic())))
        samples.append(sample(args.server, args.gdb_port, args.counter_address, time.monotonic() - started))

    first = samples[0]
    last = samples[-1]
    errors: list[str] = []
    if not all(item["running"] for item in samples):
        errors.append("emulator stopped during the sample")
    if len({item["pid"] for item in samples}) != 1:
        errors.append("emulator PID changed")
    if any(item["last_error"] for item in samples):
        errors.append("emulator reported last_error")
    for key in ("logic_frames", "rendered_frames", "audio_frames", "audio_output_frames"):
        if int(last[key]) <= int(first[key]):
            errors.append(f"{key} did not advance")
    if int(last["audio_underruns"]) != int(first["audio_underruns"]):
        errors.append("audio underrun count increased")
    if int(last["audio_overruns"]) != int(first["audio_overruns"]):
        errors.append("audio overrun count increased")
    if int(last["audio_dma_completions"]) != int(last["audio_dma_rearms"]):
        errors.append("audio DMA completion/rearm counts differ")
    report = {
        "format": "kov-guest-counter-stability-v1",
        "ok": not errors,
        "errors": errors,
        "server": args.server,
        "gdb_port": args.gdb_port,
        "counter_address": f"0x{args.counter_address:08x}",
        "duration_seconds": args.duration,
        "samples": samples,
        "deltas": {
            key: int(last[key]) - int(first[key])
            for key in (
                "logic_frames", "rendered_frames", "skipped_frames",
                "guest_instructions", "audio_frames", "audio_output_frames",
                "audio_underruns", "audio_overruns",
            )
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
