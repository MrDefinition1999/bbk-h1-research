#!/usr/bin/env python3
"""Patch V2 firmware drive prefixes for an internal NAND mounted as B:."""

from __future__ import annotations

import argparse
from pathlib import Path


REPLACEMENTS = ((b"A:\\", b"B:\\"), (b"a:\\", b"b:\\"))


def patch(source: Path, output: Path) -> dict[str, int | str]:
    data = source.read_bytes()
    patched = data
    counts: dict[str, int] = {}
    for old, new in REPLACEMENTS:
        if len(old) != len(new):
            raise AssertionError("drive-prefix replacement must preserve length")
        count = patched.count(old)
        if count:
            patched = patched.replace(old, new)
        counts[old.decode("ascii")] = count
    if not any(counts.values()):
        raise ValueError(f"no V2 drive prefixes found in {source}")
    if len(patched) != len(data):
        raise AssertionError("drive-prefix patch changed the firmware size")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(patched)
    return {
        "source": source.as_posix(),
        "output": output.as_posix(),
        "bytes": len(data),
        **counts,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = patch(args.source, args.output)
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
