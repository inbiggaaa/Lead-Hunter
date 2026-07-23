# Closed Matching Feedback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Добавить закрытую двухуровневую разметку доставленных лидов с одной расширенной таблицей `feedback`, layer snapshots, аналитикой и экспортом.

**Architecture:** Существующая пустая таблица `feedback` становится одновременно immutable item snapshot и mutable current label. Sender создаёт item только для tester allowlist, бот обновляет verdict/reason по короткому token, а admin API/UI и eval читают одну каноническую запись на user/message/batch. Любая ошибка feedback-контура fail-open только для доставки лида, но не для аналитических выводов.

**Tech Stack:** Python 3.11+, aiogram 3, SQLAlchemy 2 async, PostgreSQL/Alembic, FastAPI, React 19/TypeScript/React Query, pytest, Redis для метрик.

## Global Constraints

- Source of truth: `docs/superpowers/specs/2026-07-24-closed-matching-feedback-design.md`.
- Не создавать `feedback_rounds`, `feedback_items`, `feedback_labels` или history tables.
- Не менять keywords, segment profiles, LLM blocking allowlist и тарифные лимиты.
- Новый интерфейс fail-closed: flag OFF или пустой tester allowlist скрывает его.
- Feedback failure не блокирует доставку уведомления.
- Сохранять только masked text; raw PII в feedback/logs/export запрещён.
- `uncertain` исключается из precision и gold.
- Все callback data не длиннее 64 bytes.
- RU и EN locale keys добавляются одновременно.
- Перед изменением `poller.py` прочитать `OPERATIONS.md` §2 и §5.
- Production, migrations, seed, env и worker не трогать без отдельной команды владельца.
- Перед каждой фазой показать владельцу список файлов; после подтверждения реализовать фазу.
- Каждая фаза заканчивается commit, tag `phase-N-done` и `/skill:phase-review`.

---

## File Map

**Create**

- `app/matching_feedback/__init__.py` — публичные типы и функции контура.
- `app/matching_feedback/domain.py` — verdict/reason taxonomy, callback codec, tester gate.
- `app/matching_feedback/repository.py` — create item, load by token, update current label.
- `app/matching_feedback/analytics.py` — summary, per-segment attribution, confusion matrix, export rows.
- `app/admin/api/matching_feedback.py` — защищённые endpoints аналитики/export.
- `admin-panel/src/pages/MatchingFeedbackPage.tsx` — один экран закрытого QA.
- `migrations/versions/matching_feedback_v2.py` — обратимая миграция одной таблицы.
- `tests/test_matching_feedback_domain.py`
- `tests/test_matching_feedback_repository.py`
- `tests/test_matching_feedback_handlers.py`
- `tests/test_matching_feedback_analytics.py`
- `tests/test_matching_feedback_api.py`
- `tests/test_matching_feedback_migration.py`
- `docs/ops/closed_matching_feedback_ru.md`

**Modify**

- `app/config.py`, `.env.example`
- `app/db/models.py`
- `app/userbot/llm_validator.py`
- `app/userbot/poller.py`
- `app/worker/sender.py`
- `app/bot/handlers/feedback.py`
- `app/locales/ru.py`, `app/locales/en.py`
- `app/admin/api/__init__.py`
- `app/admin/api/stats.py`
- `admin-panel/src/App.tsx`
- `admin-panel/src/components/layout/AppLayout.tsx`
- `tools/eval_matching.py`
- `tools/export_baseline.py`
- `tools/export_recall_template.py`
- `AGENTS.md`, `docs/SESSION_LOG.md`

## Interfaces

