#!/usr/bin/env python3
"""Encode the JZ4740 RS(511,503) parity used by BBK H1 NAND pages."""

from __future__ import annotations


NN = 511
NROOTS = 8
DATA_SYMBOLS = 503
GF_POLY = 0x211
PAGE_SIZE = 2048
ECC_BLOCK_SIZE = 512
PARITY_SIZE = 9


def _modnn(value: int) -> int:
    while value >= NN:
        value -= NN
    return value


def _build_tables() -> tuple[tuple[int, ...], tuple[int, ...], tuple[tuple[int, ...], ...]]:
    alpha_to = [0] * (NN + 1)
    index_of = [0] * (NN + 1)
    generator = [0] * (NROOTS + 1)

    state = 1
    index_of[0] = NN
    for index in range(NN):
        index_of[state] = index
        alpha_to[index] = state
        state <<= 1
        if state & 0x200:
            state ^= GF_POLY
        state &= NN
    alpha_to[NN] = 0

    generator[0] = 1
    for degree in range(NROOTS):
        root = degree + 1
        generator[degree + 1] = 1
        for index in range(degree, 0, -1):
            if generator[index]:
                generator[index] = (
                    generator[index - 1]
                    ^ alpha_to[_modnn(index_of[generator[index]] + root)]
                )
            else:
                generator[index] = generator[index - 1]
        generator[0] = alpha_to[_modnn(index_of[generator[0]] + root)]
    generator = [index_of[value] for value in generator]

    terms: list[tuple[int, ...]] = []
    for feedback in range(NN):
        row = [
            alpha_to[_modnn(feedback + generator[NROOTS - index])]
            for index in range(1, NROOTS)
        ]
        row.append(alpha_to[_modnn(feedback + generator[0])])
        terms.append(tuple(row))
    terms.append((0,) * NROOTS)
    return tuple(alpha_to), tuple(index_of), tuple(terms)


_ALPHA_TO, _INDEX_OF, _TERMS = _build_tables()


def _input_symbol(data: bytes, symbol_index: int) -> int:
    bit = symbol_index * 9
    byte = bit >> 3
    shift = bit & 7
    value = data[byte] if byte < ECC_BLOCK_SIZE else 0
    if byte + 1 < ECC_BLOCK_SIZE:
        value |= data[byte + 1] << 8
    return (value >> shift) & NN


def jz4740_block_ecc(data: bytes) -> bytes:
    """Return the nine parity bytes for one 512-byte NAND data block."""

    if len(data) != ECC_BLOCK_SIZE:
        raise ValueError("JZ4740 ECC blocks must be exactly 512 bytes")

    parity = [0] * NROOTS
    for symbol_index in range(DATA_SYMBOLS):
        symbol = _input_symbol(data, symbol_index) if symbol_index < 456 else 0
        feedback = _INDEX_OF[symbol ^ parity[0]]
        row = _TERMS[feedback]
        parity = [parity[index] ^ row[index - 1] for index in range(1, NROOTS)] + [
            row[NROOTS - 1]
        ]

    packed = [parity[NROOTS - 1 - index] & NN for index in range(NROOTS)]
    first = (
        packed[7]
        | (packed[6] << 9)
        | (packed[5] << 18)
        | ((packed[4] & 0x1F) << 27)
    )
    second = (
        ((packed[4] >> 5) & 0x0F)
        | (packed[3] << 4)
        | (packed[2] << 13)
        | (packed[1] << 22)
        | ((packed[0] & 1) << 31)
    )
    return (
        first.to_bytes(4, "little")
        + second.to_bytes(4, "little")
        + bytes((packed[0] >> 1,))
    )


def jz4740_page_oob_ecc(data: bytes, *, offset: int = 6) -> bytes:
    """Return ``offset`` erased bytes followed by four 9-byte parity fields."""

    if len(data) != PAGE_SIZE:
        raise ValueError("JZ4740 ECC pages must be exactly 2,048 bytes")
    if offset < 0:
        raise ValueError("ECC OOB offset must not be negative")

    output = bytearray(b"\xFF" * offset)
    for start in range(0, PAGE_SIZE, ECC_BLOCK_SIZE):
        output.extend(jz4740_block_ecc(data[start : start + ECC_BLOCK_SIZE]))
    return bytes(output)
