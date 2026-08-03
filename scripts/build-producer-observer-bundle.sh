#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUTPUT_ROOT="${CITY2_OBSERVER_BUNDLE_DIR:-${ROOT}/build/producer-observer}"
cd "${ROOT}"
stage="$(mktemp -d /tmp/city2-observer-bundle.XXXXXX)"
trap 'rm -rf "${stage}"' EXIT
bundle="${stage}/ai-infra"

PYTHONPATH="${ROOT}/src" python3 - <<'PY'
import json
from pathlib import Path
from city2core.model import digest_profile

root = Path("config")
contract = json.loads((root / "producer-pilot.ai-infra.json").read_text())
agent = json.loads((root / "producer-agent.ai-infra.json").read_text())
assert contract["enabled"] is False
assert agent["enabled"] is False
assert contract["agent_id"] == agent["agent_id"]
assert agent["manifest_sha256"] == digest_profile(
    agent, {"manifest_sha256", "aggregate_version"}
)
PY

install -d \
  "${bundle}/etc/city2/producer" \
  "${bundle}/etc/systemd/system" \
  "${bundle}/opt/city2/lib/city2/scripts" \
  "${bundle}/opt/city2/lib/city2/src" \
  "${bundle}/opt/city2/lib/city2/schemas"
install -m 0644 "${ROOT}/config/producer-pilot.ai-infra.json" \
  "${bundle}/etc/city2/producer/ai-infra.contract.json"
install -m 0644 "${ROOT}/config/producer-agent.ai-infra.json" \
  "${bundle}/etc/city2/producer/ai-infra.agent.json"
install -m 0644 \
  "${ROOT}/infra/producer/ai-infra/city2-producer-observer-ai-infra.service" \
  "${bundle}/etc/systemd/system/city2-producer-observer-ai-infra.service"
install -m 0644 "${ROOT}/infra/producer/ai-infra/REMOVAL.md" \
  "${bundle}/REMOVAL.md"
install -m 0755 "${ROOT}/scripts/observe_producer.py" \
  "${bundle}/opt/city2/lib/city2/scripts/observe_producer.py"
cp -a "${ROOT}/src/city2core" "${bundle}/opt/city2/lib/city2/src/"
cp -a "${ROOT}/schemas/v1" "${bundle}/opt/city2/lib/city2/schemas/"
install -m 0644 "${ROOT}/VERSION" "${bundle}/opt/city2/lib/city2/VERSION"
find "${bundle}" -type d -name __pycache__ -prune -exec rm -rf {} +
if find "${bundle}" -type f \( -name '*.key' -o -name '*.env' -o -name '*.sqlite*' \) \
  -print -quit | grep -q .; then
  echo "bundle: prohibited file" >&2
  exit 1
fi

(
  cd "${bundle}"
  find . -type f ! -name MANIFEST.sha256 -print0 | sort -z |
    xargs -0 sha256sum >MANIFEST.sha256
)
mkdir -p "${OUTPUT_ROOT}"
archive="${OUTPUT_ROOT}/city2-producer-observer-ai-infra.tar.gz"
temporary="${archive}.tmp"
tar --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 --numeric-owner \
  -cf - -C "${stage}" ai-infra | gzip -n >"${temporary}"
mv -f "${temporary}" "${archive}"
printf 'bundle=%s\nsha256=%s\n' "${archive}" "$(sha256sum "${archive}" | cut -d' ' -f1)"
