# City2

City2 is P-U-C's clean replacement for the OpenClaw-era City workspace.

This source repository is public. Production relay state, channels, identities,
credentials, backups and host-specific runtime configuration remain private and
are never committed.

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
city2-core                Repository-local Core CLI
config/                   Public, non-secret activation contract
                          and declared producer fleet
contracts/v1/             Portable runner, credential, archive and authority semantics
docs/                     Architecture, migration, security and operations
fixtures/contracts/v1/    Valid and adversarial contract examples
infra/buzz/               Pinned private Buzz relay and agent integration
schemas/v1/               Canonical Company OS JSON Schemas
src/city2core/            Single-writer SQLite Core and signed local recovery
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
./city2 core status --db <path> # verify and report a local Core database
./city2 buzz preflight     # relay checks; requires infra/buzz/.env
```

The relay and coordinator are separate activation gates.
See [Architecture](docs/ARCHITECTURE.md), [Migration](docs/MIGRATION.md) and
[Operations](docs/OPERATIONS.md). The accepted long-term operating model and
its explicit milestone gates are in the
[Company OS design specification](docs/COMPANY-OS-SPEC.md). Its M0 contract
implementation includes the [portable interfaces](contracts/v1/README.md),
[canonical schemas](schemas/v1/) and [threat model](docs/THREAT-MODEL.md).
M1 adds the [Core ledger and local recovery implementation](docs/CORE.md); M2
adds [evidence-backed memory and deterministic context](docs/MEMORY.md); M3
adds the undeployed [Buzz/PfTerminal adapter boundary](docs/ADAPTERS.md).
M4 adds undeployed [independent review enforcement](docs/REVIEW.md).
M5 adds the undeployed [encrypted archive pilot boundary](docs/ARCHIVE.md).
M6 adds the accepted, removed-after-proof
[read-only producer observer boundary](docs/PRODUCER.md).
M7 starts with a disabled, fail-closed
[measured-expansion admission gate](docs/EXPANSION.md); its first decision is
`defer`, not another agent or authority grant.
Design acceptance and implementation are not deployment authorization.

## Current state

- Repository scaffold: ready.
- Repository visibility: public; full reachable history passed the repository
  credential/private-address scan before the 2026-08-01 visibility change.
- Disposable relay round-trip and destructive restore proof: passed.
- Production relay: healthy on its private Tailscale bind.
- Owner identity: connected; private key remains off-host.
- Workspace: private `control`, `city2`, and `ops` channels created.
- Coordinator: active, owner-only, mention/thread-driven, heartbeat-off, and
  bound to a read-only repository mount. Signed owner-to-model-to-signer replies
  and exact textual mentions from Buzz Desktop for macOS have passed live proof.
  Desktop through `0.5.5` filters externally hosted agents from `@` autocomplete;
  upstream `014562c0` fixes the issue after that release. Manual exact mention
  remains safe until the next Desktop release. The Desktop **Agents** page lists
  Mac-managed runtimes rather than relay agents, so the external coordinator is
  correctly absent. Thread continuation is implemented and awaiting one fresh
  macOS Desktop replay check.
- Company OS: specification version 0.2.0 is accepted after independent review;
  M0 contracts, M1 ledger, M2 memory/context and the version 0.5.0 M3 offline
  adapters, M4 independent review, M5 encrypted local/Testnet archive boundary
  and the M6 producer-observer layer are implemented. `ai-infra` passed one
  signed shadow observation, narrow Buzz attestation and complete removal proof;
  its observer, keys and identity are now absent. Core is not deployed, selected
  manifests remain disabled, the live coordinator remains outside Core and no
  off-host archive exists. M7 admission conformance is implemented, but the
  first A0 Core/coordinator candidate remains disabled and deferred pending the
  M2/M3 live criteria and three recovery drills. The coordinator is now Bot in
  all three bootstrap channels and the human identity is their sole Owner.
- Existing City producers: unchanged.
- OpenClaw: excluded from the new control path.
