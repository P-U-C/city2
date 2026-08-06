#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT}/.env"

fail() {
  echo "private-tls: FAIL: $*" >&2
  exit 1
}

[[ -f "${ENV_FILE}" ]] || fail "missing .env; run bootstrap-env.sh first"
[[ "$(stat -c '%a' "${ENV_FILE}")" == "600" ]] || fail ".env must have mode 0600"
command -v tailscale >/dev/null 2>&1 || fail "tailscale is unavailable"
command -v jq >/dev/null 2>&1 || fail "jq is unavailable"
command -v python3 >/dev/null 2>&1 || fail "python3 is unavailable"

status="$(tailscale status --json 2>/dev/null)" || fail "cannot read Tailscale status"
[[ "$(printf '%s' "${status}" | jq -r '.BackendState // empty')" == "Running" ]] ||
  fail "Tailscale is not running"

dns_name="$(printf '%s' "${status}" | jq -r '.Self.DNSName // empty')"
dns_name="${dns_name%.}"
[[ "${dns_name}" =~ ^[a-zA-Z0-9.-]+\.ts\.net$ ]] ||
  fail "this node has no valid Tailscale HTTPS DNS name"
printf '%s' "${status}" | jq -e --arg host "${dns_name}" \
  'any(.CertDomains[]?; . == $host)' >/dev/null ||
  fail "Tailscale HTTPS certificates are not enabled for this node"
unset status

tls_port="$(sed -n 's/^BUZZ_TLS_PORT=//p' "${ENV_FILE}")"
backend_port="$(sed -n 's/^BUZZ_TLS_BACKEND_PORT=//p' "${ENV_FILE}")"
relay_port="$(sed -n 's/^BUZZ_HTTP_PORT=//p' "${ENV_FILE}")"
pairing_port="$(sed -n 's/^BUZZ_PAIRING_PORT=//p' "${ENV_FILE}")"
tls_port="${tls_port:-8443}"
backend_port="${backend_port:-13000}"
[[ "${tls_port}" =~ ^[0-9]+$ ]] && (( tls_port >= 1 && tls_port <= 65535 )) ||
  fail "BUZZ_TLS_PORT is invalid"
[[ "${backend_port}" =~ ^[0-9]+$ ]] && (( backend_port >= 1 && backend_port <= 65535 )) ||
  fail "BUZZ_TLS_BACKEND_PORT is invalid"
[[ "${relay_port}" =~ ^[0-9]+$ && "${pairing_port}" =~ ^[0-9]+$ ]] ||
  fail "relay or pairing port is invalid"
[[ "${tls_port}" != "80" && "${tls_port}" != "443" ]] ||
  fail "BUZZ_TLS_PORT must be non-default"
[[ "${tls_port}" != "${backend_port}" && "${tls_port}" != "${relay_port}" &&
   "${tls_port}" != "${pairing_port}" && "${backend_port}" != "${relay_port}" &&
   "${backend_port}" != "${pairing_port}" && "${relay_port}" != "${pairing_port}" ]] ||
  fail "relay, pairing, TLS and TLS backend ports must differ"

CITY2_TLS_HOST="${dns_name}" \
CITY2_TLS_PORT="${tls_port}" \
CITY2_TLS_BACKEND_PORT="${backend_port}" \
  "${ROOT}/scripts/tailscale-serve.sh" preflight

old_relay_url="$(sed -n 's/^RELAY_URL=//p' "${ENV_FILE}")"
new_relay_url="wss://${dns_name}:${tls_port}"
[[ -n "${old_relay_url}" ]] || fail "RELAY_URL is empty"

if [[ "${old_relay_url}" != "${new_relay_url}" ]]; then
  "${ROOT}/scripts/migrate-community-host.sh" "${old_relay_url}" "${new_relay_url}"
fi

python3 - "${ENV_FILE}" "${dns_name}" "${tls_port}" "${backend_port}" <<'PY'
import os
from pathlib import Path
import sys
import tempfile

path = Path(sys.argv[1])
host, tls_port, backend_port = sys.argv[2:]
updates = {
    "BUZZ_TLS_HOST": host,
    "BUZZ_TLS_PORT": tls_port,
    "BUZZ_TLS_BACKEND_PORT": backend_port,
    "BUZZ_DOMAIN": host,
    "RELAY_URL": f"wss://{host}:{tls_port}",
    "BUZZ_PAIRING_RELAY_URL": f"wss://{host}:{tls_port}/pair",
    "BUZZ_MEDIA_BASE_URL": f"https://{host}:{tls_port}/media",
    "BUZZ_MEDIA_SERVER_DOMAIN": host,
    "BUZZ_CORS_ORIGINS": f"https://{host}:{tls_port}",
}

lines = path.read_text().splitlines()
seen = set()
output = []
for line in lines:
    key = line.split("=", 1)[0] if "=" in line else ""
    if key in updates:
        if key not in seen:
            output.append(f"{key}={updates[key]}")
            seen.add(key)
    else:
        output.append(line)

insert_at = next(
    (index + 1 for index, line in enumerate(output) if line.startswith("BUZZ_PAIRING_PORT=")),
    0,
)
missing = [
    f"{key}={updates[key]}"
    for key in ("BUZZ_TLS_HOST", "BUZZ_TLS_PORT", "BUZZ_TLS_BACKEND_PORT")
    if key not in seen
]
output[insert_at:insert_at] = missing

fd, raw_tmp = tempfile.mkstemp(prefix=".env.", dir=path.parent)
tmp = Path(raw_tmp)
try:
    with os.fdopen(fd, "w") as handle:
        handle.write("\n".join(output) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)
finally:
    tmp.unlink(missing_ok=True)
PY

unset old_relay_url new_relay_url relay_port pairing_port

echo "private-tls: configured trusted Tailscale HTTPS values without printing the endpoint or secrets"
echo "private-tls: run ./city2 buzz start to apply and verify the private ingress"
