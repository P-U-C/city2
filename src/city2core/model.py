"""Canonical values and identifiers used by City2 Core."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import math
import secrets
import time
import uuid
from typing import Any, Iterable


ZERO_SHA256 = "0" * 64
ID_PREFIXES = {
    "action": "act_",
    "archive": "arc_",
    "event": "evt_",
    "objective": "obj_",
    "review": "rev_",
    "run": "run_",
    "task": "tsk_",
}


def canonical_json(value: Any) -> str:
    """Return deterministic JSON for hashes and durable records.

    M1 emits integers, decimal strings and ordinary finite JSON values only;
    this is the RFC 8785-compatible subset required by current contracts.
    """
    _assert_canonical_value(value)
    return _encode_canonical(value)


def _encode_canonical(value: Any) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return _encode_float(value)
    if isinstance(value, list):
        return "[" + ",".join(_encode_canonical(item) for item in value) + "]"
    if isinstance(value, dict):
        keys = sorted(value, key=lambda key: key.encode("utf-16be"))
        return (
            "{"
            + ",".join(
                _encode_canonical(key) + ":" + _encode_canonical(value[key])
                for key in keys
            )
            + "}"
        )
    raise AssertionError(type(value))


def _encode_float(value: float) -> str:
    """Serialize a finite IEEE-754 value using ECMAScript/JCS thresholds."""
    if value == 0:
        return "0"
    absolute = abs(value)
    shortest = repr(value).lower()
    if 1e-6 <= absolute < 1e21:
        fixed = format(Decimal(shortest), "f")
        if "." in fixed:
            fixed = fixed.rstrip("0").rstrip(".")
        return fixed
    mantissa, exponent = shortest.split("e")
    if "." in mantissa:
        mantissa = mantissa.rstrip("0").rstrip(".")
    exponent_number = int(exponent)
    sign = "+" if exponent_number >= 0 else ""
    return f"{mantissa}e{sign}{exponent_number}"


def _assert_canonical_value(value: Any, path: str = "$") -> None:
    """Reject values outside Core's deliberately small canonical JSON profile."""
    if value is None or isinstance(value, bool):
        return
    if isinstance(value, str):
        if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
            raise ValueError(f"{path}: unpaired Unicode surrogate is not valid JCS")
        return
    if isinstance(value, int):
        if abs(value) > 9_007_199_254_740_991:
            raise ValueError(f"{path}: integer exceeds the JCS interoperable range")
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{path}: non-finite values are not valid JCS")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _assert_canonical_value(item, f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"{path}: JSON object keys must be strings")
            _assert_canonical_value(item, f"{path}.{key}")
        return
    raise ValueError(f"{path}: unsupported canonical JSON value {type(value).__name__}")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_json(value: Any) -> str:
    return sha256_bytes(canonical_json(value).encode("utf-8"))


def utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def parse_time(value: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("timestamp must be UTC RFC 3339 with Z")
    parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError("timestamp must be UTC")
    return parsed


def uuid7() -> str:
    """Generate a lowercase RFC 9562 UUIDv7 using a millisecond timestamp."""
    milliseconds = int(time.time_ns() // 1_000_000) & ((1 << 48) - 1)
    random_a = secrets.randbits(12)
    random_b = secrets.randbits(62)
    value = (
        (milliseconds << 80) | (0x7 << 76) | (random_a << 64) | (0b10 << 62) | random_b
    )
    return str(uuid.UUID(int=value))


def new_id(kind: str) -> str:
    try:
        prefix = ID_PREFIXES[kind]
    except KeyError as error:
        raise ValueError(f"unknown canonical ID kind: {kind}") from error
    return prefix + uuid7()


def digest_profile(value: dict[str, Any], excluded: Iterable[str]) -> str:
    payload = {key: item for key, item in value.items() if key not in set(excluded)}
    return sha256_json(payload)
