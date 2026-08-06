#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT="${BUZZ_COMPOSE_PROJECT:-city2-buzz}"
REPAIR_EMPTY_TARGET=false

usage() {
  echo "Usage: migrate-community-host.sh [--repair-empty-target] <old-relay-url> <new-relay-url>" >&2
  exit 2
}

if [[ "${1:-}" == "--repair-empty-target" ]]; then
  REPAIR_EMPTY_TARGET=true
  shift
fi
[[ "$#" -eq 2 ]] || usage
OLD_URL="$1"
NEW_URL="$2"
[[ "${PROJECT}" =~ ^[a-z0-9][a-z0-9_-]*$ ]] || {
  echo "host-migration: invalid Compose project name" >&2
  exit 2
}
[[ -f "${ROOT}/.env" ]] || {
  echo "host-migration: missing .env" >&2
  exit 1
}

mapfile -t authorities < <(python3 - "${OLD_URL}" "${NEW_URL}" <<'PY'
import sys
from urllib.parse import urlsplit

for raw in sys.argv[1:]:
    parsed = urlsplit(raw)
    if parsed.scheme not in {"ws", "wss"} or parsed.hostname is None:
        raise SystemExit("host-migration: relay URLs must use ws:// or wss://")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise SystemExit("host-migration: relay URLs must not contain credentials or query data")
    if parsed.path not in {"", "/"}:
        raise SystemExit("host-migration: relay URLs must not contain a path")
    port = parsed.port
    host = parsed.hostname.lower()
    if ":" in host:
        host = f"[{host}]"
    # Match Buzz's normalize_host exactly: both conventional web ports are
    # stripped from tenant authorities regardless of WebSocket scheme.
    print(host if port is None or port in {80, 443} else f"{host}:{port}")
PY
)
[[ "${#authorities[@]}" -eq 2 ]] || exit 1
OLD_HOST="${authorities[0]}"
NEW_HOST="${authorities[1]}"
[[ "${OLD_HOST}" != "${NEW_HOST}" ]] || {
  echo "host-migration: community authority is already current"
  exit 0
}

if docker info >/dev/null 2>&1; then
  DOCKER=(docker)
elif sudo -n docker info >/dev/null 2>&1; then
  DOCKER=(sudo -n docker)
else
  echo "host-migration: Docker daemon access is unavailable" >&2
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

compose ps --status running --services | grep -Fxq postgres || {
  echo "host-migration: PostgreSQL must be running under the old configuration" >&2
  exit 1
}

if [[ "${CITY2_HOST_MIGRATION_SKIP_BACKUP:-false}" != "true" ]]; then
  CITY2_BACKUP_ALLOW_MISSING_TLS_INGRESS=true "${ROOT}/scripts/backup.sh"
elif [[ "${PROJECT}" != *-e2e-* ]]; then
  echo "host-migration: backup bypass is allowed only for disposable E2E projects" >&2
  exit 1
fi

tls_ingress_was_running=false
if compose ps --status running --services | grep -Fxq tls-ingress; then
  tls_ingress_was_running=true
fi
restart_old=false
serve_route_was_present=false
restart_on_failure() {
  local status=$?
  local restart_failed=false
  trap - EXIT
  if [[ "${restart_old}" == "true" ]]; then
    restart_services=(relay)
    if [[ "${tls_ingress_was_running}" == "true" ]]; then
      restart_services+=(tls-ingress)
    fi
    compose up -d --wait "${restart_services[@]}" >/dev/null 2>&1 || restart_failed=true
    if [[ "${serve_route_was_present}" == "true" ]]; then
      "${ROOT}/scripts/tailscale-serve.sh" apply >/dev/null 2>&1 || restart_failed=true
    fi
    if [[ "${restart_failed}" == "true" ]]; then
      echo "host-migration: CRITICAL: old relay or private TLS route restart failed" >&2
      status=1
    fi
  fi
  exit "${status}"
}
trap restart_on_failure EXIT

