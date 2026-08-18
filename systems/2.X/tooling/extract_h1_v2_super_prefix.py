#!/usr/bin/env python3
"""Extract only a bounded prefix from a PC updater BZip2 member."""

from __future__ import annotations

import argparse
import bz2
from pathlib import Path


def extract(source: Path, member_offset: int, length: int, output: Path) -> int:
    with source.open("rb") as handle:
        handle.seek(member_offset)
        decoder = bz2.BZ2Decompressor()
        with output.open("wb") as target:
            while not decoder.eof and target.tell() < length:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                produced = decoder.decompress(chunk)
                remaining = length - target.tell()
                if produced and remaining > 0:
                    target.write(produced[:remaining])
    return output.stat().st_size


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("member_offset", type=lambda value: int(value, 0))
    parser.add_argument("length", type=lambda value: int(value, 0))
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    print(f"extracted={extract(args.source, args.member_offset, args.length, args.output)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