```python
# app/matching_feedback/domain.py
class FeedbackVerdict(StrEnum):
    CORRECT = "correct"
    ERROR = "error"
    UNCERTAIN = "uncertain"

class FeedbackReason(StrEnum):
    WRONG_CATEGORY = "wrong_category"
    PROVIDER_OFFER = "provider_offer"
    JOB_VACANCY = "job_vacancy"
    JOB_SEARCH = "job_search"
    SOCIAL_REQUEST = "social_request"
    DISCUSSION_NEWS = "discussion_news"
    WRONG_GEOGRAPHY = "wrong_geography"
    DUPLICATE = "duplicate"
    OTHER = "other"

@dataclass(frozen=True, slots=True)
class FeedbackSnapshot:
    test_batch: str
    user_id: int
    telegram_id: int
    chat_username: str
    message_id: int
    message_hash: str
    content_hash: str | None
    message_text_masked: str
    delivered_segments: tuple[str, ...]
    rule_segments: tuple[str, ...]
    reality_segments: tuple[str, ...]
    llm_snapshot: Mapping[str, object]

def encode_feedback_callback(action: str, token: str, value: str | None = None) -> str: ...
def decode_feedback_callback(data: str) -> FeedbackCallback: ...
def is_matching_feedback_tester(telegram_id: int) -> bool: ...

# app/matching_feedback/repository.py
async def get_or_create_feedback_item(
    snapshot: FeedbackSnapshot,
    *,
    session: AsyncSession | None = None,
) -> Feedback: ...
async def get_feedback_by_token(token: str, telegram_id: int) -> Feedback | None: ...
async def set_feedback_label(
    feedback_id: int,
    *,
    verdict: FeedbackVerdict,
    reason: FeedbackReason | None = None,
    confirmed_segments: tuple[str, ...] = (),
    expected_segment_id: int | None = None,
    expected_segment_slug: str | None = None,
    expected_segment_missing: bool = False,
) -> Feedback: ...

# app/matching_feedback/analytics.py
async def build_feedback_summary(batch: str) -> dict: ...
async def list_feedback_rows(batch: str, filters: FeedbackFilters) -> list[dict]: ...
async def export_feedback_jsonl(batch: str) -> AsyncIterator[bytes]: ...
async def export_feedback_csv(batch: str) -> AsyncIterator[bytes]: ...
```

---

### Task 1: Domain contract and closed-test configuration

**Phase:** 1
**Files:**

- Create: `app/matching_feedback/__init__.py`
- Create: `app/matching_feedback/domain.py`
- Modify: `app/config.py`
- Modify: `.env.example`
- Test: `tests/test_matching_feedback_domain.py`

**Produces:** taxonomy, callback codec and tester gate used by every later task.

- [ ] **Step 1: Write failing taxonomy and callback tests**

Cover:

```python
def test_error_requires_reason():
    with pytest.raises(ValueError):
        validate_label(FeedbackVerdict.ERROR, None, None, False)

def test_uncertain_rejects_reason():
    with pytest.raises(ValueError):
        validate_label(
            FeedbackVerdict.UNCERTAIN,
            FeedbackReason.OTHER,
            None,
            False,
        )

def test_correct_requires_confirmed_delivered_segment():
    with pytest.raises(ValueError):
        validate_label(
            FeedbackVerdict.CORRECT,
            None,
            confirmed_segments=("repair",),
            delivered_segments=("cleaning",),
        )

def test_callback_round_trip_stays_under_telegram_limit():
    data = encode_feedback_callback("reason", "AbCdEf123456", "wrong_category")
    assert len(data.encode()) <= 64
    assert decode_feedback_callback(data).value == "wrong_category"

def test_empty_tester_allowlist_is_fail_closed(monkeypatch):
    monkeypatch.setattr(settings, "matching_feedback_tester_ids", "")
    assert is_matching_feedback_tester(123) is False
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```bash
pytest -q tests/test_matching_feedback_domain.py
```

Expected: collection/import failure because `app.matching_feedback.domain` does not exist.

- [ ] **Step 3: Implement the domain module**

Add:

```python
@dataclass(frozen=True, slots=True)
class FeedbackCallback:
    action: str
    token: str
    value: str | None
