---
name: migration-checklist
description: Apply Alembic migrations safely on LeadHunter with backup and worker stopped. Use when creating or running database migrations, alembic upgrade/downgrade, or schema changes.
---

# Migration Checklist

## Requirements
- Migration must implement `upgrade()` **and** `downgrade()`.
- `pg_dump` before apply on any shared/prod DB.
- Worker **stopped** (or separate dev DB). Never migrate under a live polling worker.

## Steps

```
- [ ] Write migration under migrations/versions/
- [ ] Verify downgrade() is real (not pass-only)
- [ ] Backup: pg_dump → backups/pre_<name>_YYYY-MM-DD_HHMM.sql
- [ ] Stop worker; verify docker compose ps --all
- [ ] alembic upgrade head (isolated run preferred — see OPERATIONS §7)
- [ ] Confirm alembic current
- [ ] Ensure worker did not auto-start; start only when ready
- [ ] Smoke: bot/admin healthy; critical queries OK
```

## Compose pitfall
`compose run`, `up`, even `build` may resurrect worker. After mutating Compose commands, re-check `ps` and stop worker again before continuing.

## Rollback
`alembic downgrade -1` then restore dump if needed (`restore.sh` / RECOVERY.md). Owner approval for destructive restore.

## After
Skill `session-close` with migration id + backup path.
