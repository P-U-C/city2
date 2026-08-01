# Architecture

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

1. Interpret an owner request from Telegram/TUI/headless execution.
2. Load root `AGENTS.md` and inspect repository/runtime truth.
3. Make scoped changes.
4. Run validation and review.
5. Execute approved deployment/rollback commands.
6. Return durable evidence to the owner and, when enabled, the Buzz thread.

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

## Safety gates

1. **Repository:** validation and review pass.
2. **Relay:** owner public identity, private binding and backup path verified.
3. **Coordinator:** one owner-only, mention-driven, no-heartbeat process.
4. **Scoped write:** filesystem boundary and rollback tested.
5. **Producer:** one worker identity and one existing producer at a time.
6. **Outward action:** separate operator identity and explicit owner approval.