```

Use an explicit action map with short wire codes. Reject unknown actions, malformed tokens and payloads over 64 bytes. Parse `MATCHING_FEEDBACK_TESTER_IDS` as a comma-separated frozenset of integers; malformed values must raise at startup rather than silently widening access.

Add settings:

```python
matching_feedback_enabled: bool = False
matching_feedback_tester_ids: str = ""
matching_feedback_batch: str = ""
```

- [ ] **Step 4: Verify GREEN**

Run:

```bash
pytest -q tests/test_matching_feedback_domain.py
```

Expected: all tests pass.

- [ ] **Step 5: Phase checkpoint**

Run:

```bash
git diff --check
pytest -q tests/test_matching_feedback_domain.py
git add app/matching_feedback app/config.py .env.example tests/test_matching_feedback_domain.py
git commit -m "feat(feedback): define closed-test domain contract"
git tag phase-1-done
```

Then run `/skill:phase-review`.

---

### Task 2: Reversible single-table schema and repository

**Phase:** 2
**Files:**

- Modify: `app/db/models.py`
- Create: `migrations/versions/matching_feedback_v2.py`
- Create: `app/matching_feedback/repository.py`
- Test: `tests/test_matching_feedback_repository.py`
- Test: `tests/test_matching_feedback_migration.py`

**Consumes:** enums and validation from Task 1.
**Produces:** one canonical row per `(batch, user, chat, message)`.

- [ ] **Step 1: Write failing model/repository tests**

Required cases:

```python
async def test_get_or_create_is_idempotent(db_session, feedback_snapshot):
    first = await get_or_create_feedback_item(feedback_snapshot, session=db_session)
    second = await get_or_create_feedback_item(feedback_snapshot, session=db_session)
    assert first.id == second.id

async def test_last_confirmed_label_replaces_current_value(...):
    row = await set_feedback_label(
        item.id,
        verdict=FeedbackVerdict.ERROR,
        reason=FeedbackReason.PROVIDER_OFFER,
    )
    changed = await set_feedback_label(
        item.id,
        verdict=FeedbackVerdict.CORRECT,
    )
    assert changed.verdict == "correct"
    assert changed.reason_code is None

async def test_foreign_user_cannot_load_token(...):
    assert await get_feedback_by_token(item.public_token, other_tg_id) is None
