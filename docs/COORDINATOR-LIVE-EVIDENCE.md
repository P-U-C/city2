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
