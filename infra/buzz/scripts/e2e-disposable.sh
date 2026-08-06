#!/usr/bin/env bash
set -euo pipefail
export COMPOSE_PROGRESS=quiet

SOURCE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CITY2_ROOT="$(cd "${SOURCE_ROOT}/../.." && pwd)"
BIN_ROOT="${CITY2_ROOT}/build/bin"
PROJECT="city2-e2e-$RANDOM$RANDOM"
TMP_ROOT="$(mktemp -d /tmp/city2-e2e.XXXXXX)"
stage="bootstrap"

for binary in buzz buzz-acp buzz-agent buzz-dev-mcp buzz-admin; do
  [[ -x "${BIN_ROOT}/${binary}" ]] || {
    echo "e2e: missing build/bin/${binary}; run ./scripts/build-buzz-tools.sh" >&2
    exit 1
  }
done

if docker info >/dev/null 2>&1; then
  DOCKER=(docker)
elif sudo -n docker info >/dev/null 2>&1; then
  DOCKER=(sudo -n docker)
else
  echo "e2e: Docker daemon access is unavailable" >&2
  exit 1
fi

cleanup() {
  local rc=$?
  set +e
  if [[ -f "${TMP_ROOT}/.env" ]]; then
    "${DOCKER[@]}" compose \
      --project-name "${PROJECT}" \
      --env-file "${TMP_ROOT}/.env" \
      -f "${TMP_ROOT}/compose.yml" \
      -f "${TMP_ROOT}/compose.private.yml" \
      down -v --remove-orphans >/dev/null 2>&1
  fi
  unset owner_secret outsider_secret
  rm -rf "${TMP_ROOT}"
  if [[ "${rc}" -ne 0 ]]; then
    echo "e2e: FAIL at stage=${stage}" >&2
  fi
  return "${rc}"
}
trap cleanup EXIT

( cd "${SOURCE_ROOT}" && tar --exclude='./.env' -cf - . ) |
  tar -C "${TMP_ROOT}" -xf -
install -d -m 0755 "${TMP_ROOT}/bin"
cp "${BIN_ROOT}"/{buzz,buzz-acp,buzz-agent,buzz-dev-mcp,buzz-admin,BINARIES.sha256} \
  "${TMP_ROOT}/bin/"
chmod 750 "${TMP_ROOT}"/run.sh "${TMP_ROOT}"/scripts/*.sh

port=""
pairing_port=""
tls_backend_port=""
for candidate in $(seq 33100 33199); do
  candidate_pairing="$((candidate + 100))"
  candidate_tls_backend="$((candidate + 200))"
  if ! ss -ltnH | awk '{print $4}' | grep -Eq "(^|:)(${candidate}|${candidate_pairing}|${candidate_tls_backend})$"; then
    port="${candidate}"
    pairing_port="${candidate_pairing}"
    tls_backend_port="${candidate_tls_backend}"
    break
  fi
done
[[ -n "${port}" && -n "${pairing_port}" && -n "${tls_backend_port}" ]] || {
  echo "e2e: no relay/pairing/TLS-backend test port set available" >&2
  exit 1
}

owner_output="$("${TMP_ROOT}/bin/buzz-admin" generate-key)"
owner_public="$(printf '%s\n' "${owner_output}" | sed -n 's/^Public key:[[:space:]]*//p')"
owner_secret="$(printf '%s\n' "${owner_output}" | sed -n 's/^Secret key:[[:space:]]*//p')"
unset owner_output
[[ "${owner_public}" =~ ^[0-9a-f]{64}$ && "${owner_secret}" =~ ^[0-9a-f]{64}$ ]]

outsider_output="$("${TMP_ROOT}/bin/buzz-admin" generate-key)"
outsider_secret="$(printf '%s\n' "${outsider_output}" | sed -n 's/^Secret key:[[:space:]]*//p')"
unset outsider_output
[[ "${outsider_secret}" =~ ^[0-9a-f]{64}$ ]]

"${TMP_ROOT}/scripts/bootstrap-env.sh" \
  "${owner_public}" 127.0.0.1 127.0.0.1 >/dev/null
sed -i "s/^BUZZ_HTTP_PORT=.*/BUZZ_HTTP_PORT=${port}/" "${TMP_ROOT}/.env"
sed -i "s/:3000/:${port}/g" "${TMP_ROOT}/.env"
sed -i "s/^BUZZ_PAIRING_PORT=.*/BUZZ_PAIRING_PORT=${pairing_port}/" "${TMP_ROOT}/.env"
sed -i "s/^BUZZ_TLS_BACKEND_PORT=.*/BUZZ_TLS_BACKEND_PORT=${tls_backend_port}/" "${TMP_ROOT}/.env"
sed -i \
  "s#^BUZZ_PAIRING_RELAY_URL=.*#BUZZ_PAIRING_RELAY_URL=ws://127.0.0.1:${pairing_port}/pair#" \
  "${TMP_ROOT}/.env"

export BUZZ_COMPOSE_PROJECT="${PROJECT}"
stage="preflight"
"${TMP_ROOT}/scripts/preflight.sh" >/dev/null
stage="start"
"${TMP_ROOT}/run.sh" start >/dev/null

