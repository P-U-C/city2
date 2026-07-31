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
  docs/MIGRATION.md
  docs/PFTERMINAL.md
  docs/SECURITY.md
  docs/OPERATIONS.md
  docs/FLEET.md
  config/fleet.json
  config/fleet.schema.json
  infra/buzz/SOURCE.md
  infra/buzz/compose.yml
  infra/buzz/compose.private.yml
  infra/buzz/.env.example
)
for path in "${required[@]}"; do
  [[ -f "${path}" ]] || fail "missing ${path}"
done

mapfile -t shell_files < <(find . -type f -not -path './.git/*' -not -path './build/*' -exec awk 'FNR == 1 && /^#!.*(ba)?sh/ { print FILENAME }' {} + | sort)
for path in "${shell_files[@]}"; do
  bash -n "${path}"
done

python3 -m unittest discover -s tests -p 'test_*.py'
python3 -m py_compile \
  infra/buzz/scripts/normalize-owner-pubkey.py \
  scripts/fleet_status.py
./scripts/fleet_status.py --offline >/dev/null

for path in city2 scripts/*.sh infra/buzz/run.sh infra/buzz/scripts/*.sh infra/buzz/agents/bin/*; do
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

echo "validate: PASS"
