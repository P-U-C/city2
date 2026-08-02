# City2 Company OS design specification

| Field | Value |
|---|---|
| Status | Draft for independent agent review |
| Version | 0.2.0 |
| Date | 2026-08-02 |
| Owner | Chad (`0xzoz`) |
| Scope | Target operating model, contracts, memory and staged implementation |
| Current implementation | City2 Phase 2: private relay plus one read-only coordinator |

This document is intentionally non-normative until Chad accepts it after
review. It specifies the desired end state and the smallest path from the live
City2 system to that state. It does not authorize deployment, producer changes,
new credentials, wallet activity or external publication.

The key words **MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT** and **MAY** are
used as requirement levels for review.

## 1. Executive decision

City2 will be a small, vendor-neutral company operating system in which Chad
acts as CEO and a measured fleet of role-scoped agents performs work through
PfTerminal. It will not be a persistent group chat, a model-provider feature or
a swarm that keeps context windows alive.

The design has one stable center and replaceable edges:

- **City2 Core** owns objectives, tasks, events, policy, memory metadata,
  approvals, runs and evaluations.
- **Git and existing databases** remain authoritative for code, procedures,
  corpuses and production state.
- **PfTerminal** is the first execution runner, but its task/result boundary is
  portable.
- **Buzz and Telegram** are human interfaces, not task or memory authorities.
- **MCP, ACP and later A2A** are adapter protocols, not sources of truth.
- **Walrus** MAY hold encrypted, verifiable archives; it is not live memory.
- **Model sessions are disposable.** Durable state exists outside every model
  context window.

The first implementation MUST be a modular monolith with one database and one
dispatcher. New frameworks, services and agents are admitted only after a
measured requirement appears.

## 2. Problem statement

The old City control path failed because useful production systems became
coupled to a mutable OpenClaw workspace and one vendor-sensitive harness. It was
hard to determine what was authoritative, difficult to migrate cleanly and too
easy for context, prompts and runtime assumptions to become infrastructure.

City2 must support an automated company without recreating those conditions.
In particular, it must:

1. preserve company knowledge when a model, provider, harness or interface is
   replaced;
2. resume work from durable task state rather than conversation history;
3. prevent agents from creating competing copies of company truth;
4. make every consequential action attributable, reviewable and reversible;
5. give Chad a CEO-level decision surface instead of a stream of agent chatter;
6. add automation only when it creates measured throughput or reliability;
7. keep the functioning City producer/data plane operational throughout the
   migration.

## 3. Current baseline

As of 2026-08-02, the following is live:

- a public source repository, with runtime state, identities, credentials,
  backups and host-specific configuration kept private and off-repository;
- PfTerminal as the project implementation and operational harness;
- a private overlay-network Buzz relay with three private bootstrap channels;
- one owner-only, mention-driven, heartbeat-off coordinator with a read-only
  repository mount and no access to the operator's vault, sessions or memory;
- the existing isolated producer fleet, schedules, SQLite and Git handoffs
  unchanged;
- verified relay, state and encrypted agent-identity backups;
- repository validation and GitHub CI.

The coordinator currently has no durable City2 memory. There is no typed task
ledger, context assembler, policy engine, agent registry, independent reviewer
or producer agent. Chad and the coordinator also currently both hold Owner role
in the three bootstrap channels; coordinator demotion to Bot/Member and the
first owner-authored read-only model proof remain human gates.

## 4. Goals

### 4.1 Functional goals

City2 MUST provide:

- a company objective, project and task ledger;
- stable role and agent identities independent of model/provider;
- deterministic task assignment, leasing, retry and recovery;
- scoped private, department and company memory;
- evidence-backed memory promotion and supersession;
- deterministic bounded context assembly for every run;
- policy-driven authority and human approval;
- independent review for consequential outputs;
- provider-, runner-, interface- and archive-adapter boundaries;
- export, restore and merge procedures that do not require an LLM;
- run-level cost, latency, quality and failure observability;
- concise CEO briefs and an exception/approval inbox.

### 4.2 Non-functional goals

The system MUST be:

- **portable:** no authoritative state in a provider conversation or hosted
  memory feature;
- **durable:** abrupt process or host failure cannot erase accepted work;
- **inspectable:** an operator can understand state with SQL, JSON, Markdown and
  ordinary command-line tools;
- **least-privileged:** every agent has a narrow Unix, filesystem, network,
  tool, credential and policy boundary;
- **bounded:** every run has explicit context, turn, time and cost ceilings;
- **replay-safe:** completed side effects are not repeated after retries;
- **mergeable:** exports use stable IDs, immutable events and explicit conflict
  records;
- **boring to operate:** one host and one durable database until measurements
  justify distribution.

## 5. Explicit non-goals

City2 v1 MUST NOT attempt to provide:

- artificial general management or fully autonomous company strategy;
- an always-running LLM context or heartbeat fleet;
- autonomous financial, wallet, publishing or third-party messaging authority;
- a replacement for Git, producer SQLite databases or existing schedulers;
- a universal knowledge graph;
- a mandatory vector database;
- Kubernetes, a service mesh or one microservice per agent;
- simultaneous adoption of multiple agent orchestration frameworks;
- raw transcript retention as company memory;
- model-generated summaries as the sole record of decisions or facts;
- automatic migration of every existing producer.

## 6. Design invariants

These are the architectural rules reviewers should treat as hardest to change.

1. **City2 owns durable control state.** Interfaces and runners do not.
2. **Context is not memory.** A context window is a bounded task-local cache.
3. **Artifacts outrank recollection.** Git, databases and source evidence remain
   authoritative.
4. **Events are append-only.** Corrections supersede; they do not erase history.
5. **One fact has one canonical owner.** Other stores keep pointers or derived
   indexes, not divergent copies.
6. **Workflows precede agents.** Deterministic code handles known repeatable
   paths; models handle ambiguity and judgment.
7. **Identity is not authority.** A valid agent signature does not grant a tool,
   credential or production permission.
8. **No agent self-promotes.** Shared memory, authority and budgets require an
   explicit policy transition.
9. **Every outward side effect has an idempotency key and evidence.**
10. **Every replaceable layer has a conformance test and export path.**
11. **No new component without a measured reason and removal playbook.**

## 7. Target architecture

```text
                         CHAD — CEO
                             |
              goals, budgets, approvals, overrides
                             |
              +--------------+--------------+
              | CEO interfaces              |
              | Buzz | Telegram | CLI        |
              +--------------+--------------+
                             |
                  stateless interface adapters
                             |
  +--------------------------v---------------------------+
  |                     CITY2 CORE                       |
  | objectives | tasks | events | policy | approvals    |
  | agents | memory | artifacts | runs | evals | budget |
  +----------+-------------------+------------------------+
             |                   |
       context builder      dispatcher / workflow engine
             |                   |
             +---------+---------+
                       |
                 runner contract
          +------------+-------------+
          |            |             |
     PfTerminal     future runner   local runner
          |            |             |
          +------------+-------------+
                       |
             MCP tools / scoped capabilities
                       |
       Git | SQLite | producers | publishing systems

  Cross-cutting: audit events, policy, backups, evaluations,
                 OpenTelemetry, archive adapters
```

### 7.1 Deployment shape

The initial implementation SHOULD contain:

- one `city2d` user service on the control host;
- one SQLite WAL database under a dedicated runtime-state directory;
- one local content-addressed artifact directory;
- one PfTerminal runner adapter;
- one Buzz interface adapter;
- one deterministic context assembler;
- one policy file and approval evaluator;
- one backup/export command;
- existing agent services as separately hardened processes.

