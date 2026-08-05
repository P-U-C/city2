# Operations

All commands run from the repository root through `./city2` unless noted.

## Read-only checks

```bash
./city2 doctor
./city2 validate
./city2 status
```

`doctor` and `status` distinguish a present Tailscale binary from an actual
connection and read the coordinator's system unit (not the unrelated user
manager). `tailscale=logged-out` blocks live fleet/relay activation even when
the local relay containers and coordinator process are otherwise healthy.

## Core ledger proof

M1 is repository-local and undeployed. These commands operate only on the path
explicitly supplied by the operator:

```bash
./city2 core init --db /approved/private/path/core.sqlite
./city2 core status --db /approved/private/path/core.sqlite
./city2 core migrate --db /approved/private/path/core.sqlite
./city2 core export --db /approved/private/path/core.sqlite \
  --output /approved/private/path/events.jsonl
```

`status` performs SQLite, migration, event-chain, immutable-record and
projection verification before reporting. A mutation refuses non-WAL mode,
anything other than `synchronous=FULL`, a foreign writer identity or any
integrity mismatch.

For a synthetic local recovery proof, generate a disposable checkpoint key
outside the repository, create the archive and restore it into an empty
directory:

```bash
./city2 core keygen --private-key /private/path/checkpoint.key \
  --public-key /private/path/checkpoint.pub
./city2 core backup --db /private/path/core.sqlite \
  --output /private/path/archive-1 \
  --signing-key /private/path/checkpoint.key --key-version local-test-v1
./city2 core verify-backup --archive /private/path/archive-1 \
  --trusted-key /private/path/checkpoint.pub
./city2 core restore --archive /private/path/archive-1 \
  --output-dir /empty/private/path/restored \
  --trusted-key /private/path/checkpoint.pub
```

The M1 bundle is deliberately marked `local-plaintext-m1-test-only`. Never
upload or treat it as an off-host archive. Encryption, independent recovery
keys and archive backends remain gated on M5. Never commit databases, exports,
archives or checkpoint keys.

M5 real local encryption proof requires the pinned ignored tool build:

```bash
./scripts/build-archive-tools.sh
CITY2_AGE_BIN="$PWD/build/archive-tools" ./city2 validate
```

This makes no Walrus call. Testnet activation requires separate operator review;
Mainnet remains prohibited.

M6 examples are intentionally disabled:

```bash
cat config/producer-contract.example.json
cat config/producer-agent.example.json
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_producer.py' -v
```

Do not enable them by editing placeholders. Follow `docs/PRODUCER.md`; live
selection first requires a healthy read-only fleet probe and separate review.

The selected `ai-infra` manifests are disabled. Its one-time M6 shadow used a
systemd read-only bind namespace that made the producer's original tree
inaccessible; file mode or an A0 manifest alone was not treated as a write
boundary. The observer and keys were removed after proof.

The reviewed namespace source is
`infra/producer/ai-infra/city2-producer-observer-ai-infra.service`. Repository
validation checks its syntax and a synthetic credential-backed observation.
It remains a reviewed source template with disabled manifests; no repository
command enables or starts it. A future run must provision a new signer, bind
its public fingerprint and keep it root-only on worker-1.

Build and inspect the credential-free deployment artifact without changing the
host or worker:

```bash
make build-producer-observer-bundle
tar -tzf build/producer-observer/city2-producer-observer-ai-infra.tar.gz
```

The archive is ignored, reproducible and includes `MANIFEST.sha256` plus
`REMOVAL.md`; it intentionally contains no signing key, environment file,
database, producer output or Buzz identity.

M7 expansion remains fail-closed:

```bash
python3 scripts/validate_contracts.py
jq '{decision,candidate,measurement,evaluation}' \
  config/expansion-admission.m7.json
```

The checked-in decision is `defer` and its bound agent manifest is disabled.
Do not change either to admitted/enabled in place. Follow `docs/EXPANSION.md`,
create a new immutable decision revision and keep activation as a separate
reviewed transaction.

The coordinator's signed Owner-to-Bot reduction completed on 2026-08-03; the
human identity is now the sole Owner in each bootstrap channel. This satisfies
only the demotion precondition. The M2/M3 live criteria and three successful
recovery drills remain open. See `docs/M7-DEMOTION-EVIDENCE.md`.

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

This is the independent Buzz relay backup, not the Core proof above. It takes an
aligned PostgreSQL dump plus MinIO, Git and Redis volume
archives. `.env` and human identity keys are intentionally excluded and need a
separate encrypted backup path.

Backup stops the relay briefly to align the stores. Before stopping anything it
now requires the configured `BUZZ_BIND_IP` to be assigned locally; otherwise it
fails closed and leaves every service running. This prevents a logged-out
overlay network from turning a backup into an unrestartable relay. Run
`./city2 buzz preflight` first when network state is uncertain.

## Coordinator runtime authentication

Only after coordinator activation is approved, install the pinned adapter and
start the service. systemd bind-mounts only the existing PfTerminal ChatGPT
`auth.json` into an otherwise ephemeral `CODEX_HOME`. The narrow mount is
read-write so Codex's guarded refresh can persist rotated OAuth credentials and
all PfTerminal/Codex processes observe one current token chain. The service
still cannot traverse the host home, and no provider API key is copied or
separately billed. Restart the service after an explicit PfTerminal re-login so
the mount follows the newly created auth file.

The LXC host cannot run Codex's nested Linux sandbox. The coordinator therefore
uses ACP `agent-full-access` only *inside* the hardened systemd namespace;
`ProtectSystem=strict`, `ProtectHome=yes`, and the read-only `/srv/city2` bind
remain the actual enforcement boundary. `MemoryDenyWriteExecute` stays enabled,
so the runtime pins `gpt-5.5`, the strongest currently available direct-tool
model, rather than using a GPT-5.6 model whose required V8 code-mode executor is
incompatible with that hardening. Unrelated apps, plugins, goals, multi-agent
tools, web search, and memories are disabled in the ephemeral Codex config to
keep context and authority narrow.

`BUZZ_ACP_AUTO_PUBLISH_FINAL=true` enables the reviewed signer-side response
path. Codex returns a final answer; patched `buzz-acp` anchors, signs, and
publishes it. Do not restore model-driven `buzz messages send` for ordinary
coordinator replies or configure a signer-bearing MCP process: the model runtime
intentionally has no signing key.

Buzz clients may omit structured mention tags. The reviewed compatibility
path uses `BUZZ_ACP_TEXT_MENTION=<exact display name>` and
`BUZZ_ACP_FOLLOW_OWN_THREADS=true`: only the registered owner's signed event can
trigger by textual `@name`, and thread continuation additionally requires a
valid coordinator-signed response in that exact channel/thread.

WebSocket delivery remains primary, but the pinned harness also reconciles
persisted channel events through the authenticated HTTP bridge every three
seconds. The catch-up query reuses the live channel/kind/mention filters, has a
two-second timeout and five-second overlap, verifies signatures, and shares one
bounded event-ID dedup boundary with WebSocket delivery. This is a delivery
backstop, not a broader subscription or authority grant.

Buzz Desktop through `0.5.5` filters relay-only agents from mention
autocomplete and shows only Mac-managed runtimes on its **Agents** page.
Upstream `014562c0` fixes authorized, exact-channel relay-agent mentions after
that release. Until a release containing it is installed, use the exact textual
`@City2 Coordinator`; do not duplicate the coordinator or move its signing key
to the Mac.

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
