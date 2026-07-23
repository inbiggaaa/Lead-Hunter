# Segment-aware LLM profiles — staged enablement (Phase 11)

**Status:** code ready on `feature/segment-llm-profiles`.  
**Do not run production steps without an explicit owner command.**

This document is the operational checklist. Blocking rollback never needs a migration:

```text
LLM_SEGMENT_PROFILES_BLOCKING=false
```

---

## Flags

| Env | Default | Meaning |
|---|---|---|
| `LLM_SEGMENT_PROFILES_ENABLED` | `false` | Run v2 alongside legacy; metrics + correlation |
| `LLM_SEGMENT_PROFILES_BLOCKING` | `false` | Allow v2 to change delivery |
| `LLM_SEGMENT_PROFILES_BLOCKING_SEGMENTS` | empty | Allowlist. **Empty = fail-safe** (blocking flag ignored for delivery). `*` = all. CSV = staged wave |

First recommended wave:

```text
LLM_SEGMENT_PROFILES_BLOCKING_SEGMENTS=cleaning,plumber,electrician,accountant,lawyer
```

Do **not** put first:

- buy/supply transport (`moto-purchase`, `car-purchase`, `moto-sale`, `car-sale`, …)
- sports
- `pets`, `design`, `travel-agent`, `currency-exchange`

---

## Order (must not skip)

### 0. Dev (already on feature branch)

- [x] Phases 1–10 merged locally on feature branch
- [ ] `pytest -q tests/test_segment_llm_enablement.py tests/test_segment_llm_shadow.py`
- [ ] Owner review of PR / branch before any shared env

### 1. Staging DB (not production)

1. Stop staging worker (or use isolated compose project).
2. `pg_dump` staging.
3. `alembic upgrade head` → includes `segment_profiles01` + `segment_profile_audit01`.
4. Import profiles **staging only**:

```bash
LEADHUNTER_ALLOW_PROFILE_SEED=1 \
  venv/bin/python tools/validate_segment_profiles.py \
  --apply --i-understand-this-writes-to-db
```

(Host `db` is denylisted by the tool — use staging host/port.)

5. Restart **staging** worker/admin only after owner OK.
6. Confirm logs: profiles loaded count, no FloodWait.

### 2. Shadow ≥ 72 hours (staging or prod — owner chooses)

```text
LLM_SEGMENT_PROFILES_ENABLED=true
LLM_SEGMENT_PROFILES_BLOCKING=false
LLM_SEGMENT_PROFILES_BLOCKING_SEGMENTS=
```

Worker restart required for env (use `safe-deploy` / flat restart rules; do not compose-up while worker runs without owner).

Watch Redis (UTC hour keys, TTL 48h):

- `stats:llm_v2:total:*`
- `stats:llm_v2:disagreement_old_accept_new_reject:*`
- `stats:llm_v2:disagreement_old_reject_new_accept:*`
- `stats:llm_v2:fail_open:*`
- `stats:llm_v2:profile_missing:*`

Also review `llm_decisions.llm_reason` for `cid=` correlation.

### 3. Fix profiles / golden cases

- Admin → Categories → segment → **LLM-профиль** (draft → publish with reason)
- Re-run `tools/eval_segment_profiles.py`
- Update cases if needed via `tools/build_segment_profile_cases.py`

### 4. Blocking first wave (only after shadow review)

```text
LLM_SEGMENT_PROFILES_ENABLED=true
LLM_SEGMENT_PROFILES_BLOCKING=true
LLM_SEGMENT_PROFILES_BLOCKING_SEGMENTS=cleaning,plumber,electrician,accountant,lawyer
```

Observe ≥ 7 days: precision complaints, missed leads, fail-open rate, FloodWait.

### 5. Next waves

Add 3–5 slugs to the CSV after each quiet week. Prefer clear commercial niches.

### 6. Emergency rollback

```text
LLM_SEGMENT_PROFILES_BLOCKING=false
# optional: also disable v2 calls
LLM_SEGMENT_PROFILES_ENABLED=false
```

Restart worker per OPERATIONS. Profiles and audits stay for analysis — no migration downgrade required for blocking rollback.

---

## Helper

```bash
venv/bin/python tools/check_segment_profile_enablement.py
```

Prints current flag interpretation and the first-wave constant. Does not touch Redis/DB unless `--redis` is passed later.

---

## Production ban list for this phase alone

Without a separate owner command, agents must **not**:

- apply migrations on production
- seed profiles on production
- restart production worker
- flip production `.env` flags

---

## Review questions (Phase 11)

1. Lost lead risk → fail-open + empty allowlist fail-safe + ungated segments still dispatch.
2. Same text / other segment → allowlist only gates listed slugs.
3. `lead_direction` still from DB on bypass/prompt paths.
4–6. Vacancy/social/provider covered by profiles + Phase 7 bypass + offline corpus.
7. Fail-open preserved on v2 errors.
8. Profile version bumps invalidate cache key v2 after worker reload (5 min / restart).
9. Rollback = env flip; profile rollback via admin audit.
10–11. Per-segment / collision cases in Phase 9 fixture.
12. Production not auto-touched by this checklist.
