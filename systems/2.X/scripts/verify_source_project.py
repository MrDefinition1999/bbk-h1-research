#!/usr/bin/env python3
"""Check the source-only repository boundary before publishing."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKIP = {".git", ".local", "build", "dist", "__pycache__"}
PROHIBITED = {
    ".7z", ".bda", ".bin", ".dll", ".dlx", ".elf", ".exe", ".i64",
    ".id0", ".id1", ".id2", ".log", ".nam", ".pak", ".rar", ".raw",
    ".rom", ".til", ".zip",
}


def files():
    for path in ROOT.rglob("*"):
        if not path.is_file() or any(part in SKIP for part in path.relative_to(ROOT).parts):
            continue
        yield path


def main() -> int:
    required = {
        "README.md", "README.en.md", "LICENSE", "NOTICE",
        "components.lock.json", "inputs.lock.json", "docs/reproduce.md",
        "scripts/bootstrap_components.py", "scripts/verify_inputs.py",
        "tooling/audit_release_secrets.py",
    }
    present = {path.relative_to(ROOT).as_posix() for path in files()}
    missing = sorted(required - present)
    if missing:
        raise SystemExit("missing project files: " + ", ".join(missing))
    prohibited = sorted(
        path.relative_to(ROOT).as_posix()
        for path in files()
        if path.suffix.casefold() in PROHIBITED
    )
    if prohibited:
        raise SystemExit("proprietary/generated files entered source tree: " + ", ".join(prohibited))
    lock = json.loads((ROOT / "components.lock.json").read_text(encoding="utf-8"))
    for record in lock["components"]:
        commit = record["commit"]
        if len(commit) != 40 or any(ch not in "0123456789abcdef" for ch in commit):
            raise SystemExit(f"invalid pinned commit for {record['name']}: {commit}")
    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "verify_inputs.py"), "--allow-missing"],
        cwd=ROOT,
        check=True,
    )
    print(f"source_files={len(present)} prohibited=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
