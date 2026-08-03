#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

probe() {
  local label="$1"
  local command="$2"
  if command -v "${command}" >/dev/null 2>&1; then
    printf '%-18s %s\n' "${label}" "available"
  else
    printf '%-18s %s\n' "${label}" "missing"
  fi
}

echo "City2 doctor (read-only)"
printf '%-18s %s\n' "repository" "${ROOT}"
printf '%-18s %s\n' "version" "$(cat "${ROOT}/VERSION")"
if command -v pfterminal >/dev/null 2>&1; then
  printf '%-18s %s\n' "pfterminal" "$(pfterminal --version)"
else
  printf '%-18s %s\n' "pfterminal" "missing"
fi
probe git git
probe docker docker
probe jq jq
probe rustc rustc
probe node node
"${ROOT}/scripts/runtime_status.py" --format doctor

if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  printf '%-18s %s\n' "docker-compose" "available"
else
  printf '%-18s %s\n' "docker-compose" "missing"
fi

if [[ -f "${ROOT}/infra/buzz/.env" ]]; then
  printf '%-18s %s\n' "relay-config" "present"
else
  printf '%-18s %s\n' "relay-config" "not configured"
fi

if [[ -x "${ROOT}/build/bin/buzz-acp" ]]; then
  printf '%-18s %s\n' "buzz-tools" "built locally"
else
  printf '%-18s %s\n' "buzz-tools" "not built"
fi

git -C "${ROOT}" status --short --branch
