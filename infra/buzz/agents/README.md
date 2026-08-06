# Coordinator integration

The first coordinator is an owner-only, mention-driven Buzz ACP process. Its
configuration and lifecycle are controlled through PfTerminal and this repo.

## Build and install

```bash
./scripts/build-buzz-tools.sh
./scripts/build-agent-adapter.sh
./city2 validate
./city2 buzz install-agent-tooling
```

Installation copies pinned local build output to `/opt/city2` and installs the
`city2-buzz-agent@.service` template. It never enables or starts a service.

The service authenticates the bundled Codex runtime with the existing
PfTerminal ChatGPT login. systemd bind-mounts only `auth.json` into an otherwise
ephemeral `CODEX_HOME` under `/run`. The mount is writable so every Codex
process shares persisted OAuth rotation instead of consuming a stale copied
refresh token. The service cannot traverse the host home or see the PfTerminal
vault, configuration, sessions or memory. Restart it after an explicit
PfTerminal re-login so the mount follows the replacement file.
The intermediary ACP launcher strips the agent's Nostr private key before
starting Codex, so the model runtime and ordinary children do not inherit the
signing identity. The first coordinator configures no signer-bearing MCP
process. The City2-patched `buzz-acp` captures only the ACP `final_answer` phase
and publishes it directly with its own signer. Codex does not run the Buzz CLI
or receive the key.

For client compatibility, the owner may start a request with the exact textual
`@<display name>` even if Buzz omits the structured `p` tag. A follow-up in the
thread is accepted only when that exact channel/thread already contains a valid
message signed by this coordinator. Both fallbacks run after the owner-only
author gate.

Buzz Desktop discovers externally hosted agents from kind `10100` directory
profiles. Publish the coordinator as `respond_to=allowlist` with only the
owner's pubkey and all channels where it may be invoked; keep
`BUZZ_ACP_RESPOND_TO=owner-only` as the runtime enforcement boundary.

Released Buzz Desktop builds through `0.5.5` have an autocomplete eligibility
bug that filters relay-discovered agents unless the same Mac also manages them
locally. Upstream commit
[`014562c0`](https://github.com/block/buzz/commit/014562c063eae6ab1b7c6e3d20f2be3024c5f3a8)
fixes exact-channel, allowlist-authorized relay agent mentions, but landed after
the `0.5.5` release. Until a later Desktop release includes it, enter the exact
textual `@City2 Coordinator` manually. Prefix search does not bypass this
Desktop filter. Do not churn membership, duplicate the agent on the Mac, or
copy its private key to the Mac as a workaround. After upgrading, fully quit
and reopen Buzz so its five-minute relay-agent directory cache reloads.

Desktop's **Agents** page is a library and runtime manager for personas and
agents stored on that Mac; it is not the relay-agent directory. A
PfTerminal-hosted coordinator is therefore not expected to appear there.

Codex delegates sandboxing to the hardened systemd namespace because this LXC
cannot run a nested Linux sandbox. The runtime pins direct-tool `gpt-5.5` so
`MemoryDenyWriteExecute` remains enabled, and disables unrelated Codex apps,
plugins, goals, multi-agent tools, memories and web search to keep the first
coordinator's context and authority narrow.

## Identity

Generate the agent identity directly into the target Unix user's private config
directory. The private key is never printed; the public key is written to the
adjacent `.pub` file.

```bash
infra/buzz/scripts/create-agent-env.sh \
  "$HOME/.config/city2/agent.env" \
  "City2 Coordinator" \
  <OWNER_PUBLIC_NPUB_OR_HEX> \
  wss://<RELAY_TAILSCALE_DNS>:8443 \
  /srv/city2

infra/buzz/scripts/preflight-agent.sh "$HOME/.config/city2/agent.env"
```

Add the generated public identity without printing it:

```bash
./city2 buzz add-member "$(cat "$HOME/.config/city2/agent.env.pub")"
```

Starting the service uses the existing ChatGPT plan and remains a separate
explicit activation:

```bash
sudo systemctl enable --now city2-buzz-agent@"$USER".service
```

The initial unit hides the user's home and exposes only
`/home/<user>/city2` as read-only `/srv/city2`. Scoped write access is a later
reviewed systemd drop-in, not a prompt-level permission.