`city2d` is a modular monolith. Modules communicate through typed in-process
interfaces and the database, not a network of internal services.

### 7.2 Data ownership

| Data | Authority | Derived/cached representations |
|---|---|---|
| Company constitution and procedures | Git | Context packs, search index |
| Code and configuration | Git | Build output, reviews |
| Objectives, tasks and approvals | City2 Core DB | Buzz cards, CEO briefs |
| Run and task history | Append-only City2 events | Current-state projections |
| Agent private/department/company memory | City2 Core DB plus source pointers | FTS/vector index, context packs |
| Producer facts and corpuses | Existing producer DB/files | Memory pointers and summaries |
| Large task artifacts | Content-addressed artifact store/Git as appropriate | Buzz links, archive bundles |
| Secrets | Versioned `CredentialBroker` contract | PfTerminal vault or reviewed host store as replaceable backend; ephemeral credentials only |
| Archive copies | Local encrypted backups; optional Walrus backend | Availability manifests |

## 8. Stable contracts

All contracts MUST have a semantic schema version. Core-generated canonical IDs
MUST use UUIDv7 with the documented type prefix (`agt_`, `obj_`, `tsk_`,
`run_`, `mem_`, `evt_`, `act_`, `apr_`, `art_`, `rev_`, `fnd_`, `ctx_`,
`del_`, `arc_`) and lowercase canonical UUID text.
Adapters may submit a separate namespaced client request ID but MUST NOT choose a
canonical ID. Imports accept only the same ID profile: an identical ID/payload
is idempotent; the same ID with a different payload is a collision and fails
closed into reconciliation. External system IDs are namespaced attributes, not
City2 IDs. Timestamps MUST be UTC RFC 3339. Hash fields MUST name their
algorithm. Every mutable aggregate carries a monotonic `aggregate_version`, and
every state-changing command MUST supply its expected version.

### 8.1 Agent manifest

An agent is a stable organizational identity and contract, not a model session.

```json
{
  "schema_version": "city2.agent/v1",
  "agent_id": "agt_<uuidv7>",
  "manifest_version": 1,
  "manifest_sha256": "<sha256>",
  "name": "research-reviewer",
  "role": "reviewer",
  "department": "intelligence",
  "reports_to": "agt_<uuidv7>",
  "runner_policy": "coding-default",
  "required_capabilities": [
    "structured_output",
    "tool_calls",
    "cancellation",
    "usage_accounting"
  ],
  "model_policy": "quality-default",
  "authority_class": "A0",
  "allowed_task_types": ["research_review"],
  "tools": ["corpus_read", "web_read"],
  "filesystem_scopes": ["repository:read"],
  "network_policy": "research-readonly",
  "credential_handles": [],
  "memory_read_scopes": [
    "company",
    "department:intelligence",
    "agent:self"
  ],
  "memory_write_scopes": [
    "candidate:agent:self",
    "candidate:department:intelligence"
  ],
  "context_profile": "reviewer-default",
  "time_budget_seconds": 1800,
  "cost_budget": {
    "max_billable_usd": "0.00",
    "max_input_tokens": 30000,
    "max_output_tokens": 8000
  },
  "concurrency": 1,
  "review_policy": "independent",
  "enabled": false
}
```

The manifest MUST NOT contain secret values. Credential handles are opaque
policy references resolved outside the model environment. `runner_policy`
expresses required behavior, not an implementation name; the dispatcher records
the concrete runner on each run. A missing or `null` cost budget denies dispatch
rather than granting unlimited spend.

### 8.2 Objective

An objective records CEO intent, success measures, constraints, budget, owner,
review date and status. It MUST NOT be represented only by a chat message.

Required fields:

- `objective_id`, immutable `objective_revision`, `objective_sha256`,
  `schema_version`, `title`, `intent`;
- `created_by`, `accountable_owner`, `created_at`, `review_at`;
- measurable outcomes and stop conditions;
- authority ceiling and aggregate budget;
- status and supersession link.

Objective revisions are immutable. Changing intent, outcomes, budget, authority
or stop conditions creates a new revision and hash. Every task references one
exact revision/hash and never inherits a later expansion automatically.

### 8.3 Task envelope

Core owns the task record, including lifecycle state, lease, aggregate version,
attempts and review links. The task envelope is an immutable dispatch input to a
runner and deliberately excludes Core-owned lifecycle state.

```json
{
  "schema_version": "city2.task/v1",
  "task_id": "tsk_<uuidv7>",
  "task_revision": 2,
  "task_envelope_sha256": "<sha256>",
  "objective_id": "obj_<uuidv7>",
  "objective_revision": 1,
  "objective_sha256": "<sha256>",
  "task_type": "repository_analysis",
  "title": "Assess the first producer integration",
  "intent": "Produce a no-change recommendation with evidence",
  "created_by": "human:chad",
  "requested_role": "city2-coordinator",
  "resolved_agent_id": "agt_<uuidv7>",
  "resolved_manifest_version": 3,
  "resolved_manifest_sha256": "<sha256>",
  "attempt_number": 1,
  "expected_task_version": 7,
  "lease_fencing_token": "<opaque-random-token>",
  "authority_class": "A0",
  "inputs": [{
    "uri": "git+https://github.com/P-U-C/city2.git",
    "git_commit_sha1": "<40-lowercase-hex>"
  }],
  "constraints": ["read_only", "no_external_action"],
  "acceptance_criteria": [
    {"criterion_id": "ac_1", "requirement": "cites current contracts"},
    {"criterion_id": "ac_2", "requirement": "names rollback"}
  ],
  "memory_scopes": ["company", "project:city2"],
  "time_budget_seconds": 1800,
  "max_attempts": 2,
  "task_dedupe_key": "<namespaced-request-key>",
  "supersedes_run_id": "run_<uuidv7>",
  "review_id": "rev_<uuidv7>",
  "unresolved_finding_ids": ["fnd_<uuidv7>"]
}
```

The task MUST contain intent and acceptance criteria, not merely a prompt. A
runner MAY render the envelope into provider-specific instructions, but that
rendered prompt is not authoritative. `requested_role` is planning input;
`resolved_agent_id` and the immutable manifest version/hash are selected at
lease time. Review fields are required only for a revised task returning from
`changes_requested`. Task deduplication never substitutes for operation-level
idempotency.

### 8.4 Result envelope

Every run returns a provider-neutral result:

```json
{
  "schema_version": "city2.result/v1",
  "task_id": "tsk_<uuidv7>",
  "task_revision": 2,
  "run_id": "run_<uuidv7>",
  "expected_task_version": 7,
  "lease_fencing_token": "<opaque-random-token>",
  "run_status": "completed",
  "runner": {"id": "pfterminal", "version": "<version>"},
  "model": {
    "provider": "<provider>",
    "model": "<model>",
    "capability_profile": "<profile-version>"
  },
  "agent_manifest_version": 3,
  "agent_manifest_sha256": "<sha256>",
  "context_pack_ref": {
    "artifact_id": "art_<uuidv7>",
    "sha256": "<sha256>"
  },
  "outcome": "...",
  "artifacts": [],
  "evidence": [{
    "criterion_id": "ac_1",
    "validator": {"id": "source-check", "version": "1"},
    "subject_sha256": "<sha256>",
    "result": "pass",
    "checked_at": "2026-08-02T00:00:00Z",
    "provenance": [{"uri": "git+https://github.com/P-U-C/city2.git", "git_commit_sha1": "<40-lowercase-hex>"}]
  }],
  "checks": [{
    "criterion_id": "ac_2",
    "validator": {"id": "review-check", "version": "1"},
    "subject_sha256": "<sha256>",
    "result": "pass",
    "checked_at": "2026-08-02T00:00:00Z"
  }],
  "memory_candidates": [],
  "approvals_requested": [],
  "usage": {"wall_seconds": 0, "input_tokens": 0, "output_tokens": 0},
  "errors": []
}
```