```

Migration test must assert upgrade, constraints, unique index and downgrade back to the legacy empty schema.

- [ ] **Step 2: Verify RED**

Run:

```bash
pytest -q tests/test_matching_feedback_repository.py tests/test_matching_feedback_migration.py
```

- [ ] **Step 3: Implement the migration**

Use `down_revision = "segment_profile_audit01"`. Alter only `feedback`; do not create auxiliary tables.

Required DB checks:

```sql
CHECK (verdict IS NULL OR verdict IN ('correct', 'error', 'uncertain'))
CHECK (reason_code IS NULL OR reason_code IN (...nine exact reason codes...))
CHECK (
  (verdict = 'error' AND reason_code IS NOT NULL)
  OR (verdict IS DISTINCT FROM 'error' AND reason_code IS NULL)
  OR verdict IS NULL
)
CHECK (NOT (expected_segment_id IS NOT NULL AND expected_segment_missing))
```

Add `confirmed_segments ARRAY(String)`, `expected_segment_slug`, FK `expected_segment_id → segments.id ON DELETE SET NULL`, unique token and unique batch/user/chat/message constraint. Preserve `expected_segment_slug` even if the catalog row is later removed.

Upgrade legacy rows deterministically: `test_batch='legacy'`, `relevant→correct`, `not_relevant→error/other`, generated unique tokens and delivered segments from the latest available decision where possible. Legacy rows remain excluded from the new batch. Production is currently empty, but the migration must still handle non-empty test fixtures.

The downgrade must restore columns required by the legacy model (`verdict NOT NULL` is not possible for unrated rows); therefore delete unrated experimental rows before restoring the old constraint and document this downgrade behavior in the migration docstring.

- [ ] **Step 4: Implement repository**

Generate token with `secrets.token_urlsafe(9)` and retry on the extremely unlikely token collision. Sanitize/validate snapshots before insert. Repository functions accept an optional session for tests and own a session otherwise.

- [ ] **Step 5: Verify DB gate**

Run against the isolated test DB:

```bash
pytest -q tests/test_matching_feedback_repository.py tests/test_matching_feedback_migration.py
alembic upgrade head
alembic downgrade -1
alembic upgrade head
```

Expected: tests pass, table returns to head, one Alembic head.

- [ ] **Step 6: Phase checkpoint**

```bash
git diff --check
git add app/db/models.py app/matching_feedback/repository.py migrations/versions/matching_feedback_v2.py tests/test_matching_feedback_repository.py tests/test_matching_feedback_migration.py
git commit -m "feat(feedback): add single-table feedback snapshots"
git tag phase-2-done
```

Then run `/skill:phase-review`.

---

### Task 3: Capture classifier and LLM layer snapshots

**Phase:** 3
**Files:**

- Modify: `app/userbot/llm_validator.py`
- Modify: `app/userbot/poller.py`
- Modify: `app/userbot/llm_profiles.py` only if a pure read helper is required
- Test: `tests/test_matching_feedback_snapshot.py`
- Test: existing `tests/test_segment_llm_shadow.py`
- Test: existing `tests/test_llm_blocking_mode.py`
- Test: existing `tests/test_poller_fixes.py`

**Consumes:** feedback snapshot fields from Task 2.
**Produces:** queue payload field `matching_feedback_snapshot`.

- [ ] **Step 1: Read safety rules**

Read `OPERATIONS.md` §2 and §5 before editing `poller.py`. Record in the phase notes that this task adds no Telegram API calls and changes no polling interval.

- [ ] **Step 2: Write failing snapshot tests**

Assert that shadow mode preserves both legacy and v2 decisions:

```python
assert snapshot["delivered_segments"] == ["cleaning"]
assert snapshot["rule_segments"] == ["cleaning", "repair"]
assert snapshot["reality_segments"] == ["cleaning"]
assert snapshot["legacy_llm_verdict"] == "DEMAND"
assert snapshot["v2_intent"] == "commercial_demand"
assert snapshot["profile_versions"]["cleaning"] == 1
```

Also test legacy-only, profile missing and keyword-only delivery.

- [ ] **Step 3: Add a typed snapshot to `LLMResult`**

Do not parse `raw_response` downstream. During `validate_batch`, populate a JSON-serializable feedback snapshot while both legacy and parsed v2 objects are available. Never include raw user text or full raw LLM response.

In `_flush_llm_batch`, pass:

```python
matching_snapshot=build_matching_feedback_snapshot(
    match=match,
    llm_result=llm_result,
    delivered_segments=active_segments,
)
```

Extend `_dispatch` and notification payload with stable slugs plus the snapshot. Keep display titles separate.

Сейчас `PendingMatch.candidate_segments` уже содержит результат reality-фильтра. Добавь отдельное поле `rule_segments` и заполняй его из `result.matched_segments` до reality-фильтра; `candidate_segments` оставь reality-confirmed списком. Не восстанавливай rule candidates эвристикой позднее.

- [ ] **Step 4: Verify hot-path regressions**

Run:

```bash
pytest -q \
  tests/test_matching_feedback_snapshot.py \
  tests/test_segment_llm_shadow.py \
  tests/test_llm_blocking_mode.py \
  tests/test_poller_fixes.py
```

Expected: all pass; no new external/network calls.

- [ ] **Step 5: Phase checkpoint**

```bash
git diff --check
git add app/userbot/llm_validator.py app/userbot/poller.py app/userbot/llm_profiles.py tests/test_matching_feedback_snapshot.py
git commit -m "feat(feedback): capture matching layer snapshots"
git tag phase-3-done
```

Then run `/skill:phase-review`.

---

### Task 4: Tester-gated sender keyboard without delivery coupling

**Phase:** 4
**Files:**

- Modify: `app/worker/sender.py`
- Modify: `tests/test_sender.py`
- Test: `tests/test_matching_feedback_sender.py`

**Consumes:** repository item creation and queue snapshot.
**Produces:** `mf:v1:*` keyboard only for testers.

- [ ] **Step 1: Write failing sender tests**

Cover:

```python
async def test_tester_gets_three_feedback_buttons(...):
    assert button_texts == ["✅ Верно", "⚠️ Ошибка", "🤷 Не уверен", ...]

