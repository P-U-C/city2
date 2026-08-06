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
proxy_image="$(sed -n 's/^BUZZ_PAIRING_PROXY_IMAGE=//p' .env)"
[[ "${proxy_image}" =~ ^nginx@sha256:[0-9a-f]{64}$ ]] ||
  fail "BUZZ_PAIRING_PROXY_IMAGE must be pinned by digest"

bind_ip="$(sed -n 's/^BUZZ_BIND_IP=//p' .env)"
port="$(sed -n 's/^BUZZ_HTTP_PORT=//p' .env)"
pairing_port="$(sed -n 's/^BUZZ_PAIRING_PORT=//p' .env)"
pairing_url="$(sed -n 's/^BUZZ_PAIRING_RELAY_URL=//p' .env)"
relay_host="$(sed -n 's/^BUZZ_DOMAIN=//p' .env)"
relay_url="$(sed -n 's/^RELAY_URL=//p' .env)"
tls_host="$(sed -n 's/^BUZZ_TLS_HOST=//p' .env)"
tls_port="$(sed -n 's/^BUZZ_TLS_PORT=//p' .env)"
tls_backend_port="$(sed -n 's/^BUZZ_TLS_BACKEND_PORT=//p' .env)"
tls_port="${tls_port:-8443}"
tls_backend_port="${tls_backend_port:-13000}"
[[ -n "${bind_ip}" ]] || fail "BUZZ_BIND_IP is empty"
[[ "${port}" =~ ^[0-9]+$ ]] || fail "BUZZ_HTTP_PORT is invalid"
[[ "${pairing_port}" =~ ^[0-9]+$ ]] || fail "BUZZ_PAIRING_PORT is invalid"
[[ "${tls_port}" =~ ^[0-9]+$ ]] || fail "BUZZ_TLS_PORT is invalid"
[[ "${tls_backend_port}" =~ ^[0-9]+$ ]] || fail "BUZZ_TLS_BACKEND_PORT is invalid"
(( port >= 1 && port <= 65535 )) || fail "BUZZ_HTTP_PORT is out of range"
(( pairing_port >= 1 && pairing_port <= 65535 )) || fail "BUZZ_PAIRING_PORT is out of range"
(( tls_port >= 1 && tls_port <= 65535 )) || fail "BUZZ_TLS_PORT is out of range"
(( tls_backend_port >= 1 && tls_backend_port <= 65535 )) || fail "BUZZ_TLS_BACKEND_PORT is out of range"
[[ "${port}" != "${pairing_port}" && "${port}" != "${tls_backend_port}" &&
   "${pairing_port}" != "${tls_backend_port}" ]] ||
  fail "relay, pairing and TLS backend ports must differ"
[[ -n "${relay_host}" ]] || fail "BUZZ_DOMAIN is empty"
[[ -n "${pairing_url}" ]] || fail "BUZZ_PAIRING_RELAY_URL is empty"

