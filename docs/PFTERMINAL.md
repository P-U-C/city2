# PfTerminal harness

PfTerminal is City2's primary work harness. Buzz is the team workspace; it does
not replace the harness.

## Entry points

### Telegram/TUI

Ask for City2 work normally. The host-level memory points PfTerminal to this
repository, while this repo's `AGENTS.md` defines the project contract.

### Headless

```bash
./city2 agent "Inspect the current migration phase and implement the next safe item"
```

This resolves to:

```bash
pfterminal exec -C <repo-root> "<request>"
```

The normal PfTerminal approval policy remains active. The wrapper never uses a
bypass flag.

### Review

```bash
./city2 review
./city2 review "Focus on secret handling and rollback"
```

## Project contract

Every PfTerminal session rooted here loads `AGENTS.md`. That contract bans
OpenClaw dependencies, secret publication and implicit outward actions; it also
requires an inspect/change/check/review loop.

## Credentials

Provider credentials originate in PfTerminal's encrypted vault. Before an
approved agent activation, a dedicated script transfers only the selected key
into a root-only RAM-backed systemd credential without printing it. The running
agent cannot access the PfTerminal vault or execute `pfterminal`.

The current relay scaffold supports the whitelisted OpenRouter vault label for
its first measured ACP proof. Supporting another provider requires a reviewed
launcher/config/unit change, not a pasted key.

## Responsibility split

| Surface | Responsibility |
|---|---|
| PfTerminal | Plan, code, test, review, deploy, rollback, Task Node and vault |
| Buzz | Identity, channels, signed requests, handoffs and evidence threads |
| GitHub | Source, review history and releases |
| Host services | Relay and tightly scoped agent processes |
| Existing producers | Authoritative collection and corpus state |

The first Buzz ACP coordinator uses Buzz's pinned ACP runtime. PfTerminal still
controls its configuration and lifecycle. A native PfTerminal ACP adapter is
not claimed or required for Phase 1; it can be added later only if it provides
measurable value over the reviewed adapter.
