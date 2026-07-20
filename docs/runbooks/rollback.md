# Rollback & recovery runbook (Phase 5)

Repo-only procedures. Production apply needs an explicit owner command.

## Preconditions

- Recent `pg_dump` (deploy.sh / rollback.sh create one automatically).
- Worker **stopped** before any Alembic change or image rebuild that would
  reconnect Telethon (OPERATIONS.md §2 / §7).
- Target git SHA previously green in CI (same rule as deploy).

## App rollback (code + schema)

```bash
chmod +x scripts/rollback.sh
./scripts/rollback.sh <40-char-ci-verified-sha>
```

What it does: backup → stop worker → detached checkout → rebuild →
`alembic upgrade head` for that tree → recreate bot/worker/admin → health checks.

If a forward migration has no real `downgrade()`, do **not** use this script —
restore the SQL dump instead (RECOVERY.md §3) on a stopped worker.

## Health-failure path after deploy

1. Keep worker stopped if FloodWait / CRITICAL appears.
2. `./scripts/rollback.sh <previous-sha>` **or** restore `backups/pre_deploy_*.sql.gz`.
3. Confirm `docker compose ps --all` — Compose must not have resurrected a second worker.

## Redis password cutover (atomic)

Password is optional (`REDIS_PASSWORD=` empty = legacy open Redis on the Docker network).

To enable AUTH without a split-brain window:

1. Stop bot, worker, admin (leave redis/db up).
2. Set the **same** `REDIS_PASSWORD` in `.env`.
3. Recreate redis + apps together:
   `docker compose up -d --force-recreate redis bot worker admin`
4. Confirm healthchecks and `redis-cli -a "$REDIS_PASSWORD" ping`.

Rollback: clear `REDIS_PASSWORD`, recreate redis + apps the same way.

## Sessions volume (non-root UID 10001)

App containers run as UID/GID `10001`. Host `./sessions` must be writable:

```bash
sudo chown -R 10001:10001 sessions
# or: chmod 777 sessions  (dev only)
```

## Compose profiles

| File | Host ports |
|------|------------|
| `docker-compose.yml` | admin loopback only; **no** DB/Redis publish |
| `docker-compose.dev.yml` | DB/Redis on `127.0.0.1` |
| `docker-compose.prod.yml` | DB/Redis unpublished; admin loopback |

Local example:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d
```

Prod example:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

## Offsite backup / restore drill

Mandatory production gate, executed **outside** this repo-only phase:
copy `backups/*.sql.gz` off-box weekly and restore into an isolated Postgres once.