if [[ "${relay_url}" == wss://* ]]; then
  [[ "${tls_port}" != "80" && "${tls_port}" != "443" ]] ||
    fail "BUZZ_TLS_PORT must be non-default"
  [[ "${tls_port}" != "${port}" && "${tls_port}" != "${pairing_port}" &&
     "${tls_port}" != "${tls_backend_port}" ]] ||
    fail "TLS port must differ from relay, pairing and TLS backend ports"
  [[ "${tls_host}" =~ ^[a-zA-Z0-9.-]+\.ts\.net$ ]] || fail "BUZZ_TLS_HOST is invalid"
  [[ "${relay_host}" == "${tls_host}" ]] || fail "BUZZ_DOMAIN must match BUZZ_TLS_HOST"
  expected_relay_url="wss://${tls_host}:${tls_port}"
  expected_pairing_url="${expected_relay_url}/pair"
  [[ "${relay_url}" == "${expected_relay_url}" ]] || fail "RELAY_URL does not match the private TLS endpoint"

  command -v tailscale >/dev/null 2>&1 || fail "tailscale is unavailable for private TLS"
  tailscale_status="$(tailscale status --json 2>/dev/null)" || fail "cannot read Tailscale status"
  [[ "$(printf '%s' "${tailscale_status}" | jq -r '.BackendState // empty')" == "Running" ]] ||
    fail "Tailscale is not running"
  self_dns="$(printf '%s' "${tailscale_status}" | jq -r '.Self.DNSName // empty')"
  self_dns="${self_dns%.}"
  [[ "${self_dns}" == "${tls_host}" ]] || fail "BUZZ_TLS_HOST is not this Tailscale node"
  printf '%s' "${tailscale_status}" | jq -e --arg host "${tls_host}" \
    'any(.CertDomains[]?; . == $host)' >/dev/null ||
    fail "Tailscale HTTPS certificates are not enabled for BUZZ_TLS_HOST"
  unset tailscale_status self_dns

  serve_status="$(tailscale serve status --json 2>/dev/null)" || fail "cannot read Tailscale Serve status"
  if printf '%s' "${serve_status}" | jq -e \
    --arg port "${tls_port}" --arg authority "${tls_host}:${tls_port}" \
    '(.TCP[$port] != null)
     or (.Web[$authority] != null)
     or ((.AllowFunnel[$authority] // false) == true)' >/dev/null; then
    printf '%s' "${serve_status}" | jq -e \
      --arg port "${tls_port}" \
      --arg authority "${tls_host}:${tls_port}" \
      --arg target "http://127.0.0.1:${tls_backend_port}" \
      '(.TCP[$port].HTTPS == true)
       and (.Web[$authority].Handlers | keys == ["/"])
       and (.Web[$authority].Handlers["/"].Proxy == $target)
       and ((.AllowFunnel[$authority] // false) == false)' >/dev/null ||
      fail "the private TLS port has a conflicting Tailscale Serve route"
  fi
  unset serve_status
else
  expected_relay_url="ws://${relay_host}:${port}"
  expected_pairing_url="ws://${relay_host}:${pairing_port}/pair"
  [[ "${relay_url}" == "${expected_relay_url}" ]] || fail "RELAY_URL does not match the direct development endpoint"
fi
[[ "${pairing_url}" == "${expected_pairing_url}" ]] ||
  fail "BUZZ_PAIRING_RELAY_URL does not match the declared endpoint"

ip -o addr show | awk '{print $4}' | cut -d/ -f1 | grep -Fxq "${bind_ip}" ||
  fail "BUZZ_BIND_IP is not assigned to this host"

owner="$(sed -n 's/^RELAY_OWNER_PUBKEY=//p' .env)"
[[ "${owner}" =~ ^[0-9a-fA-F]{64}$ ]] || fail "owner pubkey is invalid"

if ! "${DOCKER[@]}" compose --project-name "${PROJECT}" --env-file .env -f compose.yml -f compose.private.yml ps -q relay 2>/dev/null | grep -q .; then
  if ss -ltnH | awk '{print $4}' | grep -Eq "(^|:)${port}$"; then
    fail "host port ${port} is already in use"
  fi
fi

pairing_owner="$(
  "${DOCKER[@]}" ps -q \
    --filter "label=com.docker.compose.project=${PROJECT}" \
    --filter "label=com.docker.compose.service=pairing-proxy"
)"
if [[ -z "${pairing_owner}" ]]; then
  # One-time migration: the prior reviewed layout exposed pairing-relay on this
  # same project/port. Treat only that exact Compose-owned container as ours.
  pairing_owner="$(
    "${DOCKER[@]}" ps -q \
      --filter "label=com.docker.compose.project=${PROJECT}" \
      --filter "label=com.docker.compose.service=pairing-relay"
  )"
fi
if [[ -z "${pairing_owner}" ]]; then
  if ss -ltnH | awk '{print $4}' | grep -Eq "(^|:)${pairing_port}$"; then
    fail "host port ${pairing_port} is already in use"
  fi
fi
unset pairing_owner

tls_owner="$(
  "${DOCKER[@]}" ps -q \
    --filter "label=com.docker.compose.project=${PROJECT}" \
    --filter "label=com.docker.compose.service=tls-ingress"
)"
if [[ -z "${tls_owner}" ]] && ss -ltnH | awk '{print $4}' | grep -Eq "(^|:)${tls_backend_port}$"; then
  fail "host TLS backend port ${tls_backend_port} is already in use"
fi
unset tls_owner

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
printf '%s' "${rendered}" | jq -e \
  --arg bind_ip "${bind_ip}" \
  --arg port "${pairing_port}" \
  '.services["pairing-proxy"].ports
   | length == 1
     and .[0].host_ip == $bind_ip
     and (.[0].published | tostring) == $port
     and (.[0].target | tostring) == "8080"' >/dev/null ||
  fail "rendered pairing proxy is not the single advertised private binding"
printf '%s' "${rendered}" | jq -e \
  --arg port "${tls_backend_port}" \
  '.services["tls-ingress"].ports
   | length == 1
     and .[0].host_ip == "127.0.0.1"
     and (.[0].published | tostring) == $port
     and (.[0].target | tostring) == "8080"' >/dev/null ||
  fail "rendered TLS ingress is not the single loopback binding"
printf '%s' "${rendered}" | jq -e \
  '.services["pairing-relay"].ports == null
   and .services["pairing-relay"].read_only == true
   and .services["pairing-relay"].cap_drop == ["ALL"]
   and any(.services["pairing-relay"].security_opt[]?; . == "no-new-privileges:true")
   and .services["pairing-proxy"].read_only == true
   and .services["pairing-proxy"].cap_drop == ["ALL"]
   and any(.services["pairing-proxy"].security_opt[]?; . == "no-new-privileges:true")
   and .services["tls-ingress"].read_only == true
   and .services["tls-ingress"].cap_drop == ["ALL"]
   and any(.services["tls-ingress"].security_opt[]?; . == "no-new-privileges:true")' \
  >/dev/null || fail "pairing relay exposure or proxy hardening is invalid"
printf '%s' "${rendered}" | jq -e \
  --arg url "${expected_pairing_url}" \
  '.services.relay.environment.BUZZ_PAIRING_RELAY_URL == $url' >/dev/null ||
  fail "rendered relay does not advertise the configured pairing URL"
unset rendered

"${DOCKER[@]}" buildx imagetools inspect "${image}" >/dev/null 2>&1 ||
  fail "pinned relay image is unavailable"
"${DOCKER[@]}" buildx imagetools inspect "${proxy_image}" >/dev/null 2>&1 ||
  fail "pinned pairing proxy image is unavailable"

echo "preflight: PASS"
echo "  project=${PROJECT}"
echo "  bind=${bind_ip}:${port}"
echo "  pairing=private:${pairing_port}/pair"
if [[ "${relay_url}" == wss://* ]]; then
  echo "  mobile-tls=tailnet-only:${tls_port}"
else
  echo "  mobile-tls=development-only"
fi
echo "  image=pinned-by-digest"
echo "  compose=valid"
if [[ "${DOCKER[0]}" == "sudo" ]]; then
  echo "  docker=passwordless-sudo"
else
  echo "  docker=direct"
fi
echo "No containers were started."