Completion MUST contain one machine-checkable acceptance record for every
mandatory criterion, including validator identity/version, subject hash,
result, time and provenance where applicable. Model prose alone is not
completion evidence. The result records run outcome; only Core may transition
task state.

### 8.5 Event envelope

Task, memory, approval and agent state changes MUST emit immutable events with:

- event ID and schema version;
- aggregate type and ID;
- event type, `aggregate_version` and per-aggregate sequence;
- authoritative `writer_id` and monotonic per-writer sequence;
- actor identity;
- occurred and recorded timestamps;
- idempotency key;
- prior-event hash within the aggregate chain and payload hash;
- structured payload;
- sensitivity classification.

The authoritative write model is one atomic SQLite transaction: begin with an
expected aggregate version, verify it, allocate the next aggregate and writer
sequences, append immutable event(s), update projection rows, and commit. A
version mismatch changes nothing and returns a conflict. The append-only event
log is the canonical transition history; projection tables are authoritative
for current reads only while their recorded event high-water marks and hashes
match the log.

Projection rebuild verifies event IDs, aggregate versions, sequence continuity,
payload hashes and per-aggregate chain hashes. Any gap, mismatch or disagreement
between a projection and the event stream fails closed, quarantines the
aggregate and requires recovery from a trusted checkpoint or operator review.
The v1 writer is singular; its global database sequence is a local restore
ordering aid, not a cross-writer merge order.

### 8.6 Artifact reference

An artifact reference includes media type, byte length, SHA-256, storage URI,
producer run, creation time, sensitivity and optional Git commit. Mutable paths
MUST be paired with immutable hashes.

### 8.7 Context-pack manifest

The context pack is a sensitivity-classified artifact. Its manifest records the
assembler, retrieval and tokenizer versions; normalized query; source snapshot;
candidate memory IDs; filters; ranking scores; selected IDs and excerpts;
excluded IDs with reasons; stable tie-break order; per-section truncation; token
counts; task-envelope hash; and final pack hash. Telemetry records only the
manifest ID/hash/size and bounded aggregate counts, never excerpts or pack
content.

### 8.8 Approval object

An approval is a versioned, immutable capability grant, not an authority-class
label. It binds:

- approval ID/schema and policy version;
- exact capability/tool and target resource;
- canonical parameters plus input/artifact hashes;
- task revision, run, requester and approver;
- operation idempotency key;
- issue time, expiry and maximum executions;
- any recurring budget envelope and revocation state.

Any parameter, target, artifact, task revision or policy change invalidates the
approval. Execution atomically consumes one permitted use. Missing, expired,
revoked, exhausted or unparsable approval denies the operation.

### 8.9 Action/outbox record

Every side effect has a durable action record separate from the task dedupe key.
It binds canonical operation parameters, exact approval, target, provider,
operation-level idempotency key, task/run and compensation where available.
States are `prepared`, `dispatched`, `confirmed`, `unknown`, `failed` and
`compensated`.

Core commits `prepared` before dispatch. Provider-native idempotency is used
where available. After dispatch, confirmation is recorded only from durable
provider evidence. A crash after remote success but before confirmation yields
`unknown`; it MUST be reconciled against the external system and MUST NOT be
blindly retried. If the outcome cannot be established, the task enters
`needs_reconciliation` and escalates.

### 8.10 CredentialBroker

`CredentialBroker` is deterministic infrastructure with a replaceable backend:

```text
CredentialBroker
  resolve(handle, operation, approval) -> ephemeral credential reference
  rotate(handle) -> rotation receipt
  revoke(handle) -> revocation receipt
  export_recovery_metadata() -> encrypted, backend-neutral recovery bundle
```

It validates the exact operation and approval, materializes the minimum secret
through a reviewed ephemeral path, emits a content-free audit event and removes
the material after use. Secret values never enter Core, model context, events or
telemetry. PfTerminal's vault is the first backend, not the canonical contract.

## 9. Task and workflow model

### 9.1 Task states

```text
proposed -> awaiting_approval -> ready -> leased -> running -> review -> accepted
    |              |              |        |          |         |
    +-> rejected   +-> rejected   |        |          |         +-> changes_requested
                                  |        |          |                    |
                                  |        |          |                    +-> ready (new task revision)
                                  |        |          +-> cancellation_requested -> cancelled
                                  |        |          +-> needs_reconciliation
                                  |        |          +-> failed_terminal
                                  |        +-> expired -> ready (replay-safe only)
                                  |                    +-> needs_reconciliation
                                  +-> cancelled
```

Transitions MUST be validated by deterministic code. Agents MAY recommend a
transition but MUST NOT directly mutate policy-protected states.

`rejected`, `cancelled`, `accepted` and `failed_terminal` are task-terminal.
Acceptance describes the output, not an external action: later compensation is
recorded on the action record and does not rewrite accepted history. Returning
from `changes_requested` creates a new immutable task revision that references
the prior run, review and unresolved finding IDs. Acceptance verifies that each
finding was dispositioned. Revision and attempt counters are separate.

Cancellation has request and confirmed states. On request, Core fences the
lease, revokes task-scoped capabilities and signals the runner. `cancelled` is
entered only after the runner is stopped and no action is unconfirmed. A late
result is stored as `completed_after_cancel`, quarantined from acceptance and
cannot mutate task or memory state.

### 9.2 Leasing and recovery

- Workers lease tasks for a bounded period.
- A lease has an owner, fencing token, expiry, monotonic attempt number and
  expected task aggregate version.
- Expired work returns to `ready` only if its operation is replay-safe.
- Expired work with dispatched or uncertain effects enters
  `needs_reconciliation`.
- External actions MUST use the Section 8.9 outbox protocol.
- Completed steps MUST NOT be repeated after process recovery.
- A retry creates a new run ID but retains the task ID.
- After the attempt ceiling, the task becomes `failed_terminal` or requires
  human review.
- Result envelope, artifact references, emitted events, lease closure and next
  task state commit atomically after artifact existence and action outcomes are
  verified.

### 9.3 Workflow versus agent decision

Use deterministic workflow code when inputs, transitions and success criteria
are known. Use an agent only when interpretation, synthesis or adaptation is
material.

Examples:

| Work | Mechanism |
|---|---|
| Backup, checksum, expiry check | Deterministic workflow |
| Schema validation and CI | Deterministic workflow |
| Research synthesis | Agent task with evidence |
| Editorial judgment | Agent task plus reviewer |
| Deployment sequence | Deterministic workflow with approval gate |
| Incident diagnosis | Agent assists; operator controls changes |

### 9.4 Run lifecycle

Each run MUST:

