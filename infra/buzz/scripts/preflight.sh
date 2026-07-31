#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"
PROJECT="${BUZZ_COMPOSE_PROJECT:-city2-buzz}"

fail() {
  echo "preflight: FAIL: $*" >&2
  exit 1
}

detect_docker() {
  if docker info >/dev/null 2>&1; then
    DOCKER=(docker)
  elif sudo -n docker info >/dev/null 2>&1; then
    DOCKER=(sudo -n docker)
  else
    fail "Docker daemon access is unavailable directly and through passwordless sudo"
  fi
}

[[ -f .env ]] || fail "missing .env; run scripts/bootstrap-env.sh"
[[ "$(stat -c '%a' .env)" == "600" ]] || fail ".env must have mode 0600"
! grep -q 'CHANGE_ME' .env || fail ".env still contains placeholders"

command -v docker >/dev/null 2>&1 || fail "docker is unavailable"
command -v jq >/dev/null 2>&1 || fail "jq is unavailable"
command -v ip >/dev/null 2>&1 || fail "iproute2 is unavailable"
command -v ss >/dev/null 2>&1 || fail "ss is unavailable"
detect_docker
"${DOCKER[@]}" compose version >/dev/null 2>&1 || fail "docker compose is unavailable"
[[ "${PROJECT}" =~ ^[a-z0-9][a-z0-9_-]*$ ]] || fail "invalid Compose project name"

image="$(sed -n 's/^BUZZ_IMAGE=//p' .env)"
[[ "${image}" =~ ^ghcr\.io/block/buzz@sha256:[0-9a-f]{64}$ ]] ||
  fail "BUZZ_IMAGE must be pinned by digest"

bind_ip="$(sed -n 's/^BUZZ_BIND_IP=//p' .env)"
port="$(sed -n 's/^BUZZ_HTTP_PORT=//p' .env)"
[[ -n "${bind_ip}" ]] || fail "BUZZ_BIND_IP is empty"
[[ "${port}" =~ ^[0-9]+$ ]] || fail "BUZZ_HTTP_PORT is invalid"

ip -o addr show | awk '{print $4}' | cut -d/ -f1 | grep -Fxq "${bind_ip}" ||
  fail "BUZZ_BIND_IP is not assigned to this host"

owner="$(sed -n 's/^RELAY_OWNER_PUBKEY=//p' .env)"
[[ "${owner}" =~ ^[0-9a-fA-F]{64}$ ]] || fail "owner pubkey is invalid"

if ! "${DOCKER[@]}" compose --project-name "${PROJECT}" --env-file .env -f compose.yml -f compose.private.yml ps -q relay 2>/dev/null | grep -q .; then
  if ss -ltnH | awk '{print $4}' | grep -Eq "(^|:)${port}$"; then
    fail "host port ${port} is already in use"
  fi
fi

"${DOCKER[@]}" compose --project-name "${PROJECT}" --env-file .env -f compose.yml -f compose.private.yml config --quiet

rendered="$("${DOCKER[@]}" compose --project-name "${PROJECT}" --env-file .env -f compose.yml -f compose.private.yml config --format json)"
printf '%s' "${rendered}" | jq -e \
  --arg bind_ip "${bind_ip}" \
  --arg port "${port}" \
  '.services.relay.ports
   | length == 1
     and .[0].host_ip == $bind_ip
     and (.[0].published | tostring) == $port
     and (.[0].target | tostring) == "3000"' >/dev/null ||
  fail "rendered relay port is not the single requested private binding"
unset rendered

"${DOCKER[@]}" buildx imagetools inspect "${image}" >/dev/null 2>&1 ||
  fail "pinned relay image is unavailable"

echo "preflight: PASS"
echo "  project=${PROJECT}"
echo "  bind=${bind_ip}:${port}"
echo "  image=pinned-by-digest"
echo "  compose=valid"
if [[ "${DOCKER[0]}" == "sudo" ]]; then
  echo "  docker=passwordless-sudo"
else
  echo "  docker=direct"
fi
echo "No containers were started."
