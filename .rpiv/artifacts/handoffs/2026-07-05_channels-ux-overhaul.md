# Handoff: Admin ChannelsPage UI/UX Overhaul

**Date:** 2026-07-05 ~11:30 UTC  
**Branch:** `main`  
**HEAD:** `44a65c7` feat(admin): remove "Направление" placeholder, add "Восстановить" (unignore)  
**Status:** Worker running, both accounts CB clear, massive uncommitted work tree

---

## Critical: Worker Crash Fixed Mid-Session

Commit `c626dfd` (discovery v3) added `settings.discovery_enabled` in `app/worker/tasks.py:27` but did NOT add `from app.config import settings`. Worker was in crash-loop (`Restarting (1) 10 seconds ago`). **Fixed** by adding the import, rebuild, restart. Both accounts now healthy.

---

## What Was Done (Admin Panel — "Чаты без группы")

### Backend Changes (FastAPI + SQLAlchemy)

1. **`app/db/models.py`:** Added `manually_reviewed: Mapped[bool]` to `CatalogChannel` (server_default=false, nullable=false)

2. **`app/admin/api/__init__.py` (channels endpoint):**
   - Each channel response now includes `city_ids: list[int]` — effective city IDs (scalar auto_matched_city_id ∪ channel_cities M2M)
   - `manually_reviewed` field in GET response and PUT updatable
   - Added `discovered_after` query param (ISO date string) for "new channels" filter
   - Added `country_id`, `city_id` query param filters in GET list

3. **`app/admin/api/crud.py`:**
   - Raised per_page max from 100→500 for countries and cities (fixing 422 errors from frontend dropdowns)
   - Channel list query: `order_by(is_ignored.asc(), participants.desc().nullslast())` — ignored channels sink to bottom

4. **Migrations (in `migrations/versions/`, Alembic linear chain):**
   ```
   ca16bab1a0cc → da0a81014466 → 4afd135dc3f1 → b11187f388a9 → c2a1d3b4e5f6 → ccb7137d7d5c → idx_disc_at01 → manrev01 (HEAD)
   ```
   - `idx_discovered_at.py` (`idx_disc_at01`): index on `catalog_channels.discovered_at`
   - `manually_reviewed.py` (`manrev01`): add `manually_reviewed bool NOT NULL DEFAULT false`
   - Both migrations: **applied** (alembic_version = manrev01), but **files only exist on host** — must be `docker compose cp`'d to container + git committed (bind-mount is broken, see Known Issues)

### Frontend Changes (`admin-panel/`)

5. **`ChannelsPage.tsx` (524 lines, complete rewrite from ~310):**
   - **Filters bar:** Status filter (Все/Активные/Игнор/Без привязки), Country dropdown (91 countries + sentinel "all"), City dropdown (dependent on country, disabled when country=all), "Новые (7д)" checkbox, perPage selector (20/100/200/500, default 100)
   - **Search:** text input with X clear button
   - **Header counters:** "Без привязки: N · Найдено: N"
   - **"+ Город" section** above filters — form with name_ru, country_id Select, "Добавить" button (POST /api/cities, 409-safe)
   - **Table (6 columns):** @username(+status dot) | Название | Участники | Страна | Города | Действия
   - **3-color status dot:** purple=ignored, green=manually_reviewed, orange=pending
   - **Per-row actions (icon-only, `size="icon"`):**
     - Save (Save icon) — sends full city set + `manually_reviewed: true`
     - Trash2 — sets `is_ignored: true` ("Удалить")  
     - RotateCcw — sets `is_ignored: false` ("Восстановить")
   - **Per-row country:** Select dropdown (calls PUT on change)
   - **Per-row cities:** MultiSelect component (Popover + Command + Badge) — pre-fills from `city_ids`, sends full set on save
   - **"Изменения применятся в течение часа"** banner
   - **Removed from old version:** Привязан column, Игнор badge column, verified filter, viewMode dropdown, old single-select city dropdown
   - **M2M safety:** Save button ONLY enabled for orphan channels (auto_matched_city_id==null); for channels with existing cities it's disabled with tooltip — prevents overwriting multi-city channel_cities (44 channels) since current UI doesn't pre-fill the full channel_cities set

6. **New shadcn/ui components** (added via `npx shadcn@latest add`):
   - `admin-panel/src/components/ui/command.tsx`
   - `admin-panel/src/components/ui/popover.tsx`
   - `admin-panel/src/components/ui/input-group.tsx`

7. **Custom MultiSelect component:**
   - `admin-panel/src/components/ui/multi-select.tsx` — uses Popover + Command + Badge pattern
   - Supports search, clear all, toggle individual items
   - Uses Lucide Check, X, ChevronsUpDown icons

8. **Static assets rebuilt:**
   - Old: `index-CUcJhb-X.css`, `index-udsvTqLS.js` → **deleted**
   - New: `index-6k6-ixNi.css`, `index-BrWtQEr-.js`, `index-C938yOEZ.css`

### Data Operations

9. **Bursa retag:** Channel 1595 (`turkiyada_ishbor`) → Bursa (city_id=59). Orphans 821→820→813.

---

## Current Numbers

| Metric | Value |
|---|---|
| Total channels | 2522 |
| Active (not ignored) | 2515 |
| Orphans (no city) | 813 |
| Countries | 91 |
| Cities | 228 |
| 24 countries have zero cities | 93 channels in these |
| Identified clear city candidates | 25 (documented in session) |
| Keywords (demand+synonym+stop) | 2234 (29 segments, 96 universal stops) |
| Users | 3 |
| Migrations applied | 8 (head: manrev01) |

---

## Uncommitted Files (ALL STAGED? NO — mixed state)

