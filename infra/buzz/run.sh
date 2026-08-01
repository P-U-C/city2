#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${ROOT}"
PROJECT="${BUZZ_COMPOSE_PROJECT:-city2-buzz}"

[[ "${PROJECT}" =~ ^[a-z0-9][a-z0-9_-]*$ ]] || {
  echo "buzz: invalid BUZZ_COMPOSE_PROJECT" >&2
  exit 2
}

detect_docker() {
  if docker info >/dev/null 2>&1; then
    DOCKER=(docker)
  elif sudo -n docker info >/dev/null 2>&1; then
    DOCKER=(sudo -n docker)
  else
    echo "buzz: Docker daemon access is unavailable" >&2
    exit 1
  fi
}

compose() {
  "${DOCKER[@]}" compose \
    --project-name "${PROJECT}" \
    --env-file .env \
    -f compose.yml \
    -f compose.private.yml \
    "$@"
}

require_env() {
  [[ -f .env ]] || {
    echo "buzz: missing infra/buzz/.env; run bootstrap-env.sh first" >&2
    exit 1
  }
}

case "${1:-help}" in
  preflight)
    exec ./scripts/preflight.sh
    ;;
  config)
    require_env
    detect_docker
    compose config --quiet
    echo "buzz: Compose configuration is valid; values were not rendered"
    ;;
  pull)
    require_env
    detect_docker
    compose pull
    ;;
  start|up)
    ./scripts/preflight.sh
    detect_docker
    compose up -d --wait
    ;;
  stop)
    require_env
    detect_docker
    compose stop
    ;;
  down)
    require_env
    detect_docker
    compose down
    ;;
  status|ps)
    require_env
    detect_docker
    compose ps
    ;;
  logs)
    require_env
    detect_docker
    shift
    if [[ "$#" -eq 0 ]]; then
      set -- relay
    fi
    compose logs -f "$@"
    ;;
  add-member)
    require_env
    detect_docker
    compose exec relay /usr/local/bin/buzz-admin add-member \
      --pubkey "${2:?Usage: ./city2 buzz add-member <npub-or-hex> [--role member|admin]}" \
      "${@:3}"
    ;;
  remove-member)
    require_env
    detect_docker
    compose exec relay /usr/local/bin/buzz-admin remove-member \
      --pubkey "${2:?Usage: ./city2 buzz remove-member <npub-or-hex> [--role member|admin]}" \
      "${@:3}"
    ;;
  list-members)
    require_env
    detect_docker
    compose exec relay /usr/local/bin/buzz-admin list-members
    ;;
  backup)
    shift
    exec ./scripts/backup.sh "$@"
    ;;
  verify-backup)
    shift
    exec ./scripts/verify-backup.sh "$@"
    ;;
  e2e)
    exec ./scripts/e2e-disposable.sh
    ;;
  install-agent-tooling)
    exec ./scripts/install-agent-tooling.sh
    ;;
  help|-h|--help)
    cat <<'EOF'
Usage: ./city2 buzz <command>

  preflight                 Validate without starting or pulling
  config                    Validate merged Compose without rendering values
  pull                      Pull pinned images
  start                     Start the relay stack after preflight
  stop                      Stop services and preserve state
  down                      Remove containers/network; preserve volumes
  status                    Show service state
  logs [service]            Follow service logs (default: relay)
  add-member <pubkey>       Add a closed-relay member
  remove-member <pubkey>    Remove a closed-relay member
  list-members              List relay members
  backup [destination]      Create an aligned backup
  verify-backup <path>      Verify backup integrity
  e2e                       Run and destroy a disposable relay proof
  install-agent-tooling     Install tools only; never enable/start a service
EOF
    ;;
  *)
    echo "buzz: unknown command: $1" >&2
    exit 2
    ;;
esac
