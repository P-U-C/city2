#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT}/.env"
ACTION="${1:-status}"

fail() {
  echo "tailscale-serve: FAIL: $*" >&2
  exit 1
}

value() {
  sed -n "s/^$1=//p" "${ENV_FILE}"
}

[[ -f "${ENV_FILE}" ]] || fail "missing .env"
command -v tailscale >/dev/null 2>&1 || fail "tailscale is unavailable"
command -v jq >/dev/null 2>&1 || fail "jq is unavailable"

host="${CITY2_TLS_HOST:-$(value BUZZ_TLS_HOST)}"
tls_port="${CITY2_TLS_PORT:-$(value BUZZ_TLS_PORT)}"
backend_port="${CITY2_TLS_BACKEND_PORT:-$(value BUZZ_TLS_BACKEND_PORT)}"
[[ "${host}" =~ ^[a-zA-Z0-9.-]+\.ts\.net$ ]] || fail "BUZZ_TLS_HOST is invalid"
[[ "${tls_port}" =~ ^[0-9]+$ ]] && (( tls_port >= 1 && tls_port <= 65535 )) ||
  fail "BUZZ_TLS_PORT is invalid"
[[ "${tls_port}" != "80" && "${tls_port}" != "443" ]] ||
  fail "BUZZ_TLS_PORT must be non-default"
[[ "${backend_port}" =~ ^[0-9]+$ ]] && (( backend_port >= 1 && backend_port <= 65535 )) ||
  fail "BUZZ_TLS_BACKEND_PORT is invalid"

authority="${host}:${tls_port}"
target="http://127.0.0.1:${backend_port}"

serve_status=""
load_status() {
  serve_status="$(tailscale serve status --json 2>/dev/null)" ||
    fail "cannot read Tailscale Serve status"
  printf '%s' "${serve_status}" | jq -e 'type == "object"' >/dev/null 2>&1 ||
    fail "Tailscale Serve status is invalid"
}

mutate_serve() {
  if tailscale serve "$@" >/dev/null 2>&1; then
    return 0
  fi
  command -v sudo >/dev/null 2>&1 || fail "Serve mutation requires root and sudo is unavailable"
  sudo -n tailscale serve "$@" >/dev/null
}

is_exact() {
  printf '%s' "${serve_status}" | jq -e \
    --arg port "${tls_port}" \
    --arg authority "${authority}" \
    --arg target "${target}" \
    '(.TCP[$port].HTTPS == true)
     and (.Web[$authority].Handlers | keys == ["/"])
     and (.Web[$authority].Handlers["/"].Proxy == $target)
     and ((.AllowFunnel[$authority] // false) == false)' >/dev/null
}

has_conflict() {
  printf '%s' "${serve_status}" | jq -e \
    --arg port "${tls_port}" \
    --arg authority "${authority}" \
    '(.TCP[$port] != null)
     or (.Web[$authority] != null)
     or ((.AllowFunnel[$authority] // false) == true)' >/dev/null
}

backend_is_available() {
  command -v ss >/dev/null 2>&1 || fail "ss is unavailable"
  if ! ss -ltnH | awk '{print $4}' | grep -Eq "(^|:)${backend_port}$"; then
    return 0
  fi

  project="${BUZZ_COMPOSE_PROJECT:-city2-buzz}"
  [[ "${project}" =~ ^[a-z0-9][a-z0-9_-]*$ ]] || fail "invalid Compose project name"
  if docker info >/dev/null 2>&1; then
    docker_cmd=(docker)
  elif sudo -n docker info >/dev/null 2>&1; then
    docker_cmd=(sudo -n docker)
  else
    fail "TLS backend port is occupied and Docker ownership cannot be verified"
  fi
  owner="$(
    "${docker_cmd[@]}" ps -q \
      --filter "label=com.docker.compose.project=${project}" \
      --filter "label=com.docker.compose.service=tls-ingress"
  )"
  [[ -n "${owner}" ]] || fail "TLS backend port is already in use"
  unset owner project docker_cmd
}

load_status

case "${ACTION}" in
  preflight)
    if ! is_exact && has_conflict; then
      fail "configured TLS port already has a different Serve route"
    fi
    backend_is_available
    echo "tailscale-serve: PASS (private TLS target available)"
    ;;
  apply)
    if is_exact; then
      echo "tailscale-serve: PASS (private TLS route already exact)"
      exit 0
    fi
    if has_conflict; then
      fail "configured TLS port already has a different Serve route; refusing to replace it"
    fi
    mutate_serve --bg --yes --https="${tls_port}" "127.0.0.1:${backend_port}"
    load_status
    is_exact || fail "Serve route did not converge to the expected private target"
    echo "tailscale-serve: PASS (private TLS route applied)"
    ;;
  status)
    is_exact || fail "private TLS route is missing or differs from the declared target"
    echo "tailscale-serve: PASS (private TLS route exact)"
    ;;
  remove)
    if is_exact; then
      mutate_serve --yes --https="${tls_port}" off
      load_status
    elif has_conflict; then
      fail "refusing to remove a route not owned exactly by City2"
    else
      echo "tailscale-serve: PASS (private TLS route already absent)"
      exit 0
    fi
    if has_conflict; then
      fail "private TLS route still exists after removal"
    fi
    echo "tailscale-serve: PASS (private TLS route removed)"
    ;;
  absent)
    has_conflict && fail "private TLS route remains while the ingress is stopped"
    echo "tailscale-serve: PASS (private TLS route absent)"
    ;;
  *)
    fail "usage: tailscale-serve.sh preflight|apply|status|remove|absent"
    ;;
esac