1. obtain a task lease;
2. resolve the immutable agent manifest and negotiate runner capabilities;
3. evaluate policy and authority, failing if any required capability is absent;
4. assemble a bounded context pack;
5. start a fresh runner/model session;
6. execute within turn, time, tool and cost limits;
7. store content-addressed artifacts and reconcile action records;
8. return a result envelope and acceptance records;
9. atomically record references/events, close the fenced lease and transition
   the task;
10. destroy task-local model state.

Conversation reuse is disabled by default. A task MAY have several runs, but
continuation is reconstructed from task state, artifacts and accepted memory.

## 10. Memory model

### 10.1 Definition

City2 memory is durable, typed information selected for future task use. It is
not the full message log, model hidden state, a recursive summary or everything
an agent happened to observe.

### 10.2 Memory scopes

| Scope | Purpose | Default writers |
|---|---|---|
| `agent:<id>` | Role-specific feedback, techniques and prior outcomes | Owning agent as candidates |
| `department:<id>` | Verified domain knowledge and procedures | Department reviewer |
| `project:<id>` | Decisions, constraints and facts for one project | Project owner/reviewer |
| `company` | Constitution, global decisions, systems and durable preferences | Chad or delegated reviewer |
| `task:<id>` | Temporary working state | Current run; expires with task policy |

Agents MUST NOT write accepted company memory directly. They create candidates.
Agent manifests express writes only as `candidate:<scope>`; acceptance is a Core
transition performed by an authorized reviewer. Task-local working state is a
separate Core record, not accepted memory.

### 10.3 Memory types

- `fact`: externally or operationally verifiable statement;
- `decision`: an accountable choice and rationale;
- `procedure`: repeatable steps and preconditions;
- `feedback`: instruction about how an agent or role should operate;
- `outcome`: result of a completed task or experiment;
- `hypothesis`: unverified belief with explicit confidence;
- `reference`: pointer to an authoritative source;
- `preference`: durable CEO or stakeholder preference.

### 10.4 Memory record

```json
{
  "schema_version": "city2.memory/v1",
  "memory_id": "mem_<uuidv7>",
  "scope": "project:city2",
  "type": "decision",
  "statement": "Model sessions are disposable; City2 owns durable state.",
  "evidence_refs": [{
    "relationship": "observed_from",
    "source_type": "git_blob",
    "authoritative_owner": "P-U-C/city2",
    "uri": "git+https://github.com/P-U-C/city2.git",
    "git_commit_sha1": "<40-lowercase-hex>",
    "path": "docs/COMPANY-OS-SPEC.md",
    "excerpt_locator": {"heading": "1. Executive decision"},
    "retrieval_method": "git_show",
    "content_sha256": "<sha256>",
    "observed_at": "2026-08-02T00:00:00Z",
    "validity_status": "current",
    "revocation_checked_at": "2026-08-02T00:00:00Z"
  }],
  "asserted_by": "human:chad",
  "owner": "human:chad",
  "created_by": "human:chad",
  "created_at": "2026-08-02T00:00:00Z",
  "valid_from": "2026-08-02T00:00:00Z",
  "fact_class": "architecture_decision",
  "revalidation_policy": "on_source_revision",
  "revalidate_at": "2027-08-02T00:00:00Z",
  "confidence": 1.0,
  "sensitivity": "internal",
  "review_state": "accepted",
  "supersedes": [],
  "labels": ["architecture", "portability"]
}
```

Required controls:

- every fact MUST cite one or more evidence references or explicitly state that
  it is a hypothesis;
- provenance distinguishes `asserted_by`, `observed_from` and `derived_from`;
  derived claims include all inputs and the deterministic method/version;
- every evidence reference identifies source type, authoritative owner,
  retrieval method, exact revision/hash, excerpt locator and validity/revocation
  state;
- volatile facts MUST have a fact-class revalidation policy and deadline;
- changing a statement creates a new record that supersedes the prior record;
- secret values are prohibited from memory content;
- a past-due revalidation, source revocation or revision/hash mismatch marks the
  memory stale and excludes it from context until reviewed.

### 10.5 Admission and deduplication

Creating memory is not a default completion step. A candidate SHOULD be created
only when the information is likely to change a future decision or prevent
repeated work.

Before writing a candidate, the producer MUST check:

1. Is the information durable beyond the current task?
2. Is it already represented by an accepted memory?
3. Is it trivially discoverable in an authoritative repository/database?
4. Can a pointer or indexed source replace a duplicated prose copy?
5. Does the proposed scope have a legitimate future reader?
6. Does the source and sensitivity permit retention?

Routine run details stay in task events. Large output stays in an artifact.
Repository structure stays in the repository. Company memory stores only the
decision, preference, feedback, verified fact or reusable outcome that is not
otherwise available in the required form.

Agent-private memory MUST NOT copy accepted department or company memory. It
references the shared record ID and adds only genuinely role-specific learning.
Duplicate candidates SHOULD be coalesced deterministically before model review.

### 10.6 Promotion

```text
observation -> candidate -> source check -> reviewer decision -> accepted
                                |                  |
                                +-> rejected       +-> scoped destination
```

Promotion policy depends on type and scope. Company decisions require Chad or
explicit delegation. Facts require source verification. Procedures require a
successful execution or test. Feedback requires an attributable human source.

The maker and reviewer MUST have distinct agent identities and manifests, no
shared maker write credential or maker-private memory, and separate model
sessions. The reviewer receives immutable source evidence and maker artifacts,
not maker reasoning or a maker-authored summary. For high-risk scopes, policy
SHOULD require a different model/provider and records which independence
dimensions were achieved. No model session may both propose and approve the
same memory.

### 10.7 Retrieval and context assembly

Retrieval MUST follow a versioned policy. Each policy fixes Unicode/query
normalization, access and validity filter order, FTS tokenizer/configuration,
ranking formula, score precision, tie-breaks, excerpt boundaries and truncation
rules. The context builder records the source snapshot and Section 8.7 manifest
so the candidate set and selection can be reproduced after a library, SQLite or
tokenizer upgrade.

Selection order:

1. company constitution and hard policy;
2. exact task envelope and acceptance criteria;
3. agent role and authority;
4. project decisions and active constraints;
5. relevant procedures;
6. evidence-backed facts and prior outcomes;
7. task-local working state.

The builder MUST enforce a configured token/character budget per section. It
MUST exclude rejected, expired, superseded or inaccessible records. It SHOULD
prefer current primary sources over summaries.

Within a selection class, the default stable order is policy priority, relevance
score descending, evidence observation time descending, then canonical memory
ID ascending. Scores are quantized according to the retrieval-policy version.
Any record with past-due revalidation or revoked/unknown source validity is
excluded and surfaced as a stale-memory event rather than silently included.

Raw transcript history and whole memory scopes are excluded by default. A
transcript excerpt MAY be included only when the task explicitly depends on
that interaction and its source is identified.

Platform automation runs deterministic revalidation sweeps on policy deadlines
and source-change signals. It re-fetches exact sources, checks authority,
revision, hash and revocation, emits `memory.stale`/`memory.revalidated` events,
removes stale records from derived indexes and surfaces missed SLOs in the CEO
exception inbox. Critical fact classes MUST detect staleness within 24 hours;
other classes use a versioned policy SLO.

### 10.8 Search

Version 1 SHOULD use SQLite FTS for memory statements, labels and source
metadata, plus exact scope/type/time/access/validity filters. Index builds record
SQLite, tokenizer, schema and retrieval-policy versions. Embeddings MAY be added
as a derived index only after retrieval evaluations demonstrate FTS failures.

