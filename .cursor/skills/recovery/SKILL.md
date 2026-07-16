---
name: recovery
description: Diagnose and recover LeadHunter outages (bot down, no notifications, OOM, FloodWait, Redis/DB). Use when something is broken in production or the user reports an incident.
---

# Recovery

Full playbook: `RECOVERY.md`. Stay calm. **Never** `docker compose down -v` unless owner explicitly confirms (destroys DB volume).

## Step 0 — Diagnose

```bash
docker compose ps
docker compose logs --tail=50
docker stats --no-stream
df -h
```

## Common paths

| Symptom | First checks |
|---|---|
| Bot ignores /start | `logs bot`; `BOT_TOKEN`; restart **bot only** |
| No notifications | worker logs; Redis queue `LLEN queue:notifications`; sender; circuit |
| FloodWait | OPERATIONS §4 — **do not restart worker**; wait circuit |
| OOM / restarts | `docker stats`; worker mem 1G; swap |
| Admin crash-loop | config ValidationError / baked `.env`; prefer flat `docker restart admin` |
| DB issues | restore from `backups/` via `restore.sh` only with owner OK |

## FloodWait (critical)
1. Do not restart worker.
2. Check circuit TTL in Redis.
3. Document incident in `OPERATIONS.md` (cause, timeline, lesson, new rule if any).

## After recovery
- Verify matching cycle / bot polling / admin HTTP as applicable.
- Skill `session-close` with incident notes.
