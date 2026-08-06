#!/usr/bin/env python3
"""Publish NIP-29 add-member events (kind 9000) as the channel owner.

Buzz Desktop releases through 0.5.5 cannot list externally hosted relay
agents in the add-member picker, so an owner cannot add the City2
coordinator to a private channel from the UI. This tool does the same thing
the `buzz channels add-member` CLI does, using only the Python standard
library, so the owner can run it on their own machine without installing a
toolchain and without the owner secret key ever leaving that machine.

It reuses the audited BIP-340 implementation in `mint-owner-attestation.py`;
download both files into the same directory.

Transport is the relay's HTTP bridge:
  POST <relay>/events
  Authorization: Nostr <base64 of a signed kind-27235 NIP-98 event>
  body: one signed kind-9000 event

Usage:
  owner-add-channel-member.py --relay https://host:port \
      --agent-pubkey <hex> --role bot <channel-uuid> [<channel-uuid> ...]

The secret key is read from BUZZ_OWNER_SECRET or a no-echo prompt and is
never printed.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.util
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

KIND_ADD_MEMBER = 9000
KIND_HTTP_AUTH = 27235
VALID_ROLES = ("owner", "admin", "member", "guest", "bot")


def load_crypto():
    """Load BIP-340 helpers from the sibling attestation tool."""
    here = Path(__file__).resolve().parent
    target = here / "mint-owner-attestation.py"
    if not target.exists():
        sys.exit(
            f"missing {target}\n"
            "Download it alongside this script:\n"
            "  curl -fsSL https://raw.githubusercontent.com/P-U-C/city2/main/"
            "infra/buzz/scripts/mint-owner-attestation.py -o "
            f"{here}/mint-owner-attestation.py"
        )
    spec = importlib.util.spec_from_file_location("buzz_oa", target)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def canonical(obj) -> str:
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)


def event_id(pubkey_hex: str, created_at: int, kind: int, tags, content: str) -> str:
    payload = canonical([0, pubkey_hex, created_at, kind, tags, content])
    return hashlib.sha256(payload.encode()).hexdigest()


def sign_event(crypto, secret: bytes, kind: int, tags, content: str, created_at=None):
    pubkey_hex = crypto.pubkey_from_secret(secret).hex()
    created_at = int(created_at if created_at is not None else time.time())
    eid = event_id(pubkey_hex, created_at, kind, tags, content)
    sig = crypto.schnorr_sign(bytes.fromhex(eid), secret, bytes(32))
    if not crypto.schnorr_verify(
        bytes.fromhex(eid), bytes.fromhex(pubkey_hex), sig
    ):  # pragma: no cover
        raise AssertionError("event self-verification failed")
    return {
        "id": eid,
        "pubkey": pubkey_hex,
        "created_at": created_at,
        "kind": kind,
        "tags": tags,
        "content": content,
        "sig": sig.hex(),
    }


def nip98_header(crypto, secret: bytes, url: str, method: str, body: bytes) -> str:
    tags = [
        ["u", url],
        ["method", method.upper()],
        ["payload", hashlib.sha256(body).hexdigest()],
    ]
    ev = sign_event(crypto, secret, KIND_HTTP_AUTH, tags, "")
    return "Nostr " + base64.b64encode(canonical(ev).encode()).decode()


def post_event(relay: str, crypto, secret: bytes, event: dict) -> tuple:
    url = relay.rstrip("/") + "/events"
    body = canonical(event).encode()
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": nip98_header(crypto, secret, url, "POST", body),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, {"raw": raw[:300]}
    except urllib.error.URLError as e:
        return 0, {"error": f"network: {e.reason}"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("channels", nargs="+", help="channel UUID(s)")
    ap.add_argument("--relay", required=True, help="https://host:port")
    ap.add_argument("--agent-pubkey", required=True, help="64 hex chars")
    ap.add_argument("--role", default="bot", choices=VALID_ROLES)
    ap.add_argument(
        "--dry-run", action="store_true", help="build and sign but do not send"
    )
    args = ap.parse_args()

    agent = args.agent_pubkey.strip().lower()
    if len(agent) != 64:
        ap.error("--agent-pubkey must be 64 hex characters")
    bytes.fromhex(agent)

    crypto = load_crypto()

    raw = os.environ.get("BUZZ_OWNER_SECRET")
    if not raw:
        import getpass

        raw = getpass.getpass("Owner secret key (nsec1... or hex, not echoed): ")
    secret = crypto.load_secret(raw)
    del raw

    print(f"owner  : {crypto.pubkey_from_secret(secret).hex()[:8]}…")
    print(f"agent  : {agent[:8]}…  role={args.role}")
    print(f"relay  : {args.relay}\n")

    failures = 0
    for ch in args.channels:
        tags = [["h", ch], ["p", agent], ["role", args.role]]
        ev = sign_event(crypto, secret, KIND_ADD_MEMBER, tags, "")
        if args.dry_run:
            print(f"{ch[:8]}…  DRY-RUN  event_id={ev['id'][:12]}…")
            continue
        status, resp = post_event(args.relay, crypto, secret, ev)
        ok = status == 200 and resp.get("accepted") is not False
        detail = resp.get("message") or resp.get("error") or resp.get("raw") or ""
        print(f"{ch[:8]}…  {'OK ' if ok else 'FAIL'}  http={status} {detail}".rstrip())
        failures += 0 if ok else 1

    del secret
    if failures:
        print(f"\n{failures} channel(s) failed", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
