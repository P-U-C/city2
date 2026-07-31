#!/usr/bin/env bash
set -euo pipefail

DEST="${CITY2_AGENT_CREDENTIAL_PATH:-/run/city2/provider.key}"

case "${DEST}" in
  /run/city2/*|/tmp/city2-credential-test/*) ;;
  *)
    echo "clear-agent-credential: refusing unexpected path ${DEST}" >&2
    exit 1
    ;;
esac

if sudo test -e "${DEST}"; then
  sudo rm -f -- "${DEST}"
  echo "clear-agent-credential: removed RAM-backed credential"
else
  echo "clear-agent-credential: credential is already absent"
fi
