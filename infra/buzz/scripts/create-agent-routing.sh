#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

usage() {
  cat >&2 <<'EOF'
Usage:
  create-agent-routing.sh <output-toml> <owner-npub-or-hex> \
    <agent-display-name> <channel-uuid> [channel-uuid ...]

Creates a public Buzz ACP routing file. It subscribes only to the declared
channels and admits exact owner-authored textual @mentions when a client omits
the structured p tag. The patched harness separately accepts an owner thread
continuation only when that exact channel/thread already contains a valid
coordinator-signed reply.
EOF
  exit 2
}

[[ "$#" -ge 4 ]] || usage
output="$1"
owner_input="$2"
display_name="$3"
shift 3

[[ "${output}" == /* ]] || usage
[[ ! -e "${output}" ]] || {
  echo "create-agent-routing: refusing to overwrite ${output}" >&2
  exit 1
}
[[ -n "${display_name}" && "${display_name}" != *[$'\n\r"\x27\\']* ]] || usage
owner="$("${ROOT}/scripts/normalize-owner-pubkey.py" "${owner_input}")" || usage
unset owner_input

channels=()
for channel in "$@"; do
  [[ "${channel}" =~ ^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$ ]] || usage
  channels+=("${channel,,}")
done

output_dir="$(dirname "${output}")"
if [[ ! -d "${output_dir}" ]]; then
  install -d -m 0755 "${output_dir}"
fi
umask 022
{
  printf '[[rules]]\n'
  printf 'name = "owner-text-mention"\n'
  printf 'channels = ['
  for index in "${!channels[@]}"; do
    (( index == 0 )) || printf ', '
    printf '"%s"' "${channels[index]}"
  done
  printf ']\n'
  printf 'kinds = [9]\n'
  printf 'require_mention = false\n'
  printf 'filter = '\''author == "%s" && str_starts_with(content, "@%s")'\''\n' \
    "${owner}" "${display_name}"
  printf 'prompt_tag = "owner-text-mention"\n'
} >"${output}"
chmod 0644 "${output}"

unset owner
echo "Created agent routing config: ${output}"
echo "Channels: ${#channels[@]}; trigger: exact owner @${display_name}"
