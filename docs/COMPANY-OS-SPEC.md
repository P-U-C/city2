# City2 Company OS design specification

| Field | Value |
|---|---|
| Status | Draft for independent agent review |
| Version | 0.1.0 |
| Date | 2026-08-01 |
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

As of 2026-08-01, the following is live:

- private repository `P-U-C/city2` at `/home/ubuntu/city2`;
- PfTerminal as the project implementation and operational harness;
- a Tailscale-only Buzz relay with private `control`, `city2` and `ops`
  channels;
- one owner-only, mention-driven, heartbeat-off coordinator;
- a read-only `/srv/city2` repository mount for that coordinator;
- no coordinator access to the host home, PfTerminal vault, session history or
  shared host memory;
- the existing `worker-1` fleet, cron, SQLite and Git handoffs unchanged;
- a declared fleet of fourteen sector producers plus `swell-checker`, with the
  peptide corpus parked as legacy;
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

- one `city2d` user service on `clawd`;
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
| Secrets | PfTerminal vault or reviewed host credential file | Ephemeral systemd credentials only |
| Archive copies | Local encrypted backups; optional Walrus backend | Availability manifests |

## 8. Stable contracts

All contracts MUST have a semantic schema version. IDs MUST be globally unique,
opaque and stable across exports. Timestamps MUST be UTC RFC 3339. Hashes MUST
name their algorithm.

### 8.1 Agent manifest

An agent is a stable organizational identity and contract, not a model session.

```yaml
schema_version: city2.agent/v1
agent_id: agt_<uuid>
name: research-reviewer
role: reviewer
department: intelligence
reports_to: agt_<uuid>
runner: pfterminal
model_policy: quality-default
authority_class: A0
allowed_task_types: [research_review]
tools: [corpus_read, web_read]
filesystem_scopes: [/srv/city2:ro]
network_policy: research-readonly
credential_handles: []
memory_read_scopes: [company, department:intelligence, agent:self]
memory_write_scopes: [agent:self, candidate:department:intelligence]
context_profile: reviewer-default
time_budget_seconds: 1800
cost_budget: null
concurrency: 1
review_policy: independent
enabled: false
```

The manifest MUST NOT contain secret values. Credential handles are opaque
policy references resolved outside the model environment.

### 8.2 Objective

An objective records CEO intent, success measures, constraints, budget, owner,
review date and status. It MUST NOT be represented only by a chat message.

Required fields:

- `objective_id`, `schema_version`, `title`, `intent`;
- `created_by`, `accountable_owner`, `created_at`, `review_at`;
- measurable outcomes and stop conditions;
- authority ceiling and aggregate budget;
- status and supersession link.

### 8.3 Task envelope

The task envelope is the portable input to any runner.

```json
{
  "schema_version": "city2.task/v1",
  "task_id": "tsk_<uuid>",
  "objective_id": "obj_<uuid>",
  "task_type": "repository_analysis",
  "title": "Assess the first producer integration",
  "intent": "Produce a no-change recommendation with evidence",
  "created_by": "human:chad",
  "assigned_role": "city2-coordinator",
  "authority_class": "A0",
  "inputs": [{"uri": "git://P-U-C/city2", "sha256": "..."}],
  "constraints": ["read_only", "no_external_action"],
  "acceptance_criteria": ["cites current contracts", "names rollback"],
  "memory_scopes": ["company", "project:city2"],
  "time_budget_seconds": 1800,
  "max_attempts": 2,
  "idempotency_key": "...",
  "status": "ready"
}
```

The task MUST contain intent and acceptance criteria, not merely a prompt. A
runner MAY render the envelope into provider-specific instructions, but that
rendered prompt is not authoritative.

### 8.4 Result envelope

Every run returns a provider-neutral result:

```json
{
  "schema_version": "city2.result/v1",
  "task_id": "tsk_<uuid>",
  "run_id": "run_<uuid>",
  "status": "completed",
  "outcome": "...",
  "artifacts": [],
  "evidence": [],
  "checks": [],
  "memory_candidates": [],
  "approvals_requested": [],
  "usage": {"wall_seconds": 0, "input_tokens": 0, "output_tokens": 0},
  "errors": []
}
```

Completion MUST require acceptance-criteria evidence. Model prose alone is not
completion evidence.

### 8.5 Event envelope

Task, memory, approval and agent state changes MUST emit immutable events with:

- event ID and schema version;
- aggregate type and ID;
- event type and sequence;
- actor identity;
- occurred and recorded timestamps;
- idempotency key;
- prior-event hash and payload hash;
- structured payload;
- sensitivity classification.

Current state is a projection of events. Projection tables MAY be rebuilt from
events plus a verified snapshot.

### 8.6 Artifact reference

