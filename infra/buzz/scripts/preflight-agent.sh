#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CITY2_ROOT="$(cd "${ROOT}/../.." && pwd)"
BIN_ROOT="${CITY2_ROOT}/build/bin"
INSTALL_ROOT="${CITY2_INSTALL_ROOT:-/opt/city2}"
ENV_FILE="${1:-}"

fail() {
  echo "agent-preflight: FAIL: $*" >&2
  exit 1
}

[[ -n "${ENV_FILE}" && -f "${ENV_FILE}" ]] ||
  fail "pass an existing agent EnvironmentFile"
[[ "$(stat -c '%a' "${ENV_FILE}")" == "600" ]] ||
  fail "agent EnvironmentFile must have mode 0600"
! grep -q 'CHANGE_ME' "${ENV_FILE}" || fail "agent EnvironmentFile has placeholders"

for tool in sed sha256sum; do
  command -v "${tool}" >/dev/null 2>&1 || fail "${tool} is unavailable"
done

cd "${BIN_ROOT}"
sha256sum -c BINARIES.sha256 >/dev/null || fail "packaged binary checksum mismatch"

value() {
  sed -n "s/^$1=//p" "${ENV_FILE}" | tail -n 1 | sed -e 's/^"//' -e 's/"$//'
}

workdir="$(value BUZZ_AGENT_WORKDIR)"
relay_url="$(value BUZZ_RELAY_URL)"
private_key="$(value BUZZ_PRIVATE_KEY)"
owner="$(value BUZZ_ACP_AGENT_OWNER)"
agent_command="$(value BUZZ_ACP_AGENT_COMMAND)"
mcp_command="$(value BUZZ_ACP_MCP_COMMAND)"
harness="$(value BUZZ_AGENT_HARNESS)"
model="$(value BUZZ_ACP_MODEL)"
initial_mode="$(value INITIAL_AGENT_MODE)"
respond_to="$(value BUZZ_ACP_RESPOND_TO)"
permission_mode="$(value BUZZ_ACP_PERMISSION_MODE)"
auto_publish="$(value BUZZ_ACP_AUTO_PUBLISH_FINAL)"
heartbeat="$(value BUZZ_ACP_HEARTBEAT_INTERVAL)"
agent_count="$(value BUZZ_ACP_AGENTS)"

[[ "${workdir}" == "/srv/city2" && -d "${CITY2_ROOT}" ]] ||
  fail "workdir must be the reviewed /srv/city2 service mount"
[[ "${relay_url}" =~ ^wss?://[^[:space:]]+$ ]] || fail "relay URL is invalid"
[[ "${private_key}" =~ ^[0-9a-f]{64}$ ]] || fail "agent private key is invalid"
[[ "${owner}" =~ ^[0-9a-f]{64}$ ]] || fail "owner public key is invalid"
[[ "${agent_command}" == "${INSTALL_ROOT}/bin/city2-codex-acp-launcher" ]] ||
  fail "unexpected agent command"
[[ -z "${mcp_command}" ]] ||
  fail "first coordinator must not expose a signer-bearing MCP process"
[[ "${harness}" == "pfterminal-chatgpt" ]] ||
  fail "first proof must use the reviewed PfTerminal ChatGPT harness"
[[ "${model}" == "gpt-5.5" ]] ||
  fail "coordinator must use the reviewed direct-tool model"
[[ "${initial_mode}" == "agent-full-access" ]] ||
  fail "Codex must delegate sandboxing to the hardened systemd boundary"
[[ "${respond_to}" == "owner-only" ]] || fail "first proof must be owner-only"
[[ "${permission_mode}" == "dont-ask" ]] ||
  fail "first proof must not bypass permission requests"
[[ "${auto_publish}" == "true" ]] ||
  fail "coordinator final answers must publish through the harness signer"
[[ "${heartbeat}" == "0" ]] || fail "heartbeat must remain disabled"
[[ "${agent_count}" == "1" ]] || fail "first proof must use one agent process"

! grep -Eq '^(OPENROUTER_API_KEY|ANTHROPIC_API_KEY|OPENAI_COMPAT_API_KEY|CODEX_API_KEY|OPENAI_API_KEY)=' "${ENV_FILE}" ||
  fail "provider secret must not be stored in the agent EnvironmentFile"
command -v systemctl >/dev/null 2>&1 || fail "systemd is unavailable"
command -v pfterminal >/dev/null 2>&1 || fail "PfTerminal is unavailable"
pfterminal login status 2>&1 | grep -q 'Logged in using ChatGPT' ||
  fail "PfTerminal is not logged in with ChatGPT"
[[ -s "${HOME}/.codex/auth.json" ]] || fail "PfTerminal ChatGPT auth file is unavailable"

adapter="${CITY2_ROOT}/build/codex-acp/node_modules/.bin/codex-acp"
[[ -x "${adapter}" ]] || fail "pinned codex-acp adapter is not built"
"${adapter}" --version | grep -q '1\.1\.7$' || fail "unexpected codex-acp version"
grep -q '^unset BUZZ_PRIVATE_KEY$' \
  "${ROOT}/agents/bin/city2-codex-acp-launcher" ||
  fail "Codex ACP launcher does not strip the Nostr private key"

unset private_key
echo "agent-preflight: PASS"
echo "  relay=$(printf '%s' "${relay_url}" | sed -E 's#(wss?://[^/:]+).*#\1#')"
echo "  workdir=${workdir}"
echo "  harness=PfTerminal ChatGPT -> pinned codex-acp -> gpt-5.5"
echo "  gate=owner-only; agents=1; heartbeat=off"
echo "No agent, model request, or container was started."
