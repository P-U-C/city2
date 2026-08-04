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
starting Codex, so model tools never inherit the signing identity.

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
