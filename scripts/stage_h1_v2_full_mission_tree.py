#!/usr/bin/env python3
"""Stage the complete V2 filesystem plus the full V1 Mission payload."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(16 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest().upper()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v2-root", type=Path, required=True)
    parser.add_argument("--mission-bda", type=Path, required=True)
    parser.add_argument("--data-lib", type=Path, required=True)
    parser.add_argument("--data-lib-index", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    source_root = args.v2_root.resolve(strict=True)
    output = args.output.resolve()
    if output.exists():
        raise FileExistsError(f"refusing to overwrite existing output: {output}")
    sources = {
        "应用/程序/使命.bda": args.mission_bda.resolve(strict=True),
        "应用/数据/游戏/LYXZ/DataLib.dat": args.data_lib.resolve(strict=True),
        "应用/数据/游戏/LYXZ/DataLibIndex.dat": args.data_lib_index.resolve(strict=True),
    }

    shutil.copytree(source_root, output)
    rows = []
    for relative, source in sources.items():
        target = output.joinpath(*relative.split("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        rows.append({
            "path": relative,
            "bytes": target.stat().st_size,
            "sha256": sha256(target),
        })

    print(json.dumps({
        "format": "bbk-h1-v2-full-mission-tree-v1",
        "v2_files": sum(path.is_file() for path in source_root.rglob("*")),
        "output_files": sum(path.is_file() for path in output.rglob("*")),
        "installed": rows,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
