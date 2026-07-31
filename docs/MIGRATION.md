# Migration from legacy City

## Why a new repository

The old City control surface is not one coherent deployable repository. It is
split across an uncommitted `clawd` workspace, a heavily mutated OpenClaw
workspace, old OpenClaw-specific templates/harnesses and live producer repos.
An in-place overhaul would preserve unclear ownership and contaminated runtime
assumptions.

City2 therefore starts in a new private `P-U-C/city2` repository.

The old workspaces are not deleted or rewritten. They remain read-only evidence
until each useful contract is either adopted here or deliberately retired.

## What survives

- `clawd` remains the control/consumer host.
- `worker-1` remains the producer host.
- Existing producer Unix-user isolation.
- Existing SQLite, cron and Git aggregate handoffs.
- Existing downstream trading, editorial and public release gates.
- Existing PfTerminal shared memory and host runbook.

## What is retired from the City control path

- OpenClaw gateway/workspace as the operator harness.
- OpenClaw heartbeat as project scheduling or authority.
- Mutable prompt files as the only institutional memory.
- Shared broad credentials between unrelated agents.
- Autonomous outward actions inferred from a chat message.

No old service is stopped merely because this document marks it legacy. Runtime
retirement requires separate verification and approval.

## Phases

### Phase 0 — repository foundation (this release)

- New repo and project contract.
- PfTerminal command surface.
- Pinned private Buzz deployment package.
- Secret-safe bootstrap, backup and restore tooling.
- Offline validation and disposable relay E2E.

### Phase 1 — private relay

- Create/back up the owner identity on Chad's device.
- Generate relay secrets locally without printing them.
- Bind only to the control host's Tailscale address.
- Start the relay and perform the first production backup/verification.
- Create `control`, `city2` and `ops`.

### Phase 2 — read-only coordinator

- Generate one dedicated agent identity.
- Register it only in the initial channels.
- Run one owner-only, no-heartbeat coordinator.
- Complete a read-only request, restart/replay and cost measurement.
- Stop and restore the relay before widening authority.

### Phase 3 — scoped writes

- Add an explicit project filesystem boundary.
- Complete one reversible change through PfTerminal.
- Verify Git diff, review, rollback and agent identity rotation.

### Phase 4 — one producer

- Select one noncritical producer.
- Keep its Unix identity, schedule and database intact.
- Add a distinct Buzz identity and narrow channel membership.
- Post signed evidence without changing the producer's authoritative output.

### Phase 5 — measured expansion

- Add roles only when the prior role has measurable throughput or reliability
  value.
- Migrate producer contracts one at a time.
- Keep publishing, financial and third-party actions separately gated.

## Rollback

At every phase, rollback means stopping the new City2 component and returning
to the unchanged producer/downstream contracts. No phase may require restoring
the OpenClaw workspace to keep production data moving.
