#!/bin/bash
# Restore database from backup
# Usage: ./restore.sh [backup_file]
# DROPS existing database and recreates from backup!
# Default: ./backups/latest.sql.gz

set -e

BACKUP_FILE="${1:-backups/latest.sql.gz}"
DB_CONTAINER="leadhunter-db-1"
DB_NAME="${POSTGRES_DB:-leadhunter}"
DB_USER="${POSTGRES_USER:-leadhunter}"

if [ ! -f "$BACKUP_FILE" ]; then
    echo "ERROR: Backup file not found: $BACKUP_FILE"
    exit 1
fi

echo "[$(date)] ⚠️  This will DROP and RECREATE the database '$DB_NAME'"
echo "Press Ctrl+C within 5 seconds to cancel..."
sleep 5

echo "[$(date)] Dropping existing connections..."
docker exec -i "$DB_CONTAINER" psql -U "$DB_USER" -d postgres -c \
    "SELECT pg_terminate_backend(pg_stat_activity.pid) FROM pg_stat_activity WHERE pg_stat_activity.datname = '$DB_NAME' AND pid <> pg_backend_pid();" 2>/dev/null || true

echo "[$(date)] Dropping and recreating database..."
docker exec -i "$DB_CONTAINER" dropdb -U "$DB_USER" --if-exists "$DB_NAME" 2>/dev/null || true
docker exec -i "$DB_CONTAINER" createdb -U "$DB_USER" "$DB_NAME"

echo "[$(date)] Restoring from $BACKUP_FILE..."
gunzip -c "$BACKUP_FILE" | docker exec -i "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME"

echo "[$(date)] ✅ Restore complete!"
