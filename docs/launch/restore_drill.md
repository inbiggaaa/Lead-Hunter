# Restore drill checklist

Goal: prove RPO ≤ 24h and RTO ≤ 2h on an isolated host/containers.

## Steps

1. [ ] Take latest `backups/latest.sql.gz` (or offsite copy)
2. [ ] Spin isolated Postgres (different compose project / port)
3. [ ] Restore dump into empty DB
4. [ ] Run `alembic current` / `upgrade head` on restored DB
5. [ ] Decrypt latest sessions archive to a temp dir (do not overwrite prod sessions)
6. [ ] Boot bot+worker against isolated DB/Redis with disposable Bot token if available
7. [ ] Verify: `/start` works, alembic head matches, sample SELECT counts sane
8. [ ] Tear down isolated stack; shred temp session files

## Record

| Field | Value |
|---|---|
| Date |  |
| Backup file |  |
| Restore duration |  |
| Issues |  |
| Pass/Fail |  |
