# Read-only producer observer — M6

M6 source/conformance adds a removable observer around one declared producer
output. `ai-infra` is the selected disabled candidate; no observer is activated.
This does not change a schedule, open a producer database, create a Buzz
identity or route the live coordinator through Core.

## Contract

`city2.producer-contract/v1` binds one disabled-by-default observer to one exact
`file:` output URI, Unix identity, A0 agent manifest, freshness SLO, scoped
candidate-memory output and rollback plan. Schedule and database authority stay
external and unchanged; source writes are denied. The example contract and
agent remain disabled and use `pending-live-selection` placeholders.

The selected `producer-pilot.ai-infra.json` and
`producer-agent.ai-infra.json` bind only the producer-owned aggregate JSON and
remain disabled. The logical agent has A0, no model, network or credentials and
only read/hash tools.

`ProducerObserver` accepts only that declared regular output file. It rejects
symlinks, database/journal suffixes, undeclared paths, oversized files,
non-read-only tools, network access, credentials, model execution and any source
mutation during hashing. It retains no source content.

The observer emits `city2.producer-observation/v1`: source hash/size/freshness,
content-free authority-touch assertions, measurable provenance checks and an
Ed25519 signature. It can also derive an M2 candidate-memory payload; normal
independent review is still required before acceptance.

## Rollback and value

The synthetic proof verifies:

- the authoritative source hash is identical before and after observation;
- evidence removal leaves the source intact;
- no downstream contract depends on observer output;
- signed provenance and freshness detection add two explicit measurements;
- source mutation, database paths and manifest escalation fail closed.

Rollback is removal of the observer/evidence output. Existing producer and
downstream behavior never depends on City2.

## Candidate evidence — 2026-08-03

The live fleet probe used the configured Tailscale alias first, then the LAN
fallback serially over one multiplexed SSH connection. All 15 active producer
contracts passed; the host remains WARN at 2.7 GiB free versus the 5 GiB floor.

The selected source is
`/home/ai-infra/ai-infra-corpus/out/ai-infrastructure-aggregates.json`. A
content-free producer-identity check found valid JSON with nine top-level
fields, 6,960 bytes, owner/group `ai-infra`, mode `0664`, and a stable double
SHA-256 of `1df93c43ab1223489b8cbf1a7e70949913f02ca988dd3f9725b91ed724c70a7d`.
No source content entered City2 or model context. Existing Git/editorial
consumers remain authoritative and have no dependency on observer evidence.

## Live activation gate

This host's Tailscale client remains logged out, but the documented LAN fallback
verified the fleet and candidate. M6 exit criteria are still not claimed because
the read-only namespace, distinct Buzz identity, signed shadow evidence and
removal proof have not been activated.

Before activation:

1. restore operator-approved Tailscale connectivity for remote relay access;
2. keep the selected manifests disabled through independent review;
3. create a systemd filesystem namespace that hides the original producer tree
   and exposes only the exact source at a read-only bind path;
4. create a distinct narrow Buzz identity/channel membership;
5. run a read-only shadow observation and independently verify its signature,
   value and source invariance;
6. remove the observer and prove producer/downstream operation is unchanged.

Only that evidence can satisfy M6 and support any M7 expansion.
