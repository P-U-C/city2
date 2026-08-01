# Operations

All commands run from the repository root through `./city2` unless noted.

## Read-only checks

```bash
./city2 doctor
./city2 validate
./city2 status
```

## Prepare the relay

The human owner first creates and backs up a Buzz identity on their own device.
Only the public `npub` or public hex reaches this host.

```bash
cp config/operator-input.example .city2/operator-input
$EDITOR .city2/operator-input
infra/buzz/scripts/validate-operator-input.sh .city2/operator-input

infra/buzz/scripts/bootstrap-env.sh <OWNER_PUBLIC_NPUB_OR_HEX>
./city2 buzz preflight
```

Bootstrap writes `infra/buzz/.env` with mode `0600` and never prints secret
values. Back it up through an encrypted path before startup.

## Start/stop

These are explicit runtime changes:

```bash
./city2 buzz pull
./city2 buzz start
./city2 buzz status
./city2 buzz stop
```

`down` removes containers/network but preserves named volumes. It is not used
for normal stops.

## Backups

```bash
./city2 buzz backup
./city2 buzz verify-backup <backup-directory>
```

The backup takes an aligned PostgreSQL dump plus MinIO, Git and Redis volume
archives. `.env` and human identity keys are intentionally excluded and need a
separate encrypted backup path.

## Coordinator runtime authentication

Only after coordinator activation is approved, install the pinned adapter and
start the service. systemd reads only the existing PfTerminal ChatGPT auth file
and materializes it privately under `/run`; the launcher uses an ephemeral
`CODEX_HOME`. No provider API key is copied or separately billed.

```bash
./scripts/build-agent-adapter.sh
./city2 buzz install-agent-tooling
infra/buzz/scripts/preflight-agent.sh "$HOME/.config/city2/agent.env"
sudo systemctl enable --now city2-buzz-agent@"$USER".service
```

## Disposable E2E

```bash
./city2 buzz e2e
```

This uses a random Compose project and loopback port, verifies a signed private
message and outsider rejection, backs up, destroys all test state, restores it,
verifies the message and removes the disposable state. It makes no model call.

## Upgrade

1. Review the new Buzz release and source diff.
2. Update `infra/buzz/SOURCE.md`, Compose and image digest together.
3. Rebuild tools with `./scripts/build-buzz-tools.sh`.
4. Run `./city2 validate` and `./city2 buzz e2e`.
5. Take and verify a production backup.
6. Apply the upgrade through a reviewed PR.
7. Roll back to the prior digest and backup if readiness or signed round-trip
   fails.
