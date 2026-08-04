# Architecture

This document describes the current deployed architecture. The accepted target
company operating model, portable contracts and memory design are in the
[Company OS design specification](COMPANY-OS-SPEC.md). Acceptance defines the
destination and gates; it does not make an undeployed component current state.

## Decision

City2 is a clean control-plane replacement, not an in-place repair of the
OpenClaw workspace and not a rewrite of the functioning producer fleet.

```text
                          HUMAN PLANE
                 Chad / Telegram / Buzz Desktop
                              |
                    PfTerminal (primary harness)
                              |
                    +---------+---------+
                    |                   |
              EXECUTION PLANE      COORDINATION PLANE
              City2 Git repo        private Buzz relay
              tests / reviews       identity / channels
              deploy / rollback     signed work record
                    |                   |
                    +---------+---------+
                              |
                          DATA PLANE
           existing worker producer users and scheduled jobs
                  SQLite -> aggregates -> Git handoff
                              |
                     downstream P-U-C systems
```

## Host responsibilities

### Control host (`clawd`)

- PfTerminal and Telegram entrypoint.
- This repository and project documentation.
- Private Buzz relay on a loopback/Tailscale address.
- Initial coordinator process.
- Aggregation, review and downstream routing.

### Producer host (`worker-1`)

- Existing isolated sector producers.
- `peptide-corpus` and `swell-checker` workloads.
- Per-user credentials, schedules, SQLite state and Git handoffs.
- Later City2 worker identities, one Unix boundary at a time.

The relay does not run on the producer host. Its storage headroom is reserved
for producer data and logs.

## PfTerminal harness

PfTerminal owns the project lifecycle:

1. Interpret an owner request and define success and stop conditions.
2. Load root `AGENTS.md` and inspect repository/runtime truth.
3. Form the least-specific valid hypothesis that explains the evidence.
4. Take the smallest reversible action that tests it.
5. Measure the result, revise from evidence and repeat without reusing an
   unchanged failed approach.
6. Run validation and review proportional to risk.
7. Execute approved deployment/rollback commands.
8. Return durable evidence to the owner and, when enabled, the Buzz thread.

This is a bounded optimization loop, not an always-running context loop. Every
pass must reduce uncertainty or improve a verified result; completion, a
documented blocker, an iteration limit or a human gate terminates it.

`./city2` is the stable command surface. It roots headless PfTerminal turns in
this repository and prevents the project from depending on an OpenClaw
workspace prompt or heartbeat.

Buzz ACP agents are subordinate runtime processes. The initial adapter is the
pinned Buzz ACP stack plus pinned Codex ACP adapter, authenticated from the
existing PfTerminal ChatGPT login through one systemd credential. Its lifecycle,
configuration and code changes remain controlled and reviewed through
PfTerminal. Buzz is not an alternate superuser control path.

## Buzz stack

The pinned single-relay bundle contains:

- Buzz relay
- PostgreSQL 17
- Redis 7
- MinIO/S3 media storage
- Git storage volume

The only published container port is the relay, bound to one explicit
loopback/Tailscale address. Caddy and public ports 80/443 are outside this repo.

## Workspace model

Start with three private channels:

| Channel | Type | Purpose |
|---|---|---|
| `control` | stream | Owner requests, priorities and stop/rotate commands |
| `city2` | forum | One thread per work item and its evidence loop |
| `ops` | stream | Health, backup and operator events without secrets |

Every substantive update uses:

```text
Outcome: what is now true
Evidence: source URLs, file paths, commits and timestamps
Changes: exact state modified, or none
Checks: commands and results
Gate: owner action required, or none
```

Add research, build, review and release channels only when distinct identities
and traffic justify them.

## Data authority

| Data | Authority | Buzz stores |
|---|---|---|
| Code | GitHub/Git | Commit, patch and review context |
| Research/corpuses | SQLite/YAML/JSON on scoped hosts | Finding and artifact pointer |
| Decisions | Project docs plus signed thread | Rationale and approval record |
| Secrets | PfTerminal vault or approved host secret file | Never |
| Backups | Host backup store | Backup ID and verification result |
| Releases | Existing deployment/publication system | Hash, URL, result and rollback pointer |

## Company OS implementation boundary

M0 adds no daemon or authority. It freezes the portable boundary:

- canonical schemas live in `schemas/v1/`;
- runner, CredentialBroker, archive and authority semantics live in
  `contracts/v1/`;
- the deny-by-default vocabulary is `config/authority-policy.v1.json`;
- valid/adversarial examples live in `fixtures/contracts/v1/`; and
- `scripts/validate_contracts.py` proves schema coverage and JSON round trips.

M1 implements an undeployed, single-writer SQLite Core under `src/city2core/`.
It owns objective/task lifecycle, immutable event chains, current projections,
leases, action/outbox reconciliation and signed local backup proof. The Core CLI
is `./city2 core`; its contract and recovery procedure are in
[`CORE.md`](CORE.md). Process-kill fixtures prove transaction rollback or
idempotent committed replay at every M1 boundary.

This implementation does not change the deployed diagram or data authorities
above. Buzz/Telegram remain interfaces, PfTerminal remains the project harness,
and no interface or runner becomes authoritative. A Core database is not a
replacement for Git or producer databases, and no service activation occurs in
M1.

M2 adds an undeployed `MemoryService` in the same modular monolith. It owns
evidence-backed candidate/review state, accepted-memory FTS, deterministic
scoped retrieval, context-pack manifests and candidate-only controlled imports.
It stores no transcript or model hidden state and does not connect the live
coordinator; that remains M3.

M3 adds offline Buzz and PfTerminal adapters plus a read-only CEO projection.
The adapter is owner/channel/A0 constrained and runner capability negotiation
fails closed. The live coordinator is deliberately not routed through Core by
this source change; see [`ADAPTERS.md`](ADAPTERS.md) for the activation gate.

M6 adds a disabled read-only producer observer. It hashes one exact declared
output and emits signed provenance plus candidate memory without reading a
producer database or becoming a downstream dependency. No live producer is
selected by source alone; see [`PRODUCER.md`](PRODUCER.md).

M7 adds a provider-neutral expansion-admission gate. It can approve only one
same-authority role or one-class write-authority increase after measurable
evidence, evaluation, budget, incident and removal checks. The first Core-routed
coordinator candidate is disabled and deferred; see
[`EXPANSION.md`](EXPANSION.md).

## Safety gates

1. **Repository:** validation and review pass.
2. **Relay:** owner public identity, private binding and backup path verified.
3. **Coordinator:** one owner-only, mention-driven, no-heartbeat process.
4. **Scoped write:** filesystem boundary and rollback tested.
5. **Producer:** one worker identity and one existing producer at a time.
6. **Outward action:** separate operator identity and explicit owner approval.

The Company OS milestones add stronger gates; they never weaken these current
deployment gates. In particular, A1+ acceptance requires the independent-review
boundary before an agent-driven scoped write is activated.
