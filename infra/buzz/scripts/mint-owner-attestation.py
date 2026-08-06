#!/usr/bin/env python3
"""Mint a NIP-OA owner attestation (`auth` tag) for an agent key.

Run this on the OWNER's machine. The owner secret key never leaves that
machine and is never printed. The output `auth` tag is public capability
evidence and is safe to transport.

NIP-OA: docs/nips/NIP-OA.md in the pinned upstream (block/buzz).
  tag        = ["auth", <owner-pubkey-hex>, <conditions>, <sig-hex>]
  preimage   = "nostr:agent-auth:" || <agent-pubkey-hex> || ":" || <conditions>
  message    = SHA256(preimage)
  sig        = BIP-340 Schnorr signature over message by the owner secret key

Dependency-free: BIP-340 and bech32 are implemented here so the owner does
not have to install anything or paste a key into third-party tooling.

Usage:
  mint-owner-attestation.py --agent-pubkey <hex> [--conditions <str>]
                            [--expires-in-days N] [--self-test]

The secret key is read from the BUZZ_OWNER_SECRET environment variable or,
if unset, from an interactive no-echo prompt. It accepts hex or nsec1.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time

# --- secp256k1 / BIP-340 (reference implementation) -----------------------

P = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F
N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
G = (
    0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798,
    0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8,
)

Point = tuple  # (x, y) or None for the point at infinity


def tagged_hash(tag: str, msg: bytes) -> bytes:
    t = hashlib.sha256(tag.encode()).digest()
    return hashlib.sha256(t + t + msg).digest()


def point_add(a: Point | None, b: Point | None) -> Point | None:
    if a is None:
        return b
    if b is None:
        return a
    if a[0] == b[0] and a[1] != b[1]:
        return None
    if a == b:
        lam = (3 * a[0] * a[0] * pow(2 * a[1], P - 2, P)) % P
    else:
        lam = ((b[1] - a[1]) * pow(b[0] - a[0], P - 2, P)) % P
    x3 = (lam * lam - a[0] - b[0]) % P
    return (x3, (lam * (a[0] - x3) - a[1]) % P)


def point_mul(pt: Point | None, k: int) -> Point | None:
    r = None
    for i in range(256):
        if (k >> i) & 1:
            r = point_add(r, pt)
        pt = point_add(pt, pt)
    return r


def bytes_from_int(x: int) -> bytes:
    return x.to_bytes(32, "big")


def lift_x(x: int) -> Point | None:
    if x >= P:
        return None
    y_sq = (pow(x, 3, P) + 7) % P
    y = pow(y_sq, (P + 1) // 4, P)
    if pow(y, 2, P) != y_sq:
        return None
    return (x, y if y & 1 == 0 else P - y)


def pubkey_from_secret(seckey: bytes) -> bytes:
    d0 = int.from_bytes(seckey, "big")
    if not 1 <= d0 <= N - 1:
        raise ValueError("secret key out of range")
    pt = point_mul(G, d0)
    assert pt is not None
    return bytes_from_int(pt[0])


def schnorr_sign(msg32: bytes, seckey: bytes, aux_rand: bytes) -> bytes:
    d0 = int.from_bytes(seckey, "big")
    if not 1 <= d0 <= N - 1:
        raise ValueError("secret key out of range")
    pt = point_mul(G, d0)
    assert pt is not None
    d = d0 if pt[1] % 2 == 0 else N - d0
    t = bytes(
        a ^ b for a, b in zip(bytes_from_int(d), tagged_hash("BIP0340/aux", aux_rand))
    )
    rand = tagged_hash("BIP0340/nonce", t + bytes_from_int(pt[0]) + msg32)
    k0 = int.from_bytes(rand, "big") % N
    if k0 == 0:
        raise ValueError("nonce is zero")
    r_pt = point_mul(G, k0)
    assert r_pt is not None
    k = k0 if r_pt[1] % 2 == 0 else N - k0
    e = (
        int.from_bytes(
            tagged_hash(
                "BIP0340/challenge",
                bytes_from_int(r_pt[0]) + bytes_from_int(pt[0]) + msg32,
            ),
            "big",
        )
        % N
    )
    return bytes_from_int(r_pt[0]) + bytes_from_int((k + e * d) % N)


def schnorr_verify(msg32: bytes, pubkey: bytes, sig: bytes) -> bool:
    if len(pubkey) != 32 or len(sig) != 64:
        return False
    pt = lift_x(int.from_bytes(pubkey, "big"))
    if pt is None:
        return False
    r = int.from_bytes(sig[:32], "big")
    s = int.from_bytes(sig[32:], "big")
    if r >= P or s >= N:
        return False
    e = (
        int.from_bytes(
            tagged_hash("BIP0340/challenge", sig[:32] + pubkey + msg32), "big"
        )
        % N
    )
    r_pt = point_add(point_mul(G, s), point_mul(pt, N - e))
    if r_pt is None or r_pt[1] % 2 != 0 or r_pt[0] != r:
        return False
    return True


# --- bech32 (nsec) --------------------------------------------------------

CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"


def bech32_decode_nsec(s: str) -> bytes:
    s = s.strip()
    if not s.lower().startswith("nsec1"):
        raise ValueError("not an nsec key")
    s = s.lower()
    data = [CHARSET.find(c) for c in s[5:]]
    if any(d == -1 for d in data):
        raise ValueError("invalid bech32 character")
    data = data[:-6]  # drop checksum; nostr keys are fixed-length
    acc, bits, out = 0, 0, bytearray()
    for value in data:
        acc = (acc << 5) | value
        bits += 5
        if bits >= 8:
            bits -= 8
            out.append((acc >> bits) & 0xFF)
    if len(out) != 32:
        raise ValueError("decoded key is not 32 bytes")
    return bytes(out)


def load_secret(raw: str) -> bytes:
    raw = raw.strip()
    if raw.lower().startswith("nsec1"):
        return bech32_decode_nsec(raw)
    key = bytes.fromhex(raw)
    if len(key) != 32:
        raise ValueError("hex secret key must be 32 bytes")
    return key


# --- NIP-OA ---------------------------------------------------------------

DOMAIN = "nostr:agent-auth:"


def attestation_message(agent_pubkey_hex: str, conditions: str) -> bytes:
    preimage = f"{DOMAIN}{agent_pubkey_hex}:{conditions}".encode()
    return hashlib.sha256(preimage).digest()


def validate_conditions(conditions: str) -> None:
    if conditions == "":
        return
    if any(ch.isspace() for ch in conditions):
        raise ValueError("conditions must not contain whitespace")
    if conditions.startswith("&") or conditions.endswith("&") or "&&" in conditions:
        raise ValueError("malformed clause delimiter in conditions")
    for clause in conditions.split("&"):
        for prefix, lo, hi in (
            ("kind=", 0, 65535),
            ("created_at<", 0, 4294967295),
            ("created_at>", 0, 4294967295),
        ):
            if clause.startswith(prefix):
                digits = clause[len(prefix) :]
                if not digits.isdigit():
                    raise ValueError(f"non-decimal value in clause {clause!r}")
                if len(digits) > 1 and digits[0] == "0":
                    raise ValueError(f"leading zero in clause {clause!r}")
                if not lo <= int(digits) <= hi:
                    raise ValueError(f"value out of range in clause {clause!r}")
                break
        else:
            raise ValueError(f"unsupported clause {clause!r}")


def mint(agent_pubkey_hex: str, conditions: str, secret: bytes) -> list:
    validate_conditions(conditions)
    agent_pubkey_hex = agent_pubkey_hex.strip().lower()
    if len(agent_pubkey_hex) != 64:
        raise ValueError("agent pubkey must be 64 hex characters")
    bytes.fromhex(agent_pubkey_hex)
    owner_pubkey = pubkey_from_secret(secret)
    if owner_pubkey.hex() == agent_pubkey_hex:
        raise ValueError("self-attestation is invalid under NIP-OA")
    msg = attestation_message(agent_pubkey_hex, conditions)
    sig = schnorr_sign(msg, secret, bytes(32))
    if not schnorr_verify(msg, owner_pubkey, sig):
        raise AssertionError("self-verification failed")
    return ["auth", owner_pubkey.hex(), conditions, sig.hex()]


# --- self-test against the NIP-OA specification vector --------------------


def self_test() -> int:
    owner_secret = bytes.fromhex(
        "0000000000000000000000000000000000000000000000000000000000000001"
    )
    owner_pubkey = "79be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798"
    agent_pubkey = "c6047f9441ed7d6d3045406e95c07cd85c778e4b8cef3ca7abac09b95c709ee5"
    conditions = "kind=1&created_at<1713957000"
    want_digest = "08cdecd55af4c28d3801fd69615dcf5cc04fab3bc134b38a840bf157197069a6"
    spec_sig = (
        "8b7df2575caf0a108374f8471722b233c53f9ff827a8b0f91861966c3b9dd5cb"
        "2e189eae9f49d72187674c2f5bd244145e10ff86c9f257ffe65a1ee5f108b369"
    )

    ok = True

    got_pub = pubkey_from_secret(owner_secret).hex()
    print(f"owner pubkey derivation : {'PASS' if got_pub == owner_pubkey else 'FAIL'}")
    ok &= got_pub == owner_pubkey

    digest = attestation_message(agent_pubkey, conditions).hex()
    print(f"preimage sha256         : {'PASS' if digest == want_digest else 'FAIL'}")
    ok &= digest == want_digest

    v = schnorr_verify(
        bytes.fromhex(want_digest), bytes.fromhex(owner_pubkey), bytes.fromhex(spec_sig)
    )
    print(f"verify spec signature   : {'PASS' if v else 'FAIL'}")
    ok &= v

    tag = mint(agent_pubkey, conditions, owner_secret)
    mine = schnorr_verify(
        bytes.fromhex(want_digest), bytes.fromhex(tag[1]), bytes.fromhex(tag[3])
    )
    print(f"verify minted signature : {'PASS' if mine else 'FAIL'}")
    ok &= mine
    ok &= tag[0] == "auth" and tag[1] == owner_pubkey and tag[2] == conditions

    for bad in ("kind=1&", "&kind=1", "kind=01", "kind=1&&kind=2", "kind 1", "nope=1"):
        try:
            validate_conditions(bad)
        except ValueError:
            continue
        print(f"conditions reject {bad!r}: FAIL")
        ok = False
    print("conditions rejection    : PASS" if ok else "conditions rejection    : FAIL")

    print("\nSELF-TEST:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--agent-pubkey", help="agent x-only public key, 64 hex chars")
    ap.add_argument(
        "--conditions",
        default=None,
        help="explicit NIP-OA conditions string (overrides --expires-in-days)",
    )
    ap.add_argument(
        "--expires-in-days",
        type=int,
        default=365,
        help="bound the attestation with created_at<now+N days (0 = unbounded)",
    )
    ap.add_argument("--self-test", action="store_true", help="run spec vector checks")
    args = ap.parse_args()

    if args.self_test:
        return self_test()

    if not args.agent_pubkey:
        ap.error("--agent-pubkey is required")

    if args.conditions is not None:
        conditions = args.conditions
    elif args.expires_in_days > 0:
        conditions = f"created_at<{int(time.time()) + args.expires_in_days * 86400}"
    else:
        conditions = ""

    raw = os.environ.get("BUZZ_OWNER_SECRET")
    if not raw:
        import getpass

        raw = getpass.getpass("Owner secret key (nsec1... or hex, not echoed): ")
    secret = load_secret(raw)

    tag = mint(args.agent_pubkey, conditions, secret)
    del secret, raw

    print(
        "\nNIP-OA auth tag (PUBLIC — safe to copy; contains no secret key):\n",
        file=sys.stderr,
    )
    print(json.dumps(tag, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
