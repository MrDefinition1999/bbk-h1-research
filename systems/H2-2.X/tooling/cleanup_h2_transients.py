#!/usr/bin/env python3
"""Plan or remove exact, reproducible H2 transients and the retired H1 x86 ZIP."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
H2_TARGETS = (
    REPOSITORY_ROOT / "work" / "h2" / "toolchain-temp",
    REPOSITORY_ROOT / "work" / "h2" / "mission-debug",
    REPOSITORY_ROOT / "work" / "h2" / "build-temp",
    REPOSITORY_ROOT / "work" / "h2" / "screencheck",
    REPOSITORY_ROOT / "systems" / "H2-2.X" / "runtime" / "__pycache__",
    REPOSITORY_ROOT / "systems" / "H2-2.X" / "tooling" / "__pycache__",
    REPOSITORY_ROOT / "emulator" / "h2" / "__pycache__",
    REPOSITORY_ROOT / "deliverables" / "bbk-h2-v2.zip",
    REPOSITORY_ROOT / "deliverables" / "bbk-h2-v2.2l-arm64-source-20260825.zip",
)
H1_X86_TARGETS = (
    REPOSITORY_ROOT
    / "deliverables"
    / "BBK-H1-emulator-x86_64-runtime-only-2026-08-04.zip",
)


def validate_exact_target(path: Path) -> Path:
    target = path.resolve()
    root = REPOSITORY_ROOT.resolve()
    if target == root or root not in target.parents:
        raise SystemExit(f"refusing target outside repository: {target}")
    allowed = {item.resolve() for item in (*H2_TARGETS, *H1_X86_TARGETS)}
    if target not in allowed:
        raise SystemExit(f"refusing non-allowlisted target: {target}")
    return target


def allocated_bytes(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    if path.is_dir():
        return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--delete", action="store_true", help="perform the exact deletions; default is plan only"
    )
    parser.add_argument(
        "--include-h1-x86",
        action="store_true",
        help="also remove the retired generated H1 x86-64 release ZIP",
    )
    args = parser.parse_args()
    requested = [*H2_TARGETS]
    if args.include_h1_x86:
        requested.extend(H1_X86_TARGETS)
    total = 0
    existing: list[tuple[Path, int]] = []
    for configured in requested:
        target = validate_exact_target(configured)
        size = allocated_bytes(target)
        if target.exists():
            existing.append((target, size))
            total += size
        print(f"{'DELETE' if args.delete else 'PLAN  '} {size:12d} {target.relative_to(REPOSITORY_ROOT)}")
    print(f"total_bytes={total}")
    if not args.delete:
        print("status=plan-only")
        return 0
    for target, _size in existing:
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
    print("status=deleted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
