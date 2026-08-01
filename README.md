# City2

City2 is P-U-C's clean replacement for the OpenClaw-era City workspace.

It keeps the useful City producer/data plane, adds a private
[Buzz](https://github.com/block/buzz) coordination layer, and makes
**PfTerminal the operating harness** for planning, implementation, review,
deployment and incident work.

## Architecture

```text
Chad / Telegram / Buzz Desktop
              |
         PfTerminal harness
              |
       City2 repository (clawd)
       |                    |
  Buzz coordination     existing data plane
  relay + agents        worker producers
       |                SQLite + cron + Git
       +-------- evidence --------+
```

Buzz does not replace Git, SQLite, scheduled producers or existing publishing
gates. OpenClaw is not a dependency and its mutable workspace is not imported.

## Repository

```text
AGENTS.md                 PfTerminal's project operating contract
city2                     Single operator command surface
config/                   Public, non-secret activation contract
                          and declared producer fleet
docs/                     Architecture, migration, security and operations
infra/buzz/               Pinned private Buzz relay and agent integration
scripts/                  Validation and reproducible tool builds
tests/                    Offline contract tests
```

## Start here

```bash
./city2 doctor             # inspect; changes nothing
./city2 validate           # static and contract checks
./city2 fleet --offline    # validate the producer inventory
./city2 fleet              # one-SSH, read-only live fleet check
./city2 agent "<request>"  # run PfTerminal rooted in this repository
./city2 review             # PfTerminal review of uncommitted changes
./city2 buzz preflight     # relay checks; requires infra/buzz/.env
```

The relay and coordinator are separate activation gates.
See [Architecture](docs/ARCHITECTURE.md), [Migration](docs/MIGRATION.md) and
[Operations](docs/OPERATIONS.md). The proposed long-term company operating
model is the review draft in
[Company OS design specification](docs/COMPANY-OS-SPEC.md); it is not an
activation authorization.

## Current state

- Repository scaffold: ready.
- Disposable relay round-trip and destructive restore proof: passed.
- Production relay: healthy on its Tailscale-only address.
- Owner identity: connected; private key remains off-host.
- Workspace: private `control`, `city2`, and `ops` channels created.
- Coordinator: active, owner-only, mention-driven, heartbeat-off, and bound to
  a read-only repository mount; first owner-authored model proof remains gated.
- Company OS: target architecture and memory/Walrus design drafted for
  independent review; no implementation is implied by the draft.
- Existing City producers: unchanged.
- OpenClaw: excluded from the new control path.
