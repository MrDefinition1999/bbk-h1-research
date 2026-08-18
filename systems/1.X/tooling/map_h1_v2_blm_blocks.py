#!/usr/bin/env python3
"""Map EEBBKBLM tail markers to records in the PC ``bbk.`` index."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tail_analysis", type=Path)
    parser.add_argument("bbk_index", type=Path)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()
    tail = json.loads(args.tail_analysis.read_text(encoding="utf-8"))
    wrapper = json.loads(args.bbk_index.read_text(encoding="utf-8"))
    records = wrapper["records"]
    by_offset = {int(record["payload_offset"]): record for record in records}
    markers = [
        int(hit["offset"])
        for hit in tail["marker_hits"]
        if hit["marker"] == "EEBBKBLM"
    ]
    rows = []
    starts = []
    for marker in markers:
        wrapper_offset = marker + 126976
        record = by_offset.get(wrapper_offset)
        starts.append(None if record is None else int(record["index"]))
    for marker, start in zip(markers, starts):
        wrapper_offset = marker + 126976
        record = by_offset.get(wrapper_offset)
        if start is None:
            end = None
            group = []
        else:
            next_starts = [value for value in starts if value is not None and value > start]
            end = (min(next_starts) - 1) if next_starts else len(records) - 1
            group = records[start : end + 1]
        rows.append(
            {
                "tail_offset": marker,
                "wrapper_offset": wrapper_offset,
                "record_index": None if record is None else record["index"],
                "record_size": None if record is None else record["size"],
                "record_prefix": None if record is None else record["prefix_hex"],
                "record_text": None if record is None else record["ascii_prefix"],
                "record_start": start,
                "record_end": end,
                "record_count": len(group),
                "record_size_sum": sum(int(item["size"]) for item in group),
            }
        )
    result = {"mapping_delta": 126976, "marker_count": len(markers), "rows": rows}
    rendered = json.dumps(result, ensure_ascii=True, indent=2) + "\n"
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