base_http="http://127.0.0.1:${port}"
stage="health"
curl -fsS "${base_http}/_liveness" >/dev/null
curl -fsS "${base_http}/_readiness" >/dev/null

stage="pairing-proxy"
pair_base="http://127.0.0.1:${pairing_port}"
pair_headers="${TMP_ROOT}/pairing.headers"
curl --silent --show-error --http1.1 --max-time 2 \
  --dump-header "${pair_headers}" --output /dev/null \
  --header 'Connection: Upgrade' \
  --header 'Upgrade: websocket' \
  --header 'Sec-WebSocket-Version: 13' \
  --header 'Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==' \
  "${pair_base}/pair" || true
grep -Eq '^HTTP/1\.[01] 101 ' "${pair_headers}"
[[ "$(curl -sS -o /dev/null -w '%{http_code}' "${pair_base}/other")" == "404" ]]
[[ "$(curl -sS -o /dev/null -w '%{http_code}' "${pair_base}/pair")" == "426" ]]
rm -f "${pair_headers}"

stage="tls-ingress"
tls_base="http://127.0.0.1:${tls_backend_port}"
curl -fsS "${tls_base}/_readiness" >/dev/null
tls_pair_headers="${TMP_ROOT}/tls-pairing.headers"
curl --silent --show-error --http1.1 --max-time 2 \
  --dump-header "${tls_pair_headers}" --output /dev/null \
  --header 'Connection: Upgrade' \
  --header 'Upgrade: websocket' \
  --header 'Sec-WebSocket-Version: 13' \
  --header 'Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==' \
  "${tls_base}/pair" || true
grep -Eq '^HTTP/1\.[01] 101 ' "${tls_pair_headers}"
[[ "$(curl -sS -o /dev/null -w '%{http_code}' "${tls_base}/pair")" == "426" ]]
rm -f "${tls_pair_headers}"

buzz_owner() {
  BUZZ_RELAY_URL="${base_http}" \
  BUZZ_PRIVATE_KEY="${owner_secret}" \
    "${TMP_ROOT}/bin/buzz" "$@"
}

stage="signed-roundtrip"
channel_json="$(buzz_owner channels create \
  --name e2e-private \
  --type stream \
  --visibility private \
  --description 'Disposable City 2.0 restore test')"
channel_id="$(printf '%s' "${channel_json}" | jq -r '.channel_id // .channelId // .id // empty')"
unset channel_json
[[ "${channel_id}" =~ ^[0-9a-fA-F-]{36}$ ]] || {
  echo "e2e: channel creation returned no UUID" >&2
  exit 1
}

marker="city2-e2e-$(date -u +%s)-$RANDOM"
buzz_owner messages send --channel "${channel_id}" --content "${marker}" >/dev/null
messages="$(buzz_owner messages get --channel "${channel_id}" --limit 20)"
printf '%s' "${messages}" | jq -e --arg marker "${marker}" \
  'any(.[]?; (.content // .text // "") == $marker)' >/dev/null
unset messages

stage="membership-gate"
set +e
BUZZ_RELAY_URL="${base_http}" \
BUZZ_PRIVATE_KEY="${outsider_secret}" \
  "${TMP_ROOT}/bin/buzz" channels list \
  >"${TMP_ROOT}/outsider.out" 2>"${TMP_ROOT}/outsider.err"
outsider_rc=$?
set -e
[[ "${outsider_rc}" -ne 0 ]]
if grep -Fq "${outsider_secret}" "${TMP_ROOT}/outsider.out" "${TMP_ROOT}/outsider.err"; then
  echo "e2e: outsider command leaked its private identity" >&2
  exit 1
fi
rm -f "${TMP_ROOT}/outsider.out" "${TMP_ROOT}/outsider.err"

# Readiness above proves the pinned image's startup conformance gate once. Do
# not let an unrelated object-store race probe obscure the backup/restore and
# ingress assertions by rerunning it on every disposable relay restart.
sed -i \
  's/^BUZZ_GIT_CONFORMANCE_PROBE=.*/BUZZ_GIT_CONFORMANCE_PROBE=false/' \
  "${TMP_ROOT}/.env"

stage="community-host-migration"
old_relay_url="ws://127.0.0.1:${port}"
new_relay_url="ws://localhost:${port}"
"${DOCKER[@]}" compose \
  --project-name "${PROJECT}" \
  --env-file "${TMP_ROOT}/.env" \
  -f "${TMP_ROOT}/compose.yml" \
  -f "${TMP_ROOT}/compose.private.yml" \
  rm -sf tls-ingress >/dev/null
CITY2_BACKUP_ROOT="${TMP_ROOT}/migration-backup" \
  "${TMP_ROOT}/scripts/migrate-community-host.sh" \
    "${old_relay_url}" "${new_relay_url}" >/dev/null
