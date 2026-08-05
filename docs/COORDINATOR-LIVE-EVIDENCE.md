# Coordinator live evidence

## 2026-08-05 macOS Desktop acceptance

The deployed owner-only coordinator passed the remaining live thread-
continuation gate at `2026-08-05T19:14:13Z`.

An authenticated NIP-42 relay query verified the raw Nostr events without
publishing private channel, thread, event, or identity identifiers:

- the owner-authored reply had a valid signature;
- the reply carried a thread reference but no structured `p` mention;
- the exact channel/thread already contained a valid coordinator-signed reply;
- the coordinator follow-up had a valid signature and the same channel/thread
  reference;
- response latency was nine seconds; and
- the hardened coordinator service remained active.

This proves the client-compatible continuation path rather than the textual-
mention fallback. The proof changed no channel membership, directory profile,
identity, authority, Core/M7 state, producer, or downstream contract. Private
relay identifiers remain in runtime state only.

**Result:** accepted. The live coordinator mention and thread-routing gates are
complete.

## 2026-08-05 repeated-turn delivery remediation

Later owner replies exposed a transport reliability gap after the accepted
proof: valid signed thread events were persisted by the relay's authenticated
HTTP bridge, but the coordinator's otherwise healthy WebSocket subscription did
not receive them. The continuation predicate itself was not at fault. A
signer-safe production-equivalent query confirmed that every missed event had a
valid signature, correct channel/thread tags, no structured mention and a valid
coordinator reply already present in that thread.

The pinned `buzz-acp` patch now keeps WebSocket delivery primary and adds a
bounded persisted-event reconciliation backstop:

- one authenticated query covers all active channel subscriptions every three
  seconds;
- queries reuse each live subscription's channel, kind and mention constraints;
- a five-second overlap protects same-second writes and reconnect races;
- WebSocket and catch-up events meet at one bounded event-ID dedup boundary;
- each catch-up request has a two-second hard timeout; and
- results are signature-checked and delivered oldest-first.

Focused regressions cover filter equivalence and acceptance of valid
owner-thread events without a `p` tag while rejecting wrong channel, kind,
signature or mention state. A clean build from the pinned Buzz commit applied
the patch and reproduced all five local tools. After deployment, a disposable
signed message submitted through the same HTTP bridge was observed at the
coordinator's shared delivery boundary and rejected by the existing self-author
gate, proving catch-up without invoking the model; the probe event was then
deleted. `./city2 validate` passes 104 tests and the hardened service remains
active.

The original acceptance remains valid. Consecutive owner-authored turns after
this remediation are tracked separately from the transport proof so a missed
message cannot be rewritten as a success.
