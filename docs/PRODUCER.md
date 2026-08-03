# Read-only producer observer — M6

M6 source/conformance adds a removable observer around one declared producer
output. It does not select or activate a live producer, change a schedule, open
a producer database, create a Buzz identity or route the live coordinator
through Core.

## Contract

`city2.producer-contract/v1` binds one disabled-by-default observer to one exact
`file:` output URI, Unix identity, A0 agent manifest, freshness SLO, scoped
candidate-memory output and rollback plan. Schedule and database authority stay
external and unchanged; source writes are denied. The example contract and
agent remain disabled and use `pending-live-selection` placeholders.

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

## Live activation gate

The 2026-08-03 read-only fleet probe could not verify candidates because this
host's Tailscale client is logged out and the configured SSH hostname does not
resolve. Therefore no live producer is selected and M6 exit criteria are not
claimed.

Before activation:

1. restore operator-approved Tailscale connectivity and rerun `./city2 fleet`;
2. choose one verified noncritical producer and a non-database durable output;
3. verify downstream independence and baseline output hash/freshness;
4. replace placeholders, recompute/review the agent manifest and keep both
   manifests disabled until approval;
5. create a distinct narrow Buzz identity/channel membership;
6. run a read-only shadow observation and independently verify its signature,
   value and source invariance;
7. remove the observer and prove producer/downstream operation is unchanged.

Only that evidence can satisfy M6 and support any M7 expansion.
