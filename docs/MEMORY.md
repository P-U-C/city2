# City2 Memory and Context — M2

M2 implements durable memory and deterministic context assembly on the M1
ledger. It remains undeployed: no coordinator, runner, Buzz channel or producer
is routed through this code yet.

## Admission and review

`MemoryService.create_candidate` is the only creation path. It allocates a Core
ID, validates `city2.memory/v1`, rejects secret-shaped content/metadata and
coalesces the same canonical candidate within a scope. Non-hypotheses require
evidence. Evidence binds an authoritative owner, URI, retrieval method, exact
content hash, observation time and revocation/validity status.

Agents cannot accept their own candidate. Company-scope acceptance requires
`human:chad`; source checks must exactly prove every reference current. Review
records contain only fixed boolean independence dimensions. Conflicting
accepted facts are quarantined in an explicit conflict record rather than
overwritten. A replacement names exact accepted records in `supersedes`; their
events and projections atomically become `superseded` when the replacement is
accepted.

Accepted memory alone enters FTS. Rejected, quarantined, stale and superseded
records remain auditable but never enter context.

## Revalidation

Retrieval excludes a record when its revalidation or validity deadline passed,
its source is non-current or its sensitivity exceeds the caller's clearance.
Context assembly first runs the deterministic stale sweep so deadline failures
also emit `memory.stale` events and leave FTS. Source-change signals compare the
exact URI/content hash and stale affected records immediately. Critical fact
classes enforce a maximum 24-hour interval from the last source/revocation
check. Revalidation can restore the same exact evidence; changed content must
become a new reviewed candidate.

## Retrieval policy v1

- query normalization: Unicode NFKC, casefold, whitespace collapse;
- index: SQLite FTS5 `unicode61 remove_diacritics 2` over statement, labels and
  source metadata;
- filter order: explicit scope allowlist, accepted state, sensitivity,
  validity/source state, FTS match;
- ranking: type-policy priority, deterministic normalized term frequency
  quantized to six decimals, latest evidence time, then memory ID;
- tokenizer/budget: deterministic Unicode-codepoint `ceil(chars/4)` profile;
- excerpt: prefix truncation to the exact per-section budget.

`rebuild_index` derives FTS entirely from accepted projections and runs full
integrity verification. The integrity checker compares every indexed row to
canonical projection content, so missing, extra or poisoned index rows fail
closed.

## Context packs

`assemble_context` requires an existing leased run and refuses scopes not
granted by its immutable task envelope. It stores a schema-valid
`city2.context-pack/v1` manifest containing the event/memory snapshot, filters,
candidate and exclusion sets, scores, stable tie-breaks, selected excerpts,
section budgets and hashes. The durable content includes the task intent,
criteria and constraints but deliberately does not duplicate the active lease
fencing token. A fresh process can reconstruct the same work from Core without
conversation history.

## Export and merge

`export_memories` emits accepted records and their original, hash-verified
memory events in stable sequence order. Import verifies every event identity and
hash. Unknown external records become local **candidates** with new Core IDs;
they never append foreign canonical transitions or gain acceptance. Reimport is
idempotent. Event identity collisions or altered payloads fail closed.

## Evidence

`tests/test_memory.py` proves candidate/review rules, company authority,
secret/poisoned-source rejection, cross-scope and sensitivity isolation,
supersession/conflict handling, stale/revalidation and critical SLOs,
deterministic FTS rebuild, bounded fresh-session context, candidate-only
export/import and verified M1→M2 migration. Run all checks with
`./city2 validate`.
