#!/usr/bin/env python3
"""Create a short encrypted EEBBKBMD clip from a compatible source video.

This keeps a contiguous prefix of the source's interleaved MP3/MPEG-4 frames,
rebuilds both relative and absolute indexes, and re-encrypts the six-record
payload.  It is intended for compatibility testing on small H1 FAT volumes.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import lzma
import struct
import sys
import types
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parents[1]
DEFAULT_DECRYPTOR = (
    REPOSITORY / "work" / "references" / "h2-video-decryptor" / "scripts" / "h2_decrypt.py"
)


def load_decryptor(path: Path):
    # Parsing and cipher helpers do not need FFmpeg.  Permit a source checkout
    # without its optional imageio-ffmpeg runtime dependency.
    sys.modules.setdefault("imageio_ffmpeg", types.SimpleNamespace())
    for search_path in (path.parent, path.parent.parent):
        if str(search_path) not in sys.path:
            sys.path.insert(0, str(search_path))
    spec = importlib.util.spec_from_file_location("h2_bmd_clip_decryptor", path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def read_u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def write_u32(data: bytearray, offset: int, value: int) -> None:
    struct.pack_into("<I", data, offset, value & 0xFFFFFFFF)


def build_track_record(
    source: bytes,
    track,
    count: int,
    *,
    video: bool,
    offset_shift: int = 0,
) -> bytes:
    count_offset = 0x48 if video else 0x44
    sizes_offset = 0x4C if video else 0x48
    original_count = len(track.sizes)
    original_offsets_header = sizes_offset + original_count * 4
    original_keyframes_header = original_offsets_header + 0x10 + original_count * 4

    sizes = track.sizes[:count]
    offsets = tuple(value + offset_shift for value in track.offsets[:count])
    durations = track.durations_ms[:count]
    output = bytearray(source[:sizes_offset])
    write_u32(output, count_offset, count)
    output.extend(struct.pack(f"<{count}I", *sizes))

    offsets_header = bytearray(source[original_offsets_header : original_offsets_header + 0x10])
    write_u32(offsets_header, 0x0C, count)
    output.extend(offsets_header)
    output.extend(struct.pack(f"<{count}I", *offsets))

    if video:
        original_keyframe_count = read_u32(source, original_keyframes_header + 0x0C)
        original_keyframes = struct.unpack_from(
            f"<{original_keyframe_count}I", source, original_keyframes_header + 0x10
        )
        keyframes = tuple(value for value in original_keyframes if value < count)
        keyframe_header = bytearray(
            source[original_keyframes_header : original_keyframes_header + 0x10]
        )
        write_u32(keyframe_header, 0x0C, len(keyframes))
        output.extend(keyframe_header)
        output.extend(struct.pack(f"<{len(keyframes)}I", *keyframes))
        original_durations_header = (
            original_keyframes_header + 0x10 + original_keyframe_count * 4
        )
    else:
        original_durations_header = original_keyframes_header

    duration_header = bytearray(
        source[original_durations_header : original_durations_header + 0x10]
    )
    write_u32(duration_header, 0x0C, count)
    output.extend(duration_header)
    output.extend(struct.pack(f"<{count}I", *durations))

    write_u32(output, 0, len(output))
    if video:
        write_u32(output, 0x20, sum(durations))
        write_u32(output, 0x28, len(output) - 0x28)
        write_u32(output, 0x30, count * 4 + 0x1C)
        write_u32(output, 0x40, sum(sizes))
    else:
        write_u32(output, 0x1C, sum(durations))
        write_u32(output, 0x24, len(output) - 0x24)
        write_u32(output, 0x2C, count * 4 + 0x1C)
        write_u32(output, 0x3C, sum(sizes))
    return bytes(output)


def make_lzma_index_record(source: bytes, index_data: bytes) -> bytes:
    compressed = lzma.compress(index_data, format=lzma.FORMAT_ALONE)
    output = bytearray(source[:0x30])
    output.extend(compressed)
    write_u32(output, 0, len(output))
    write_u32(output, 0x20, len(index_data))
    write_u32(output, 0x24, len(compressed))
    return bytes(output)


def make_tail_index_record(source: bytes, index_data: bytes) -> bytes:
    output = bytearray(source[:8])
    output.extend(index_data)
    write_u32(output, 0, len(output))
    return bytes(output)


def rebase_extb(tail: bytes, old_base: int, new_base: int, old_file_size: int) -> tuple[bytes, int]:
    output = bytearray(tail)
    patched = 0
    delta = new_base - old_base
    for offset in range(0, len(output) - 3, 4):
        value = read_u32(output, offset)
        if old_base <= value < old_file_size:
            write_u32(output, offset, value + delta)
            patched += 1
    return bytes(output), patched


def select_prefix(audio, video, target_ms: int) -> tuple[int, int, int]:
    ranges = sorted(
        [(offset, size, 0, index) for index, (offset, size) in enumerate(zip(audio.offsets, audio.sizes))]
        + [(offset, size, 1, index) for index, (offset, size) in enumerate(zip(video.offsets, video.sizes))]
    )
    audio_count = 0
    video_count = 0
    audio_ms = 0
    video_ms = 0
    end = 8
    for offset, size, kind, index in ranges:
        if offset != end:
            raise ValueError(f"source frame map is not contiguous at 0x{end:X}")
        end += size
        if kind == 0:
            if index != audio_count:
                raise ValueError("audio index is not ordered")
            audio_ms += audio.durations_ms[index]
            audio_count += 1
        else:
            if index != video_count:
                raise ValueError("video index is not ordered")
            video_ms += video.durations_ms[index]
            video_count += 1
        if audio_ms >= target_ms and video_ms >= target_ms:
            break
    if audio_ms < target_ms or video_ms < target_ms:
        raise ValueError("source is shorter than the requested test duration")
    return audio_count, video_count, end


def build_clip(source: bytes, target_ms: int, decryptor) -> tuple[bytes, dict[str, object]]:
    weights, xor_table = decryptor.load_decryption_tables(None, None, None)
    plaintext = decryptor.decrypt_bmd_payload(source, weights, xor_table)
    records = decryptor.parse_records(plaintext)
    if len(records) != 6:
        raise ValueError("source does not contain six BMD inner records")
    index_data = lzma.decompress(records[3][0x30:], format=lzma.FORMAT_ALONE)
    index_records = decryptor.parse_records(index_data)
    if len(index_records) != 2:
        raise ValueError("source index does not contain audio and video records")
    audio = decryptor.parse_track_index(index_records[0], video=False)
    video = decryptor.parse_track_index(index_records[1], video=True)
    audio_count, video_count, media_end = select_prefix(audio, video, target_ms)

    relative_audio = build_track_record(index_records[0], audio, audio_count, video=False)
    relative_video = build_track_record(index_records[1], video, video_count, video=True)
    relative_index = relative_audio + relative_video
    compressed_index = make_lzma_index_record(records[3], relative_index)
    media = bytearray(records[4][:media_end])
    write_u32(media, 0, len(media))

    media_start = len(records[0]) + len(records[1]) + len(records[2]) + len(compressed_index)
    absolute_audio = build_track_record(
        index_records[0], audio, audio_count, video=False, offset_shift=media_start
    )
    absolute_video = build_track_record(
        index_records[1], video, video_count, video=True, offset_shift=media_start
    )
    tail_index = make_tail_index_record(records[5], absolute_audio + absolute_video)
    new_plaintext = b"".join(records[:3]) + compressed_index + bytes(media) + tail_index

    header = bytearray(source[: decryptor.BMD_HEADER_SIZE])
    write_u32(header, 0x14, len(new_plaintext))
    old_extb = read_u32(source, 0x218)
    new_extb = (decryptor.BMD_HEADER_SIZE + len(new_plaintext) + 0x0F) & ~0x0F
    write_u32(header, 0x218, new_extb)
    encrypted = decryptor.decrypt_bmd_payload(
        bytes(header) + new_plaintext, weights, xor_table
    )
    padding = bytes(new_extb - decryptor.BMD_HEADER_SIZE - len(encrypted))
    rebased_tail, rebased_pointers = rebase_extb(
        source[old_extb:], old_extb, new_extb, len(source)
    )
    output = bytes(header) + encrypted + padding + rebased_tail

    verified_plaintext = decryptor.decrypt_bmd_payload(output, weights, xor_table)
    if verified_plaintext != new_plaintext:
        raise AssertionError("encrypted clip did not decrypt byte-for-byte")
    recovered_audio, recovered_video, checked_audio_count, checked_video_count = (
        decryptor.recover_streams(verified_plaintext)
    )
    if checked_audio_count != audio_count or checked_video_count != video_count:
        raise AssertionError("rebuilt index frame counts differ after parsing")
    report = {
        "format": "eebbkbmd-test-clip-v1",
        "requested_duration_ms": target_ms,
        "audio_frames": audio_count,
        "video_frames": video_count,
        "audio_stream_bytes": len(recovered_audio),
        "video_stream_bytes": len(recovered_video),
        "encrypted_bytes": len(output),
        "plaintext_bytes": len(new_plaintext),
        "extb_rebased_pointers": rebased_pointers,
        "verified": True,
    }
    return output, report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--duration-ms", type=int, default=5000)
    parser.add_argument("--decryptor", type=Path, default=DEFAULT_DECRYPTOR)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if args.duration_ms <= 0:
        raise ValueError("duration must be positive")
    decryptor = load_decryptor(args.decryptor.resolve(strict=True))
    output, report = build_clip(args.source.read_bytes(), args.duration_ms, decryptor)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(output)
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered, encoding="utf-8", newline="\n")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
