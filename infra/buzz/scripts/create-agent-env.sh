#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CITY2_ROOT="$(cd "${ROOT}/../.." && pwd)"
ADMIN="${CITY2_ROOT}/build/bin/buzz-admin"
INSTALL_ROOT="${CITY2_INSTALL_ROOT:-/opt/city2}"

usage() {
  cat >&2 <<'EOF'
Usage:
  ./scripts/create-agent-env.sh \
    <output-env> <display-name> <owner-pubkey-hex> \
    <relay-ws-url> <workdir>

Creates a mode-0600 agent EnvironmentFile plus <output-env>.pub. The generated
private Nostr key is written only to the EnvironmentFile and is never printed.
The full public key is written to the .pub file; stdout shows only a fingerprint.

The runtime is the pinned Codex ACP adapter using the host's existing PfTerminal
ChatGPT login. systemd exposes only the ChatGPT auth file as a private runtime
credential; the service cannot access PfTerminal's vault. No provider API key
is stored in this file.
EOF
  exit 2
}

[[ "$#" -eq 5 ]] || usage

output="$1"
display_name="$2"
owner_input="$3"
relay_url="$4"
workdir="$5"
pub_file="${output}.pub"

owner="$("${ROOT}/scripts/normalize-owner-pubkey.py" "${owner_input}")" || usage
unset owner_input
[[ "${relay_url}" =~ ^wss?://[^[:space:]]+$ ]] || usage
[[ "${workdir}" == /* && "${workdir}" != *[[:space:]]* ]] || usage
[[ "${workdir}" == "/srv/city2" && -d "${CITY2_ROOT}" ]] || {
  echo "create-agent-env: workdir does not exist" >&2
  exit 1
}
[[ -n "${display_name}" && "${display_name}" != *[$'\n\r"\\']* ]] || usage
[[ -x "${ADMIN}" ]] || {
  echo "create-agent-env: missing pinned buzz-admin" >&2
  exit 1
}
[[ ! -e "${output}" && ! -e "${pub_file}" ]] || {
  echo "create-agent-env: refusing to overwrite existing identity files" >&2
  exit 1
}

install -d -m 0700 "$(dirname "${output}")"
umask 077

key_output="$("${ADMIN}" generate-key)"
public_key="$(printf '%s\n' "${key_output}" | sed -n 's/^Public key:[[:space:]]*//p')"
private_key="$(printf '%s\n' "${key_output}" | sed -n 's/^Secret key:[[:space:]]*//p')"
unset key_output

[[ "${public_key}" =~ ^[0-9a-f]{64}$ ]] || {
  unset private_key
  echo "create-agent-env: invalid generated public key" >&2
  exit 1
}
[[ "${private_key}" =~ ^[0-9a-f]{64}$ ]] || {
  unset private_key
  echo "create-agent-env: invalid generated private key" >&2
  exit 1
}

cat >"${output}" <<EOF
BUZZ_AGENT_WORKDIR=${workdir}
BUZZ_RELAY_URL=${relay_url}
BUZZ_PRIVATE_KEY=${private_key}
BUZZ_ACP_AGENT_OWNER=${owner}
BUZZ_ACP_DISPLAY_NAME="${display_name}"
BUZZ_ACP_TEXT_MENTION="${display_name}"
BUZZ_ACP_FOLLOW_OWN_THREADS=true
BUZZ_ACP_AGENT_COMMAND=${INSTALL_ROOT}/bin/city2-codex-acp-launcher
BUZZ_ACP_AGENT_ARGS=
BUZZ_ACP_MCP_COMMAND=
BUZZ_AGENT_HARNESS=pfterminal-chatgpt
BUZZ_ACP_MODEL=gpt-5.5
INITIAL_AGENT_MODE=agent-full-access
NO_BROWSER=1
BUZZ_ACP_SYSTEM_PROMPT_FILE=${INSTALL_ROOT}/prompts/coordinator.md
BUZZ_ACP_RESPOND_TO=owner-only
BUZZ_ACP_ALLOWED_RESPOND_TO=owner-only
BUZZ_ACP_SUBSCRIBE=mentions
BUZZ_ACP_AGENTS=1
BUZZ_ACP_LAZY_POOL=true
BUZZ_ACP_DEDUP=queue
BUZZ_ACP_MULTIPLE_EVENT_HANDLING=queue
BUZZ_ACP_PERMISSION_MODE=dont-ask
BUZZ_ACP_AUTO_PUBLISH_FINAL=true
BUZZ_ACP_HEARTBEAT_INTERVAL=0
BUZZ_ACP_CONTEXT_MESSAGE_LIMIT=20
BUZZ_ACP_MAX_TURNS_PER_SESSION=20
BUZZ_ACP_IDLE_TIMEOUT=300
BUZZ_ACP_MAX_TURN_DURATION=1800
BUZZ_ACP_NO_MEMORY=true
EOF
chmod 0600 "${output}"
printf '%s\n' "${public_key}" >"${pub_file}"
chmod 0644 "${pub_file}"

fingerprint="${public_key:0:8}…${public_key: -8}"
unset private_key public_key
echo "Created agent identity ${fingerprint}."
echo "Private key: ${output} (mode 0600; value not printed)"
echo "Public key: ${pub_file} (use command substitution when adding membership)"
