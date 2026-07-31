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

## Agent runtime credential

Only after coordinator activation is approved:

```bash
./city2 buzz prepare-agent-credential
# start and test the agent
./city2 buzz clear-agent-credential
```

The selected key moves from PfTerminal's vault into a root-only file under
`/run`; it is never printed or committed, disappears on reboot and is removed
after the agent stops.

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
