#!/usr/bin/env python3
"""Create an erased-block expansion of an H1 raw NAND for emulator use."""

from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path

from h1_ftl import RAW_ERASE_BLOCK_SIZE, scan_image


ERASED_CHUNK = b"\xFF" * (16 * 1024 * 1024)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--physical-blocks", type=int, default=8192)
    parser.add_argument("--scan-start-block", type=lambda value: int(value, 0), default=0x40)
    args = parser.parse_args()

    template = args.template.resolve(strict=True)
    output = args.output.resolve()
    if output.exists():
        raise FileExistsError(f"refusing to overwrite existing output: {output}")
    source = scan_image(template, args.scan_start_block)
    if args.physical_blocks <= source.physical_blocks:
        raise ValueError("target physical block count must exceed the template")

    target_bytes = args.physical_blocks * RAW_ERASE_BLOCK_SIZE
    output.parent.mkdir(parents=True, exist_ok=True)
    with template.open("rb") as input_stream, output.open("xb") as output_stream:
        shutil.copyfileobj(input_stream, output_stream, 16 * 1024 * 1024)
        remaining = target_bytes - template.stat().st_size
        while remaining:
            count = min(remaining, len(ERASED_CHUNK))
            output_stream.write(ERASED_CHUNK[:count])
            remaining -= count
        output_stream.flush()
        os.fsync(output_stream.fileno())

    check = scan_image(output, args.scan_start_block)
    free = sum(record.kind == "free" for record in check.records)
    print(json.dumps({
        "format": "bbk-h1-expanded-emulator-template-v1",
        "template_name": template.name,
        "output_name": output.name,
        "source_physical_blocks": source.physical_blocks,
        "target_physical_blocks": check.physical_blocks,
        "output_bytes": output.stat().st_size,
        "free_ftl_blocks": free,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
