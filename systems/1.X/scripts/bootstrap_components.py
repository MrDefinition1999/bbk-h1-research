#!/usr/bin/env python3
"""Clone and pin the public SDK and emulator components."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "components.lock.json"
COMPONENTS = ROOT / ".local" / "components"


def run(*args: str, cwd: Path | None = None) -> str:
    completed = subprocess.run(
        list(args), cwd=cwd, check=True, text=True, capture_output=True
    )
    return completed.stdout.strip()


def main() -> int:
    records = json.loads(LOCK.read_text(encoding="utf-8"))["components"]
    COMPONENTS.mkdir(parents=True, exist_ok=True)
    for record in records:
        destination = COMPONENTS / record["directory"]
        if not (destination / ".git").is_dir():
            if destination.exists():
                raise SystemExit(f"refusing non-Git component directory: {destination}")
            run("git", "clone", "--filter=blob:none", "--no-checkout", record["url"], str(destination))
        remote = run("git", "remote", "get-url", "origin", cwd=destination)
        if remote.rstrip("/").removesuffix(".git") != record["url"].rstrip("/").removesuffix(".git"):
            raise SystemExit(f"unexpected origin for {record['name']}: {remote}")
        run("git", "fetch", "--depth=1", "origin", record["commit"], cwd=destination)
        run("git", "checkout", "--detach", record["commit"], cwd=destination)
        actual = run("git", "rev-parse", "HEAD", cwd=destination)
        if actual != record["commit"]:
            raise SystemExit(f"commit mismatch for {record['name']}: {actual}")
        print(f"{record['name']}={actual}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
