#!/usr/bin/env python3
"""Fail when release artifacts expose local paths, host identity, or secrets."""

from __future__ import annotations

import argparse
import os
import re
import socket
import sys
import zipfile
from collections.abc import Iterable
from pathlib import Path
from typing import BinaryIO


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TARGETS = [
    REPOSITORY_ROOT / "deliverables",
    REPOSITORY_ROOT / "emulator" / "windows-x86_64",
    REPOSITORY_ROOT / "h1-bda-sdk" / "build",
    REPOSITORY_ROOT / "docs",
]
CHUNK_SIZE = 16 * 1024 * 1024
OVERLAP = 4096

SECRET_PATTERNS = {
    "OpenAI-style API key": re.compile(
        rb"(?<![A-Za-z0-9_-])sk-(?=[A-Za-z0-9_-]{24,}(?:[^A-Za-z0-9_-]|$))"
        rb"(?=[A-Za-z0-9_-]*[0-9])[A-Za-z0-9_-]{24,}(?![A-Za-z0-9_-])"
    ),
    "GitHub token": re.compile(
        rb"(?<![A-Za-z0-9_])(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{22,})"
        rb"(?![A-Za-z0-9_])"
    ),
    "AWS access key": re.compile(rb"AKIA[0-9A-Z]{16}"),
    "Bearer token": re.compile(
        rb"(?i)(?<![A-Za-z0-9_-])Bearer[ \t]+[A-Za-z0-9._~+/=-]{20,}"
    ),
    "private key": re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
}
SECRET_MARKERS = {
    "OpenAI-style API key": (b"sk-",),
    "GitHub token": (
        b"ghp_",
        b"gho_",
        b"ghu_",
        b"ghs_",
        b"ghr_",
        b"github_pat_",
    ),
    "AWS access key": (b"AKIA",),
    "Bearer token": (b"bearer",),
    "private key": (b"-----begin",),
}
UTF16_MARKERS = (
    b"C\x00:\x00\\\x00",
    b"C\x00:\x00/\x00",
    b"/\x00h\x00o\x00m\x00e\x00/\x00",
    b"/\x00U\x00s\x00e\x00r\x00s\x00/\x00",
    b"s\x00k\x00-\x00",
    b"g\x00h\x00p\x00_\x00",
    b"g\x00h\x00o\x00_\x00",
    b"g\x00h\x00u\x00_\x00",
    b"g\x00h\x00s\x00_\x00",
    b"g\x00h\x00r\x00_\x00",
    b"g\x00i\x00t\x00h\x00u\x00b\x00_\x00p\x00a\x00t\x00_\x00",
    b"A\x00K\x00I\x00A\x00",
    b"B\x00e\x00a\x00r\x00e\x00r\x00",
    b"-\x00-\x00-\x00-\x00-\x00B\x00E\x00G\x00I\x00N\x00",
)
CANDIDATE_MARKERS = (
    b":\\users\\",
    b":/users/",
    b":\\\\users\\\\",
    b":\\documents and settings\\",
    b":/documents and settings/",
    b"/home/",
    b"/users/",
    b".codex",
    b"desktop-",
    b"sk-",
    b"ghp_",
    b"gho_",
    b"ghu_",
    b"ghs_",
    b"ghr_",
    b"github_pat_",
    b"akia",
    b"bearer",
    b"-----begin",
)

PLACEHOLDER_USER_NAMES = {
    b"all users",
    b"default",
    b"distutils",
    b"example",
    b"exampleuser",
    b"foo",
    b"myuser",
    b"public",
    b"test",
    b"to",
    b"trentm",
    b"user",
    b"username",
}


def canonical_path(value: str) -> bytes:
    return value.replace("/", "\\").replace("\\\\", "\\").lower().encode()


def identity_needles() -> dict[str, tuple[bytes, ...]]:
    hostname = os.environ.get("COMPUTERNAME") or socket.gethostname()
    workspace = str(REPOSITORY_ROOT)
    home = str(Path.home().resolve())
    return {
        "current workspace path": (canonical_path(workspace),),
        "current user profile": (canonical_path(home),),
        "current host name": (hostname.lower().encode(),) if hostname else (),
    }


IDENTITY_NEEDLES = identity_needles()


def utf16_identity_markers() -> tuple[bytes, ...]:
    markers: list[bytes] = []
    for needles in IDENTITY_NEEDLES.values():
        for needle in needles:
            markers.append(needle.decode("utf-8").encode("utf-16le"))
    return tuple(markers)


