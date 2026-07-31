#!/usr/bin/env bash
set -euo pipefail

backup_dir="${1:-}"
[[ -n "${backup_dir}" && -d "${backup_dir}" ]] || {
  echo "Usage: ./scripts/verify-backup.sh <backup-directory>" >&2
  exit 2
}

for file in MANIFEST SHA256SUMS postgres.dump minio.tar.gz git.tar.gz redis.tar.gz; do
  [[ -f "${backup_dir}/${file}" ]] || {
    echo "verify-backup: missing ${file}" >&2
    exit 1
  }
done

( cd "${backup_dir}" && sha256sum -c SHA256SUMS >/dev/null )
for archive in minio.tar.gz git.tar.gz redis.tar.gz; do
  tar -tzf "${backup_dir}/${archive}" >/dev/null
done

if docker info >/dev/null 2>&1; then
  DOCKER=(docker)
elif sudo -n docker info >/dev/null 2>&1; then
  DOCKER=(sudo -n docker)
else
  echo "verify-backup: Docker daemon access is unavailable" >&2
  exit 1
fi

"${DOCKER[@]}" run --rm -i postgres:17-alpine \
  pg_restore --list <"${backup_dir}/postgres.dump" >/dev/null

echo "verify-backup: PASS"
echo "  checksums=valid"
echo "  postgres=catalog-readable"
echo "  volume-archives=readable"
