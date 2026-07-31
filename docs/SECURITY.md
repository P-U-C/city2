# Security model

## Trust boundaries

- Chad's human Buzz/Nostr private key remains on a human-controlled device.
- The relay has its own server key and closed membership list.
- Every agent has a unique Nostr key and Unix/service boundary.
- Provider credentials originate in PfTerminal's encrypted vault and reach a
  running agent only through a root-only RAM-backed systemd credential.
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
- scoped to a reviewed working directory mounted read-only by default;
- unable to access the PfTerminal vault after startup.

Channel membership is not a filesystem sandbox. Systemd hardening and Unix
identity boundaries remain required.

## Supply chain

- Relay image is pinned by immutable digest.
- Compose is copied from a reviewed upstream commit.
- Agent tools are built with `cargo --locked` from that commit.
- Generated binaries and checksums are local build output and are not committed.
- Version bumps require source review, rebuilt tools and the disposable E2E.

## Approval model

Buzz workflow approval suspension is not treated as a complete security gate.
Deployment, publication, financial actions, third-party messages and production
schedule changes require explicit owner approval plus a separately enabled
operator path.
