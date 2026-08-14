#!/usr/bin/env python3
"""Remove reproducible CS15 optimization scratch data and test tool caches."""

from __future__ import annotations

import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "references" / "CS15-Lite-for9588"
KEEP_H1_BUILD = {"H1CS15Lite.bda"}


def checked(path: Path) -> Path:
    resolved = path.resolve()
    if resolved == ROOT or ROOT not in resolved.parents:
        raise RuntimeError(f"refusing path outside workspace: {resolved}")
    return resolved


def remove(path: Path) -> int:
    path = checked(path)
    if not path.exists():
        return 0
    if path.is_dir():
        size = sum(item.stat().st_size for item in path.rglob("*") if item.is_file())
        shutil.rmtree(path)
        return size
    size = path.stat().st_size
    path.unlink()
    return size


def main() -> int:
    targets: list[Path] = []
    h1_build = ENGINE / "build" / "h1"
    if h1_build.is_dir():
        targets.extend(item for item in h1_build.iterdir() if item.name not in KEEP_H1_BUILD)

    experiments = ROOT / "work" / "experiments"
    if experiments.is_dir():
        targets.extend(
            item for item in experiments.iterdir()
            if item.name.lower().startswith("cs15-")
            or item.name.lower().startswith("h1cs15lite-")
        )

    targets.append(ROOT / "work" / "tools" / "ziglang-portable")
    for parent in (ROOT / "scripts", ROOT / "h1-bda-sdk", ENGINE):
        if parent.is_dir():
            targets.extend(parent.rglob("__pycache__"))

    removed = 0
    for target in sorted(set(targets), key=lambda item: len(item.parts), reverse=True):
        removed += remove(target)
    print(f"removed_bytes={removed}")
    print(f"retained={next(iter(KEEP_H1_BUILD))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