### Modified (tracked, unstaged):
```
M CLAUDE.md
M admin-panel/package-lock.json
M admin-panel/package.json
M admin-panel/src/pages/ChannelsPage.tsx
M app/admin/api/__init__.py
M app/admin/api/crud.py
M app/admin/static/index.html
M app/db/models.py
M app/worker/tasks.py          <-- NEW (settings import fix)
```

### Deleted (tracked, unstaged):
```
D app/admin/static/assets/index-CUcJhb-X.css
D app/admin/static/assets/index-udsvTqLS.js
```

### New (untracked):
```
?? .rpiv/artifacts/handoffs/
?? admin-panel/src/components/ui/command.tsx
?? admin-panel/src/components/ui/input-group.tsx
?? admin-panel/src/components/ui/multi-select.tsx
?? admin-panel/src/components/ui/popover.tsx
?? app/admin/static/assets/index-6k6-ixNi.css
?? app/admin/static/assets/index-BrWtQEr-.js
?? app/admin/static/assets/index-C938yOEZ.css
?? migrations/versions/idx_discovered_at.py
?? migrations/versions/manually_reviewed.py
```

### Docs (untracked, safe to leave):
```
docs/AUDIT_STATE_2026-07-03.md
docs/DIAG1_2026-07-03.md
docs/DIAG_DANANG_2026-07-04.md
docs/admin_front_recon.txt
docs/audit_adminpanel.md
docs/audit_alembic_heads.md
docs/audit_alembic_state.md
docs/audit_channels_api.md
docs/audit_discovery_guard.md
docs/audit_grouping.md
docs/audit_grouping2.md
docs/audit_ignore_points.md
docs/audit_migration_drift.md
docs/audit_migrations.md
docs/audit_mount_read.md
docs/audit_segments.md
docs/audit_volume.md
docs/discovery_deep_audit.md
docs/discovery_refactoring_plan.md
docs/discovery_supplement.md
docs/kw_recon.txt
docs/matcher_anatomy.txt
docs/orphans_diag.txt
docs/retag_bursa.txt
docs/retag_dryrun.txt
```

---

## Infrastructure Status

| Container | Status |
|---|---|
| admin (port 17421) | Up 11 min (healthy) |
| bot | Up 40 hours (healthy) |
| db (PostgreSQL 16) | Up 5 days (healthy) |
| redis (Redis 7) | Up 5 days (healthy) |
| worker | Up (restarted after settings import fix) |

- **Worker:** Both accounts (@iraluxme, @mill_sofi) CB clear, polling normally
- **Admin panel:** http://server:17421/login, password from `ADMIN_PASSWORD` in `.env`

---

## Known Issues / Tech Debt

1. **bind-mount `./migrations:/app/migrations` BROKEN** (tech debt #7). Files in `migrations/versions/` on host do NOT reach the container — overlay2 conflict with `COPY . .` in Dockerfile. Workaround: write migration on host (for git), then `docker compose cp` into container, then `docker compose exec worker alembic upgrade head`. Migration files `idx_discovered_at.py` and `manually_reviewed.py` exist on host but were applied via cp+exec.

2. **Worker restart rule:** NEVER `docker compose up -d` / `restart` / `exec` while worker is running without explicit approval — risks double Telegram API load + FloodWait ban. (CLAUDE.md §0). Worker was already crashed in this session, so restart was justified.

3. **MultiSelect city pre-fill:** For the 44 multi-city channels, the UI disables the "Save" button because it can't safely pre-fill channel_cities. Full M2M editing from admin UI needs `channel_cities` loaded separately (tech debt #8).

4. **India duplicate country:** id=102 and id=119 both appear to be India. Needs investigation + potential merge (data integrity task).

5. **24 zero-city countries** with 93 orphans. 25 clear city candidates identified (session knowledge — need to reconstruct or re-audit).

6. **Admin static rebuild:** After Vite build, you must `docker compose build admin && docker compose up -d admin` to pick up the new `app/admin/static/assets/` files. The build was done in this session but new static files are untracked.

---

## Next Session Priorities

### Immediate (first 30 min):
1. **Commit everything.** Large changeset, split into logical commits:
   - migrations (idx_discovered_at + manually_reviewed)
   - backend changes (models + api + crud)
   - frontend (ChannelsPage.tsx + new components + package.json)
   - worker fix (settings import)
2. **Push to origin**

### If continuing work:
3. Add cities for the 24 zero-city countries (reduces orphans below 813)
4. Fix India duplicate (merge id=102 and id=119)
5. Test manually_reviewed flow: tag a channel → save → confirm green dot appears
6. Tech debt #8: load channel_cities for multi-city channels so "Save" is enabled for all orphans

### Blockers to watch:
- Worker: monitor for any new crashes (it was just revived from the `settings` NameError)
- Both accounts are post-ban — verify budget/interval multipliers are still active
- Discovery v3: needs `DISCOVERY_ENABLED=true` and `DISCOVERY_ACCOUNT_ID=3` to operate in dedicated mode

---

## Quick Reference

```bash
# Admin panel
http://<server>:17421/login

# DB access
docker compose exec db psql -U leadhunter -d leadhunter

# Alembic (container — bind-mount broken, cp files first)
docker compose cp migrations/versions/new_migration.py leadhunter-worker-1:/app/migrations/versions/
docker compose exec worker alembic upgrade head

# Rebuild + restart (ONLY with approval)
docker compose build worker && docker compose up -d worker

# Worker logs
docker compose logs worker --tail 50 -f

# Redis
docker compose exec redis redis-cli

# Tests
docker compose run --rm worker pytest tests/ -v
```
