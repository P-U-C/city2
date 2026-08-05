#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMMIT="10d5a26414dc90dc89fd27de74b21e105d4fa622"
REPO="https://github.com/block/buzz.git"
PATCH="${ROOT}/infra/buzz/patches/0001-auto-publish-final-answer.patch"
OUT="${ROOT}/build/bin"
WORK="$(mktemp -d /tmp/city2-buzz-build.XXXXXX)"

cleanup() {
  rm -rf "${WORK}"
}
trap cleanup EXIT

for tool in git cargo sha256sum; do
  command -v "${tool}" >/dev/null 2>&1 || {
    echo "build-buzz-tools: ${tool} is required" >&2
    exit 1
  }
done

git clone --filter=blob:none "${REPO}" "${WORK}/buzz"
git -C "${WORK}/buzz" checkout --detach "${COMMIT}"
[[ "$(git -C "${WORK}/buzz" rev-parse HEAD)" == "${COMMIT}" ]]
git -C "${WORK}/buzz" apply --check "${PATCH}"
git -C "${WORK}/buzz" apply "${PATCH}"

cargo build \
  --manifest-path "${WORK}/buzz/Cargo.toml" \
  --release \
  --locked \
  -p buzz-cli \
  -p buzz-acp \
  -p buzz-agent \
  -p buzz-dev-mcp \
  -p buzz-admin

install -d -m 0755 "${OUT}"
for binary in buzz buzz-acp buzz-agent buzz-dev-mcp buzz-admin; do
  install -m 0755 "${WORK}/buzz/target/release/${binary}" "${OUT}/${binary}"
done

(
  cd "${OUT}"
  sha256sum buzz buzz-acp buzz-agent buzz-dev-mcp buzz-admin > BINARIES.sha256
)

echo "build-buzz-tools: built pinned commit ${COMMIT}"
echo "build-buzz-tools: output=${OUT}"
