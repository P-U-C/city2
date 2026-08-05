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

## 2026-08-05 routing-drift closure

A later missed owner turn had a separate configuration cause: the deployed ACP
routing file contained only `control`, while the valid signed thread event was
in `ops`. The relay profile, owner gate, Bot membership and continuation
predicate remained valid; the coordinator was not subscribed to that channel.

Production routing was restored to the complete `control`, `city2` and `ops`
set. The service restarted cleanly, discovered three channels and established
three subscriptions. PR #24 added an exact-name routing synchronizer that:

- resolves every requested name against the agent's current memberships;
- requires exactly one match per name;
- atomically replaces routing only after the complete set validates;
- preserves the last known-good file on missing or duplicate names; and
- prints neither channel identifiers nor credentials.

Two consecutive post-fix owner turns then passed the complete path. Raw relay
events independently established valid owner and coordinator signatures,
correct thread linkage and no structured mention on either owner event.
Coordinator response latency was seven seconds for the first turn and five
seconds for the second. The hardened service remained active with zero restarts.

**Result:** closed. Both the persisted-event remediation and complete-channel
routing now have consecutive live owner-turn evidence.

## 2026-08-05 recovery drill 2: bounded relay loss

The second predeclared recovery drill stopped only the Buzz relay container for
three seconds. A fresh aligned backup passed checksum, PostgreSQL-catalog and
volume-archive verification before injection. PostgreSQL, Redis, MinIO and the
coordinator process remained running and unchanged.

The relay loss was observed and recovered healthy in 25.973 seconds, below the
60-second ceiling. The unchanged coordinator autonomously reconnected and
restored exactly three channel subscriptions. Protected runtime bytes did not
drift, no owner event was replayed, and the directory profile, owner gate and
Bot memberships remained valid.

Chad then replied inside the existing `ops` thread without a structured
mention. An authenticated raw-event query independently verified the owner's
signature, the coordinator's signature and identical thread linkage. The
coordinator replied seven seconds later.

**Result:** accepted. Two of the three required recovery drills are complete.
No Core/M7 state, authority, identity, membership, producer, schedule or
downstream contract changed.

## 2026-08-05 private mobile pairing path

Buzz Desktop's **Settings → Mobile** initially failed with HTTP 404. The main
relay advertised NIP-43 but no `pairing_relay_url`, so Desktop used its legacy
fallback and attempted `/pair` on the main relay, which does not implement that
route.

City2 now runs the pinned image's dedicated, stateless `buzz-pair-relay` binary
as an internal Compose service. A digest-pinned, read-only Nginx sidecar is the
only service with the explicit Tailscale pairing binding; it permits exact
`/pair` WebSocket upgrades and enforces connection and HTTP timeout limits. The
main relay advertises that exact private URL in NIP-11; no pairing port is
published on a public interface.

The first relay recreation remained fail-closed in its existing Git object-store
conformance gate and became unhealthy. An independent MinIO write/read/delete
probe passed. One bounded relay-only restart then passed the same conformance
gate and became healthy in 20 seconds; dependencies, the pairing service and the
coordinator process did not restart. The coordinator autonomously restored all
three subscriptions.

Final runtime checks proved a matching NIP-11 pairing URL and HTTP 101 WebSocket
upgrade on `/pair`. Relay, pairing sidecar, PostgreSQL, Redis and MinIO were all
healthy; the coordinator remained active with zero restarts.

An independent review then found that the upstream pairing binary explicitly
requires a path-restricting reverse proxy with HTTP timeouts. The direct private
binding was therefore not accepted as final. The remediated layout places the
pairing relay behind a digest-pinned, non-root, read-only Nginx sidecar; only
exact `/pair` WebSocket upgrades are proxied, other paths return 404, non-GET
requests are denied, and the internal relay has no host port. A final live probe
reconfirmed NIP-11, HTTP 101, path rejection, healthy services and all three
coordinator subscriptions.

The review also exposed an unsafe harness boundary: a reviewer cleanup command
stopped both production containers sharing the Buzz image. The runtime gate
caught the outage before publication and the normal wrapper restored service in
13 seconds without restarting dependencies or the coordinator. `./city2 review`
now runs in a root-created transient systemd boundary with a read-only repo,
hidden home, disposable config-only state, `NoNewPrivileges` and no Docker
access.

**Result:** infrastructure accepted; iPhone scan/import remains a client-side
acceptance check. The human private key remains on human-controlled devices and
no Core/M7 authority changed.

## Desktop owner-label caveat

Buzz Desktop's `owner unavailable` text is independent of runtime ownership.
The coordinator's latest signed kind-0 profile is signature-valid but carries
no NIP-OA owner-attestation tag, so Desktop has no cryptographic owner value to
display. The relay's registered owner gate and Bot membership remain valid.

The human private key remains off-host. Removing the label requires a public
NIP-OA attestation signed on the human Mac and a coordinator profile republish;
the human key must not be copied or exported merely to change this cosmetic
label.
