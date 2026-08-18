#!/usr/bin/env python3
"""Stage deterministic V2 first-boot configuration into the indexed filesystem."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class NativeConfig:
    name: str
    size: int
    sha256: str


NATIVE_CONFIGS = (
    NativeConfig(
        "Config.inf",
        1332,
        "06D353A111BC7C2AD6DAF9AC46391DC6525B8C3A0215899CF008AD0B67C11FA1",
    ),
    NativeConfig(
        "SysTp.cfg",
        76,
        "99A247782271425A437F7138D31EC70410E0FBE9FCAA422188046CD255DF02D6",
    ),
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest().upper()


def validate(path: Path, expected: NativeConfig) -> None:
    if not path.is_file():
        raise FileNotFoundError(path)
    size = path.stat().st_size
    if size != expected.size:
        raise ValueError(f"{expected.name}: expected {expected.size} bytes, got {size}")
    digest = sha256_file(path)
    if digest != expected.sha256:
        raise ValueError(
            f"{expected.name}: expected SHA-256 {expected.sha256}, got {digest}"
        )


def atomic_copy(source: Path, destination: Path) -> None:
    temporary = destination.with_name(destination.name + ".stage.tmp")
    if temporary.exists():
        temporary.unlink()
    try:
        with source.open("rb") as input_stream, temporary.open("xb") as output_stream:
            shutil.copyfileobj(input_stream, output_stream, 1024 * 1024)
            output_stream.flush()
            os.fsync(output_stream.fileno())
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()


def main() -> int:
    repository = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=repository / "work" / "v2-emulator" / "native-config",
    )
    parser.add_argument(
        "--system-data",
        type=Path,
        default=repository / "work" / "v2-indexed",
    )
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument(
        "--force",
        action="store_true",
        help="replace a destination file only when its verified bytes differ",
    )
    args = parser.parse_args()

    source_root = args.source.resolve()
    destination_root = args.system_data.resolve() / "系统" / "数据"
    if not source_root.is_dir():
        raise NotADirectoryError(source_root)
    if not args.system_data.resolve().is_dir():
        raise NotADirectoryError(args.system_data.resolve())

    report: list[dict[str, object]] = []
    for expected in NATIVE_CONFIGS:
        source = source_root / expected.name
        destination = destination_root / expected.name
        validate(source, expected)
        action = "checked"
        if destination.exists():
            try:
                validate(destination, expected)
                action = "unchanged"
            except ValueError:
                if not args.force:
                    raise FileExistsError(
                        f"{destination} differs from the verified native file; pass --force"
                    )
                if not args.check_only:
                    atomic_copy(source, destination)
                    validate(destination, expected)
                    action = "replaced"
        elif not args.check_only:
            destination_root.mkdir(parents=True, exist_ok=True)
            atomic_copy(source, destination)
            validate(destination, expected)
            action = "created"
        report.append(
            {
                "name": expected.name,
                "bytes": expected.size,
                "sha256": expected.sha256,
                "action": action,
            }
        )

    print(json.dumps({"format": "bbk-h1-v2-native-config-v1", "files": report}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
