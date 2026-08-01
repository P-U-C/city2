#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE="${ROOT}/infra/buzz/agents/codex-acp"
DEST="${ROOT}/build/codex-acp"

for tool in node npm; do
  command -v "${tool}" >/dev/null 2>&1 || {
    echo "build-agent-adapter: ${tool} is required" >&2
    exit 1
  }
done

[[ "$(node --version)" == v22.* ]] || {
  echo "build-agent-adapter: Node 22 is required" >&2
  exit 1
}

rm -rf "${DEST}"
install -d -m 0755 "${DEST}"
cp "${SOURCE}/package.json" "${SOURCE}/package-lock.json" "${DEST}/"

npm ci \
  --prefix "${DEST}" \
  --omit=dev \
  --ignore-scripts \
  --no-audit \
  --no-fund \
  --silent

version="$("${DEST}/node_modules/.bin/codex-acp" --version)"
[[ "${version}" == "@agentclientprotocol/codex-acp 1.1.7" ]] || {
  echo "build-agent-adapter: unexpected adapter version" >&2
  exit 1
}

printf '%s  %s\n' \
  "$(sha256sum "${SOURCE}/package-lock.json" | cut -d' ' -f1)" \
  "package-lock.json" >"${DEST}/SOURCE.sha256"

echo "build-agent-adapter: PASS (${version})"
