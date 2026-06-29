#!/bin/bash
# LeadHunter database backup script
# Run via cron: 0 3 * * * /opt/LeadHunter/backup.sh

set -e

BACKUP_DIR="/opt/LeadHunter/backups"
RETENTION_DAYS=7
DB_CONTAINER="leadhunter-db-1"
DB_NAME="${POSTGRES_DB:-leadhunter}"
DB_USER="${POSTGRES_USER:-leadhunter}"

mkdir -p "$BACKUP_DIR"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/leadhunter_${TIMESTAMP}.sql.gz"

echo "[$(date)] Starting backup to $BACKUP_FILE"

# Dump and compress
docker exec "$DB_CONTAINER" pg_dump -U "$DB_USER" -d "$DB_NAME" | gzip > "$BACKUP_FILE"

echo "[$(date)] Backup complete: $(du -h "$BACKUP_FILE" | cut -f1)"

# Rotate old backups
find "$BACKUP_DIR" -name "leadhunter_*.sql.gz" -mtime +$RETENTION_DAYS -delete
echo "[$(date)] Cleaned backups older than $RETENTION_DAYS days"

# Keep last backup symlink for easy restore
ln -sf "$BACKUP_FILE" "$BACKUP_DIR/latest.sql.gz"
echo "[$(date)] Updated latest symlink"
