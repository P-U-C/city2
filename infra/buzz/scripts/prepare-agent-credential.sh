#!/usr/bin/env bash
set -euo pipefail

DEST="${CITY2_AGENT_CREDENTIAL_PATH:-/run/city2/provider.key}"

case "${DEST}" in
  /run/city2/*|/tmp/city2-credential-test/*) ;;
  *)
    echo "prepare-agent-credential: refusing unexpected path ${DEST}" >&2
    exit 1
    ;;
esac

command -v pfterminal >/dev/null 2>&1 || {
  echo "prepare-agent-credential: pfterminal is required" >&2
  exit 1
}
[[ ! -e "${DEST}" ]] || {
  echo "prepare-agent-credential: refusing to overwrite ${DEST}" >&2
  exit 1
}

key="$(pfterminal vault auth-helper provider/openrouter_api_key)"
[[ -n "${key}" ]] || {
  echo "prepare-agent-credential: vault returned an empty credential" >&2
  exit 1
}

cleanup() {
  unset key
}
trap cleanup EXIT

sudo install -d -o root -g root -m 0700 "$(dirname "${DEST}")"
printf '%s' "${key}" | sudo tee "${DEST}" >/dev/null
unset key
sudo chown root:root "${DEST}"
sudo chmod 0400 "${DEST}"

echo "prepare-agent-credential: RAM-backed systemd credential prepared"
echo "prepare-agent-credential: value was not printed"
