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

## Coordinator authentication

The first coordinator uses the host's existing PfTerminal ChatGPT login through
the pinned `codex-acp` adapter. systemd bind-mounts only PfTerminal's
`auth.json` into an otherwise ephemeral, service-private `CODEX_HOME`. That one
file is writable because OAuth refresh-token rotation must be shared rather
than copied into an independent token chain. The process cannot traverse the
host home or read PfTerminal's vault, configuration, session history or memory
store. An explicit re-login replaces `auth.json`, so restart the coordinator
after re-login to attach the new file.

This path uses Chad's existing ChatGPT plan instead of a separately billed API
key. If a later agent needs a provider API key, it must originate in
PfTerminal's encrypted vault and move through a separately reviewed RAM-backed
credential path; never paste one into Buzz or an EnvironmentFile.

## Responsibility split

| Surface | Responsibility |
|---|---|
| PfTerminal | Plan, code, test, review, deploy, rollback, Task Node and vault |
| Buzz | Identity, channels, signed requests, handoffs and evidence threads |
| GitHub | Source, review history and releases |
| Host services | Relay and tightly scoped agent processes |
| Existing producers | Authoritative collection and corpus state |

The first Buzz ACP coordinator uses Buzz's pinned ACP runtime plus the pinned
`@agentclientprotocol/codex-acp` adapter. PfTerminal controls its configuration,
authentication source and lifecycle; the service remains subordinate to the
read-only systemd boundary.