Embedding vectors MUST be rebuildable and MUST NOT be required to restore
canonical memory.

### 10.9 Merge and conflict semantics

City2 memory is merged by event identity, not by concatenating prose summaries.

- Exported events use stable UUIDs and payload hashes.
- Reimporting an identical event is idempotent.
- The same event ID with a different payload is corruption and MUST fail closed.
- Concurrent candidates about the same subject remain separate.
- Conflicting accepted facts generate a conflict record and require review.
- No last-write-wins behavior is allowed for accepted company memory.
- Snapshot sequence and event ranges make missing history detectable.
- A deterministic export sorted by event sequence supports diff and review.

Version 1 supports one authoritative writer plus idempotent imports from
controlled, non-concurrent exports. A disconnected export records its writer
and branch identity and cannot directly append canonical aggregate transitions;
it imports candidates that require explicit reconciliation. Per-aggregate hash
chains and `(writer_id, writer_sequence)` remain intact. No total order is
invented across writers. Concurrent multi-writer leases or acceptance are out
of scope until a later protocol explicitly defines ownership and conflict
namespaces. A CRDT is not required.

### 10.10 Privacy/legal deletion

Deletion is a first-class authorized workflow, not an ad hoc database edit. A
versioned deletion order binds legal/privacy authority, subject/scope, affected
memory/artifact IDs, approver and deadline. Execution:

Memory classes subject to deletion MUST store content under a per-record data
encryption key and append only its content hash/encrypted reference to immutable
events. Plaintext MUST NOT be copied into an event payload, trace or diagnostic
log. This keeps append-only audit history compatible with later cryptographic
erasure.

1. appends a non-sensitive tombstone/redaction event;
2. replaces content in canonical projections while preserving only ID, content
   hash, deletion authority/time and proof status;
3. purges FTS/vector indexes, context packs, task-local copies and deletable
   artifacts;
4. tracks every backup/archive generation containing the content;
5. physically deletes where supported or performs cryptographic erasure by
   destroying the independently wrapped content key;
6. verifies propagation and records a content-free completion proof.

Immutable off-host ciphertext, including Walrus blobs, remains unreadable after
key erasure and expires under retention policy; the audit trail MUST NOT retain
the removed plaintext or sensitive locator. Backup retention policy defines the
maximum deletion-completion window and exceptions require Chad's explicit
recorded decision.

## 11. Walrus archival profile

### 11.1 Role

Walrus is an optional `ArchiveBackend` for encrypted City2 snapshots, immutable
evidence bundles and accepted decision history. It MUST NOT be used as:

- the live task database;
- a search or vector store;
- the only copy of memory;
- a destination for plaintext internal or secret data;
- one blob per memory write;
- a reason to give agents wallet or signing authority.

### 11.2 Archive interface

```text
ArchiveBackend
  store(encrypted_bundle, retention_policy) -> ArchiveReceipt
  retrieve(archive_reference) -> encrypted_bundle
  verify(archive_reference, expected_hash) -> VerificationResult
  status(archive_reference) -> availability and expiry
  extend(archive_reference, retention_policy) -> ArchiveReceipt
```

The same interface MUST support a local-filesystem backend. Additional backends
such as S3-compatible storage MAY be added later.

### 11.3 Bundle format

```text
city2-archive-<snapshot-sequence>/
  manifest.json
  core-snapshot.sqlite
  events.jsonl
  git-refs.json
  artifacts/<sha256>
  SHA256SUMS
```

`core-snapshot.sqlite` MUST be produced by SQLite's online backup API or
`VACUUM INTO`, never by copying an active database/WAL pair. `manifest.json`
records source database identity, snapshot method, schema/application versions,
event high-water sequence and terminal hashes, backup barrier ID, Git commits,
artifact Merkle/root hash and inventory, integrity-check result, encryption
profile and creation software versions.

The backup barrier freezes one logical high-water mark: all database references
at or below it MUST resolve to captured Git commits and content-addressed
artifacts, and no later reference may enter the manifest. Backup creation fails
if any referenced artifact/commit is missing or if the exported event range and
snapshot projection disagree.

The outer archive MUST be encrypted before leaving the host. The plaintext
manifest MAY contain internal metadata and is therefore encrypted with the
bundle. A separate minimal receipt may contain only non-sensitive archive ID,
  ciphertext hash, sequence, storage end epoch and verification time.

### 11.4 Encryption and keys

- Client-side authenticated encryption is mandatory. Version 1 uses the
  published age v1 X25519 recipient format; nonce construction, chunking,
  header authentication and payload authentication follow the age
  specification without local modification.
- The outer `city2.archive-envelope/v1` receipt records format/profile version,
  ciphertext SHA-256, archive ID, recipient public-key fingerprints, key
  versions, creation time and inner-manifest SHA-256, then signs the canonical
  receipt with the archive-checkpoint key. Age v1 supplies no
  application-defined external associated data; instead the authenticated inner
  manifest and signed outer receipt repeat the same unpredictable archive ID,
  recipient fingerprints and snapshot checkpoint digest. Restore verifies all
  three plus the ciphertext hash, preventing substitution without a cyclic
  receipt dependency.
- Recovery keys MUST be independent of Walrus and the live City2 host.
- Recipient private keys remain behind `CredentialBroker` or an approved
  offline recovery path; the envelope contains no PfTerminal-specific metadata.
- Key rotation adds a new recipient/version and rewrites a fresh encrypted
  archive before retiring the old key. Custom cryptography and manual nonce
  construction are prohibited.
- Agent model processes never receive archive or wallet private keys.
- Seal MAY be evaluated later for onchain access control, but City2 recovery
  MUST NOT depend solely on Seal key servers.

### 11.5 Walrus lifecycle

Walrus blobs are publicly retrievable bytes, so only ciphertext is uploaded.
`permanent` means non-deletable during the purchased storage period, not
infinite retention. City2 MUST track the end epoch, alert before expiry and
verify extension. Quilts SHOULD batch small incremental event/artifact chunks
when they materially reduce overhead.

Mainnet writes spend WAL and SUI and are external wallet actions. They therefore
require an operator-controlled uploader and explicit budget policy. A4 policy
MAY pre-authorize recurring renewal only within an immutable maximum spend,
blob set, epoch window and execution count. It is revoked on any parameter
change and every renewal is independently audited and verified.

Renewal begins no later than the greater of two storage epochs or 30 days before
expiry. Policy defines bounded retry/backoff and a verification deadline. If
extension is not independently verified by one epoch before expiry, Core writes
a fresh encrypted copy to a second approved backend and raises a CEO exception.
No retention policy may allow the only usable off-host copy to depend on a
pending wallet action.

### 11.6 Pilot acceptance criteria

Before Mainnet use, a synthetic Testnet proof MUST demonstrate:

1. consistent SQLite snapshot and deterministic event export;
2. local encryption without key disclosure;
3. Walrus upload of ciphertext only;
4. retrieval through an independent aggregator;
5. ciphertext hash verification;
6. offline decryption and SQLite integrity check;
7. backup-barrier consistency, signed checkpoint continuity, event-range and
   artifact/Git hash checks;
8. complete recovery onto an empty directory;
9. expiry detection, failed-renewal fallback and post-extension verification;
10. cleanup of all local synthetic secret material.

Mainnet activation requires Chad's explicit approval after cost and recovery
evidence are reviewed.

## 12. Authority and security

### 12.1 Authority classes