async def test_non_tester_keeps_legacy_keyboard(...):
    assert "👍" in button_texts and "👎" in button_texts

async def test_feedback_db_failure_still_sends_lead(...):
    create_item.side_effect = RuntimeError("db unavailable")
    assert await sender._send_notification(payload) == "ok"
    sender.bot.send_message.assert_awaited_once()

async def test_retry_reuses_same_feedback_item(...):
    assert create_item.await_count == 1
```

- [ ] **Step 2: Verify RED**

```bash
pytest -q tests/test_matching_feedback_sender.py tests/test_sender.py
```

- [ ] **Step 3: Refactor keyboard input minimally**

Make `_build_keyboard(payload, feedback_token: str | None = None)`. Item creation occurs once before `_deliver_with_retry`; retries reuse the same keyboard and token.

Do not change Free paywall, paid chat/sender URLs, throttle, retry, dedup, digest or lifecycle behavior.

- [ ] **Step 4: Verify GREEN**

```bash
pytest -q tests/test_matching_feedback_sender.py tests/test_sender.py
```

- [ ] **Step 5: Phase checkpoint**

```bash
git diff --check
git add app/worker/sender.py tests/test_sender.py tests/test_matching_feedback_sender.py
git commit -m "feat(feedback): add closed-test notification keyboard"
git tag phase-4-done
```

Then run `/skill:phase-review`.

---

### Task 5: Two-level bot handlers and wrong-category correction

**Phase:** 5
**Files:**

- Modify: `app/bot/handlers/feedback.py`
- Modify: `app/locales/ru.py`
- Modify: `app/locales/en.py`
- Create: `tests/test_matching_feedback_handlers.py`
- Modify: locale schema/snapshot tests

**Consumes:** callback codec and repository.
**Produces:** complete tester UX.

- [ ] **Step 1: Write failing handler tests**

Required flows:

- single-segment `correct` saves immediately and shows summary/change.
- multi-segment `correct` opens a selector and saves one or more confirmed delivered segments.
- `uncertain` saves immediately.
- `error` only opens reasons and does not save an incomplete label.
- reason saves `error`.
- `wrong_category` saves, then shows candidate alternatives.
- catalog choice saves `expected_segment_id`.
- `category missing`, `skip`, `back`, `change`.
- stale token, foreign user, disabled flag, closed batch.
- DB commit succeeds but Telegram edit fails: label remains saved.

Example assertion:

```python
assert saved.verdict == FeedbackVerdict.ERROR
assert saved.reason == FeedbackReason.WRONG_CATEGORY
assert callback.message.edit_reply_markup.await_count == 1
```

- [ ] **Step 2: Verify RED**

```bash
pytest -q tests/test_matching_feedback_handlers.py
```

- [ ] **Step 3: Implement focused handler functions**

Keep the router file orchestration-only. Extract pure keyboard builders:

```python
def build_feedback_primary_keyboard(token: str, lang: str) -> InlineKeyboardMarkup: ...
def build_feedback_reason_keyboard(token: str, lang: str) -> InlineKeyboardMarkup: ...
def build_feedback_summary_keyboard(feedback: Feedback, lang: str) -> InlineKeyboardMarkup: ...
def build_confirmed_segments_keyboard(feedback: Feedback, lang: str) -> InlineKeyboardMarkup: ...
```

Reuse existing catalog reads; do not reuse the subscription FSM state because feedback category correction must not alter user subscriptions.

- [ ] **Step 4: Add exact RU/EN copy**

RU is the active test language, but every new locale key must exist in EN. Do not use casual promotional copy. Validation errors are neutral and do not expose internal IDs.

- [ ] **Step 5: Verify handlers and locale parity**

```bash
pytest -q tests/test_matching_feedback_handlers.py tests/test_userflow_u1_i18n.py
python tools/validate_locale_schema.py
```

- [ ] **Step 6: Phase checkpoint**

```bash
git diff --check
git add app/bot/handlers/feedback.py app/locales/ru.py app/locales/en.py tests/test_matching_feedback_handlers.py
git commit -m "feat(feedback): add two-level matching review flow"
git tag phase-5-done
```

Then run `/skill:phase-review`.

---

### Task 6: Canonical analytics, admin API and gold exports

**Phase:** 6
**Files:**

- Create: `app/matching_feedback/analytics.py`
- Create: `app/admin/api/matching_feedback.py`
- Modify: `app/admin/api/__init__.py`
- Modify: `app/admin/api/stats.py`
- Modify: `tools/eval_matching.py`
- Modify: `tools/export_baseline.py`
- Modify: `tools/export_recall_template.py`
- Create: `tests/test_matching_feedback_analytics.py`
- Create: `tests/test_matching_feedback_api.py`

**Consumes:** current labels and immutable snapshots.
**Produces:** one calculation path used by API, eval and export.

- [ ] **Step 1: Write failing aggregation tests**

Fixtures must cover:

- correct/error/uncertain/unrated;
- multi-segment item;
- multi-segment item with only one confirmed segment;
- wrong-category edge;
- missing snapshot;
- multiple batches;
- expected segment deleted with FK set null;
- PII markers absent from export.

Expected precision example:

```python
summary = aggregate_feedback(rows)
assert summary["rated"] == 3
assert summary["defined"] == 2
assert summary["uncertain"] == 1
assert summary["precision"] == 0.5
```

- [ ] **Step 2: Verify RED**

```bash
pytest -q tests/test_matching_feedback_analytics.py tests/test_matching_feedback_api.py
```

- [ ] **Step 3: Implement one canonical aggregator**

`app/admin/api/matching_feedback.py` and `tools/eval_matching.py` must call the same domain aggregation functions. Remove legacy joins to the latest mutable `llm_decisions` for experimental rows; snapshots are authoritative.

Extend `tools/export_recall_template.py` to produce a deduplicated masked sample of 50 unmatched and 50 LLM-rejected messages with manual columns `missed_lead`, `expected_segment`, `missed_at_layer`. Keep recall as a file-based eval artifact, not a runtime table.

Endpoints:

```text
GET /api/matching-feedback/summary?batch=ru_matching_v1
GET /api/matching-feedback/items?batch=...&verdict=...&reason=...&segment=...
GET /api/matching-feedback/export.csv?batch=...
GET /api/matching-feedback/export.jsonl?batch=...
```

- [ ] **Step 4: Verify export rules**

Assert:

- uncertain and unrated excluded from gold;
- wrong_category without expected segment marked `intent_only=true`;
- no telegram ID, sender, phone, raw link or raw message text;
- stable ordering and UTF-8.

- [ ] **Step 5: Verify GREEN**

```bash
pytest -q tests/test_matching_feedback_analytics.py tests/test_matching_feedback_api.py
```

- [ ] **Step 6: Phase checkpoint**

```bash
git diff --check
git add app/matching_feedback/analytics.py app/admin/api/matching_feedback.py app/admin/api/__init__.py app/admin/api/stats.py tools/eval_matching.py tools/export_baseline.py tools/export_recall_template.py tests/test_matching_feedback_analytics.py tests/test_matching_feedback_api.py
git commit -m "feat(feedback): add matching quality analytics and exports"
git tag phase-6-done
```

Then run `/skill:phase-review`.

---

### Task 7: Minimal admin QA page

**Phase:** 7
**Files:**

- Create: `admin-panel/src/pages/MatchingFeedbackPage.tsx`
- Modify: `admin-panel/src/App.tsx`
- Modify: `admin-panel/src/components/layout/AppLayout.tsx`
- Build output: `app/admin/static/`

**Consumes:** Task 6 API.
**Produces:** owner-facing analysis without a general experiment platform.

- [ ] **Step 1: Add page behavior**

The page contains:

- batch input/filter;
- KPI cards: delivered, rated, precision, uncertain, missing snapshot;
- per-segment table;
- reasons distribution;
- confusion matrix table;
- filtered masked examples;
- CSV/JSONL download links.

No create/delete round UI, no automatic keyword/profile actions.

- [ ] **Step 2: Add frontend tests if the project test harness supports them**

At minimum, type-check API response types and verify empty/loading/error states through lint/build. Do not introduce a new frontend test framework only for this page.

- [ ] **Step 3: Run frontend gate**

```bash
cd admin-panel
npm ci
npm run lint
npm run build
```

Expected: exit 0 and updated static bundle.

- [ ] **Step 4: Phase checkpoint**

```bash
git diff --check
git add admin-panel/src app/admin/static
git commit -m "feat(admin): add closed matching QA dashboard"
git tag phase-7-done
```

Then run `/skill:phase-review`.

---

### Task 8: Full regression, operations runbook and release gate

**Phase:** 8
**Files:**

- Create: `docs/ops/closed_matching_feedback_ru.md`
- Modify: `TESTING.md` if a new command is added
- Modify: `AGENTS.md`
- Modify: `docs/SESSION_LOG.md`

- [ ] **Step 1: Write the exact runbook**

Include:

- subscribe in waves of 5–10 categories;
- generate and label the 50 unmatched + 50 LLM-rejected recall sample for each batch;
- backup path and restore command;
- worker stop rule before migration/deploy;
- migration dry run on test DB;
- tester env values without real Telegram ID in git;
- smoke scenarios;
- metrics and quality gates;
- rollback `MATCHING_FEEDBACK_ENABLED=false`;
- explicit statement that segment-aware LLM blocking is separate.

- [ ] **Step 2: Run focused backend gate**

```bash
pytest -q \
  tests/test_matching_feedback_domain.py \
  tests/test_matching_feedback_repository.py \
  tests/test_matching_feedback_migration.py \
  tests/test_matching_feedback_snapshot.py \
  tests/test_matching_feedback_sender.py \
  tests/test_matching_feedback_handlers.py \
  tests/test_matching_feedback_analytics.py \
  tests/test_matching_feedback_api.py \
  tests/test_sender.py \
  tests/test_segment_llm_shadow.py \
  tests/test_llm_blocking_mode.py
