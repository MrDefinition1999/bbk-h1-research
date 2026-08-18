#!/usr/bin/env python3
"""Remove build-machine identity prefixes from release binaries in place."""

from __future__ import annotations

import argparse
import os
import socket
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def padded_replacement(length: int, label: str, separator: str) -> str:
    base = f"R:{separator}release{separator}{label}"
    if len(base) > length:
        base = f"R:{separator}r"
    return base + "_" * (length - len(base))


def replacement_pairs(extra_roots: list[str] | None = None) -> list[tuple[str, str]]:
    home = Path.home().resolve()
    roots = [
        (str(REPOSITORY_ROOT), "repo"),
        (str(home), "home"),
    ]
    roots.extend(
        (str(Path(root).resolve()), f"build{index}")
        for index, root in enumerate(extra_roots or [])
    )
    pairs: list[tuple[str, str]] = []
    for source, label in roots:
        for variant in (source, source.replace("\\", "/")):
            separator = "/" if "/" in variant else "\\"
            pairs.append((variant, padded_replacement(len(variant), label, separator)))

    host = os.environ.get("COMPUTERNAME") or socket.gethostname()
    if host:
        replacement = "BUILDHOST"[: len(host)] + "_" * max(0, len(host) - 9)
        pairs.append((host, replacement))
    return sorted(set(pairs), key=lambda item: len(item[0]), reverse=True)


def replace_case_insensitive(data: bytes, old: bytes, new: bytes) -> tuple[bytes, int]:
    if len(old) != len(new):
        raise ValueError("binary replacements must preserve length")
    lowered = data.lower()
    needle = old.lower()
    cursor = 0
    count = 0
    output = bytearray(data)
    while (index := lowered.find(needle, cursor)) >= 0:
        output[index : index + len(old)] = new
        cursor = index + len(old)
        count += 1
    return bytes(output), count


def sanitize(path: Path, extra_roots: list[str] | None = None) -> int:
    data = path.read_bytes()
    total = 0
    for old_text, new_text in replacement_pairs(extra_roots):
        for encoding in ("utf-8", "utf-16le"):
            old = old_text.encode(encoding)
            new = new_text.encode(encoding)
            data, count = replace_case_insensitive(data, old, new)
            total += count
    if total:
        path.write_bytes(data)
    return total


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--in-place", action="store_true", required=True)
    parser.add_argument(
        "--prefix",
        action="append",
        default=[],
        help="additional source or build root to remove (repeatable)",
    )
    parser.add_argument("files", nargs="+", type=Path)
    args = parser.parse_args()
    for path in args.files:
        if not path.is_file():
            raise FileNotFoundError(path)
        print(f"{path}: replacements={sanitize(path, args.prefix)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
