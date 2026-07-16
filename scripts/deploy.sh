#!/usr/bin/env bash
# Production deploy on the VPS. Called by GitHub Actions over SSH after git pull.
# Follows OPERATIONS.md: stop worker before build/migrate/up; recreate app
# services with --no-deps only (never touch db/redis).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

BACKUP_DIR="${BACKUP_DIR:-$ROOT/backups}"
COMPOSE="${COMPOSE:-docker compose}"
DB_CONTAINER="${DB_CONTAINER:-}"
REDIS_CONTAINER="${REDIS_CONTAINER:-}"

log() { printf '[deploy] %s\n' "$*"; }

detect_container() {
  local pattern="$1"
  docker ps --format '{{.Names}}' | grep -E "$pattern" | head -1 || true
}

if [[ -z "$DB_CONTAINER" ]]; then
  DB_CONTAINER="$(detect_container 'db|postgres')"
fi
if [[ -z "$REDIS_CONTAINER" ]]; then
  REDIS_CONTAINER="$(detect_container 'redis')"
fi

mkdir -p "$BACKUP_DIR"
STAMP="$(date +%F_%H%M)"

if [[ -n "$DB_CONTAINER" ]]; then
  log "pg_dump via $DB_CONTAINER → backups/pre_deploy_${STAMP}.sql.gz"
  docker exec "$DB_CONTAINER" sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' \
    | gzip > "$BACKUP_DIR/pre_deploy_${STAMP}.sql.gz"
else
  log "WARN: db container not found — skipping pg_dump"
fi

log "Stopping worker (anti-ban: no double Telegram load during rebuild)"
$COMPOSE stop worker

log "Build bot/worker/admin (BuildKit off — Docker race workaround)"
DOCKER_BUILDKIT=0 COMPOSE_DOCKER_CLI_BUILD=0 $COMPOSE build bot worker admin

log "Alembic migrate (new image, worker still stopped)"
$COMPOSE run --rm --no-deps worker alembic upgrade head

log "Recreate app services (--no-deps: leave db/redis alone)"
$COMPOSE up -d --no-deps bot worker admin

log "Health snapshot"
$COMPOSE ps
log "Recent bot logs"
$COMPOSE logs --tail=40 bot || true
log "Recent worker logs"
$COMPOSE logs --tail=40 worker || true
log "Done"
