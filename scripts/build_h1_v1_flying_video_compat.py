#!/usr/bin/env python3
"""Repack the H1 2.X Flying Video player for the H1 V1.41 loader ABI.

The 2.X payload is position-dependent at 0x83C00040, while normal 1.X BDA
files enter at 0x83C00020.  This builder keeps the stock 1.X BDA envelope and
menu resources, inserts a 32-byte entry shim, and supplies compatibility GUI,
media, general, and extended-service tables for the unmodified 2.X code.

This is deliberately a V1.41-only compatibility build.  It validates the
known stock players and the service pointers used by the shim instead of
silently applying firmware-specific addresses to another 1.X release.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parents[1]
SDK = REPOSITORY / "h1-bda-sdk"
if str(SDK) not in sys.path:
    sys.path.insert(0, str(SDK))

from h1_bda.header import (  # noqa: E402
    CHECKSUM_OFFSET,
    CHECKSUM_XOR_KEY,
    ENCODED_WORD_COUNT,
    HEADER_SIZE,
    HEADER_XOR_KEY,
    decode_header,
)
from h1_bda.validate import validate_bda  # noqa: E402


V1_STOCK_BDA_SHA256 = "B964EB9CA0EF7172933D079E7209B7AE6E69CC4CD29C675814FCF348EA1853D0"
V2_PLAYER_BDA_SHA256 = "8ADFCF4981CA8ABDCA00854EF3CC499C2033976A96BC66717E18DC0A566D7043"

V1_OS_VA = 0x80004000
V1_OS_ELF_LOAD_OFFSET = 0x1000
V1_GUI_TABLE = 0x802AA110
V1_MEDIA_TABLE = 0x802A9EF0

V1_ENTRY = 0x83C00020
V2_ENTRY = 0x83C00040
COMPAT_BASE = 0x83F40000
GUI_TABLE = COMPAT_BASE
MEDIA_TABLE = COMPAT_BASE + 0xB00
GENERAL_TABLE = COMPAT_BASE + 0xC00
EXTENDED_TABLE = COMPAT_BASE + 0xF00
CODE_BASE = COMPAT_BASE + 0x1000

GUI_TABLE_SIZE = 0xB00
MEDIA_TABLE_SIZE = 0x100
GENERAL_TABLE_SIZE = 0x300
EXTENDED_TABLE_SIZE = 0x100


# 2.X GUI slot -> 1.X GUI slot.  Each moved service was matched in IDA by
# implementation and call contract.  Slots absent from this map retain the
# original V1.41 table entry copied into the compatibility table.
GUI_SLOT_MAP = {
    0x030: 0x030,
    0x03C: 0x03C,
    0x04C: 0x04C,
    0x050: 0x050,
    0x054: 0x054,
    0x07C: 0x084,
    0x080: 0x088,
    0x084: 0x08C,
    0x174: 0x17C,
    0x2F4: 0x2FC,
    0x598: 0x5A8,
    0x674: 0x6B8,
    0x678: 0x6BC,
    0x67C: 0x6C8,
    0x688: 0x72C,
    0x68C: 0x730,
    0x690: 0x734,
    0x6A4: 0x764,
    0x6A8: 0x768,
    0xA54: 0xA54,
    0xA58: 0xA58,
    0xA6C: 0xA6C,
}


# 2.X media/SYS slot -> 1.X media slot.  The three queue-reset helpers at
# 0xBC..0xC4 have no V1 table equivalent and are installed as conservative
# no-ops below; V1's 0x78 write service already starts its DMA queue.
MEDIA_SLOT_MAP = {
    0x06C: 0x06C,
    0x070: 0x070,
    0x074: 0x074,
    0x078: 0x078,
    0x07C: 0x080,
    0x080: 0x084,
    0x088: 0x0A0,
    0x0B8: 0x0D0,
}


# V2 general services were moved from several V1 tables into a new prefix
# table.  These are exact V1.41 implementation counterparts established by
# IDA comparison.  0x060 (the framebuffer base) is supplied by a shim helper.
GENERAL_POINTERS = {
    0x000: 0x80004C88,
    0x0AC: 0x80004480,
    0x0FC: 0x80040EBC,
    0x18C: 0x8001F378,
    0x190: 0x8001F398,
    0x194: 0x8001F3B4,
    0x198: 0x8001F3E8,
    0x1A0: 0x801EDD1C,
    0x1A8: 0x801EDD50,
    0x1B0: 0x801EDDDC,
    0x1B4: 0x801EDE64,
    0x1C0: 0x800DC9E8,
    0x23C: 0x8001F318,
    0x248: 0x8001F160,
    0x2A4: 0x801EBA4C,
    0x2D8: 0x800213D0,
    0x2DC: 0x800213DC,
    0x2E0: 0x8001F610,
}


# Expected V1.41 pointers guard the hard-coded ABI mapping against a different
# firmware image accidentally being supplied.
EXPECTED_POINTERS = {
    (V1_GUI_TABLE, 0x030): 0x80113070,
    (V1_GUI_TABLE, 0x084): 0x80102EB0,
    (V1_GUI_TABLE, 0x6B8): 0x8003B550,
    (V1_GUI_TABLE, 0x6BC): 0x8003B534,
    (V1_GUI_TABLE, 0x6C8): 0x8003B664,
    (V1_GUI_TABLE, 0x72C): 0x8002E540,
    (V1_GUI_TABLE, 0x730): 0x8002E5B0,
    (V1_GUI_TABLE, 0x734): 0x8002DCB0,
    (V1_GUI_TABLE, 0x764): 0x8002F944,
    (V1_GUI_TABLE, 0x768): 0x8002F954,
    (V1_MEDIA_TABLE, 0x06C): 0x801EB1E0,
    (V1_MEDIA_TABLE, 0x070): 0x801EA900,
    (V1_MEDIA_TABLE, 0x074): 0x801EC1C0,
    (V1_MEDIA_TABLE, 0x078): 0x801EAE70,
    (V1_MEDIA_TABLE, 0x080): 0x800043A0,
    (V1_MEDIA_TABLE, 0x0D0): 0x801EC300,
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def read_u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def write_u32(data: bytearray, offset: int, value: int) -> None:
    struct.pack_into("<I", data, offset, value & 0xFFFFFFFF)


def v1_os_offset(address: int) -> int:
    return V1_OS_ELF_LOAD_OFFSET + address - V1_OS_VA


def read_v1_pointer(v1_os: bytes, table: int, offset: int) -> int:
    location = v1_os_offset(table + offset)
    if location < 0 or location + 4 > len(v1_os):
        raise ValueError(f"V1 OS image does not contain 0x{table + offset:08X}")
    return read_u32(v1_os, location)


def verify_v1_os(v1_os: bytes) -> None:
    if not v1_os.startswith(b"\x7fELF"):
        raise ValueError("V1 OS input must be the wrapped ELF used by this project")
    for (table, offset), expected in EXPECTED_POINTERS.items():
        actual = read_v1_pointer(v1_os, table, offset)
        if actual != expected:
            raise ValueError(
                f"V1.41 service mismatch at 0x{table:08X}+0x{offset:X}: "
                f"0x{actual:08X}, expected 0x{expected:08X}"
            )


def copy_table(v1_os: bytes, address: int, size: int) -> bytearray:
    start = v1_os_offset(address)
    end = start + size
    if start < 0 or end > len(v1_os):
        raise ValueError(f"V1 OS table 0x{address:08X} is outside the ELF load image")
    return bytearray(v1_os[start:end])


def patch_table_from_slots(
    destination: bytearray,
    v1_os: bytes,
    source_table: int,
    mapping: dict[int, int],
) -> None:
    for destination_offset, source_offset in mapping.items():
        write_u32(
            destination,
            destination_offset,
            read_v1_pointer(v1_os, source_table, source_offset),
        )


def encode_i(opcode: int, rs: int, rt: int, immediate: int) -> int:
    return (opcode << 26) | (rs << 21) | (rt << 16) | (immediate & 0xFFFF)


def encode_j(address: int) -> int:
    if address & 3:
        raise ValueError(f"jump target 0x{address:08X} is not aligned")
    return (2 << 26) | ((address >> 2) & 0x03FFFFFF)


def load_immediate(register: int, value: int) -> list[int]:
    return [
        encode_i(0x0F, 0, register, value >> 16),
        encode_i(0x0D, register, register, value),
    ]


def words(values: list[int]) -> bytes:
    return struct.pack(f"<{len(values)}I", *values)


def make_init_code() -> bytes:
    # t0 = runtime prefix; t1 = each compatibility table address.
    instructions = [encode_i(0x0F, 0, 8, 0x83C0)]
    for prefix_offset, address in (
        (0x04, GUI_TABLE),
        (0x0C, MEDIA_TABLE),
        (0x18, GENERAL_TABLE),
        (0x30, EXTENDED_TABLE),
    ):
        instructions.extend(load_immediate(9, address))
        instructions.append(encode_i(0x2B, 8, 9, prefix_offset))
    instructions.extend((encode_j(V2_ENTRY), 0))
    return words(instructions)


def make_return_zero() -> bytes:
    # move v0, zero; jr ra; nop
    return words([0x00001021, 0x03E00008, 0x00000000])


def make_framebuffer_getter() -> bytes:
    # Read LCD_DA0, then the descriptor's source word, and return its uncached
    # KSEG1 alias.  V1.41 currently programs physical 0x01902000, but reading
    # the live descriptor also remains correct if the OS flips buffers.
    return words(
        [
            encode_i(0x0F, 0, 2, 0xB305),
            encode_i(0x23, 2, 2, 0x0040),
            encode_i(0x0F, 0, 3, 0x8000),
            0x00431025,
            encode_i(0x23, 2, 2, 0x0004),
            encode_i(0x0F, 0, 3, 0xA000),
            0x00431025,
            0x03E00008,
            0x00000000,
        ]
    )


def replace_fixed_string(data: bytearray, old: str, new: str, count: int) -> None:
    old_bytes = old.encode("gbk")
    new_bytes = new.encode("gbk")
    if len(new_bytes) > len(old_bytes):
        raise ValueError(f"replacement {new!r} is longer than {old!r}")
    positions: list[int] = []
    cursor = 0
    while True:
        cursor = data.find(old_bytes, cursor)
        if cursor < 0:
            break
        positions.append(cursor)
        cursor += len(old_bytes)
    if len(positions) != count:
        raise ValueError(f"found {len(positions)} copies of {old!r}, expected {count}")
    replacement = new_bytes + bytes(len(old_bytes) - len(new_bytes))
    for position in positions:
        data[position : position + len(old_bytes)] = replacement


def patch_v2_payload(payload: bytes) -> bytes:
    patched = bytearray(payload)
    replace_fixed_string(
        patched,
        "A:\\应用\\数据\\player.bin",
        "A:\\应用\\数据\\play2.bin",
        2,
    )
    replace_fixed_string(
        patched,
        "A:\\应用\\数据\\player.cfg",
        "A:\\应用\\数据\\play2.cfg",
        1,
    )
    replace_fixed_string(
        patched,
        "B:\\多媒体\\飞天影音\\",
        "A:\\飞天影音\\",
        2,
    )
    return bytes(patched)


def extract_payload(bda: bytes) -> tuple[int, bytes]:
    decoded = decode_header(bda)
    payload_offset = read_u32(decoded, 0x14)
    file_size_minus_4 = read_u32(decoded, 0x10)
    if file_size_minus_4 != len(bda) - 4:
        raise ValueError("BDA file-size field does not match the input")
    if payload_offset < HEADER_SIZE or payload_offset >= len(bda):
        raise ValueError(f"invalid BDA payload offset 0x{payload_offset:X}")
    return payload_offset, bda[payload_offset:]


def encode_preserved_header(stock_bda: bytes, total_size: int) -> bytes:
    header = bytearray(decode_header(stock_bda))
    write_u32(header, 0x10, total_size - 4)
    checksum = sum(header[:CHECKSUM_OFFSET]) & 0xFFFFFFFF
    write_u32(header, CHECKSUM_OFFSET, checksum ^ CHECKSUM_XOR_KEY)
    for index in range(ENCODED_WORD_COUNT):
        offset = index * 4
        write_u32(header, offset, read_u32(header, offset) ^ HEADER_XOR_KEY)
    return bytes(header[:HEADER_SIZE])


def build_compat_bda(stock_v1_bda: bytes, v2_bda: bytes, v1_os: bytes) -> tuple[bytes, dict[str, object]]:
    if sha256(stock_v1_bda) != V1_STOCK_BDA_SHA256:
        raise ValueError("stock V1 Flying Video BDA hash is not the supported V1.41 build")
    if sha256(v2_bda) != V2_PLAYER_BDA_SHA256:
        raise ValueError("V2 Flying Video BDA hash is not the analyzed 2010-08-31 build")
    verify_v1_os(v1_os)

    v1_payload_offset, v1_payload = extract_payload(stock_v1_bda)
    _v2_payload_offset, v2_payload = extract_payload(v2_bda)
    patched_v2 = patch_v2_payload(v2_payload)

    init_code = make_init_code()
    return_zero = make_return_zero()
    framebuffer_getter = make_framebuffer_getter()
    return_zero_address = CODE_BASE + len(init_code)
    framebuffer_address = return_zero_address + len(return_zero)

    gui = copy_table(v1_os, V1_GUI_TABLE, GUI_TABLE_SIZE)
    patch_table_from_slots(gui, v1_os, V1_GUI_TABLE, GUI_SLOT_MAP)
    write_u32(gui, 0x664, return_zero_address)

    media = copy_table(v1_os, V1_MEDIA_TABLE, MEDIA_TABLE_SIZE)
    patch_table_from_slots(media, v1_os, V1_MEDIA_TABLE, MEDIA_SLOT_MAP)
    for offset in (0x0BC, 0x0C0, 0x0C4):
        write_u32(media, offset, return_zero_address)

    general = bytearray(GENERAL_TABLE_SIZE)
    for offset, pointer in GENERAL_POINTERS.items():
        write_u32(general, offset, pointer)
    write_u32(general, 0x060, framebuffer_address)

    extended = bytearray(EXTENDED_TABLE_SIZE)
    write_u32(extended, 0x0DC, return_zero_address)
    write_u32(extended, 0x0F4, read_v1_pointer(v1_os, V1_GUI_TABLE, 0x6E4))
    write_u32(extended, 0x0F8, read_v1_pointer(v1_os, V1_GUI_TABLE, 0x6E8))

    entry_prefix = bytearray(0x20)
    write_u32(entry_prefix, 0, encode_j(CODE_BASE))
    write_u32(entry_prefix, 4, 0)
    write_u32(entry_prefix, 0x10, EXTENDED_TABLE)
    payload = entry_prefix + patched_v2
    compat_offset = COMPAT_BASE - V1_ENTRY
    if len(payload) > compat_offset:
        raise ValueError("2.X player overlaps the reserved compatibility area")
    payload.extend(bytes(compat_offset - len(payload)))
    payload.extend(gui)
    payload.extend(media)
    payload.extend(general)
    payload.extend(extended)
    if V1_ENTRY + len(payload) != CODE_BASE:
        raise AssertionError("compatibility table layout does not end at code base")
    payload.extend(init_code)
    payload.extend(return_zero)
    payload.extend(framebuffer_getter)

    padding = (-(v1_payload_offset + len(payload))) & 3
    total_size = v1_payload_offset + len(payload) + padding
    if len(payload) + padding > len(v1_payload):
        raise ValueError(
            f"compat payload requires 0x{len(payload) + padding:X} bytes, "
            f"stock V1 chain provides only 0x{len(v1_payload):X}"
        )
    prefix = bytearray(stock_v1_bda[:v1_payload_offset])
    prefix[:HEADER_SIZE] = encode_preserved_header(stock_v1_bda, total_size)
    output = bytes(prefix) + bytes(payload) + bytes(padding)

    report = {
        "format": "bbk-h1-v1-flying-video-compat-build-v1",
        "stock_v1_sha256": sha256(stock_v1_bda),
        "source_v2_sha256": sha256(v2_bda),
        "output_sha256": sha256(output),
        "payload_offset": v1_payload_offset,
        "payload_bytes": len(payload) + padding,
        "stock_payload_capacity": len(v1_payload),
        "spare_bytes": len(v1_payload) - len(payload) - padding,
        "v2_entry": f"0x{V2_ENTRY:08X}",
        "compatibility_base": f"0x{COMPAT_BASE:08X}",
        "resource_path": "A:\\应用\\数据\\play2.bin",
        "config_path": "A:\\应用\\数据\\play2.cfg",
        "media_path": "A:\\飞天影音\\",
        "gui_remaps": len(GUI_SLOT_MAP) + 1,
        "media_remaps": len(MEDIA_SLOT_MAP) + 3,
        "general_services": len(GENERAL_POINTERS) + 1,
    }
    return output, report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stock-v1-bda", type=Path, required=True)
    parser.add_argument("--v2-bda", type=Path, required=True)
    parser.add_argument("--v1-os-elf", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    output, report = build_compat_bda(
        args.stock_v1_bda.read_bytes(),
        args.v2_bda.read_bytes(),
        args.v1_os_elf.read_bytes(),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(output)
    validation = validate_bda(args.output)
    if not validation["ok"]:
        args.output.unlink(missing_ok=True)
        raise SystemExit("compatibility BDA failed validation: " + "; ".join(validation["errors"]))
    report["validation"] = {
        "ok": True,
        "title": validation["title"],
        "category": validation["category"],
    }
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered, encoding="utf-8", newline="\n")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
