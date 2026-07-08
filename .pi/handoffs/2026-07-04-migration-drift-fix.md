# Handoff: Migration Drift Fix — 2026-07-04

## Session snapshot

- **Date:** 2026-07-04 ~08:30 UTC
- **Repo:** /opt/LeadHunter, branch `main`
- **Commit:** `895b05f` — "docs(session-log): grouping audit complete, admin feature plan, tech debt updated"
- **Git status:** ahead=1 (CLAUDE.md session-log, NOT pushed to origin), behind=0
- **Working tree:** 1 file modified (app/db/models.py), 10+ untracked audit docs
- **Worker:** RUNNING in production — **DO NOT RESTART**

## What we were doing

Implementing "Step 1" of the admin feature plan: adding an `is_ignored` boolean column to `catalog_channels` so we can soft-delete/noise-mark channels in the "Chats without group" admin panel.

## Current state — 3 key pieces

### 1. models.py (modified, NOT committed)

Two changes in `app/db/models.py`:

```python
# In imports (line 17):
    text,   # <-- ADDED (was not there before)

# In CatalogChannel (line 200):
    is_ignored: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false"), default=False
    )
```

This is correct, importable (`python -c "import app.db.models"` passes), and follows the existing style pattern (matches `is_verified` on the same class).

### 2. Auto-generated migration (Docker container ONLY, NOT on host)

File: `/app/migrations/versions/0479653cd24b_add_is_ignored_to_catalog_channels.py`
Exists ONLY inside the Docker worker container (not synced to `./migrations/versions/` on host due to bind-mount permission issue — container runs as root, host is `leadhunter` user).

The migration has **3 operations** — 1 wanted, 2 unwanted:

```python
def upgrade():
    op.add_column('catalog_channels', sa.Column('is_ignored', ...))   # ✓ WANTED
    op.drop_constraint(op.f('uq_cities_country_slug'), 'cities', ...) # ✗ UNWANTED
    op.drop_index(op.f('idx_sent_log_content_dedup'), 'sent_log')     # ✗ UNWANTED
```

The 2 unwanted drops happen because Alembic detects drift between the ORM models and the actual DB:

