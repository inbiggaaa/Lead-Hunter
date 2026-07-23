#!/usr/bin/env bash
# Production deploy on the VPS. Called by GitHub Actions over SSH after git pull.
# Follows OPERATIONS.md: stop worker before build/migrate/up; recreate app
# services with --no-deps only (never touch db/redis).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

BACKUP_DIR="${BACKUP_DIR:-$ROOT/backups}"
DB_CONTAINER="${DB_CONTAINER:-}"
REDIS_CONTAINER="${REDIS_CONTAINER:-}"

log() { printf '[deploy] %s\n' "$*"; }

# COMPOSE may override to a single binary (e.g. docker-compose). Default is the
# Compose V2 plugin invoked as `docker compose` (two words — never quote as one).
compose() {
  if [[ -n "${COMPOSE:-}" ]]; then
    # shellcheck disable=SC2086
    $COMPOSE "$@"
  else
    docker compose "$@"
  fi
}

detect_container() {
  local pattern="$1"
  docker ps --format '{{.Names}}' | grep -E "$pattern" | head -1 || true
}

check_worker_stopped() {
  compose ps --all
  if compose ps --status running --services | grep -qx worker; then
    log "Worker was resurrected; stopping it before the next deploy step"
    compose stop worker
  fi
}

require_healthy_service() {
  local service="$1"
  local container
  container="$(compose ps -q "$service")"
  [[ -n "$container" ]] || { log "ERROR: $service container is not running"; exit 1; }
  [[ "$(docker inspect --format '{{.State.Health.Status}}' "$container")" == "healthy" ]] ||
    { log "ERROR: $service is not healthy"; exit 1; }
}

if [[ -z "$DB_CONTAINER" ]]; then
  DB_CONTAINER="$(detect_container 'db|postgres')"
fi
if [[ -z "$REDIS_CONTAINER" ]]; then
  REDIS_CONTAINER="$(detect_container 'redis')"
fi

mkdir -p "$BACKUP_DIR"
STAMP="$(date +%F_%H%M)"

[[ -n "$DB_CONTAINER" ]] || { log "ERROR: db container not found"; exit 1; }
BACKUP_FILE="$BACKUP_DIR/pre_deploy_${STAMP}.sql.gz"
log "pg_dump via $DB_CONTAINER → $BACKUP_FILE"
docker exec "$DB_CONTAINER" sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' \
  | gzip > "$BACKUP_FILE"
[[ -s "$BACKUP_FILE" ]] || { log "ERROR: pg_dump produced an empty backup"; exit 1; }

log "Stopping worker (anti-ban: no double Telegram load during rebuild)"
compose stop worker || true
check_worker_stopped

log "Ensure sessions/ is writable by non-root UID 10001"
if [[ -d sessions ]]; then
  chown -R 10001:10001 sessions 2>/dev/null || \
    log "WARN: chown sessions failed — worker may crash if UID 10001 cannot write"
fi

log "Build bot/worker/admin (BuildKit off — Docker race workaround)"
DOCKER_BUILDKIT=0 COMPOSE_DOCKER_CLI_BUILD=0 compose build bot worker admin
check_worker_stopped

log "Alembic migrate (new image, worker still stopped)"
compose run --rm --no-deps worker alembic upgrade head
check_worker_stopped

log "Recreate app services (--no-deps: leave db/redis alone)"
compose up -d --no-deps bot worker admin

log "Verify all expected services are healthy"
for service in db redis bot worker admin; do
  require_healthy_service "$service"
done

log "Verify Alembic is current at head"
compose exec -T worker sh -ec '
  heads="$(alembic heads | awk "{print \$1}" | sort)"
  current="$(alembic current | awk "{print \$1}" | sort)"
  test -n "$heads" && test "$current" = "$heads"
'

log "Check Telegram worker errors"
compose logs --tail=80 worker | tee /tmp/lh_worker_tail.txt
if grep -Eiq 'FloodWait|CRITICAL' /tmp/lh_worker_tail.txt; then
  log "ERROR: FloodWait/CRITICAL in worker logs"
  exit 1
fi
log "Done"
