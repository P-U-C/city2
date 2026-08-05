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

For mobile compatibility, the owner may start a request with the exact textual
`@<display name>` even if the app drops the structured `p` tag. A follow-up in
the thread is accepted only when that exact channel/thread already contains a
valid message signed by this coordinator. Both fallbacks run after the
owner-only author gate.

Buzz mobile loads agent autocomplete from kind `10100` directory profiles and
channel bot membership. Without a NIP-OA owner attestation, an `owner-only`
non-member directory entry is intentionally hidden. Until the owner creates the
agent through Buzz Desktop and supplies that attestation, publish the equivalent
directory projection as `respond_to=allowlist` with only the owner's pubkey;
keep `BUZZ_ACP_RESPOND_TO=owner-only` as the runtime enforcement boundary. The
mobile provider refreshes the directory on relay reconnect, so relaunch the app
after changing the profile.

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
  ws://<RELAY_TAILSCALE_HOST>:3000 \
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
