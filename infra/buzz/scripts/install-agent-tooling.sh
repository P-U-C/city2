#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CITY2_ROOT="$(cd "${ROOT}/../.." && pwd)"
BIN_ROOT="${CITY2_ROOT}/build/bin"
INSTALL_ROOT="${CITY2_INSTALL_ROOT:-/opt/city2}"

cd "${BIN_ROOT}"
sha256sum -c BINARIES.sha256 >/dev/null

sudo install -d -m 0755 "${INSTALL_ROOT}/bin" "${INSTALL_ROOT}/prompts"
for binary in buzz buzz-acp buzz-agent buzz-dev-mcp buzz-admin; do
  sudo install -o root -g root -m 0755 "${BIN_ROOT}/${binary}" "${INSTALL_ROOT}/bin/${binary}"
done
sudo install -o root -g root -m 0755 \
  "${ROOT}/agents/bin/city2-agent-launcher" \
  "${INSTALL_ROOT}/bin/city2-agent-launcher"
sudo install -o root -g root -m 0644 \
  "${ROOT}/agents/prompts/coordinator.md" \
  "${INSTALL_ROOT}/prompts/coordinator.md"
sudo install -o root -g root -m 0644 \
  "${ROOT}/agents/systemd/city2-buzz-agent@.service" \
  /etc/systemd/system/city2-buzz-agent@.service
sudo systemctl daemon-reload

echo "Installed pinned City2 agent tooling and unit template."
echo "No service was enabled or started."
