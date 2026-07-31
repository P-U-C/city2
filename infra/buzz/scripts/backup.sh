#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST_ROOT="${1:-${CITY2_BACKUP_ROOT:-${HOME}/backups/city2}}"
PROJECT="${BUZZ_COMPOSE_PROJECT:-city2-buzz}"

[[ "${PROJECT}" =~ ^[a-z0-9][a-z0-9_-]*$ ]] || {
  echo "backup: invalid Compose project name" >&2
  exit 2
}
[[ -f "${ROOT}/.env" ]] || {
  echo "backup: missing ${ROOT}/.env" >&2
  exit 1
}

if docker info >/dev/null 2>&1; then
  DOCKER=(docker)
elif sudo -n docker info >/dev/null 2>&1; then
  DOCKER=(sudo -n docker)
else
  echo "backup: Docker daemon access is unavailable" >&2
  exit 1
fi

compose() {
  "${DOCKER[@]}" compose \
    --project-name "${PROJECT}" \
    --env-file "${ROOT}/.env" \
    -f "${ROOT}/compose.yml" \
    -f "${ROOT}/compose.private.yml" \
    "$@"
}

for service in relay postgres redis minio; do
  compose ps --status running --services | grep -Fxq "${service}" || {
    echo "backup: ${service} is not running" >&2
    exit 1
  }
done

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
dest="${DEST_ROOT}/${stamp}"
install -d -m 0700 "${dest}"

restart_required=false
restart_services() {
  if [[ "${restart_required}" == "true" ]]; then
    compose up -d --wait redis minio >/dev/null 2>&1 || true
    compose up -d --wait relay >/dev/null 2>&1 || true
  fi
}
trap restart_services EXIT

compose stop relay >/dev/null
restart_required=true

postgres_user="$(sed -n 's/^POSTGRES_USER=//p' "${ROOT}/.env")"
postgres_db="$(sed -n 's/^POSTGRES_DB=//p' "${ROOT}/.env")"
[[ -n "${postgres_user}" && -n "${postgres_db}" ]] || {
  echo "backup: PostgreSQL identity is incomplete" >&2
  exit 1
}

compose exec -T postgres \
  pg_dump -U "${postgres_user}" -d "${postgres_db}" -Fc >"${dest}/postgres.dump"

compose stop minio redis >/dev/null

archive_volume() {
  local logical="$1"
  local output="$2"
  local volume="${PROJECT}_${logical}"
  local mountpoint
  mountpoint="$("${DOCKER[@]}" volume inspect -f '{{.Mountpoint}}' "${volume}")"
  sudo -n tar -C "${mountpoint}" -czf - . |
    dd of="${dest}/${output}" status=none
}

archive_volume buzz-minio-data minio.tar.gz
archive_volume buzz-git-data git.tar.gz
archive_volume buzz-redis-data redis.tar.gz

cat >"${dest}/MANIFEST" <<EOF
created_at=${stamp}
compose_project=${PROJECT}
source_commit=10d5a26414dc90dc89fd27de74b21e105d4fa622
relay_image=ghcr.io/block/buzz@sha256:a2b59030b29242adb0783a05cbabd63f51518fdfe7b724845a68f77adab7e1f9
postgres_format=custom
env_included=false
EOF

( cd "${dest}" && sha256sum MANIFEST postgres.dump minio.tar.gz git.tar.gz redis.tar.gz > SHA256SUMS )
chmod 0600 "${dest}"/*

compose up -d --wait redis minio >/dev/null
compose up -d --wait relay >/dev/null
restart_required=false
trap - EXIT

echo "backup: created ${dest}"
echo "backup: .env and human identity keys are intentionally excluded; back them up separately through an encrypted path"
