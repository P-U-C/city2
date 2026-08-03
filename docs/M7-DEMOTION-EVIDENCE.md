# M7 coordinator demotion evidence

## Scope

This record covers one least-privilege precondition for the deferred M7 A0
Core/coordinator pilot. It does not admit or activate that pilot.

## Outcome

On 2026-08-03, after explicit direction from the human owner through
PfTerminal, the existing coordinator signed a role reduction from Owner to Bot
in each of the three private bootstrap channels. Authoritative post-state
checks found:

- exactly three active coordinator memberships, all role `bot`;
- exactly one active Owner in each channel, the human-controlled identity;
- the coordinator service active and subscribed to all three channels; and
- no Core service, database, route, new identity, channel or authority grant.

The aligned pre-change relay backup `20260803T221936Z` passed checksum,
PostgreSQL-catalog and volume-archive verification. Full event IDs, signatures,
channel identifiers and membership projections are retained off-repository in
a mode-0600 evidence record with SHA-256
`11779cf5853f70a90ae05a377946290416b73ca233db189f0f2aa21c86a94886`.
No private key or secret value is present in this repository.

After the role change, the hardened backup path created generation
`20260803T223128Z`, restarted the relay successfully and passed the same three
verification classes. The coordinator remained active with three Bot
memberships and one human Owner per channel after that restart.

## Failed-closed compatibility finding

The first signed attempt changed nothing. The pinned upstream Buzz CLI's
kind-9000 builder did not opt into self-tag preservation, so its Nostr library
removed the `p` tag when signer and target matched. The relay rejected that
event as malformed before any membership mutation.

A disposable build from the exact pinned source added
`allow_self_tagging()` to that builder and a focused regression test proving a
self-targeted Bot role retains its `p` and `role` tags. The test passed, the
relay accepted exactly three signed events and the disposable binary was never
installed or committed. Membership post-state, not event acceptance alone, was
the success criterion.

## Remaining gate

The checked-in admission decision remains `defer`. Before a new immutable
decision can be reviewed, City2 still needs:

1. the M2 fresh-session criterion through the live path;
2. the M3 Core-routing and restart criterion through the live path; and
3. three successful restart/relay-loss recovery drills with immutable evidence.
