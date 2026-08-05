#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

usage() {
  cat >&2 <<'EOF'
Usage:
  sync-agent-routing.sh <agent-env> <output-toml> <channel-name> [channel-name ...]

Resolves exact member-channel names through the configured Buzz identity and
atomically regenerates the scoped ACP routing file. No channel IDs or key
material are printed.
EOF
  exit 2
}

[[ "$#" -ge 3 ]] || usage
env_file="$1"
output="$2"
shift 2

[[ "${env_file}" == /* && -f "${env_file}" && ! -L "${env_file}" ]] || usage
[[ "${output}" == /* && ! -L "${output}" ]] || usage
for channel_name in "$@"; do
  [[ -n "${channel_name}" && "${channel_name}" != *$'\n'* && "${channel_name}" != *$'\r'* ]] || usage
done

set -a
# shellcheck disable=SC1090
source "${env_file}"
set +a

: "${BUZZ_PRIVATE_KEY:?agent env is missing BUZZ_PRIVATE_KEY}"
: "${BUZZ_ACP_AGENT_OWNER:?agent env is missing BUZZ_ACP_AGENT_OWNER}"
: "${BUZZ_ACP_DISPLAY_NAME:?agent env is missing BUZZ_ACP_DISPLAY_NAME}"

buzz_bin="${CITY2_BUZZ_BIN:-buzz}"
[[ "${buzz_bin}" == /* && -x "${buzz_bin}" ]] || {
  echo "sync-agent-routing: CITY2_BUZZ_BIN must be an absolute executable path" >&2
  exit 1
}
command -v jq >/dev/null || {
  echo "sync-agent-routing: jq is required" >&2
  exit 1
}

output_dir="$(dirname "${output}")"
[[ -d "${output_dir}" ]] || install -d -m 0755 "${output_dir}"
tmp_dir="$(mktemp -d "${output_dir}/.city2-routing.XXXXXX")"
cleanup() {
  rm -rf -- "${tmp_dir}"
}
trap cleanup EXIT
umask 077

"${buzz_bin}" --format json channels list --member >"${tmp_dir}/channels.json"

channel_ids=()
for channel_name in "$@"; do
  channel_id="$({
    jq -er --arg name "${channel_name}" '
      [.[] | select(.name == $name) | .channel_id]
      | if length == 1 then .[0]
        else error("expected exactly one member channel named " + $name)
        end
    ' "${tmp_dir}/channels.json"
  })" || {
    echo "sync-agent-routing: cannot resolve exact member channel '${channel_name}'" >&2
    exit 1
  }
  channel_ids+=("${channel_id}")
done

"${ROOT}/scripts/create-agent-routing.sh" \
  "${tmp_dir}/buzz-acp.toml" \
  "${BUZZ_ACP_AGENT_OWNER}" \
  "${BUZZ_ACP_DISPLAY_NAME}" \
  "${channel_ids[@]}" >/dev/null

chmod 0644 "${tmp_dir}/buzz-acp.toml"
mv -f -- "${tmp_dir}/buzz-acp.toml" "${output}"
echo "Synced agent routing: ${#channel_ids[@]} exact member channel(s)."
