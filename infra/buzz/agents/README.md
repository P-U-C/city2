# Coordinator integration

The first coordinator is an owner-only, mention-driven Buzz ACP process. Its
configuration and lifecycle are controlled through PfTerminal and this repo.

## Build and install

```bash
./scripts/build-buzz-tools.sh
./city2 validate
./city2 buzz install-agent-tooling
```

Installation copies pinned local build output to `/opt/city2` and installs the
`city2-buzz-agent@.service` template. It never enables or starts a service.

Prepare the runtime provider credential from PfTerminal's vault. This creates a
root-only file under the host's RAM-backed `/run` filesystem and never prints
the value:

```bash
infra/buzz/scripts/prepare-agent-credential.sh
```

This is deliberately separate from installation and requires approval because
it reads a real provider credential. The file disappears on reboot and should
be removed after stopping the agent. The service cannot see the PfTerminal vault
or execute `pfterminal` after startup.

```bash
./city2 buzz clear-agent-credential
```

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
  /absolute/path/to/city2 \
  <REVIEWED_MODEL_ID>

infra/buzz/scripts/preflight-agent.sh "$HOME/.config/city2/agent.env"
```

Add the generated public identity without printing it:

```bash
./city2 buzz add-member "$(cat "$HOME/.config/city2/agent.env.pub")"
```

Starting the service incurs provider usage and remains a separate explicit
approval:

```bash
sudo systemctl enable --now city2-buzz-agent@"$USER".service
```

The initial unit bind-mounts `/home/<user>/city2` read-only. Scoped write access
is a later reviewed systemd drop-in, not a prompt-level permission.
