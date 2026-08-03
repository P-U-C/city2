# City2 Company OS threat model

| Field | Value |
|---|---|
| Version | 1.0.0 |
| Date | 2026-08-03 |
| Scope | M0 canonical contracts and the planned Core/runner boundaries |
| Runtime authorization | None; M0 changes no deployment or authority |

## Security objective

An untrusted message, model, runner, tool, archive backend or provider must not
be able to alter durable company truth, widen authority, obtain a secret,
repeat an uncertain side effect or persist unreviewed memory. Loss of an
interface or replaceable backend must not lose authoritative state.

## Assets

1. Objective, task, approval, action, event and memory integrity.
2. Credential, wallet, archive and identity private material.
3. Exact human approvals and their remaining execution counts.
4. Source provenance, artifact hashes and signed backup checkpoints.
5. Availability of Core state and at least one independently recoverable copy.
6. Scope isolation between agents, departments, projects and tasks.
7. Chad's attention: alerts and approval requests must be bounded and genuine.

## Trust boundaries

```text
untrusted content / human interfaces
               |
               v
       interface adapters (untrusted input)
               |
               v
 City2 Core + policy + single writer (trusted computing base)
       |          |             |
       v          v             v
    runner     broker        archive backend
  untrusted   trusted narrow   untrusted bytes
  workload    infrastructure   and availability
       |
       v
 model/provider/tools/external systems (untrusted or partially trusted)
```

Git commits, producer databases and signed source evidence are authoritative
only for their declared domains. Their content is still untrusted instruction
input. Buzz and Telegram authenticate an interface actor but do not confer Core
authority.

## Adversaries and failure sources

- malicious or compromised external content attempting prompt injection;
- a mistaken, compromised or incentive-misaligned agent/model;
- a runner that silently drops schemas, limits, cancellation or accounting;
- a confused-deputy tool, broker or interface adapter;
- replay, reordering, duplication, stale leases and crash windows;
- a compromised archive backend serving missing or substituted bytes;
- an operator mistake, stale approval, bad migration or incomplete deletion;
- host, database, provider, network or credential-backend loss.

The initial M0 validator and repository are not a security boundary. M1 must
implement the deterministic controls described here before Core writes are
trusted.

## Threats and required controls

| Threat | Failure mode | Required deterministic control | Proof gate |
|---|---|---|---|
| Spoofed canonical identity | Adapter chooses a privileged ID | Core-only UUIDv7 allocation; collision quarantine | ID and import fixtures |
| Approval spoof/replay | Broad or stale grant authorizes changed operation | Exact immutable approval; atomic use count; expiry/revocation checks | Approval mismatch and overconsumption fixtures |
| Prompt-based privilege escalation | Retrieved text asks for a hidden tool or policy change | Deny-by-default intersection outside the model; undeclared capability absent | Hostile-content and undeclared-tool conformance |
| Confused deputy | Allowed tool applies valid credential to another target | Broker recomputes operation/approval binding and emits no value | Broker target-mismatch test |
| Secret exfiltration | Secret reaches prompt, result, event, log or schema | Opaque handles; ephemeral materialization; forbidden canonical fields; redaction tests | Secret-field fixture and process inspection |
| Task/result replay | Duplicate or late result mutates accepted state | Expected aggregate version, lease fence, idempotency and late-result quarantine | Cancellation and stale-fence tests |
| Repeated side effect | Crash after remote success triggers blind retry | Prepared outbox record, provider evidence, `unknown` reconciliation | Every dispatch crash boundary |
| Event tampering | Event deleted/reordered or projection edited | Hash/sequence verification, single writer and trusted signed checkpoints | Gap/hash mismatch plus empty restore |
| Memory poisoning | Untrusted claim becomes future policy/context | Candidate-only writes, provenance, independent review, scope and staleness filters | Poisoned/revoked-source fixtures |
| Context displacement | Large content hides policy or criteria | Fixed section order/budgets, deterministic truncation and manifest | Budget/truncation reproducibility test |
| Runner deception | Unsupported limit is silently ignored | Versioned capabilities; degraded/unsupported declaration; fail-closed negotiation | Silent-degradation fixture and hostile runner |
| Reviewer collusion | Maker self-accepts or reviewer can execute | Distinct identity/session/workspace/credential/capability dimensions | A1+ negative authorization test |
| Archive substitution | Backend serves another valid ciphertext | Ciphertext hash, repeated archive/checkpoint IDs and signed receipt | Independent retrieval and substitution test |
| Archive expiry/loss | Renewal fails and only off-host copy expires | Early renewal, bounded verification deadline, second-backend fallback | Failed-renewal drill |
| Incomplete deletion | Search, backup or archive copy survives | Versioned deletion order across every representation; crypto-erasure proof | Synthetic deletion drill |
| Telemetry leakage | Content or stable IDs leave the protected store | Low-cardinality allowlist and keyed short-lived trace correlation | Export inspection and cardinality test |
| Denial/attention exhaustion | Agent floods queue, approvals or alerts | Per-agent concurrency/budget, dedupe, rate limits and exception thresholds | Load and duplicate-request test |

## M0 fixture coverage

Committed invalid fixtures prove that the contract boundary rejects secret
fields, null budgets, tasks without acceptance criteria or immutable inputs,
unfenced results, hidden event state, unsourced facts, unbounded or overconsumed
approvals, blind-retry action states, unsigned archive receipts, silent runner
degradation, allow decisions containing a deny and deletion records containing a
raw subject.

These are shape and semantic contract proofs only. They do not prove SQLite
atomicity, process isolation, credential cleanup, remote reconciliation,
cryptography or restore correctness; those remain explicit M1-M5 gates.

## Security invariants for implementation

1. Core validates schema and semantics before evaluating authority.
2. Validation failure has no side effect and emits only bounded diagnostics.
3. One application writer commits event and projection changes atomically.
4. No runner/model can invoke `CredentialBroker` outside an approved operation.
5. No interface, provider session or model output is authoritative by itself.
6. Unknown external outcomes are never automatically retried.
7. Unreviewed/stale/revoked memory never enters a context pack.
8. Every M1+ change adds a failure-injection or negative authorization test at
   its new trust boundary.

## Residual risks and review triggers

- The custom offline validator implements only the schema keywords linted in
  `scripts/validate_contracts.py`; validation also cross-checks with the
  standard `jsonschema` implementation whenever it is installed. Adding a
  keyword requires tests in both paths.
- JSON Schema cannot prove digest correctness, temporal ordering, exact
  criterion coverage or cryptographic validity. Core must enforce these as
  semantic checks.
- A compromised control host can attack the initial single-host trusted
  computing base. Signed off-host checkpoints and restore proofs limit
  undetected persistence; they do not prevent compromise.
- Human approval can still authorize a harmful exact operation. The CEO surface
  must show target, effect, rollback, evidence and bounded cost without relying
  on model prose.

Review this model at every milestone, any authority expansion, any new runner or
credential/archive backend, and after an incident or failed drill.
