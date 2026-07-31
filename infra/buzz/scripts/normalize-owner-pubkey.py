#!/usr/bin/env python3
"""Normalize a public Buzz/Nostr identity (npub or 64-char hex) to hex.

Private `nsec` values are deliberately rejected.
"""

from __future__ import annotations

import re
import sys

CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
CHARSET_MAP = {char: index for index, char in enumerate(CHARSET)}


def polymod(values: list[int]) -> int:
    generators = (0x3B6A57B2, 0x26508E6D, 0x1EA119FA, 0x3D4233DD, 0x2A1462B3)
    checksum = 1
    for value in values:
        top = checksum >> 25
        checksum = ((checksum & 0x1FFFFFF) << 5) ^ value
        for index, generator in enumerate(generators):
            if (top >> index) & 1:
                checksum ^= generator
    return checksum


def hrp_expand(hrp: str) -> list[int]:
    return [ord(char) >> 5 for char in hrp] + [0] + [ord(char) & 31 for char in hrp]


def convert_bits(values: list[int], from_bits: int, to_bits: int, *, pad: bool) -> bytes:
    accumulator = 0
    bit_count = 0
    result = bytearray()
    max_value = (1 << to_bits) - 1
    max_accumulator = (1 << (from_bits + to_bits - 1)) - 1

    for value in values:
        if value < 0 or value >> from_bits:
            raise ValueError("invalid bech32 data value")
        accumulator = ((accumulator << from_bits) | value) & max_accumulator
        bit_count += from_bits
        while bit_count >= to_bits:
            bit_count -= to_bits
            result.append((accumulator >> bit_count) & max_value)

    if pad:
        if bit_count:
            result.append((accumulator << (to_bits - bit_count)) & max_value)
    elif bit_count >= from_bits or ((accumulator << (to_bits - bit_count)) & max_value):
        raise ValueError("invalid bech32 padding")

    return bytes(result)


def decode_npub(value: str) -> str:
    if value.lower() != value and value.upper() != value:
        raise ValueError("mixed-case bech32 value")
    value = value.lower()
    separator = value.rfind("1")
    if separator <= 0 or separator + 7 > len(value):
        raise ValueError("invalid bech32 separator/checksum")

    hrp = value[:separator]
    if hrp != "npub":
        raise ValueError("only public npub identities are accepted")

    try:
        data = [CHARSET_MAP[char] for char in value[separator + 1 :]]
    except KeyError as error:
        raise ValueError("invalid bech32 character") from error

    if polymod(hrp_expand(hrp) + data) != 1:
        raise ValueError("invalid bech32 checksum")

    decoded = convert_bits(data[:-6], 5, 8, pad=False)
    if len(decoded) != 32:
        raise ValueError("npub payload must be 32 bytes")
    return decoded.hex()


def normalize(value: str) -> str:
    value = value.strip()
    if re.fullmatch(r"[0-9a-fA-F]{64}", value):
        return value.lower()
    if value.lower().startswith("nsec1"):
        raise ValueError("private nsec identities are forbidden")
    if value.lower().startswith("npub1"):
        return decode_npub(value)
    raise ValueError("expected a public npub or 64-character hex key")


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: normalize-owner-pubkey.py <npub-or-hex>", file=sys.stderr)
        return 2
    try:
        print(normalize(sys.argv[1]))
    except ValueError as error:
        print(f"invalid public identity: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
