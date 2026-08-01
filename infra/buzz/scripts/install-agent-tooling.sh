#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CITY2_ROOT="$(cd "${ROOT}/../.." && pwd)"
BIN_ROOT="${CITY2_ROOT}/build/bin"
ADAPTER_ROOT="${CITY2_ROOT}/build/codex-acp"
INSTALL_ROOT="${CITY2_INSTALL_ROOT:-/opt/city2}"

case "${INSTALL_ROOT}" in
  /opt/city2|/tmp/city2-install-test/*) ;;
  *)
    echo "install-agent-tooling: refusing unsafe install root ${INSTALL_ROOT}" >&2
    exit 1
    ;;
esac

cd "${BIN_ROOT}"
sha256sum -c BINARIES.sha256 >/dev/null
[[ -x "${ADAPTER_ROOT}/node_modules/.bin/codex-acp" ]] || {
  echo "Pinned codex-acp adapter is not built; run ./scripts/build-agent-adapter.sh" >&2
  exit 1
}
"${ADAPTER_ROOT}/node_modules/.bin/codex-acp" --version | grep -q '1\.1\.7$'

sudo install -d -m 0755 \
  "${INSTALL_ROOT}/bin" \
  "${INSTALL_ROOT}/lib/codex-acp" \
  "${INSTALL_ROOT}/prompts" \
  /srv/city2
for binary in buzz buzz-acp buzz-agent buzz-dev-mcp buzz-admin; do
  sudo install -o root -g root -m 0755 "${BIN_ROOT}/${binary}" "${INSTALL_ROOT}/bin/${binary}"
done
sudo rm -rf -- "${INSTALL_ROOT}/lib/codex-acp/node_modules"
sudo cp -a "${ADAPTER_ROOT}/node_modules" "${INSTALL_ROOT}/lib/codex-acp/"
sudo chown -R root:root "${INSTALL_ROOT}/lib/codex-acp/node_modules"
sudo ln -sfn \
  "${INSTALL_ROOT}/lib/codex-acp/node_modules/.bin/codex-acp" \
  "${INSTALL_ROOT}/bin/codex-acp"
sudo install -o root -g root -m 0755 \
  "${ROOT}/agents/bin/city2-agent-launcher" \
  "${INSTALL_ROOT}/bin/city2-agent-launcher"
sudo install -o root -g root -m 0755 \
  "${ROOT}/agents/bin/city2-codex-acp-launcher" \
  "${INSTALL_ROOT}/bin/city2-codex-acp-launcher"
sudo install -o root -g root -m 0644 \
  "${ROOT}/agents/prompts/coordinator.md" \
  "${INSTALL_ROOT}/prompts/coordinator.md"
sudo install -o root -g root -m 0644 \
  "${ROOT}/agents/systemd/city2-buzz-agent@.service" \
  /etc/systemd/system/city2-buzz-agent@.service
sudo systemctl daemon-reload

echo "Installed pinned City2 agent tooling, Codex ACP adapter and unit template."
echo "No service was enabled or started."
