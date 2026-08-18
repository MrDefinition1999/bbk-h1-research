#!/usr/bin/env python3
"""Verify user-supplied and derived private inputs without publishing them."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(16 * 1024 * 1024):
            value.update(chunk)
    return value.hexdigest().upper()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-missing", action="store_true")
    args = parser.parse_args()
    records = json.loads((ROOT / "inputs.lock.json").read_text(encoding="utf-8"))["files"]
    verified = 0
    missing = []
    for record in records:
        path = ROOT / record["path"]
        if not path.is_file():
            if record.get("required", False):
                missing.append(record["path"])
            continue
        size = path.stat().st_size
        actual = digest(path)
        if size != record["bytes"] or actual != record["sha256"]:
            raise SystemExit(
                f"input mismatch: {record['path']} bytes={size} sha256={actual}"
            )
        verified += 1
        print(f"verified={record['path']}")
    if missing and not args.allow_missing:
        raise SystemExit("missing required inputs: " + ", ".join(missing))
    print(f"verified_files={verified} missing_required={len(missing)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
