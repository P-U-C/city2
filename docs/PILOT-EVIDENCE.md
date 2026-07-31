# Prepared pilot evidence

Verified on the control host on 2026-07-31 before repository creation:

- Upstream Compose matched reviewed Buzz commit
  `10d5a26414dc90dc89fd27de74b21e105d4fa622` byte-for-byte.
- Relay image digest existed in the official registry.
- Private override rendered one explicit loopback/Tailscale port binding.
- Pinned CLI, ACP, agent, MCP and admin binaries passed checksums and dynamic
  library checks.
- Selected release-mode Rust suites completed with no failures.
- The binaries passed portability/help/key-generation checks from a temporary
  worker-host directory; no files were left there.
- Disposable relay E2E passed owner-signed private channel/message round-trip,
  outsider rejection, backup integrity, complete state deletion, fresh restore
  and recovered-message verification.
- No provider request, model spend, production identity, production container,
  systemd install or existing producer change occurred.

This is preparation evidence, not proof that production is deployed.
