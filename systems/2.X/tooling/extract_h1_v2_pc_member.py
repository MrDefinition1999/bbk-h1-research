#!/usr/bin/env python3
"""Extract the final V2 filesystem files from a PC updater BZip2 member."""

from __future__ import annotations

import argparse
import bz2
import hashlib
import json
import os
import shutil
import struct
import tempfile
from pathlib import Path

from decode_bda import HEADER_SIZE
from parse_h1_v2_upd import locate_table, open_image, parse_entries, safe_relative_path
from validate_h1_v2_bda_sources import validate_header


WRAPPER_HEADER_SIZE = 16
WRAPPER_RECORD_SIZE = 0x100
WRAPPER_RECORD_CAPACITY = 500
WRAPPER_PREFIX_SIZE = WRAPPER_HEADER_SIZE + WRAPPER_RECORD_CAPACITY * WRAPPER_RECORD_SIZE
READ_CHUNK = 1024 * 1024


def parse_records(prefix: bytes, entries) -> list[dict[str, object]]:
    if len(prefix) != WRAPPER_PREFIX_SIZE or prefix[:4] != b"bbk.":
        raise ValueError("invalid or incomplete bbk. wrapper prefix")
    count = struct.unpack_from("<I", prefix, 8)[0]
    if count != len(entries):
        raise ValueError(f"wrapper/UPD record count differs: {count}/{len(entries)}")
    records = []
    previous_end = WRAPPER_PREFIX_SIZE
    seen_paths: set[Path] = set()
    for index, entry in enumerate(entries):
        base = WRAPPER_HEADER_SIZE + index * WRAPPER_RECORD_SIZE
        size, relative_offset = struct.unpack_from("<II", prefix, base)
        if size != entry.size:
            raise ValueError(f"record {index} size differs: PC={size} SD={entry.size}")
        start = WRAPPER_HEADER_SIZE + relative_offset
        if start != previous_end:
            raise ValueError(
                f"record {index} is not contiguous: start={start} expected={previous_end}"
            )
        relative_path = safe_relative_path(entry.path)
        normalized = Path(*[part.casefold() for part in relative_path.parts])
        if normalized in seen_paths:
            raise ValueError(f"duplicate output path: {entry.path}")
        seen_paths.add(normalized)
        records.append(
            {
                "index": index,
                "path": entry.path,
                "relative_path": relative_path,
                "size": size,
                "start": start,
                "end": start + size,
            }
        )
        previous_end = start + size
    return records


def extract(sd_upd: Path, pc_updater: Path, member_offset: int, output: Path) -> dict[str, object]:
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise FileExistsError(f"refusing to replace existing output: {output}")

    handle, image = open_image(sd_upd)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output.name}.tmp-", dir=output.parent))
    try:
        entries = parse_entries(image, locate_table(image))
        decoder = bz2.BZ2Decompressor()
        prefix = bytearray()
        records: list[dict[str, object]] | None = None
        record_index = 0
        record_stream = None
        record_hash = None
        record_written = 0
        record_header = bytearray()
        manifest: list[dict[str, object]] = []
        output_offset = 0
        compressed_read = 0

        with pc_updater.open("rb") as stream:
            stream.seek(member_offset)
            while not decoder.eof:
                compressed = stream.read(READ_CHUNK)
                if not compressed:
                    raise ValueError("truncated BZip2 member")
                compressed_read += len(compressed)
                produced = decoder.decompress(compressed)
                if not produced:
                    continue
                chunk_start = output_offset
                chunk_end = chunk_start + len(produced)
                output_offset = chunk_end

                if len(prefix) < WRAPPER_PREFIX_SIZE:
                    amount = min(WRAPPER_PREFIX_SIZE - len(prefix), len(produced))
                    prefix.extend(produced[:amount])
                    if len(prefix) == WRAPPER_PREFIX_SIZE:
                        records = parse_records(bytes(prefix), entries)

                if records is None:
                    continue

                while record_index < len(records):
                    record = records[record_index]
                    start = int(record["start"])
                    end = int(record["end"])
                    if start >= chunk_end:
                        break
                    if end <= chunk_start:
                        raise ValueError(f"missed output bytes for record {record_index}")
                    overlap_start = max(start, chunk_start)
                    overlap_end = min(end, chunk_end)
                    if overlap_start >= overlap_end:
                        break

                    if record_stream is None:
                        if overlap_start != start:
                            raise ValueError(f"record {record_index} did not begin at its first byte")
                        destination = temporary / record["relative_path"]
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        record_stream = destination.open("wb")
                        record_hash = hashlib.sha256()
                        record_written = 0
                        record_header = bytearray()

                    block = produced[overlap_start - chunk_start : overlap_end - chunk_start]
                    record_stream.write(block)
                    record_hash.update(block)
                    record_written += len(block)
                    if len(record_header) < HEADER_SIZE:
                        record_header.extend(block[: HEADER_SIZE - len(record_header)])

                    if overlap_end < end:
                        break

                    record_stream.close()
                    record_stream = None
                    if record_written != int(record["size"]):
                        raise ValueError(
                            f"record {record_index} length differs: {record_written}/{record['size']}"
                        )
                    bda_valid = None
                    if str(record["path"]).lower().endswith(".bda"):
                        bda_valid, reason = validate_header(bytes(record_header), record_written)
                        if not bda_valid:
                            raise ValueError(f"record {record_index} invalid BDA: {reason}")
                    manifest.append(
                        {
                            "index": record_index,
                            "path": record["path"],
                            "size": record_written,
                            "sha256": record_hash.hexdigest(),
                            "bda_valid": bda_valid,
                        }
                    )
                    record_index += 1

        if record_stream is not None:
            record_stream.close()
            raise ValueError(f"incomplete final record {record_index}")
        if records is None or record_index != len(records):
            raise ValueError(
                f"not all records were extracted: {record_index}/{0 if records is None else len(records)}"
            )
        payload_end = int(records[-1]["end"])
        if output_offset < payload_end:
            raise ValueError(f"member output is short: {output_offset}/{payload_end}")

        os.replace(temporary, output)
        return {
            "sd_index": sd_upd.name,
            "pc_updater": pc_updater.name,
            "pc_member_offset": member_offset,
            "pc_member_compressed_size": compressed_read - len(decoder.unused_data),
            "pc_member_output_size": output_offset,
            "wrapper_prefix_size": WRAPPER_PREFIX_SIZE,
            "payload_end": payload_end,
            "trailing_output_size": output_offset - payload_end,
            "file_count": len(manifest),
            "bda_count": sum(1 for item in manifest if item["bda_valid"] is True),
            "files": manifest,
        }
    except BaseException:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise
    finally:
        image.close()
        handle.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sd_upd", type=Path, help="SD UPD used only for paths and sizes")
    parser.add_argument("pc_updater", type=Path)
    parser.add_argument("member_offset", type=lambda value: int(value, 0))
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()
    result = extract(args.sd_upd, args.pc_updater, args.member_offset, args.out)
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(rendered, encoding="utf-8")
    print(
        f"extracted={result['file_count']} bda_valid={result['bda_count']} "
        f"output_size={result['pc_member_output_size']} trailing={result['trailing_output_size']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
