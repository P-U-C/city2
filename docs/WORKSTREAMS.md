# Workstreams and agents

## Recommended shape

Use one private Buzz **forum channel per workstream** and one top-level thread
per task. Start with one City2 Coordinator process: Buzz ACP keeps a separate
Codex session per channel, so trading context does not bleed into editorial or
product work. This is the smallest reliable company shape today.

`config/workstreams.json` declares the initial map. Inspect it with:

```bash
./city2 workstreams
./city2 workstreams --plan trading
```

The live `control`, `city2`, and `ops` channels already back the `executive`,
`city2-build`, and `city2-ops` workstreams. Reuse them; do not create redundant
channels. The remaining business workstreams stay proposed until Chad creates
their private forum channels with his human owner identity.

## Add a workstream channel

1. In Buzz, create the private forum channel named by the manifest.
2. Keep Chad as sole Owner and add `City2 Coordinator` as Bot.
3. Give PfTerminal the channel UUID. PfTerminal regenerates the coordinator's
   routing file with `create-agent-routing.sh`, preflights it, and restarts the
   service.
4. Start requests with `@City2 Coordinator`. Continue naturally by replying to
   its message in the thread; no repeated mention is required.

## Bring over existing work

Do not dump another agent's transcript or entire memory into Buzz. For every
open item, create one task thread containing:

- **Objective** — the concrete outcome;
- **State** — proposed, active, blocked, review, or done;
- **Source** — Task Node ID, repository issue/PR, or durable artifact link;
- **Evidence** — latest verified facts, not old narrative;
- **Next action** — one owner or agent action;
- **Stop condition** — what makes the task complete or blocked.

The source system remains authoritative. Buzz is the workstream view and signed
conversation record; Git, Task Node, SQLite, and project artifacts keep their
existing authority.

## Add a dedicated specialist agent

Dedicated agents are phase two, not the default. Promote a workstream only when
its throughput, context volume, schedule, or authority needs isolation. The
activation gate requires:

1. a distinct Nostr identity and exact channel allowlist;
2. a dedicated systemd/process boundary and scoped workdir;
3. reviewed PfTerminal authentication and refresh handling;
4. its own working memory plus read-only shared-memory retrieval;
5. owner-only textual mention and verified thread-continuation routing;
6. no heartbeat or autonomous outward action until separately approved;
7. backup, restore, removal, and provider-substitution proof.

`create-agent-env.sh` and `create-agent-routing.sh` generate the identity/runtime
and public channel routing without printing private keys. They prepare an agent;
they do not bypass the activation gate or add relay/channel membership.
