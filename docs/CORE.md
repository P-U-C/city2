# City2 Core — M1/M2 operator and integrity contract

City2 Core is a small Python/SQLite modular monolith implementing the M1 ledger
in the accepted [Company OS specification](COMPANY-OS-SPEC.md). It is source
code and test evidence only: M1 does not install a daemon, activate a runner,
change producer authority or deploy a database. M2 extends the same ledger with
the memory/context boundary documented in [`MEMORY.md`](MEMORY.md).

## Boundary

Core owns:

- immutable objective and task revisions;
- deterministic objective/task state transitions;
- UUIDv7 identities allocated inside the write transaction;
- a singular writer event log and verified current projections;
- optimistic aggregate versions, bounded leases and fencing tokens;
- run attempts, cancellation races and late-result quarantine;
- action/outbox preparation, dispatch acknowledgement and reconciliation; and
- deterministic event export plus signed local backup/restore proof.

Core does not own Git history, existing producer databases, schedules, secrets,
provider sessions, model context, external side effects or human approval. The
first four remain authoritative where the specification says they do. Secrets
must later resolve through `CredentialBroker`; no secret value belongs in a
Core command, event, export or archive.

## Storage model

`src/city2core/migrations/0001_core.sql` creates one SQLite database with:

- `events`: immutable aggregate chains with payload, prior-event and event
  SHA-256 values plus monotonic database/writer/aggregate sequences;
- `objectives`, `tasks`, `actions`: current projections bound to their exact
  terminal event ID, hash and database high-water mark;
- immutable `objective_revisions` and `task_revisions`;
- `runs`: exact task envelopes and result hashes;
- `command_dedup`: command hash and committed result by idempotency key; and
- metadata/migration/writer state used during startup verification.

Initialization enables WAL, `synchronous=FULL` and foreign keys. Every mutation
rechecks the safety settings, begins `IMMEDIATE`, checks command deduplication
and expected aggregate version, appends event(s), updates projections and
records the result before one commit. A version conflict or injected failure
rolls the whole operation back. A crash after commit is retried with the same
idempotency key and returns the original result without a duplicate event.

Core uses the M0 schemas at runtime through the same dependency-free validator
used by repository fixtures. Hash inputs use RFC 8785 JCS; integers outside the
interoperable IEEE-754 range and non-finite numbers are rejected.

## Lease and action protocol

A lease atomically creates a new run, monotonic attempt number, bounded expiry
and unpredictable fencing token. Start/result/action commands must present the
current run and fence. Cancellation clears the live fence; a late result can
only be retained as `completed_after_cancel` and cannot advance the task.

External execution is intentionally outside Core:

1. `prepare_action` commits exact parameters, approval hashes and a unique
   operation idempotency key.
2. `begin_action_dispatch` commits `dispatched` before an adapter calls the
   provider.
3. The adapter uses provider-native idempotency when available.
4. Durable provider evidence permits `confirmed`; an unknowable result becomes
   `unknown`, moves the task to `needs_reconciliation` and cannot be dispatched
   again.
5. Reconciliation confirms/fails/compensates the existing action. It never
   creates a replacement action or blindly repeats a side effect.

This ordering covers crashes before dispatch, after remote success but before
local confirmation, and after confirmation but before task transition for both
idempotent and non-idempotent providers.

## Integrity and recovery

Every open verifies the migration checksum, SQLite integrity, contiguous event
and writer sequences, payload/event/chain hashes, immutable revision/run hashes
and exact projection terminal markers. Any mismatch fails closed before a
command can run.

`backup` uses SQLite's online backup API, then derives the event export and
manifest from that snapshot. `checkpoint.json` binds the database identity,
barrier high-water, terminal hashes, manifest and checksum inventory and is
signed with Ed25519. `restore` requires the trusted public key, verifies every
binding, uses SQLite's backup API into an empty directory and re-runs full Core
integrity checks.

The M1 archive is local plaintext test evidence. Off-host use is prohibited;
authenticated encryption and backend adapters are M5 work.

## Commands

```text
./city2 core init --db PATH
./city2 core status --db PATH
./city2 core migrate --db PATH
./city2 core export --db PATH --output FILE
./city2 core keygen --private-key FILE --public-key FILE
./city2 core backup --db PATH --output DIRECTORY \
  --signing-key FILE --key-version VERSION
./city2 core verify-backup --archive DIRECTORY --trusted-key FILE
./city2 core restore --archive DIRECTORY --output-dir EMPTY_DIRECTORY \
  --trusted-key FILE
```

All runtime paths and keys must remain outside this public repository. The CLI
prints metadata and hashes, never private-key content.

## M1 evidence

`tests/test_core.py` covers:

- schema-valid objective, task, event and action records;
- immutable objective/task revisions and pinned task intent;
- optimistic conflicts, command replay and operation deduplication;
- lease fencing, expiry, retry ceiling, cancellation and late results;
- prepared/dispatched/confirmed/unknown action outcomes and reconciliation;
- interrupted side effects with and without provider-native idempotency;
- process kills before/after append, between event/projection, before/after
  commit, lease, dispatch, result, acknowledgement and backup boundaries;
- unsafe PRAGMAs, event/projection tampering and migration drift; and
- signed backup tampering plus empty-directory restore.

Run all evidence with `./city2 validate`.
