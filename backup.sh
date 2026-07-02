#!/bin/bash
# LeadHunter backup script — database + session files
# Run via cron: 0 3 * * * /opt/LeadHunter/backup.sh
#
# Requires .env with: POSTGRES_DB, POSTGRES_USER, SESSION_BACKUP_PASSPHRASE
# Optional .env: S3_BUCKET, S3_ACCESS_KEY, S3_ENDPOINT (NOT YET TESTED)

set -e

# ── Load .env for cron (cron does not source it automatically) ──
set -a
[ -f /opt/LeadHunter/.env ] && . /opt/LeadHunter/.env
set +a

BACKUP_DIR="/opt/LeadHunter/backups"
RETENTION_DAYS=7
DB_CONTAINER="leadhunter-db-1"
DB_NAME="${POSTGRES_DB:-leadhunter}"
DB_USER="${POSTGRES_USER:-leadhunter}"
SESSION_DIR="/opt/LeadHunter/sessions"

mkdir -p "$BACKUP_DIR"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# ══════════════════════════════════════════════════
# 1. Database backup (pg_dump)
# ══════════════════════════════════════════════════

DB_BACKUP="$BACKUP_DIR/leadhunter_${TIMESTAMP}.sql.gz"

echo "[$(date)] Starting database backup to $DB_BACKUP"

docker exec "$DB_CONTAINER" pg_dump -U "$DB_USER" -d "$DB_NAME" | gzip > "$DB_BACKUP"

echo "[$(date)] Database backup complete: $(du -h "$DB_BACKUP" | cut -f1)"

find "$BACKUP_DIR" -name "leadhunter_*.sql.gz" -mtime +$RETENTION_DAYS -delete
ln -sf "$DB_BACKUP" "$BACKUP_DIR/latest.sql.gz"

echo "[$(date)] Database rotation done"

# ══════════════════════════════════════════════════
# 2. Session backup (encrypted, local only)
# ══════════════════════════════════════════════════
#
# LIMITATIONS (known, accepted until S3 is set up):
#  - Backup is on the same disk as sessions.  If the disk dies,
#    both original .session files and this backup are lost.
#  - S3 upload placeholder below is NOT tested against real B2/S3.
#    curl with Bearer token does NOT work with Backblaze B2 native API
#    (B2 requires two-step auth: b2_authorize_account → upload_url).
#    Replace with awscli --endpoint-url or b2 CLI when bucket is ready.
#
# Failure in this section does NOT roll back the DB backup above —
# pg_dump is already saved.  We disable set -e temporarily.

SESSION_BACKUP_DIR="$BACKUP_DIR/sessions"
mkdir -p "$SESSION_BACKUP_DIR"

# ls inside if-condition: set -e is active but `if !` safely absorbs the
# non-zero exit code of `ls` when no .session files exist — script does
# NOT abort, falls through to the "skipping" message.
if ! ls "$SESSION_DIR"/*.session >/dev/null 2>&1; then
    echo "[$(date)] No session files found — skipping session backup"
else
    SESSION_ARCHIVE="$SESSION_BACKUP_DIR/sessions_${TIMESTAMP}.tar.gz.gpg"

    set +e  # session backup failures must not abort the whole script

    if [ -z "${SESSION_BACKUP_PASSPHRASE:-}" ]; then
        echo "[$(date)] ERROR: SESSION_BACKUP_PASSPHRASE not set in .env — skipping session backup"
    else
        echo "[$(date)] Encrypting session files to $SESSION_ARCHIVE"

        # cd into SESSION_DIR so *.session glob expands there, not in CWD
        ( cd "$SESSION_DIR" && tar czf - *.session ) | \
            gpg --symmetric --batch --yes \
                --passphrase "$SESSION_BACKUP_PASSPHRASE" \
                --cipher-algo AES256 \
                -o "$SESSION_ARCHIVE"

        if [ $? -eq 0 ] && [ -f "$SESSION_ARCHIVE" ]; then
            # Verify archive is not empty — decrypt and count .session files inside
            FILE_COUNT=$(gpg --decrypt --batch --passphrase "$SESSION_BACKUP_PASSPHRASE" \
                "$SESSION_ARCHIVE" 2>/dev/null | tar tzf - 2>/dev/null | grep -c '\.session$' || true)

            if [ "$FILE_COUNT" -lt 1 ]; then
                echo "[$(date)] ERROR: Session archive is EMPTY (0 .session files) — backup failed"
            else
                echo "[$(date)] Session backup encrypted: $(du -h "$SESSION_ARCHIVE" | cut -f1) ($FILE_COUNT files)"

            # ── S3 upload (PLACEHOLDER — NOT TESTED against real B2/S3) ──
            # Backblaze B2 requires either:
            #   awscli:  aws s3 cp --endpoint-url "$S3_ENDPOINT" ... (S3-compatible API)
            #   b2 CLI:  b2 upload-file ... (native API with key + application key)
            # Current curl approach is NOT functional — DO NOT rely on it.
            if [ -n "${S3_BUCKET:-}" ] && [ -n "${S3_ACCESS_KEY:-}" ]; then
                echo "[$(date)] WARNING: S3 upload not implemented — use awscli or b2 CLI"
                echo "[$(date)] Session backup is LOCAL ONLY: $SESSION_ARCHIVE"
            else
                echo "[$(date)] S3 not configured — local backup only"
            fi

            # Rotation
            find "$SESSION_BACKUP_DIR" -name "sessions_*.tar.gz.gpg" -mtime +$RETENTION_DAYS -delete
            echo "[$(date)] Session rotation done"
            fi   # FILE_COUNT check
        else
            echo "[$(date)] ERROR: Session encryption failed — check SESSION_BACKUP_PASSPHRASE"
        fi
    fi

    set -e  # restore
fi

echo "[$(date)] Backup finished"