An artifact reference includes media type, byte length, SHA-256, storage URI,
producer run, creation time, sensitivity and optional Git commit. Mutable paths
MUST be paired with immutable hashes.

## 9. Task and workflow model

### 9.1 Task states

```text
proposed -> awaiting_approval -> ready -> leased -> running -> review
    |              |              |        |          |         |
    +-> rejected   +-> rejected   |        |          |         +-> accepted
                                  |        |          +-> failed
                                  |        +-> expired
                                  +-> cancelled

review -> changes_requested -> ready
accepted -> rolled_back (when an accepted side effect is reversed)
```

Transitions MUST be validated by deterministic code. Agents MAY recommend a
transition but MUST NOT directly mutate policy-protected states.

### 9.2 Leasing and recovery

- Workers lease tasks for a bounded period.
- A lease has an owner, expiry and monotonic attempt number.
- Expired work returns to `ready` only if its operation is replay-safe.
- External actions MUST record their idempotency key before execution.
- Completed steps MUST NOT be repeated after process recovery.
- A retry creates a new run ID but retains the task ID.
- After the attempt ceiling, the task becomes `failed` or requires human review.

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
2. resolve the immutable agent manifest version;
3. evaluate policy and authority;
4. assemble a bounded context pack;
5. start a fresh runner/model session;
6. execute within turn, time, tool and cost limits;
7. store artifacts and evidence;
8. return a result envelope;
9. release the lease and transition the task;
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
  "memory_id": "mem_<uuid>",
  "scope": "project:city2",
  "type": "decision",
  "statement": "Model sessions are disposable; City2 owns durable state.",
  "source": {
    "uri": "git://P-U-C/city2/docs/COMPANY-OS-SPEC.md",
    "sha256": "...",
    "observed_at": "2026-08-01T00:00:00Z"
  },
  "owner": "human:chad",
  "created_by": "human:chad",
  "created_at": "2026-08-01T00:00:00Z",
  "valid_from": "2026-08-01T00:00:00Z",
  "revalidate_at": null,
  "confidence": 1.0,
  "sensitivity": "internal",
  "review_state": "accepted",
  "supersedes": [],
  "labels": ["architecture", "portability"]
}
```

Required controls:

- every fact MUST cite a source or explicitly state that it is a hypothesis;
- volatile facts SHOULD have `revalidate_at`;
- changing a statement creates a new record that supersedes the prior record;
- deleting accepted history is prohibited outside a separately audited privacy
  or legal procedure;
- secret values are prohibited from memory content;
- a source hash mismatch marks the memory stale until reviewed.

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

No model may both propose and independently approve the same memory.

### 10.7 Retrieval and context assembly

Retrieval MUST be deterministic enough to audit. The context builder records
which memories and source excerpts were selected and why.

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

Raw transcript history and whole memory scopes are excluded by default. A
transcript excerpt MAY be
included only when the task explicitly depends on that interaction and its
source is identified.

### 10.8 Search

Version 1 SHOULD use SQLite FTS for memory statements, labels and source
metadata, plus exact scope/type/time filters. Embeddings MAY be added as a
derived index only after retrieval evaluations demonstrate FTS failures.

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

A CRDT is not required for the initial single-writer deployment. The storage
interface MUST leave room for a future multi-writer implementation.

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
  core.sqlite
  events.jsonl
  git-refs.json
  artifacts/<sha256>
  SHA256SUMS
```

The outer archive MUST be encrypted before leaving the host. The plaintext
manifest MAY contain internal metadata and is therefore encrypted with the
bundle. A separate minimal receipt may contain only non-sensitive archive ID,
ciphertext hash, sequence, storage end epoch and verification time.

### 11.4 Encryption and keys

- Client-side authenticated encryption is mandatory.
- Recovery keys MUST be independent of Walrus and the live City2 host.
- Keys remain in PfTerminal's vault or an approved offline recovery path.
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
require an operator-controlled uploader and explicit budget policy.

### 11.6 Pilot acceptance criteria

Before Mainnet use, a synthetic Testnet proof MUST demonstrate:

1. consistent SQLite snapshot and deterministic event export;
2. local encryption without key disclosure;
3. Walrus upload of ciphertext only;
4. retrieval through an independent aggregator;
5. ciphertext hash verification;
6. offline decryption and SQLite integrity check;
7. event-range continuity and artifact hash checks;
8. complete recovery onto an empty directory;
9. expiry detection and renewal alert behavior;
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
| `A4` | Financial, wallet, credential, destructive or irreversible action | Chad plus hardened operator path |

An agent's effective authority is the minimum of task, manifest, tool,
filesystem, network, credential and policy ceilings. No prompt can raise it.

### 12.2 Separation of duties

