#!/usr/bin/env python3
"""Replace local build identity in selected UTF-8 text artifacts."""

from __future__ import annotations

import argparse
import json
import os
import re
import socket
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def decode_artifact(data: bytes) -> tuple[str, str]:
    if data.startswith(b"\xff\xfe") or data.startswith(b"\xfe\xff"):
        return data.decode("utf-16"), "utf-16"
    if data.startswith(b"\xef\xbb\xbf"):
        return data.decode("utf-8-sig"), "utf-8-sig"
    return data.decode("utf-8"), "utf-8"


def variants(value: str) -> set[str]:
    return {
        value,
        value.replace("\\", "/"),
        json.dumps(value)[1:-1],
        json.dumps(value.replace("\\", "/"))[1:-1],
    }


def sanitize_text(text: str) -> str:
    home = str(Path.home().resolve())
    workspace = str(REPOSITORY_ROOT)
    replacements: list[tuple[str, str]] = []
    for source in variants(workspace):
        replacements.append((source, "${WORKSPACE}"))
    for source in variants(home):
        replacements.append((source, "%USERPROFILE%"))
    for source, target in sorted(replacements, key=lambda item: len(item[0]), reverse=True):
        text = text.replace(source, target)

    username = os.environ.get("USERNAME", "")
    hostname = os.environ.get("COMPUTERNAME") or socket.gethostname()
    if username and hostname:
        actor = re.compile(
            rf"{re.escape(username)}\s+<{re.escape(username)}@{re.escape(hostname)}(?:\.\(none\))?>",
            re.IGNORECASE,
        )
        text = actor.sub("builder <builder@localhost>", text)
        text = re.sub(
            rf"{re.escape(username)}@{re.escape(hostname)}(?:\.\(none\))?",
            "builder@localhost",
            text,
            flags=re.IGNORECASE,
        )
    if hostname:
        text = re.sub(re.escape(hostname), "BUILDHOST", text, flags=re.IGNORECASE)
    return text


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="+", type=Path)
    args = parser.parse_args()
    changed = 0
    for path in args.files:
        original, encoding = decode_artifact(path.read_bytes())
        sanitized = sanitize_text(original)
        if sanitized != original:
            path.write_bytes(sanitized.encode(encoding))
            changed += 1
            print(path)
    print(f"changed={changed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