| Class | Meaning | Default approval |
|---|---|---|
| `A0` | Read and report | Agent may execute within scope |
| `A1` | Reversible internal write, such as a branch or draft | Policy plus independent review |
| `A2` | Controlled production change with tested rollback | Explicit human approval |
| `A3` | Publish, submit or message an external party | Explicit human approval at action time |
| `A4` | Financial, wallet, credential, destructive or irreversible action | Chad plus hardened operator path; only exact bounded recurring operations may use a pre-approved envelope |

Effective authority is a deny-by-default intersection, not a numeric minimum.
Every requested operation is independently checked against task revision,
manifest, runner capability, tool policy, filesystem/network sandbox,
CredentialBroker decision, authority policy and exact approval. Explicit deny
wins; missing, stale, conflicting or unparsable input denies. The evaluator
emits a machine-readable decision trace containing policy versions and
content-free reasons. No prompt can raise authority.

### 12.2 Separation of duties

- A maker MUST NOT be the sole reviewer of an `A1+` result.
- For `A1+`, the reviewer MUST be technically unable to execute the reviewed
  operation: no maker write credential, approval, task capability, mutable
  workspace or shared model session. A recorded exception makes the check
  explicitly non-independent and cannot satisfy an independent-review gate.
- Review context is assembled from immutable maker artifacts, evidence and
  source records, not maker-private memory or reasoning. The review record names
  distinct identity, manifest, session, credential, workspace and model/provider
  dimensions actually achieved.
- The coordinator routes work but SHOULD NOT hold broad production authority.
- Credential brokerage follows Section 8.10 and is not an agent tool.
- Wallet signing is outside normal model processes.
- Approvals follow Section 8.8 and are consumed only by their exact operation.

### 12.3 Untrusted content

Web pages, messages, documents, repository issues and retrieved memories are
untrusted data. Tool and system instructions MUST remain distinguishable from
retrieved content. Prompt-injection resistance relies on layered capability
limits, not model compliance alone.

Security fixtures MUST include exfiltration, confused-deputy requests, indirect
tool invocation, undeclared tools, retrieval poisoning, approval spoofing,
policy/context displacement and malicious-memory persistence. Passing means
deterministic capability denial, no credential exposure, rejected/quarantined
memory, immutable audit evidence and a bounded incident signal; model refusal
alone is not a control.

### 12.4 Agent process boundary

Each agent SHOULD have a dedicated identity and hardened service boundary. The
model child receives only task-required capabilities. The relay signer may need
an agent Nostr key, but the key MUST be removed before the model/tool child is
started, as in the current coordinator launcher.

## 13. Organizational model

Roles are introduced only when their inputs, outputs, authority and performance
can be measured.

### 13.1 CEO

Chad sets company objectives, allocates budgets, appoints accountable roles,
approves high-authority actions and resolves strategy/conflict escalations.

### 13.2 Chief of Staff / coordinator

The coordinator converts approved objectives into proposed plans, routes tasks,
maintains the decision inbox and assembles briefs. It SHOULD be broad in read
access but narrow in execution authority.

### 13.3 Department-lead template

This is a role template, not a planned hierarchy. A lead is instantiated only
when a domain has a measurable recurring backlog, prioritization decisions and
review-capacity constraint that deterministic routing cannot solve. Candidate
domains include intelligence, products/editorial, markets, PostFiat and
platform; naming a domain does not create an agent.

### 13.4 Workers

Workers execute one defined class of task against narrow sources and tools. An
existing deterministic producer does not become an LLM agent merely for naming
symmetry.

### 13.5 Reviewer/auditor

The reviewer checks evidence, acceptance criteria, policy and memory candidates.
It cannot make the action it reviews. Deterministic validators run before model
judgment.

### 13.6 Platform/reliability

Platform automation owns health, backups, expiry, restore tests and incident
evidence. Known checks remain deterministic; agents assist diagnosis.

## 14. CEO experience

The default CEO surface SHOULD show:

- current objectives and confidence of delivery;
- approvals and decisions required;
- material exceptions, risks and budget variance;
- accepted output since the previous brief;
- failed or blocked work requiring intervention;
- department scorecards;
- links to evidence, not complete agent transcripts.

Recommended cadence:

- event-driven alerts only for material exceptions;
- one concise daily operating brief;
- one weekly strategy and resource-allocation review;
- task-level detail on demand.

Buzz mapping:

- `control`: CEO requests, decisions, approvals and stop/rotate controls;
- `city2`: one thread per objective/project/task evidence loop;
- `ops`: health, backup, deployment and incident evidence.

Buzz is a projection of Core state. Losing a channel must not lose the task,
decision or memory.

## 15. Portability and replacement

### 15.1 Provider replacement

Agent manifests select a model policy, not a hard-coded provider. A runner maps
that policy to an available model. Provider-specific conversation IDs,
reasoning state and memory are caches and may be discarded.

Substitution is evaluated at the contract boundary, not by identical prose.
Golden fixtures allow output variance while requiring schema validity, evidence
coverage, policy compliance, acceptance-criterion satisfaction, tool behavior,
budget/cancellation enforcement and no hidden-state dependency.

### 15.2 Runner replacement

A runner publishes a versioned capability manifest covering structured output,
tool schema fidelity, sandboxing, cancellation, usage accounting, model controls
and unsupported/degraded behavior. Dispatch intersects task requirements with
that manifest and fails closed when a required capability is absent.

A runner must pass a conformance suite:

1. accept a versioned task envelope;
2. consume an explicit context pack;
3. expose only declared tools/capabilities;
4. enforce cancellation and budgets;
5. return a valid result envelope;
6. preserve artifact hashes and evidence;
7. produce no authoritative hidden state.
8. reject envelope mutation and undeclared tools;
9. remain unable to forge Core acceptance or approval;
10. quarantine late work after cancellation/fencing;
11. expose degraded/unsupported capabilities rather than silently dropping
    schemas, controls or accounting.

PfTerminal is the first implementation. ACP MAY connect compatible coding-agent
runtimes. A plain CLI/file adapter remains the recovery baseline.

### 15.3 Interface replacement

Buzz and Telegram adapters translate human input into proposed objectives,
tasks or approvals and render Core projections. Neither stores exclusive state.

### 15.4 Tool replacement

MCP is preferred for portable tools and data resources. A tool's business
contract remains an internal JSON schema so a direct local implementation can
replace an MCP server if necessary.

### 15.5 Agent interoperability

A2A SHOULD NOT be introduced until City2 operates at least two independent
agent runtimes that need discovery and remote task exchange. Internal City2
task envelopes remain canonical even if an A2A adapter is added.

### 15.6 Archive replacement

Archive receipts and encrypted bundles are backend-neutral. Walrus, local and
future backends use the same ciphertext and manifest semantics.

### 15.7 Credential replacement

Credential backends implement Section 8.10. A replacement proves handle
resolution, least-privilege materialization, revocation, rotation, audit and
recovery-metadata export without exposing values or changing agent manifests.
Loss of PfTerminal therefore does not redefine the credential contract.

## 16. Persistence, backup and restore

The initial SQLite store MUST use WAL mode, `PRAGMA synchronous=FULL`, foreign
keys, checked migrations and an application-level single writer. Startup
verifies these settings and refuses writes if they drift. Backups MUST use
SQLite's online backup API or `VACUUM INTO`, never copy an active database file
blindly.

Every backup includes:

- schema and application versions;
- event high-water mark, per-aggregate terminal hashes and writer sequence;
- SQLite integrity result;
- event export and content hashes;
- referenced Git commits;
- artifact inventory;
- backup barrier and artifact root hash;
- signature from a dedicated archive-checkpoint key held behind
  `CredentialBroker`;
- encryption and archive receipt metadata, never keys.

Restore testing MUST create an empty target, restore the database and artifacts,
rebuild projections/search indexes and verify a known objective-task-memory
chain. A backup is not considered valid until this proof passes.

Signed checkpoint manifests are copied off-host and bind the event range,
terminal hashes, database/schema versions, Git set and artifact root. Restore
verifies continuity against a previously trusted checkpoint; an in-database
hash chain alone is not considered tamper proof.

Retention SHOULD include local daily snapshots, longer weekly snapshots and at
least one off-host encrypted backend. Exact retention is an operational policy,
not hard-coded in this specification.

Restore proofs are periodic health data, not creation-time receipts only. Policy
samples retained generations and reruns restores after schema, migration,
decryptor, key or archive-backend upgrades. Each proof records backup ID,
software/key versions, result and timestamp; an overdue or failed sample raises
a CEO exception.

## 17. Observability and evaluations

### 17.1 Telemetry

City2 SHOULD emit OpenTelemetry-compatible traces and metrics for:

- task queue and lease latency;
- run duration and outcome;
- model/provider selection;
- input, output and reasoning token usage where available;
- tool calls, latency and errors;
- context-pack size, pseudonymous pack hash and bounded selection counts;
- retries and idempotent replays;
- approval wait time;
- acceptance and changes-requested rates;
- memory candidate acceptance, rejection and staleness;
- archive age, verification and expiry.

Exported metrics use an allowlist of low-cardinality attributes and MUST NOT
contain raw task/memory/artifact IDs, source paths, host topology or user text.
Configured labels are bounded and unknown labels are dropped. Traces may use
keyed pseudonymous correlation IDs, sampled and retained for a short versioned
period under access control separate from aggregate metrics. Logs have their
own redaction, retention and access policy.

Prompt, completion, context-pack, tool payload and memory content capture is
prohibited by default. A time-bounded diagnostic mode requires Chad's exact
approval, isolated encrypted storage, named viewers, expiry and deletion proof.
The Section 8.7 context artifact—not telemetry—holds auditable selected content.

### 17.2 Evaluation dimensions

Every agent role requires a small versioned evaluation set before activation:

- task completion against objective criteria;
- source and evidence correctness;
- memory retrieval precision and omission;
- cross-scope isolation, poisoned/revoked source exclusion, deterministic
  budget truncation, conflict/supersession handling and rebuild stability;
- stale/superseded memory exclusion;
- policy and authority compliance;
- duplicate-work detection;
- recovery into a fresh session;
- model/provider substitution;
- hostile/degraded runner behavior and capability negotiation;
- prompt-injection containment and approval spoofing;
- cost and latency envelope;
- refusal/escalation under ambiguity.

Model self-grading MAY supplement but MUST NOT replace deterministic checks or
independent review.

### 17.3 Company metrics

CEO scorecards SHOULD emphasize accepted business output rather than agent
activity:

- accepted artifacts per objective;
- lead time and blocked time;
- rework and rollback rate;
- verified freshness of critical memory;
- automation cost per accepted result;
- human approval burden;
- incidents and near misses;
- producer reliability and downstream impact.

Token usage, message count and number of agents are operating metrics, not goals.

## 18. Anti-overengineering admission rules

The following components are prohibited until their threshold is demonstrated:

| Component | Admission threshold |
|---|---|
| Postgres for Core | Measured SQLite contention, required multi-host writes or unavailable SQLite feature |
| Vector database | Versioned retrieval eval shows FTS/filtering misses material relevant memory |
| Temporal/durable framework | Multi-host or multi-day workflows make simple leases/checkpoints unreliable |
| LangGraph/Microsoft Agent Framework | A workflow requires graph checkpointing that Core cannot express simply |
| Letta runtime | A measured role needs autonomous editable memory blocks beyond the City2 protocol |
| A2A | A second independent runtime needs remote agent discovery/task exchange |
| Knowledge graph | Relationship queries cannot be met by relational tables and explicit links |
| Dedicated memory agent | Candidate/revalidation workload exceeds deterministic rules plus reviewer capacity |
| New department channel | Existing channel traffic or permissions create a measurable coordination problem |
| New worker agent | Unique role contract, backlog, evaluation and expected value exist |
| Kubernetes/microservices | Single-host modular monolith fails an explicit availability or scaling requirement |

An admission decision records metric and evaluation version/window, current
baseline, numeric or explicit threshold, target improvement, accountable
approver, expected operating cost, review date, rollback and removal trigger.

## 19. Phased implementation

### M0 — Specification and schemas

Deliver:

- accepted version of this document;
- JSON Schemas for agent, objective, task record/envelope, result, evidence,
  event, artifact, memory, context pack, approval, action/outbox, deletion order
  and archive envelope/receipt;
- authority-policy vocabulary;
- runner capability, CredentialBroker and archive interfaces;
- review fixtures and threat model.

Exit criteria:

- independent reviews resolved;
- no secret or provider-specific state in a canonical schema;
- sample exports validate and round-trip.

### M1 — Core ledger

Deliver:

- SQLite migrations and event/projection model;
- objective/task lifecycle;
- optimistic concurrency, lease fencing, retry, cancellation and action/outbox
  reconciliation;
- CLI status/export/restore;
- local backup proof.

Exit criteria:

- startup proves WAL plus `synchronous=FULL` and refuses unsafe settings;
- process-kill and power-loss-equivalent fixtures at each transaction boundary
  prove no lost accepted transition;
- fault injection covers before/after event append, between event/projection
  operations, lease acquisition, action dispatch, result persistence,
  acknowledgement and backup;
- external-action fixtures cover crash before dispatch, after remote success
  before local confirmation, and after confirmation before task transition for
  providers with and without native idempotency; unknowable outcomes reconcile
  or escalate and are never replayed blindly;
- duplicate event and side-effect tests pass;
- projection gaps/hash mismatches fail closed;
- empty-directory restore reproduces a barrier-consistent known state and
  verifies a signed trusted checkpoint.

### M2 — Memory and context

Deliver:

- memory candidate, review, accept, supersede and stale flows;
- FTS and scoped retrieval;
- deterministic context pack;
- retrieval and fresh-session evals.

Exit criteria:

- coordinator completes the same task after a fresh session using only Core;
- stale and inaccessible memories are excluded;
- critical source changes are detected within the 24-hour revalidation SLO;
- negative fixtures prove cross-scope isolation, poisoned/revoked-source
  exclusion, deterministic budget truncation, supersession/conflict behavior
  and stable retrieval after projection/index rebuild;
- accepted memory has evidence and can be exported/merged.

### M3 — Coordinator integration

Deliver:

- Buzz adapter to create/render tasks;
- PfTerminal runner adapter;
- CEO decision/approval projection;
- current read-only coordinator routed through Core.

Exit criteria:

- Buzz loss/restart does not lose work;
- coordinator remains A0 and owner-only;
- provider substitution passes M0 golden fixtures for schema, evidence,
  criteria, tools, policy, budget, cancellation and hidden-state independence
  within declared cost/latency variance;
- capability negotiation fails closed for an unsupported/degraded runner;
- no conversation persistence is required.

### M4 — Independent review

Deliver:

