#!/usr/bin/env bash
set -euo pipefail

DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DEPLOY_DIR"

if [[ ! -f .env ]]; then
  echo "缺少 $DEPLOY_DIR/.env，请先执行: cp .env.example .env"
  exit 1
fi

compose() {
  docker compose --env-file .env -f compose.yaml "$@"
}

task_worker_processes() {
  local value
  value="$(sed -n 's/^TASK_WORKER_PROCESSES=//p' .env | tail -1 | tr -d '[:space:]')"
  if [[ ! "$value" =~ ^[1-9][0-9]*$ ]]; then
    value=2
  fi
  printf '%s' "$value"
}

case "${1:-}" in
  start)
    compose up -d --build --scale task-worker="$(task_worker_processes)"
    compose ps
    ;;
  stop)
    compose down
    ;;
  restart)
    # `compose restart` only restarts existing containers and does not restore
    # missing dependencies or wait for MySQL/Redis health before workers start.
    compose up -d --no-build --force-recreate --scale task-worker="$(task_worker_processes)"
    compose ps
    ;;
  status)
    compose ps
    ;;
  logs)
    if [[ -n "${2:-}" ]]; then
      compose logs -f --tail=200 "$2"
    else
      compose logs -f --tail=200
    fi
    ;;
  update)
    cd "$DEPLOY_DIR/../.."
    git pull --ff-only
    cd "$DEPLOY_DIR"
    compose up -d --build --remove-orphans --scale task-worker="$(task_worker_processes)"
    compose ps
    ;;
  *)
    echo "用法: $0 {start|stop|restart|status|logs [服务名]|update}"
    exit 1
    ;;
esac
