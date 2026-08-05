# Security model

## Trust boundaries

- Chad's human Buzz/Nostr private key remains on a human-controlled device.
- The relay has its own server key and closed membership list.
- Every agent has a unique Nostr key and Unix/service boundary.
- The first coordinator receives only PfTerminal's ChatGPT `auth.json` through
  a narrow systemd bind mount into an otherwise ephemeral `CODEX_HOME`; it
  cannot traverse the host home or read the vault. The file is writable only
  because all Codex processes must share OAuth refresh-token rotation.
- Any future provider API key must originate in PfTerminal's encrypted vault
  and reach a service only through a reviewed RAM-backed credential path.
- Git, SQLite and existing production services remain independent authorities.

## Prohibited data

Never commit, post to Buzz, print to logs or send through chat:

- private Nostr keys or recovery material;
- provider, GitHub, Telegram or service tokens;
- wallet/seed material;
- `.env` contents or database passwords;
- internal credential-routing labels that are not already public contracts.

Public identities should be shown as short fingerprints except where an exact
value is required through a local file or command substitution.

## Relay exposure

- Bind the relay to exactly one loopback/Tailscale address.
- Require authentication token support and relay membership.
- Do not add Caddy, a public hostname or public TLS ingress in Phase 1.
- Treat relay administrators and host root as able to access stored content;
  do not put secrets in messages even on a private relay.

## Agent authority

The first coordinator is:

- owner-only;
- mention-driven;
- one process;
- heartbeat disabled;
- no autonomous publishing or external action;
- scoped to `/srv/city2`, a read-only bind of the reviewed repository, while
  the rest of the user's home is inaccessible;
- unable to access the PfTerminal vault after startup.

The `agent-full-access` ACP label is internal to the service namespace; it does
not grant host access. It prevents Codex from attempting a second Linux sandbox
inside an LXC that cannot support one. systemd still enforces the read-only repo
bind, hidden home, strict system filesystem, empty capability set, and
`MemoryDenyWriteExecute`. The direct-tool model pin avoids disabling that last
control for GPT-5.6's required V8 code-mode runtime.

The relay signer retains the agent's Nostr key, but the Codex ACP launcher
removes it from the model-runtime environment and ordinary child processes.
`buzz-acp` passes it separately only to the configured Buzz MCP broker, which
performs signed relay operations on the coordinator's behalf. The ChatGPT
runtime credential remains available only through the single-file bind inside
the service-private `CODEX_HOME` required by Codex
itself. A credential-file write therefore affects the shared PfTerminal login;
the service exposes no surrounding host configuration or vault paths.

Channel membership is not a filesystem sandbox. Systemd hardening and Unix
identity boundaries remain required.

## Supply chain

- Relay image is pinned by immutable digest.
- Compose is copied from a reviewed upstream commit.
- Agent tools are built with `cargo --locked` from that commit.
- The Codex ACP adapter and bundled Codex runtime are pinned by npm lockfile.
- Generated binaries and checksums are local build output and are not committed.
- Version bumps require source review, rebuilt tools and the disposable E2E.

## Approval model

Buzz workflow approval suspension is not treated as a complete security gate.
Deployment, publication, financial actions, third-party messages and production
schedule changes require explicit owner approval plus a separately enabled
operator path.