- reviewer identity and manifest;
- deterministic checks plus independent model review;
- changes-requested and acceptance flows;
- memory promotion review.

Exit criteria:

- maker cannot self-accept A1+ work;
- evidence and policy failures block acceptance;
- reviewer is technically unable to execute the maker operation and the review
  records all achieved independence dimensions.

### M5 — Walrus archive pilot

Deliver:

- generic archive backend;
- local encrypted backend;
- synthetic Walrus Testnet backend proof;
- expiry and restoration checks.

Exit criteria:

- all Section 11.6 criteria pass;
- no plaintext or keys leave the host;
- no Mainnet spend occurred;
- backend can be disabled without affecting Core;
- retained-generation restore sampling and failed-renewal fallback pass.

### M6 — First noncritical producer

Deliver:

- selected producer contract and read-only agent identity;
- scoped memory and evidence output;
- no change to producer schedule/database authority;
- rollback and value measurement.

Exit criteria:

- existing output remains unchanged;
- signed evidence adds measurable value;
- failure/removal does not interrupt downstream systems.

### M7 — Measured expansion

Only after M6 evidence, add role or write authority one unit at a time. Every
expansion requires a role manifest, evaluation, budget, incident boundary and
removal plan.

## 20. Gap from current state

| Capability | Ideal | Current | Gap |
|---|---|---|---|
| CEO interface | Objectives, approvals, scorecards | Buzz/Telegram channels | Typed Core projection |
| Control ledger | Durable objective/task/event state | Manual messages and docs | M1 |
| Agent contract | Versioned manifest and conformance | One environment-configured coordinator | M0/M3 |
| Memory | Scoped, sourced, reviewed and mergeable | Coordinator memory disabled | M2 |
| Context | Deterministic bounded pack | Repo prompt plus channel context | M2 |
| Runner portability | Task/result envelope | Pinned Codex ACP path | M0/M3 |
| Review | Independent maker/checker | CI and operator review | M4 |
| Archive | Encrypted backend-neutral snapshots | Local relay/identity backups | M5 |
| Producer agents | One identity/contract per proven role | Existing deterministic fleet only | M6+ |
| Evaluation | Role, memory, recovery and substitution suites | Repository validation | M2-M4 |
| Company automation | Exception-driven operating loops | Human-directed read-only coordinator | M6+ |

The present system is a strong secure foundation, not yet an automated company.

## 21. Failure and replacement drills

Before calling City2 production-ready as a company OS, operators MUST prove:

1. **Provider loss:** run golden contract fixtures with a different supported
   model/provider and verify declared semantic equivalence, not identical prose.
2. **Runner loss/hostility:** execute through a minimal alternate runner and
   prove it cannot mutate envelopes, forge acceptance, use undeclared tools,
   hide degraded capabilities or continue authoritative work after fencing.
3. **Buzz loss:** create and complete a task through CLI while Buzz is stopped.
4. **Coordinator loss:** replace its process without losing task/memory state.
5. **Database/power loss:** inject process kills and power-loss equivalents at
   every M1 boundary, then restore Core into an empty path and verify the trusted
   checkpoint.
6. **Archive loss:** restore from a second backend when Walrus is unavailable
   and prove renewal failure cannot expire the only off-host copy.
7. **Conflicting memory:** import two sourced candidates without silent overwrite.
8. **Interrupted side effect:** inject failure before dispatch, after remote
   success/before confirmation and after confirmation/before transition against
   one provider with native idempotency and one without; unknown outcomes
   reconcile/escalate and never replay automatically.
9. **Compromised content:** request secret disclosure, policy mutation,
   undeclared/indirect tools, approval bypass and malicious-memory persistence;
   verify capability denial, no exposure, rejected memory, immutable evidence
   and bounded incident signal.
10. **Credential-backend loss:** replace the PfTerminal vault backend using only
    independently encrypted recovery metadata; prove resolve, revoke and rotate
    without changing agent/task contracts or exposing a value.
11. **Deletion:** execute a synthetic privacy deletion across projections,
    indexes, artifacts, backups and encrypted archive keys and verify the
    content-free tombstone/proof.
12. **Cancellation race:** quarantine a result and side effect completed after
    cancellation/fencing.
13. **Agent removal:** disable one agent without blocking unrelated work.

These drills are more important than the number of agents deployed.

## 22. Review questions

Reviewers should answer explicitly:

1. Which invariant is wrong, missing or insufficiently testable?
2. Does any canonical contract accidentally depend on PfTerminal, Buzz, OpenAI,
   Anthropic, Sui or Walrus?
3. Can task state be resumed without replaying a conversation?
4. Can memory be merged without trusting model summaries?
5. Can accepted memory become stale without detection?
6. Is the single-writer SQLite design sufficient through the first producer?
7. Are authority classes and maker/reviewer separation enforceable outside the
   prompt?
8. Is Walrus correctly limited to encrypted archival storage?
9. Which proposed component lacks a measured admission threshold?
10. Which state or secret would be lost if the control host disappeared
    completely?
11. Which failure drill cannot be automated?
12. What is the smallest implementation that would falsify the architecture?

Review findings should be classified as:

- `BLOCKER`: risks durable state, security or replaceability;
- `MAJOR`: material design or operability problem before implementation;
- `MINOR`: clarity, schema or implementation detail;
- `QUESTION`: requires Chad's product or risk decision.

Each finding should cite the section, failure mode and smallest correction.

## 23. External references

These references inform the design; none is adopted wholesale:

- Anthropic, [Building effective agents](https://www.anthropic.com/engineering/building-effective-agents)
- Anthropic, [Long-running Claude for scientific computing](https://www.anthropic.com/research/long-running-Claude)
- Model Context Protocol, [Architecture overview](https://modelcontextprotocol.io/docs/learn/architecture)
- A2A Protocol, [Specification](https://a2a-protocol.org/v0.3.0/specification/)
- Zed, [Agent Client Protocol](https://zed.dev/acp)
- OpenAI, [Agentic AI Foundation and AGENTS.md](https://openai.com/index/agentic-ai-foundation/)
- Microsoft Research, [Magentic-One](https://www.microsoft.com/en-us/research/publication/magentic-one-a-generalist-multi-agent-system-for-solving-complex-tasks/)
- MetaGPT, [software company as a multi-agent system](https://github.com/FoundationAgents/MetaGPT)
- Letta, [agent memory](https://www.letta.com/blog/agent-memory/)
- LangGraph, [persistence](https://docs.langchain.com/oss/python/langgraph/persistence)
- Temporal, [durable execution](https://temporal.io/)
- age, [file encryption format](https://age-encryption.org/v1)
- OpenTelemetry, [GenAI observability](https://opentelemetry.io/blog/2026/genai-observability/)
- Walrus, [system overview](https://docs.wal.app/)
- Walrus, [managing blobs and public-data warning](https://docs.wal.app/docs/walrus-client/managing-blobs)
- Walrus, [Quilt batch storage](https://docs.wal.app/docs/system-overview/quilt)
- Walrus, [production readiness and retention](https://docs.wal.app/docs/production-readiness)

## 24. Acceptance record

This draft becomes normative only when:

1. independent reviews are recorded and resolved;
2. Chad decides all open product/risk questions;
3. the accepted text receives a Git commit and version;
4. `docs/ARCHITECTURE.md`, `docs/MIGRATION.md` and the implementation plan are
   reconciled with it;
5. no deployment or authority change is bundled into the documentation-only
   acceptance commit.
