# Upstream pin

- Repository: `https://github.com/block/buzz`
- Source commit: `10d5a26414dc90dc89fd27de74b21e105d4fa622`
- Source date: `2026-07-30T18:20:58-07:00`
- Relay image: `ghcr.io/block/buzz@sha256:a2b59030b29242adb0783a05cbabd63f51518fdfe7b724845a68f77adab7e1f9`
- Observed image tag: `sha-10d5a26`
- Reviewed: `2026-07-31`

`compose.yml` is the upstream `deploy/compose/compose.yml` at that commit.
`compose.private.yml` replaces the relay's all-interface port publication with
one explicit loopback/Tailscale binding.

`scripts/build-buzz-tools.sh` clones this exact commit and builds `buzz`,
`buzz-acp`, `buzz-agent`, `buzz-dev-mcp` and `buzz-admin` with `cargo --locked`.
Generated tools and checksums are local output under `build/bin/`; they are not
committed.
