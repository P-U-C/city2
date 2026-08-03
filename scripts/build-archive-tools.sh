#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION=1.3.1
SHA256=bdc69c09cbdd6cf8b1f333d372a1f58247b3a33146406333e30c0f26e8f51377
URL="https://github.com/FiloSottile/age/releases/download/v${VERSION}/age-v${VERSION}-linux-amd64.tar.gz"
TARGET="${ROOT}/build/archive-tools"
archive="$(mktemp /tmp/city2-age.XXXXXX.tar.gz)"
trap 'rm -f "${archive}"' EXIT
curl -fsSL "${URL}" -o "${archive}"
printf '%s  %s\n' "${SHA256}" "${archive}" | sha256sum -c -
mkdir -p "${TARGET}"
tar -xzf "${archive}" -C "${TARGET}" --strip-components=1 age/age age/age-keygen
"${TARGET}/age" --version | grep -Fx "v${VERSION}"
"${TARGET}/age-keygen" --version | grep -Fx "v${VERSION}"
