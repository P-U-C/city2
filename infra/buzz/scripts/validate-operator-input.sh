#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INPUT="${1:-}"

fail() {
  echo "operator-input: FAIL: $*" >&2
  exit 1
}

[[ -n "${INPUT}" && -f "${INPUT}" ]] ||
  fail "pass a filled copy of OPERATOR-INPUT.example"

if grep -Eq '^[A-Z0-9_]*(PRIVATE|SECRET|TOKEN|PASSWORD|MNEMONIC|SEED|API_KEY)[A-Z0-9_]*=' "${INPUT}"; then
  fail "secret-bearing fields are forbidden"
fi
if grep -Eq '(sk-[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9_]{12,}|xox[baprs]-)' "${INPUT}"; then
  fail "the file appears to contain a credential"
fi

value() {
  sed -n "s/^$1=//p" "${INPUT}" | tail -n 1
}

name="$(value CITY2_PROJECT_NAME)"
slug="$(value CITY2_PROJECT_SLUG)"
path="$(value CITY2_PROJECT_PATH)"
owner_input="$(value CITY2_OWNER_PUBLIC_KEY)"
relay_mode="$(value CITY2_RELAY_MODE)"
first_request="$(value CITY2_FIRST_REQUEST)"
provider="$(value CITY2_MODEL_PROVIDER)"
model="$(value CITY2_MODEL_ID)"
public_hostname="$(value CITY2_PUBLIC_HOSTNAME)"

[[ -n "${name}" && "${name}" != *[$'\n\r']* ]] || fail "project name is empty"
[[ "${slug}" =~ ^[a-z0-9][a-z0-9-]*$ ]] || fail "project slug is invalid"
[[ "${path}" == /* && -d "${path}" ]] || fail "project path is not an existing absolute directory"
owner_hex="$("${ROOT}/scripts/normalize-owner-pubkey.py" "${owner_input}")" ||
  fail "owner public key is invalid"
[[ "${relay_mode}" == "tailscale" ]] || fail "first proof must use tailscale"
[[ -n "${first_request}" ]] || fail "first read-only request is empty"
[[ "${provider}" == "openrouter" ]] || fail "prepared first agent currently supports openrouter"
[[ -n "${model}" && "${model}" != *[[:space:]\"\\]* ]] || fail "model ID is invalid"
[[ -z "${public_hostname}" ]] || fail "public hostname must remain blank for the first proof"

fingerprint="${owner_hex:0:8}…${owner_hex: -8}"
unset owner_hex owner_input

echo "operator-input: PASS"
echo "  project=${name} (${slug})"
echo "  path=${path}"
echo "  owner=${fingerprint}"
echo "  relay=tailscale"
echo "  model=${provider}/${model}"
echo "  first-request=present"
echo "No secrets, keys, services, containers, or provider requests were created."