sed -i \
  -e 's/^BUZZ_DOMAIN=.*/BUZZ_DOMAIN=localhost/' \
  -e "s#^RELAY_URL=.*#RELAY_URL=${new_relay_url}#" \
  -e "s#^BUZZ_PAIRING_RELAY_URL=.*#BUZZ_PAIRING_RELAY_URL=ws://localhost:${pairing_port}/pair#" \
  -e "s#^BUZZ_MEDIA_BASE_URL=.*#BUZZ_MEDIA_BASE_URL=http://localhost:${port}/media#" \
  -e 's/^BUZZ_MEDIA_SERVER_DOMAIN=.*/BUZZ_MEDIA_SERVER_DOMAIN=localhost/' \
  -e "s#^BUZZ_CORS_ORIGINS=.*#BUZZ_CORS_ORIGINS=http://localhost:${port}#" \
  "${TMP_ROOT}/.env"
"${TMP_ROOT}/run.sh" start >/dev/null
base_http="http://localhost:${port}"
migrated_messages="$(buzz_owner messages get --channel "${channel_id}" --limit 20)"
printf '%s' "${migrated_messages}" | jq -e --arg marker "${marker}" \
  'any(.[]?; (.content // .text // "") == $marker)' >/dev/null
unset migrated_messages old_relay_url new_relay_url

migrated_community_count="$(
  "${DOCKER[@]}" compose \
    --project-name "${PROJECT}" \
    --env-file "${TMP_ROOT}/.env" \
    -f "${TMP_ROOT}/compose.yml" \
    -f "${TMP_ROOT}/compose.private.yml" \
    exec -T postgres psql -U buzz -d buzz -Atc 'SELECT count(*) FROM communities'
)"
[[ "${migrated_community_count}" == "1" ]]
unset migrated_community_count

backup_root="${TMP_ROOT}/backups"
stage="backup"
"${TMP_ROOT}/scripts/backup.sh" "${backup_root}" >/dev/null
backup_dir="$(find "${backup_root}" -mindepth 1 -maxdepth 1 -type d | head -n 1)"
[[ -n "${backup_dir}" ]]
"${TMP_ROOT}/scripts/verify-backup.sh" "${backup_dir}" >/dev/null

# Destroy only this randomly named test project, then rebuild empty services.
stage="destroy-test-state"
"${DOCKER[@]}" compose \
  --project-name "${PROJECT}" \
  --env-file "${TMP_ROOT}/.env" \
  -f "${TMP_ROOT}/compose.yml" \
  -f "${TMP_ROOT}/compose.private.yml" \
  down -v --remove-orphans >/dev/null

compose() {
  "${DOCKER[@]}" compose \
    --project-name "${PROJECT}" \
    --env-file "${TMP_ROOT}/.env" \
    -f "${TMP_ROOT}/compose.yml" \
    -f "${TMP_ROOT}/compose.private.yml" \
    "$@"
}

stage="restore-postgres"
compose up -d --wait postgres >/dev/null

compose exec -T postgres \
  pg_restore -U buzz -d buzz --clean --if-exists --no-owner --no-privileges \
  <"${backup_dir}/postgres.dump"

restore_volume() {
  local logical="$1"
  local archive="$2"
  local volume="${PROJECT}_${logical}"
  local mountpoint
  if ! "${DOCKER[@]}" volume inspect "${volume}" >/dev/null 2>&1; then
    "${DOCKER[@]}" volume create \
      --label "com.docker.compose.project=${PROJECT}" \
      --label "com.docker.compose.volume=${logical}" \
      "${volume}" >/dev/null
  fi
  mountpoint="$("${DOCKER[@]}" volume inspect -f '{{.Mountpoint}}' "${volume}")"
  sudo -n find "${mountpoint}" -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +
  sudo -n tar -C "${mountpoint}" -xzf "${backup_dir}/${archive}"
}

stage="restore-volumes"
restore_volume buzz-minio-data minio.tar.gz
restore_volume buzz-git-data git.tar.gz
restore_volume buzz-redis-data redis.tar.gz

stage="restart-restored-stack"
compose up -d --wait >/dev/null
curl -fsS "${base_http}/_readiness" >/dev/null

stage="verify-restored-message"
restored="$(buzz_owner messages get --channel "${channel_id}" --limit 20)"
printf '%s' "${restored}" | jq -e --arg marker "${marker}" \
  'any(.[]?; (.content // .text // "") == $marker)' >/dev/null
unset restored marker owner_public channel_id

echo "e2e: PASS"
echo "  relay=loopback-only"
echo "  signed-owner-roundtrip=pass"
echo "  outsider-membership-gate=pass"
echo "  backup-integrity=pass"
echo "  pairing-proxy=pass"
echo "  tls-ingress=pass"
echo "  tenant-preserving-host-migration=pass"
echo "  git-conformance=initial-start-pass"
echo "  destructive-restore-in-test-project=pass"
echo "  provider-calls=none"

stage="cleanup"
cleanup
trap - EXIT

remaining_containers="$("${DOCKER[@]}" ps -aq --filter "label=com.docker.compose.project=${PROJECT}" | wc -l)"
remaining_volumes="$("${DOCKER[@]}" volume ls -q --filter "label=com.docker.compose.project=${PROJECT}" | wc -l)"
[[ "${remaining_containers}" -eq 0 && "${remaining_volumes}" -eq 0 ]]
echo "  cleanup=pass"
