---
name: safe-deploy
description: Safely deploy or restart LeadHunter Docker services without FloodWait or double-loading Telegram. Use when deploying, restarting bot/worker/admin, docker compose up/build, or applying production changes.
---

# Safe Deploy

## Goal
Ship code without Telegram ban risk and without accidentally restarting a live worker.

## Decision tree

| Change | Action |
|---|---|
| Locales / bot handlers only | Prefer `docker restart leadhunter-bot-1` (flat docker) |
| Admin SPA/API only | Build SPA → `docker restart leadhunter-admin-1` |
| Poller / rate_limiter / classifier / pool | Owner approval + OPERATIONS §5 + restart **worker** |
| Migrations | Skill `migration-checklist` first |

## Never while worker must stay up
- Blind `docker compose up -d`, `compose run`, `compose restart`, even `compose build` can auto-start worker (OPERATIONS §7).
- Prefer `--no-deps` and flat `docker restart <name>` when isolating services.

## Procedure (full rebuild)

1. Confirm owner wants deploy; note whether worker can stop.
2. `pg_dump` if DB/migrations involved.
3. If worker must stop: `docker compose stop worker` then verify `docker compose ps --all`.
4. Pull/build as needed. Prefer `up -d --no-deps bot worker admin` over bare `up -d`.
5. After any mutating Compose command: re-check `ps` — stop worker again if it came back early.
6. Start worker last when ready.
7. Monitor **2 minutes**:

```bash
docker compose logs -f worker --tail=100 | grep -E "FloodWait|circuit|ERROR|CRITICAL|Pool initialized"
```

FloodWait / CRITICAL → STOP, rollback, document in OPERATIONS.md.

8. Bot: confirm polling. Admin: HTTP 200 on `/login` if changed.
9. Close with skill `session-close`.

## CI/CD note
GitHub `deploy.yml` uses `scripts/deploy.sh` (stop worker → alembic → build → up --no-deps). Do not bypass its worker-stop sequence.
