#!/usr/bin/env python3
"""Run one deterministic producer observation inside the reviewed namespace."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from city2core.model import utc_now  # noqa: E402
from city2core.producer import ProducerError, ProducerObserver, write_observation  # noqa: E402


def load_object(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ProducerError(f"invalid observer configuration: {path.name}") from error
    if not isinstance(value, dict):
        raise ProducerError(f"invalid observer configuration: {path.name}")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--agent", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--signer-key-version", required=True)
    args = parser.parse_args()

    credential_value = os.environ.get("CREDENTIALS_DIRECTORY")
    if not credential_value:
        raise ProducerError("observer signing credential is unavailable")
    credential_dir = Path(credential_value)
    signing_key = credential_dir / "observer.signing-key"
    if not credential_dir.is_dir() or not signing_key.is_file():
        raise ProducerError("observer signing credential is unavailable")

    observer = ProducerObserver(load_object(args.contract), load_object(args.agent))
    observation = observer.observe(
        args.source,
        observed_at=utc_now(),
        signing_key=signing_key,
        signer_key_version=args.signer_key_version,
    )
    write_observation(args.output, observation)
    print(
        "producer-observer: PASS "
        f"state={observation['freshness_state']} bytes={observation['byte_length']}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ProducerError as error:
        print(f"producer-observer: FAIL: {error}", file=sys.stderr)
        raise SystemExit(1) from None