IDENTITY_UTF16_MARKERS = utf16_identity_markers()


def has_real_windows_profile(normalized: bytes) -> bool:
    pattern = re.compile(
        rb"(?i)[a-z]:\\(?:users|documents and settings)\\([^\\\x00\r\n\t]+)"
    )
    return any(
        match.group(1).strip(b"<>\"').,;:{[]} ").lower() not in PLACEHOLDER_USER_NAMES
        for match in pattern.finditer(normalized)
    )


def has_real_unix_profile(lowered: bytes) -> bool:
    pattern = re.compile(
        rb"(?:^|[\x00\s\"'=(])/(?:home|users)/([^/\x00\s]+)/"
    )
    return any(
        match.group(1).lower() not in PLACEHOLDER_USER_NAMES
        for match in pattern.finditer(lowered)
    )


def inspect_chunk(chunk: bytes) -> set[str]:
    findings: set[str] = set()
    lowered_chunk = chunk.lower()
    has_utf16_candidate = any(
        marker.lower() in lowered_chunk
        for marker in (*UTF16_MARKERS, *IDENTITY_UTF16_MARKERS)
    )
    identity_candidates = tuple(
        needle for needles in IDENTITY_NEEDLES.values() for needle in needles
    )
    if (
        not has_utf16_candidate
        and not any(marker in lowered_chunk for marker in CANDIDATE_MARKERS)
        and not any(needle in lowered_chunk for needle in identity_candidates)
    ):
        return findings
    views = [chunk]
    if has_utf16_candidate:
        views.extend((chunk[::2], chunk[1::2]))
    for view in views:
        lowered = view.lower()
        normalized = lowered.replace(b"\\\\", b"\\").replace(b"/", b"\\")
        if has_real_windows_profile(normalized):
            findings.add("Windows user-profile path")
        if has_real_unix_profile(lowered):
            findings.add("Unix user-profile path")
        for label, needles in IDENTITY_NEEDLES.items():
            comparable = normalized if "path" in label or "profile" in label else lowered
            if any(needle and needle in comparable for needle in needles):
                findings.add(label)
        for label, pattern in SECRET_PATTERNS.items():
            if any(marker.lower() in lowered for marker in SECRET_MARKERS[label]) and pattern.search(view):
                findings.add(label)
    return findings


def inspect_stream(stream: BinaryIO) -> set[str]:
    findings: set[str] = set()
    tail = b""
    while chunk := stream.read(CHUNK_SIZE):
        combined = tail + chunk
        findings.update(inspect_chunk(combined))
        tail = combined[-OVERLAP:]
    return findings


def inspect_file(path: Path) -> list[tuple[str, str]]:
    with path.open("rb") as stream:
        results = [(str(path), item) for item in inspect_stream(stream)]
    if path.suffix.lower() != ".zip":
        return results
    try:
        with zipfile.ZipFile(path) as archive:
            for entry in archive.infolist():
                if entry.is_dir():
                    continue
                name_findings = inspect_chunk(entry.filename.encode("utf-8", errors="replace"))
                results.extend((f"{path}!{entry.filename}", item) for item in name_findings)
                with archive.open(entry) as stream:
                    results.extend(
                        (f"{path}!{entry.filename}", item)
                        for item in inspect_stream(stream)
                    )
    except (OSError, RuntimeError, zipfile.BadZipFile) as error:
        results.append((str(path), f"uninspectable ZIP: {error}"))
    return results


def files_from_targets(targets: Iterable[Path]) -> Iterable[Path]:
    seen: set[Path] = set()
    for target in targets:
        if target.is_file():
            candidates = [target]
        elif target.is_dir():
            candidates = (item for item in target.rglob("*") if item.is_file())
        else:
            raise FileNotFoundError(target)
        for candidate in candidates:
            resolved = candidate.resolve()
            if resolved not in seen:
                seen.add(resolved)
                yield resolved


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("targets", nargs="*", type=Path)
    args = parser.parse_args()
    targets = args.targets or DEFAULT_TARGETS
    findings: list[tuple[str, str]] = []
    count = 0
    for path in files_from_targets(targets):
        count += 1
        findings.extend(inspect_file(path))
    findings = sorted(set(findings))
    if findings:
        for path, rule in findings:
            print(f"FAIL {rule}: {path}")
        print(f"audited_files={count} findings={len(findings)}")
        return 1
    print(f"audited_files={count} findings=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
