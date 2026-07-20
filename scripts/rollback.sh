#!/usr/bin/env bash
# Reproducible rollback to a previously verified git SHA.
# Requires: owner-approved SHA, recent pg_dump, worker stopped before migrate.
# See docs/runbooks/rollback.md.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

COMPOSE="${COMPOSE:-docker compose}"
TARGET_SHA="${1:-}"

if [[ ! "$TARGET_SHA" =~ ^[0-9a-fA-F]{40}$ ]]; then
  echo "Usage: $0 <40-char-git-sha>" >&2
  exit 1
fi

log() { printf '[rollback] %s\n' "$*"; }

BACKUP_DIR="${BACKUP_DIR:-$ROOT/backups}"
mkdir -p "$BACKUP_DIR"
STAMP="$(date +%F_%H%M)"
DB_CONTAINER="$(docker ps --format '{{.Names}}' | grep -E 'db|postgres' | head -1 || true)"
[[ -n "$DB_CONTAINER" ]] || { log "ERROR: db container not found"; exit 1; }

BACKUP_FILE="$BACKUP_DIR/pre_rollback_${STAMP}.sql.gz"
log "pg_dump via $DB_CONTAINER → $BACKUP_FILE"
docker exec "$DB_CONTAINER" sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' \
  | gzip > "$BACKUP_FILE"
[[ -s "$BACKUP_FILE" ]] || { log "ERROR: empty backup"; exit 1; }

log "Stop worker before checkout/migrate"
$COMPOSE stop worker || true
if $COMPOSE ps --status running --services 2>/dev/null | grep -qx worker; then
  log "Worker resurrected — stopping again"
  $COMPOSE stop worker
fi

log "Checkout detached $TARGET_SHA"
git fetch origin "$TARGET_SHA"
git checkout --detach "$TARGET_SHA"
[[ "$(git rev-parse HEAD)" = "$TARGET_SHA" ]] || { log "SHA mismatch"; exit 1; }

log "Rebuild app images"
DOCKER_BUILDKIT=0 COMPOSE_DOCKER_CLI_BUILD=0 $COMPOSE build bot worker admin

log "Downgrade/upgrade Alembic to the tree's head (reversible migrations only)"
$COMPOSE run --rm --no-deps worker alembic upgrade head
if $COMPOSE ps --status running --services 2>/dev/null | grep -qx worker; then
  $COMPOSE stop worker
fi

log "Recreate bot/worker/admin (--no-deps)"
$COMPOSE up -d --no-deps bot worker admin

for service in db redis bot worker admin; do
  cid="$($COMPOSE ps -q "$service")"
  [[ -n "$cid" ]] || { log "ERROR: $service not running"; exit 1; }
  status="$(docker inspect --format '{{.State.Health.Status}}' "$cid")"
  [[ "$status" == "healthy" ]] || { log "ERROR: $service health=$status"; exit 1; }
done

log "Done. Backup: $BACKUP_FILE  HEAD=$(git rev-parse --short HEAD)"
