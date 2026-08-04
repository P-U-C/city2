#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

fail() {
  echo "validate: FAIL: $*" >&2
  exit 1
}

required=(
  AGENTS.md
  README.md
  docs/ARCHITECTURE.md
  docs/COMPANY-OS-SPEC.md
  docs/CORE.md
  docs/MEMORY.md
  docs/ADAPTERS.md
  docs/REVIEW.md
  docs/ARCHIVE.md
  docs/PRODUCER.md
  docs/PRODUCER-REHEARSAL.md
  docs/PRODUCER-INSTALL-EVIDENCE.md
  docs/PRODUCER-KEY-EVIDENCE.md
  docs/PRODUCER-SHADOW-EVIDENCE.md
  docs/EXPANSION.md
  docs/M7-DEMOTION-EVIDENCE.md
  docs/MIGRATION.md
  docs/PFTERMINAL.md
  docs/SECURITY.md
  docs/OPERATIONS.md
  docs/FLEET.md
  docs/THREAT-MODEL.md
  contracts/v1/README.md
  contracts/v1/RUNNER.md
  contracts/v1/CREDENTIAL-BROKER.md
  contracts/v1/ARCHIVE-BACKEND.md
  contracts/v1/AUTHORITY.md
  config/authority-policy.v1.json
  config/coordinator-core.example.json
  config/coordinator-agent.m7.json
  config/expansion-admission.m7.json
  config/producer-contract.example.json
  config/producer-agent.example.json
  config/producer-pilot.ai-infra.json
  config/producer-agent.ai-infra.json
  config/producer-observer.ai-infra.pub
  scripts/observe_producer.py
  infra/producer/ai-infra/city2-producer-observer-ai-infra.service
  infra/producer/ai-infra/REMOVAL.md
  scripts/build-producer-observer-bundle.sh
  fixtures/contracts/v1/manifest.json
  schemas/v1/common.schema.json
  schemas/v1/agent.schema.json
  schemas/v1/expansion-admission.schema.json
  schemas/v1/task-envelope.schema.json
  schemas/v1/result.schema.json
  scripts/validate_spec.py
  scripts/validate_contracts.py
  scripts/runtime_status.py
  config/fleet.json
  config/fleet.schema.json
  infra/buzz/SOURCE.md
  infra/buzz/compose.yml
  infra/buzz/compose.private.yml
  infra/buzz/.env.example
  infra/buzz/agents/codex-acp/package.json
  infra/buzz/agents/codex-acp/package-lock.json
)
for path in "${required[@]}"; do
  [[ -f "${path}" ]] || fail "missing ${path}"
done

if [[ "${CI:-}" == "true" && ! -x build/archive-tools/age ]]; then
  ./scripts/build-archive-tools.sh
fi

mapfile -t shell_files < <(find . -type f -not -path './.git/*' -not -path './build/*' -exec awk 'FNR == 1 && /^#!.*(ba)?sh/ { print FILENAME }' {} + | sort)
for path in "${shell_files[@]}"; do
  bash -n "${path}"
done