restart_old=true
configured_relay_url="$(sed -n 's/^RELAY_URL=//p' "${ROOT}/.env")"
if [[ "${tls_ingress_was_running}" == "true" && "${configured_relay_url}" == wss://* ]]; then
  if "${ROOT}/scripts/tailscale-serve.sh" status >/dev/null 2>&1; then
    serve_route_was_present=true
  fi
  "${ROOT}/scripts/tailscale-serve.sh" remove >/dev/null
fi
unset configured_relay_url
compose stop relay >/dev/null
if [[ "${tls_ingress_was_running}" == "true" ]]; then
  compose stop tls-ingress >/dev/null
fi

compose exec -T postgres sh -lc \
  'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v old_host="$1" -v new_host="$2" -v repair="$3"' \
  sh "${OLD_HOST}" "${NEW_HOST}" "${REPAIR_EMPTY_TARGET}" <<'SQL'
BEGIN;
LOCK TABLE communities IN ACCESS EXCLUSIVE MODE;
SET LOCAL city2.old_host = :'old_host';
SET LOCAL city2.new_host = :'new_host';
SET LOCAL city2.repair = :'repair';

DO $city2$
DECLARE
  source_id uuid;
  target_id uuid;
BEGIN
  SELECT id INTO source_id
  FROM communities
  WHERE lower(host) = lower(current_setting('city2.old_host'));
  IF source_id IS NULL THEN
    RAISE EXCEPTION 'source community is missing';
  END IF;

  SELECT id INTO target_id
  FROM communities
  WHERE lower(host) = lower(current_setting('city2.new_host'));
  IF target_id IS NOT NULL THEN
    IF NOT current_setting('city2.repair')::boolean THEN
      RAISE EXCEPTION 'target community already exists';
    END IF;
    IF EXISTS (SELECT 1 FROM channels WHERE community_id = target_id)
       OR EXISTS (SELECT 1 FROM events WHERE community_id = target_id AND kind <> 13534)
       OR EXISTS (
         SELECT 1
         FROM audit_log target_audit
         WHERE target_audit.community_id = target_id
           AND (
             target_audit.action <> 'event_created'
             OR NOT EXISTS (
               SELECT 1 FROM events target_event
               WHERE target_event.community_id = target_id
                 AND target_event.kind = 13534
                 AND target_audit.object_id = encode(target_event.id, 'hex')
             )
           )
       )
       OR (SELECT count(*) FROM audit_log WHERE community_id = target_id)
          <> (SELECT count(*) FROM events WHERE community_id = target_id)
       OR EXISTS (
         SELECT 1 FROM relay_members
         WHERE community_id = target_id AND role <> 'owner'
       )
       OR (SELECT count(*) FROM relay_members WHERE community_id = target_id) > 1
       OR EXISTS (
         SELECT 1
         FROM relay_members target_owner
         WHERE target_owner.community_id = target_id
           AND NOT EXISTS (
             SELECT 1 FROM relay_members source_owner
             WHERE source_owner.community_id = source_id
               AND source_owner.pubkey = target_owner.pubkey
               AND source_owner.role = 'owner'
           )
       ) THEN
      RAISE EXCEPTION 'target community contains non-bootstrap state';
    END IF;
    DELETE FROM audit_log
    WHERE community_id = target_id AND action = 'event_created';
    DELETE FROM events
    WHERE community_id = target_id AND kind = 13534;
    DELETE FROM relay_members
    WHERE community_id = target_id AND role = 'owner';
    DELETE FROM communities WHERE id = target_id;
  END IF;

  UPDATE communities
  SET host = current_setting('city2.new_host')
  WHERE id = source_id;
END
$city2$;
COMMIT;
SQL

restart_old=false
trap - EXIT
echo "host-migration: preserved the existing community under the new authority"
echo "host-migration: relay intentionally remains stopped until the new environment is installed"
