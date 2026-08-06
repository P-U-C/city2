# Upstream pin

- Repository: `https://github.com/block/buzz`
- Source commit: `10d5a26414dc90dc89fd27de74b21e105d4fa622`
- Source date: `2026-07-30T18:20:58-07:00`
- Relay image: `ghcr.io/block/buzz@sha256:a2b59030b29242adb0783a05cbabd63f51518fdfe7b724845a68f77adab7e1f9`
- Observed image tag: `sha-10d5a26`
- Pairing proxy image: `nginx@sha256:4a73073bd557c65b759505da037898b61f1be6cbcc3c2c3aeac22d2a470c1752`
- Pairing proxy version/source: `1.31.3-alpine`, official Nginx image revision `ccdab6c99ae2e2fc53a144dc68d6b8f44163adf2`
- Reviewed: `2026-07-31`
- Codex ACP adapter: `@agentclientprotocol/codex-acp@1.1.7`
- Adapter lockfile SHA-256: `33207b0e54905f6b3c7889ba1fc8b9b63eaa12b8cfd936e4991eec3a8365e224`

`compose.yml` is the upstream `deploy/compose/compose.yml` at that commit.
`compose.private.yml` replaces the relay's all-interface port publication with
one explicit Tailscale binding and publishes the trusted-TLS backend only on
loopback.

The pairing extension runs the Buzz image's `buzz-pair-relay` binary only on
the internal Compose network. The separately pinned official Nginx image is a
non-root, read-only path and timeout boundary; only its private host binding is
advertised to clients. Updating either image digest requires source review and
the disposable E2E.

The same pinned Nginx image provides a second loopback-only ingress for the main
relay plus exact `/pair`. Host-managed Tailscale Serve terminates a publicly
trusted certificate on a non-public tailnet port and proxies only to that
loopback ingress. City2 never invokes Funnel, never resets unrelated Serve
routes and refuses a conflicting route instead of replacing it.
Existing deployments migrate the durable community host in one locked database
transaction before starting under the new authority; the disposable E2E proves
that signed content survives and no parallel tenant is created.

`scripts/build-buzz-tools.sh` clones this exact commit and builds `buzz`,
`buzz-acp`, `buzz-agent`, `buzz-dev-mcp` and `buzz-admin` with `cargo --locked`.
Generated tools and checksums are local output under `build/bin/`; they are not
committed.

The build verifies and applies
`patches/0001-auto-publish-final-answer.patch` against that exact commit. The
opt-in patch captures only ACP `final_answer` messages and lets `buzz-acp`
publish them with its signer; the model runtime never receives the Nostr key.

The coordinator adapter dependency graph is locked in
`infra/buzz/agents/codex-acp/package-lock.json`. `scripts/build-agent-adapter.sh`
installs that graph under ignored `build/codex-acp/`; installation copies it to
the root-owned `/opt/city2` runtime.
