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
bind-ip. This creates .env with mode 0600 and prints no secret values.
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

relay_host="${3:-${bind_ip}}"

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
BUZZ_DOMAIN=${relay_host}
RELAY_URL=ws://${relay_host}:3000
BUZZ_PAIRING_RELAY_URL=ws://${relay_host}:5000/pair
BUZZ_MEDIA_BASE_URL=http://${relay_host}:3000/media
BUZZ_MEDIA_SERVER_DOMAIN=${relay_host}
BUZZ_CORS_ORIGINS=http://${relay_host}:3000
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
echo "Created ${ENV_FILE} with mode 0600; secret values were not printed."
echo "Back it up through an encrypted path before starting Buzz."
