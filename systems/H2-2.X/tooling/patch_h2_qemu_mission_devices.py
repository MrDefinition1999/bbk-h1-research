#!/usr/bin/env python3
"""Apply the narrow H2 Mission device fixes to the ARM64 QEMU build.

The maintained source fix is documented in h2-qemu-mission-devices.patch.  This
binary patcher exists so the already finalized local Windows ARM64 build can be
validated without retaining a full QEMU build tree.  It accepts exactly one
known input hash and three known AArch64 instruction sequences.
"""

from __future__ import annotations

import argparse
import hashlib
import struct
from pathlib import Path


EXPECTED_INPUT_SHA256 = (
    "1BE066D86DF4EF939FF50B61ECC47259722982762ABFC4CAFFF6C6D9FE36F363"
)

# File offsets in the stripped PE32+ image.  Both addresses are inside
# hw/timer/ingenic_tcu.c in the finalized QEMU 11.0.0 ARM64 build.
PATCHES = (
    # The stock ADC model pauses the whole VM when ADENA contains its SLEEP
    # bits.  H2 writes 0x44 while enabling the touchscreen; branch directly
    # to the normal sampler path after preserving the low three ADENA bits.
    # B 0x1400A1324 replaces B.EQ 0x1400A1324.
    (0x000A0700, bytes.fromhex("20 01 00 54"), bytes.fromhex("09 00 00 14")),
    # qmp_stop(NULL) in the unknown TCU-read fallback -> AArch64 NOP.
    (0x001C1500, bytes.fromhex("92 E7 02 94"), bytes.fromhex("1F 20 03 D5")),
    # If WDT enable bit is set, skip the premature reset request and retain
    # the guest-visible enable state.  B 0x1401C2678 replaces TBZ W20,#0,...
    (0x001C1910, bytes.fromhex("54 0B 00 36"), bytes.fromhex("5A 00 00 14")),
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def verify_arm64_pe(data: bytes) -> None:
    if len(data) < 0x100 or data[:2] != b"MZ":
        raise ValueError("input is not a PE executable")
    pe_offset = struct.unpack_from("<I", data, 0x3C)[0]
    if pe_offset + 6 > len(data) or data[pe_offset : pe_offset + 4] != b"PE\0\0":
        raise ValueError("input has an invalid PE header")
    machine = struct.unpack_from("<H", data, pe_offset + 4)[0]
    if machine != 0xAA64:
        raise ValueError(f"expected ARM64 PE machine 0xAA64, found 0x{machine:04X}")


def patch(input_path: Path, output_path: Path, force: bool) -> str:
    source = input_path.read_bytes()
    verify_arm64_pe(source)
    actual_hash = sha256(source)
    if actual_hash != EXPECTED_INPUT_SHA256:
        raise ValueError(
            "refusing unknown QEMU input: "
            f"expected {EXPECTED_INPUT_SHA256}, found {actual_hash}"
        )
    if output_path.exists() and not force:
        raise FileExistsError(f"output exists (pass --force to replace it): {output_path}")

    result = bytearray(source)
    for offset, expected, replacement in PATCHES:
        actual = bytes(result[offset : offset + len(expected)])
        if actual != expected:
            raise ValueError(
                f"instruction mismatch at file offset 0x{offset:X}: "
                f"expected {expected.hex()}, found {actual.hex()}"
            )
        result[offset : offset + len(expected)] = replacement

    verify_arm64_pe(result)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(result)
    written = output_path.read_bytes()
    if written != result:
        raise IOError("output readback does not match patched bytes")
    return sha256(written)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if args.input.resolve() == args.output.resolve():
        raise SystemExit("input and output must be different paths")
    output_hash = patch(args.input.resolve(), args.output.resolve(), args.force)
    print(f"patched H2 ARM64 QEMU SHA-256: {output_hash}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