- A maker MUST NOT be the sole reviewer of an `A1+` result.
- A reviewer SHOULD lack the maker's write credential.
- The coordinator routes work but SHOULD NOT hold broad production authority.
- Credential brokerage is deterministic infrastructure, not an agent tool.
- Wallet signing is outside normal model processes.
- Approval records identify the exact action, artifact hash and expiry.

### 12.3 Untrusted content

Web pages, messages, documents, repository issues and retrieved memories are
untrusted data. Tool and system instructions MUST remain distinguishable from
retrieved content. Prompt-injection resistance relies on layered capability
limits, not model compliance alone.

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

### 13.3 Department leads

Leads own a measurable domain backlog, review worker output and request budget
or authority. Initial candidate departments are intelligence, products/editorial,
markets, PostFiat and platform.

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

### 15.2 Runner replacement

A runner must pass a conformance suite:

1. accept a versioned task envelope;
2. consume an explicit context pack;
3. expose only declared tools/capabilities;
4. enforce cancellation and budgets;
5. return a valid result envelope;
6. preserve artifact hashes and evidence;
7. produce no authoritative hidden state.

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

## 16. Persistence, backup and restore

The initial SQLite store MUST use WAL mode, foreign keys, checked migrations and
an application-level single writer. Backups MUST use SQLite's consistent backup
mechanism rather than copying an active database file blindly.

Every backup includes:

- schema and application versions;
- latest event sequence and hash;
- SQLite integrity result;
- event export and content hashes;
- referenced Git commits;
- artifact inventory;
- encryption and archive receipt metadata, never keys.

Restore testing MUST create an empty target, restore the database and artifacts,
rebuild projections/search indexes and verify a known objective-task-memory
chain. A backup is not considered valid until this proof passes.

Retention SHOULD include local daily snapshots, longer weekly snapshots and at
least one off-host encrypted backend. Exact retention is an operational policy,
not hard-coded in this specification.

## 17. Observability and evaluations

### 17.1 Telemetry

City2 SHOULD emit OpenTelemetry-compatible traces and metrics for:

- task queue and lease latency;
- run duration and outcome;
- model/provider selection;
- input, output and reasoning token usage where available;
- tool calls, latency and errors;
- context-pack size and selected memory IDs;
- retries and idempotent replays;
- approval wait time;
- acceptance and changes-requested rates;
- memory candidate acceptance, rejection and staleness;
- archive age, verification and expiry.

Prompt, completion, tool payload and memory content capture MUST be disabled by
default. IDs and aggregate metrics are sufficient for routine operations.

### 17.2 Evaluation dimensions

Every agent role requires a small versioned evaluation set before activation:

- task completion against objective criteria;
- source and evidence correctness;
- memory retrieval precision and omission;
- stale/superseded memory exclusion;
- policy and authority compliance;
- duplicate-work detection;
- recovery into a fresh session;
- model/provider substitution;
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

An admission decision records evidence, owner, expected benefit, rollback and a
removal test.

## 19. Phased implementation

### M0 — Specification and schemas

Deliver:

- accepted version of this document;
- JSON Schemas for agent, objective, task, result, event, artifact and memory;
- authority-policy vocabulary;
- runner and archive interfaces;
- review fixtures and threat model.

Exit criteria:

- independent reviews resolved;
- no secret or provider-specific state in a canonical schema;
- sample exports validate and round-trip.

### M1 — Core ledger

Deliver:

- SQLite migrations and event/projection model;
- objective/task lifecycle;
- lease, retry, cancellation and idempotency;
- CLI status/export/restore;
- local backup proof.

Exit criteria:

- crash/restart loses no accepted transition;
- duplicate event and side-effect tests pass;
- empty-directory restore reproduces known state.

### M2 — Memory and context

Deliver:

- memory candidate, review, accept, supersede and stale flows;
- FTS and scoped retrieval;
- deterministic context pack;
- retrieval and fresh-session evals.

Exit criteria:

- coordinator completes the same task after a fresh session using only Core;
- stale and inaccessible memories are excluded;
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
- provider substitution conformance test passes;
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
- reviewer has no maker write credential.

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
- backend can be disabled without affecting Core.

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

1. **Provider loss:** run a fixture with a different supported model/provider.
2. **Runner loss:** execute a fixture through a minimal alternate runner.
3. **Buzz loss:** create and complete a task through CLI while Buzz is stopped.
4. **Coordinator loss:** replace its process without losing task/memory state.
5. **Database loss:** restore Core from an encrypted backup into an empty path.
6. **Archive loss:** restore from a second backend when Walrus is unavailable.
7. **Conflicting memory:** import two sourced candidates without silent overwrite.
8. **Interrupted side effect:** resume without repeating the completed action.
9. **Compromised content:** demonstrate that retrieved prompt injection cannot
   exceed the task's effective authority.
10. **Agent removal:** disable one agent without blocking unrelated work.

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
10. Which state or secret would be lost if `clawd` disappeared completely?
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