| DB object | Exists in DB? | Declared in ORM model? |
|---|---|---|
| `uq_cities_country_slug` — UNIQUE(country_id, slug) on cities | YES | NO (City class has no `__table_args__`) |
| `idx_sent_log_content_dedup` — btree(user_id, content_hash, sent_at) | YES | NO (SentLog class doesn't declare this index) |

Both DB objects were created by migration `c2a1d3b4e5f6` (content_hash migration) and `4afd135dc3f1` (Samui dedup). They exist and MUST remain. Alembic wants to drop them only because the ORM doesn't know about them.

### 3. Database state

- `alembic_version` table: single row `c2a1d3b4e5f6` (the content_hash migration)
- `catalog_channels.is_ignored` column: DOES NOT EXIST in DB yet (confirmed: 0 rows from information_schema)
- `uq_cities_country_slug`: EXISTS, must be preserved
- `idx_sent_log_content_dedup`: EXISTS, must be preserved
- The 0479 migration has NOT been applied

## The fix — Option A (recommended in audit_migration_drift.md)

**Add `__table_args__` to City and SentLog in models.py** to declare the constraint/index that already exist in the DB. Then re-autogenerate — it will produce a CLEAN migration with only the `add_column is_ignored`.

### City (around line 143 in models.py):

Currently:
```python
class City(Base):
    __tablename__ = "cities"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ...
    country: Mapped["Country"] = relationship(back_populates="cities")
```

Add `__table_args__`:
```python
class City(Base):
    __tablename__ = "cities"
    __table_args__ = (
        UniqueConstraint("country_id", "slug", name="uq_cities_country_slug"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ...
```

### SentLog (around line 111 in models.py):

Currently:
```python
class SentLog(Base):
    __tablename__ = "sent_log"
    __table_args__ = (UniqueConstraint("user_id", "message_hash"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ...
```

Add the Index to the existing tuple (note: need to import `Index` — already imported at line 10):
```python
class SentLog(Base):
    __tablename__ = "sent_log"
    __table_args__ = (
        UniqueConstraint("user_id", "message_hash"),
        Index("idx_sent_log_content_dedup", "user_id", "content_hash", "sent_at"),
    )
    ...
```

## Procedure to complete (in order)

### Step A: Edit models.py to add the missing constraint/index declarations

Edit `app/db/models.py` (which already has the `is_ignored` and `text` import in the working tree):
1. Add `__table_args__` with `UniqueConstraint("country_id", "slug", name="uq_cities_country_slug")` to `class City`
2. Add `Index("idx_sent_log_content_dedup", "user_id", "content_hash", "sent_at")` to `class SentLog.__table_args__`

Verify: `python -c "import app.db.models"` must pass. `grep -A2 'class City\|class SentLog' app/db/models.py` should show the constraints.

### Step B: Re-generate the migration (CLEAN this time)

```bash
# Remove the dirty migration from the container first
docker compose exec worker rm /app/migrations/versions/0479653cd24b_add_is_ignored_to_catalog_channels.py

# Generate fresh — should produce ONLY add_column, no drops
docker compose exec worker alembic revision --autogenerate -m "add is_ignored to catalog_channels"

# Verify the generated file has ONLY add_column in upgrade()
docker compose exec worker cat /app/migrations/versions/*is_ignored*.py | grep -E "op\.(add|drop|create)"
# Should show: op.add_column('catalog_channels', ...)
# Should NOT show: op.drop_constraint, op.drop_index
```

### Step C: Copy migration to host

The file is inside the container at `/app/migrations/versions/*is_ignored*.py`. Since bind-mount sync may not work, use `docker cp`:

```bash
# Get the revision ID
REV=$(docker compose exec -T worker ls /app/migrations/versions/*is_ignored*.py | xargs basename | head -c12)
# Copy to host
docker compose exec worker cat /app/migrations/versions/${REV}_add_is_ignored_to_catalog_channels.py > migrations/versions/${REV}_add_is_ignored_to_catalog_channels.py
```

### Step D: Apply the migration

```bash
# STOP WORKER FIRST (CRITICAL — CLAUDE.md §0 rule: do NOT touch prod with worker running)
docker compose stop worker

# Apply migration
docker compose run --rm worker alembic upgrade head

# Verify
docker exec leadhunter-db-1 psql -U leadhunter -d leadhunter \
  -c "SELECT column_name, data_type, is_nullable FROM information_schema.columns WHERE table_name='catalog_channels' AND column_name='is_ignored';"
# Should show: is_ignored | boolean | NO

docker exec leadhunter-db-1 psql -U leadhunter -d leadhunter \
  -c "SELECT indexname FROM pg_indexes WHERE indexname IN ('uq_cities_country_slug', 'idx_sent_log_content_dedup');"
# Should show BOTH indexes

# Restart worker
docker compose up -d worker
```

### Step E: Verify hot-path safety

After migration, verify `is_ignored` defaults are correct:
```bash
docker exec leadhunter-db-1 psql -U leadhunter -d leadhunter \
  -c "SELECT count(*) FROM catalog_channels WHERE is_ignored IS NULL OR is_ignored = true;"
# Should be 0 (or only manually-set ones)
```

Then confirm the 3 code points that will filter by `is_ignored` are ready (this is the NEXT task — Step 2 of the admin feature plan):
- `discovery_v2.py:266` — discovery query
- `_get_all_channels()` in `poller.py:196` — poller channel selection
- `_tag_new_channels()` in `poller.py:1187` — new channel tagging

**These filters do NOT exist yet** — Step 2 is a separate task AFTER migration.

### Step F: Commit everything

```bash
git add app/db/models.py migrations/versions/*is_ignored*.py
git commit -m "feat(db): add is_ignored column to catalog_channels + fix ORM constraint/index drift

- Add is_ignored bool to CatalogChannel model (server_default=false)
- Add UniqueConstraint(country_id, slug) to City model (matches DB)
- Add Index idx_sent_log_content_dedup to SentLog model (matches DB)
- Autogenerated migration: add_column only, no unwanted drops"
```

## Files inventory

| File | Status | Notes |
|---|---|---|
| `app/db/models.py` | Modified (not committed) | `is_ignored` field + `import text` added |
| `migrations/versions/` (host) | 5 files | Missing 0479* (only in container) |
| `migrations/versions/` (container) | 6 files | Has 0479* with 3 ops (dirty) |
| `docs/audit_migration_drift.md` | Untracked | Full analysis + 3 fix options |
| `docs/audit_segments.md` | Untracked | Segment model audit |
| `docs/audit_grouping.md`, `grouping2.md`, `grouping3.md` | Untracked | Grouping audit passes |
| `docs/AUDIT_STATE_2026-07-03.md` | Untracked | Previous session state snapshot |
| `docs/DIAG1_2026-07-03.md` | Untracked | DIAG-1 resolution |
| `docs/DIAG_DANANG_2026-07-04.md` | Untracked | Danang channel analysis |
| `docs/audit_adminpanel.md` | Untracked | Admin panel architecture |
| `docs/audit_alembic_heads.md` | Untracked | Alembic head verification |
| `docs/audit_alembic_state.md` | Untracked | Alembic state audit |
| `docs/audit_migrations.md` | Untracked | All migration files review |
| `check_cursors.py` | Untracked | Redis cursor inspection script |

## Critical constraints

1. **WORKER IS RUNNING.** Do NOT run `docker compose restart/stop/exec` on worker while it's polling. Per CLAUDE.md §0: "запрещено запускать docker compose run/exec/restart/up -d при работающем worker в проде."

2. **Migration procedure requires stopping worker.** Plan a brief maintenance window: `docker compose stop worker` → apply migration → `docker compose up -d worker`. This is safe because post-ban mode + session model mean recovery is gradual (warmup ramp).

3. **Post-ban is active** on both accounts until ~2026-07-04 14:06 MSK (budget 5000, interval x2). Stopping/resuming within post-ban window is safe — Redis preserves state via AOF.

4. **Origin is behind by 1 commit.** The `895b05f` commit (CLAUDE.md session log) was never pushed. Push when convenient.

5. **All audit docs are untracked.** Decide whether to `git add docs/audit_*.md` or leave them as working notes.

## What comes after migration (separate tasks)

Per the admin feature plan in CLAUDE.md §8, after the `is_ignored` migration:

- **Step 2 (HOT):** Add `WHERE is_ignored = false` filters in 3 code points (discovery_v2, _get_all_channels, _tag_new_channels). Test that ignored channels disappear from all 3 selections AND are not polled.
- **Step 3:** Backend routes — extend `/api/channels` with filters (has_city, country_id, city_id, is_ignored), POST for multi-city binding, POST "add city", PATCH is_ignored.
- **Step 4:** Frontend "Chats without group" panel — list, dropdowns, actions.

## Session log entry (to append to CLAUDE.md §8)

```
**04.07.2026 08:30 — Migration drift: is_ignored + ORM constraint/index drift fix.**
models.py: added is_ignored bool to CatalogChannel. Auto-generated migration 0479* in container only
(3 ops: add_column + 2 unwanted drops due to uq_cities_country_slug and idx_sent_log_content_dedup
not declared in ORM). Root cause: City and SentLog models missing __table_args__ for
existing DB constraint/index. Recommended fix: add UniqueConstraint to City, Index to SentLog,
re-autogenerate for clean migration. Full analysis in docs/audit_migration_drift.md.
Worker running, migration NOT applied yet. NEXT: apply fix → re-autogenerate → stop worker → apply → restart.
```