```

- [ ] **Step 3: Run full project gate**

```bash
pytest tests/ -v --tb=short
cd admin-panel && npm run lint && npm run build
alembic heads
```

Expected: zero failures, frontend exit 0, exactly one Alembic head.

- [ ] **Step 4: Static safety checks**

```bash
rg -n "MATCHING_FEEDBACK_" .env.example app/config.py docs/ops/closed_matching_feedback_ru.md
rg -n "phone|sender|telegram_id|message_text" app/matching_feedback app/admin/api/matching_feedback.py
git diff --check
```

Review every hit for PII leakage; identifiers may be used for authorization but must not appear in exports/logs.

- [ ] **Step 5: Final commit and tag**

```bash
git add docs/ops/closed_matching_feedback_ru.md TESTING.md AGENTS.md docs/SESSION_LOG.md
git commit -m "docs: add closed matching feedback rollout"
git tag phase-8-done
```

Run `/skill:phase-review`, then request code review. Do not merge until CI is green.

## Execution Handoff

After the implementation PR is green:

1. Merge code with flags OFF.
2. Do not approve production Deploy automatically.
3. Validate migration in staging/test DB.
4. Apply staging migration and enable only owner tester.
5. Smoke all four core flows.
6. Only with explicit owner approval schedule production backup, worker stop, migration, restart and two-minute FloodWait monitoring.
