#!/usr/bin/env python3
"""Create a hard-linked V2 filesystem tree with one BDA replacement."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


DEFAULT_REPLACEMENT_PATH = Path("应用") / "程序" / "中学时间.bda"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("replacement", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--path", type=Path, default=DEFAULT_REPLACEMENT_PATH)
    args = parser.parse_args()

    source = args.source.resolve(strict=True)
    replacement = args.replacement.resolve(strict=True)
    destination = args.destination.resolve()
    if destination.exists():
        raise FileExistsError(f"destination already exists: {destination}")
    if source == destination or source in destination.parents:
        raise ValueError("destination must not contain the source tree")
    if destination in source.parents:
        raise ValueError("destination must not be an ancestor of the source tree")

    files = sorted(path for path in source.rglob("*") if path.is_file())
    replacement_relative = args.path
    if not (source / replacement_relative).is_file():
        raise FileNotFoundError(source / replacement_relative)

    linked = 0
    destination.mkdir(parents=True)
    try:
        for source_file in files:
            relative = source_file.relative_to(source)
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if relative == replacement_relative:
                os.link(replacement, target)
            else:
                os.link(source_file, target)
            linked += 1
    except BaseException:
        for path in sorted(destination.rglob("*"), reverse=True):
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                path.rmdir()
        destination.rmdir()
        raise

    result = {
        "format": "h1-v2-hardlink-probe-tree-v1",
        "source_name": source.name,
        "destination_name": destination.name,
        "files_linked": linked,
        "replacement_path": replacement_relative.as_posix(),
        "replacement_name": replacement.name,
        "replacement_bytes": replacement.stat().st_size,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
