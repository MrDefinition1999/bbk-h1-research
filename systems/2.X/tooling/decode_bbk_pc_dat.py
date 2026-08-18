#!/usr/bin/env python3
"""Decode BBK PC-recovery DAT payloads with the confirmed XOR stream.

The DAT header is 16 bytes and begins with ``26 04 04 20``.  The payload is
XORed with a 4096-byte repeating stream.  To avoid embedding an unexplained
vendor key, this tool derives the stream from one trusted PC DAT / SD raw-file
pair and validates the complete overlap before decoding another DAT.
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path


HEADER_SIZE = 16
KEY_PERIOD = 4096
MAGIC = bytes.fromhex("26040420")


def derive_key(known_dat: bytes, known_plain: bytes) -> bytes:
    if known_dat[:4] != MAGIC:
        raise ValueError("known DAT is missing the BBK PC header")
    ciphertext = known_dat[HEADER_SIZE:]
    if len(ciphertext) != len(known_plain):
        raise ValueError("known DAT payload/plaintext lengths differ")
    if len(known_plain) < KEY_PERIOD:
        raise ValueError("known pair is too short to derive the 4096-byte stream")
    key = bytes(left ^ right for left, right in zip(ciphertext[:KEY_PERIOD], known_plain[:KEY_PERIOD]))
    for offset, (left, right) in enumerate(zip(ciphertext, known_plain)):
        if left ^ key[offset % KEY_PERIOD] != right:
            raise ValueError(f"known pair does not follow the 4096-byte XOR stream at offset {offset}")
    return key


def decode(payload: bytes, key: bytes) -> bytes:
    if payload[:4] != MAGIC:
        raise ValueError("input is missing the BBK PC DAT header")
    ciphertext = payload[HEADER_SIZE:]
    return bytes(value ^ key[index % len(key)] for index, value in enumerate(ciphertext))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("known_dat", type=Path)
    parser.add_argument("known_plain", type=Path)
    parser.add_argument("input_dat", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    key = derive_key(args.known_dat.read_bytes(), args.known_plain.read_bytes())
    encoded = args.input_dat.read_bytes()
    decoded = decode(encoded, key)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(decoded)
    print(f"header={encoded[:HEADER_SIZE].hex()}")
    print(f"key_sha256={hashlib.sha256(key).hexdigest()}")
    print(f"decoded_size={len(decoded)}")
    print(f"decoded_sha256={hashlib.sha256(decoded).hexdigest()}")
    print(f"decoded_prefix={decoded[:32].hex()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