python3 -m unittest discover -s tests -p 'test_*.py'
python3 -m py_compile \
  infra/buzz/scripts/normalize-owner-pubkey.py \
  scripts/fleet_status.py \
  scripts/runtime_status.py \
  scripts/observe_producer.py \
  scripts/validate_contracts.py \
  scripts/validate_spec.py \
  city2-core \
  src/city2core/*.py
./scripts/fleet_status.py --offline >/dev/null
python3 scripts/validate_spec.py
python3 scripts/validate_contracts.py

if command -v systemd-analyze >/dev/null 2>&1; then
  unit_tmp="$(mktemp -d /tmp/city2-units.XXXXXX)"
  sed \
    "s|^ExecStart=/opt/city2/bin/city2-agent-launcher$|ExecStart=${ROOT}/infra/buzz/agents/bin/city2-agent-launcher|" \
    infra/buzz/agents/systemd/city2-buzz-agent@.service \
    >"${unit_tmp}/city2-buzz-agent@.service"
  SYSTEMD_UNIT_PATH="${unit_tmp}:${ROOT}/infra/producer/ai-infra:/lib/systemd/system:/usr/lib/systemd/system" \
    systemd-analyze verify city2-buzz-agent@.service
  rm -rf "${unit_tmp}"
  SYSTEMD_UNIT_PATH="${ROOT}/infra/producer/ai-infra:/lib/systemd/system:/usr/lib/systemd/system" \
    systemd-analyze verify city2-producer-observer-ai-infra.service
fi

for path in city2 city2-core scripts/*.sh infra/buzz/run.sh infra/buzz/scripts/*.sh infra/buzz/agents/bin/*; do
  [[ -x "${path}" ]] || fail "expected executable: ${path}"
done

if command -v shellcheck >/dev/null 2>&1; then
  shellcheck "${shell_files[@]}"
fi

if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  tmp="$(mktemp -d /tmp/city2-compose.XXXXXX)"
  trap 'rm -rf "${tmp}"' EXIT
  cp infra/buzz/compose.yml infra/buzz/compose.private.yml "${tmp}/"
  cat >"${tmp}/.env" <<'EOF'
BUZZ_IMAGE=ghcr.io/block/buzz@sha256:a2b59030b29242adb0783a05cbabd63f51518fdfe7b724845a68f77adab7e1f9
BUZZ_BIND_IP=127.0.0.1
BUZZ_HTTP_PORT=3000
BUZZ_DOMAIN=127.0.0.1
RELAY_URL=ws://127.0.0.1:3000
BUZZ_MEDIA_BASE_URL=http://127.0.0.1:3000/media
BUZZ_MEDIA_SERVER_DOMAIN=127.0.0.1
BUZZ_CORS_ORIGINS=http://127.0.0.1:3000
BUZZ_REQUIRE_AUTH_TOKEN=true
BUZZ_REQUIRE_RELAY_MEMBERSHIP=true
BUZZ_ALLOW_NIP_OA_AUTH=true
BUZZ_AUTO_MIGRATE=true
BUZZ_GIT_CONFORMANCE_PROBE=true
RUST_LOG=info
RELAY_OWNER_PUBKEY=0000000000000000000000000000000000000000000000000000000000000001
BUZZ_RELAY_PRIVATE_KEY=0000000000000000000000000000000000000000000000000000000000000002
BUZZ_GIT_HOOK_HMAC_SECRET=0000000000000000000000000000000000000000000000000000000000000003
POSTGRES_DB=buzz
POSTGRES_USER=buzz
POSTGRES_PASSWORD=static-validation-only
REDIS_PASSWORD=static-validation-only
BUZZ_S3_ACCESS_KEY=static-validation-only
BUZZ_S3_SECRET_KEY=static-validation-only
BUZZ_S3_BUCKET=buzz-media
BUZZ_S3_ADDRESSING_STYLE=path
EOF
  docker compose \
    --project-name city2-static \
    --env-file "${tmp}/.env" \
    -f "${tmp}/compose.yml" \
    -f "${tmp}/compose.private.yml" \
    config --quiet
  rm -rf "${tmp}"
  trap - EXIT
fi

if rg -n --hidden \
  --glob '!.git/**' \
  --glob '!build/**' \
  --glob '!*.example' \
  '(-----BEGIN (OPENSSH|RSA|EC) PRIVATE KEY-----|sk-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9_]{20,}|xox[baprs]-[A-Za-z0-9-]{20,})' .; then
  fail "credential-like material detected"
fi

if rg -n '(100\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}|192\.168\.[0-9]{1,3}\.[0-9]{1,3})' \
  --glob '!docs/PILOT-EVIDENCE.md' .; then
  fail "hard-coded private host address detected"
fi

git diff --check
./city2 --help >/dev/null

if [[ -f build/bin/BINARIES.sha256 ]]; then
  (cd build/bin && sha256sum -c BINARIES.sha256 >/dev/null)
fi

python3 - <<'PY'
import json
from pathlib import Path

root = Path("infra/buzz/agents/codex-acp")
package = json.loads((root / "package.json").read_text())
lock = json.loads((root / "package-lock.json").read_text())
expected = "1.1.7"
assert package["dependencies"]["@agentclientprotocol/codex-acp"] == expected
assert lock["packages"]["node_modules/@agentclientprotocol/codex-acp"]["version"] == expected
PY

if [[ -x build/codex-acp/node_modules/.bin/codex-acp ]]; then
  build/codex-acp/node_modules/.bin/codex-acp --version | grep -q '1\.1\.7$'
fi

grep -q '^unset BUZZ_PRIVATE_KEY$' \
  infra/buzz/agents/bin/city2-codex-acp-launcher ||
  fail "Codex ACP child must not inherit the Nostr private key"
grep -q '^export NODE_OPTIONS=--jitless$' \
  infra/buzz/agents/bin/city2-codex-acp-launcher ||
  fail "Codex ACP must stay compatible with MemoryDenyWriteExecute"
grep -q '^BindPaths=/home/%i/.codex/auth.json:/run/city2-agent-%i/codex/auth.json$' \
  infra/buzz/agents/systemd/city2-buzz-agent@.service ||
  fail "coordinator must share exactly the PfTerminal auth file for OAuth rotation"
if grep -q '^LoadCredential=codex.auth:' \
  infra/buzz/agents/systemd/city2-buzz-agent@.service; then
  fail "coordinator must not clone a rotating OAuth credential"
fi

echo "validate: PASS"
