#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT}/.env"

usage() {
  cat >&2 <<'EOF'
Usage: ./scripts/bootstrap-env.sh <owner-pubkey-hex> [bind-ip] [relay-host]

The owner argument is the 64-character PUBLIC Nostr key from Buzz Desktop.
Never copy the owner's private key to this host or into chat.

bind-ip defaults to this host's Tailscale IPv4 address. relay-host defaults to
the node's certificate-enabled Tailscale DNS name, with bind-ip as a local-dev
fallback. This creates .env with mode 0600 and prints no secret values.
EOF
  exit 2
}

owner_input="${1:-}"
owner="$("${ROOT}/scripts/normalize-owner-pubkey.py" "${owner_input}")" || usage
unset owner_input

bind_ip="${2:-}"
if [[ -z "${bind_ip}" ]] && command -v tailscale >/dev/null 2>&1; then
  bind_ip="$(tailscale ip -4 2>/dev/null | head -n 1)"
fi
[[ -n "${bind_ip}" ]] || usage

relay_host="${3:-}"
if [[ -z "${relay_host}" ]] && command -v jq >/dev/null 2>&1; then
  tailscale_status="$(tailscale status --json 2>/dev/null || true)"
  candidate_host="$(printf '%s' "${tailscale_status}" | jq -r '.Self.DNSName // empty' 2>/dev/null)"
  candidate_host="${candidate_host%.}"
  if [[ -n "${candidate_host}" ]] && printf '%s' "${tailscale_status}" | jq -e \
    --arg host "${candidate_host}" 'any(.CertDomains[]?; . == $host)' >/dev/null 2>&1; then
    relay_host="${candidate_host}"
  fi
  unset tailscale_status candidate_host
fi
relay_host="${relay_host:-${bind_ip}}"

tls_port=8443
tls_backend_port=13000
if [[ "${relay_host}" == *.ts.net ]]; then
  tls_host="${relay_host}"
  relay_url="wss://${relay_host}:${tls_port}"
  pairing_url="wss://${relay_host}:${tls_port}/pair"
  media_base_url="https://${relay_host}:${tls_port}/media"
  cors_origins="https://${relay_host}:${tls_port}"
else
  tls_host=""
  relay_url="ws://${relay_host}:3000"
  pairing_url="ws://${relay_host}:5000/pair"
  media_base_url="http://${relay_host}:3000/media"
  cors_origins="http://${relay_host}:3000"
fi

if [[ -e "${ENV_FILE}" ]]; then
  echo "Refusing to overwrite ${ENV_FILE}" >&2
  exit 1
fi

command -v openssl >/dev/null 2>&1 || {
  echo "openssl is required" >&2
  exit 1
}

umask 077
relay_key="$(openssl rand -hex 32)"
git_hmac="$(openssl rand -hex 32)"
postgres_password="$(openssl rand -hex 32)"
redis_password="$(openssl rand -hex 32)"
s3_access_key="$(openssl rand -hex 16)"
s3_secret_key="$(openssl rand -hex 32)"

cat >"${ENV_FILE}" <<EOF
BUZZ_IMAGE=ghcr.io/block/buzz@sha256:a2b59030b29242adb0783a05cbabd63f51518fdfe7b724845a68f77adab7e1f9
BUZZ_PAIRING_PROXY_IMAGE=nginx@sha256:4a73073bd557c65b759505da037898b61f1be6cbcc3c2c3aeac22d2a470c1752
BUZZ_BIND_IP=${bind_ip}
BUZZ_HTTP_PORT=3000
BUZZ_PAIRING_PORT=5000
BUZZ_TLS_HOST=${tls_host}
BUZZ_TLS_PORT=${tls_port}
BUZZ_TLS_BACKEND_PORT=${tls_backend_port}
BUZZ_DOMAIN=${relay_host}
RELAY_URL=${relay_url}
BUZZ_PAIRING_RELAY_URL=${pairing_url}
BUZZ_MEDIA_BASE_URL=${media_base_url}
BUZZ_MEDIA_SERVER_DOMAIN=${relay_host}
BUZZ_CORS_ORIGINS=${cors_origins}
BUZZ_REQUIRE_AUTH_TOKEN=true
BUZZ_REQUIRE_RELAY_MEMBERSHIP=true
BUZZ_ALLOW_NIP_OA_AUTH=true
BUZZ_AUTO_MIGRATE=true
BUZZ_GIT_CONFORMANCE_PROBE=true
RUST_LOG=buzz_relay=info,buzz_db=info,buzz_auth=info,buzz_pubsub=info,tower_http=info
RELAY_OWNER_PUBKEY=${owner,,}
BUZZ_RELAY_PRIVATE_KEY=${relay_key}
BUZZ_GIT_HOOK_HMAC_SECRET=${git_hmac}
POSTGRES_DB=buzz
POSTGRES_USER=buzz
POSTGRES_PASSWORD=${postgres_password}
REDIS_PASSWORD=${redis_password}
BUZZ_S3_ACCESS_KEY=${s3_access_key}
BUZZ_S3_SECRET_KEY=${s3_secret_key}
BUZZ_S3_BUCKET=buzz-media
BUZZ_S3_ADDRESSING_STYLE=path
EOF

chmod 600 "${ENV_FILE}"
unset relay_key git_hmac postgres_password redis_password s3_access_key s3_secret_key
unset tls_host tls_port tls_backend_port relay_url pairing_url media_base_url cors_origins
echo "Created ${ENV_FILE} with mode 0600; secret values were not printed."
echo "Back it up through an encrypted path before starting Buzz."
