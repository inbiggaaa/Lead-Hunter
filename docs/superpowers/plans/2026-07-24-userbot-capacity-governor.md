# Userbot Capacity Governor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Защитить userbot-аккаунты от повторных FloodWait, автоматически управлять их мощностью и показывать владельцу, когда требуется новый аккаунт, сохраняя минимальную задержку лидов.

**Architecture:** Расширить существующий `TelegramRateLimiter` до единой RPC-границы с Redis-метриками и governor state. Заменить непрерывный полный обход на один адаптивный due-loop внутри текущего worker: eligible chats хранят простой `empty_streak/next_poll_at`, выдаются ограниченными slices и немедленно прекращают работу при PAUSED/COOLDOWN. Admin API читает те же Redis-данные и показывает компактный fleet summary, карточки аккаунтов и один RPC-график.

**Tech Stack:** Python 3.11, Telethon 1.x, asyncio, Redis 5/AOF, FastAPI, React 19, TypeScript, React Query 5, Chart.js 4, pytest/pytest-asyncio.

## Global Constraints

- Перед любым изменением `poller.py`, `rate_limiter.py` или `pool.py` полностью прочитать `OPERATIONS.md` §2 и §5.
- Начать от актуального `origin/main`; не реализовывать поверх устаревшего локального main.
- Production, production Redis/PostgreSQL, session-файлы и работающий worker не изменять.
- Никаких live Telegram-тестов без отдельного разрешения владельца.
- Первая версия не создаёт PostgreSQL-миграций и не добавляет новый процесс.
- Метрики/state хранятся в Redis/AOF; тексты сообщений, phone, api_hash и session contents не сохраняются.
- Safe daily budget по умолчанию: `4000` RPC на аккаунт; reserve: `30%`.
- Telegram safety всегда важнее SLO.
- География без активных подписчиков: `0` polling RPC.
- Никаких dashboard-кнопок start/stop/reset/change-limit.
- Background Telegram updates не отключать и не переводить в event-driven режим в этой задаче.
- Каждая задача: failing test → минимальная реализация → targeted suite → regression suite → commit → тег `userbot-governor-phase-N-done`.
- После каждой задачи запускать `/skill:phase-review`; исправлять blocker до следующей задачи.

---

## File Structure

### Create

- `app/userbot/capacity.py` — чистые типы и расчёты governor/recovery/capacity.
- `app/userbot/poll_schedule.py` — чистая политика `empty_streak → class/interval/next_poll_at` и Redis-сериализация.
- `app/admin/api/userbot_capacity.py` — read-only fleet/account capacity API.
- `admin-panel/src/components/dashboard/UserbotCapacity.tsx` — компактный dashboard-блок.
- `tests/test_userbot_capacity.py` — unit state machine/capacity tests.
- `tests/test_poll_schedule.py` — unit schedule/backoff tests.
- `tests/test_userbot_capacity_api.py` — API aggregation tests.

### Modify

- `app/config.py` — только необходимые governor/schedule settings.
- `.env.example` — документировать новые settings.
- `app/userbot/rate_limiter.py` — RPC buckets, governor permit, FloodWait/cooldown/recovery.
- `app/userbot/pool.py` — `flood_sleep_threshold=0`; health RPC через limiter boundary.
- `app/userbot/poller.py` — единый adaptive due-loop, bounded slices, state checks, poll outcomes.
- `app/cache/subscription_cache.py` — bump eligibility generation через существующую общую invalidation.
- `app/admin/api/__init__.py` — подключить capacity router.
- `admin-panel/src/pages/DashboardPage.tsx` — вставить `UserbotCapacity`.
- `tests/test_rate_limiter.py` — governor integration и Redis persistence.
- `tests/test_poller_fixes.py` — mid-slice stop, no takeover, cursor safety.
- `tests/test_tier_geo.py` — geo eligibility и immediate rebuild.
- `tests/test_cache_invalidation.py` — eligibility generation меняется при общей invalidation.
- `tests/test_pool.py` — short FloodWait is not hidden.
- `scripts/watchdog.sh` — только новые CRITICAL governor/fleet signals.
- `tests/test_watchdog_integrity.py` — дедупликация новых сигналов.
- `OPERATIONS.md`, `TESTING.md`, `AGENTS.md`, `docs/SESSION_LOG.md` — runbook и результат фаз.

---

### Task 1: Pure governor model and configuration

**Files:**
- Create: `app/userbot/capacity.py`
- Create: `tests/test_userbot_capacity.py`
- Modify: `app/config.py`
- Modify: `.env.example`

**Interfaces:**
- Produces: `GovernorState`, `FloodSeverity`, `RecoveryStage`, `GovernorSnapshot`.
- Produces: `classify_flood(seconds: int) -> FloodSeverity`.
- Produces: `recovery_plan(severity: FloodSeverity) -> tuple[RecoveryStage, ...]`.
- Produces: `capacity_required(projected_daily_rpc: int, account_count: int, safe_daily_budget: int, reserve_ratio: float) -> CapacityResult`.
- Consumes: no application I/O; module remains pure.

- [ ] **Step 1: Add failing state/recovery tests**

```python
from app.userbot.capacity import (
    FloodSeverity,
    GovernorState,
    capacity_required,
    classify_flood,
    recovery_plan,
)


def test_classify_flood_boundaries() -> None:
    assert classify_flood(60) is FloodSeverity.SHORT
    assert classify_flood(61) is FloodSeverity.MEDIUM
    assert classify_flood(1800) is FloodSeverity.MEDIUM
    assert classify_flood(1801) is FloodSeverity.LONG


def test_long_recovery_is_gradual() -> None:
    stages = recovery_plan(FloodSeverity.LONG)
    assert [stage.power_percent for stage in stages] == [10, 25, 50, 75, 100]
    assert [stage.hold_seconds for stage in stages[:-1]] == [1800, 3600, 7200, 14400]


def test_capacity_keeps_thirty_percent_reserve() -> None:
    result = capacity_required(
        projected_daily_rpc=8000,
        account_count=2,
        safe_daily_budget=4000,
        reserve_ratio=0.30,
    )
    assert result.usable_per_account == 2800
    assert result.required_accounts == 3
    assert result.additional_accounts == 1
    assert result.has_deficit is True
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
pytest tests/test_userbot_capacity.py -q
```

Expected: collection error because `app.userbot.capacity` does not exist.

- [ ] **Step 3: Implement pure types and calculations**

Use `StrEnum` and frozen dataclasses. Exact recovery defaults:

```python
class GovernorState(StrEnum):
    NORMAL = "NORMAL"
    THROTTLED = "THROTTLED"
    COOLDOWN = "COOLDOWN"
    RECOVERY = "RECOVERY"
    QUARANTINED = "QUARANTINED"
    OFFLINE = "OFFLINE"


class FloodSeverity(StrEnum):
    SHORT = "short"
    MEDIUM = "medium"
    LONG = "long"


@dataclass(frozen=True)
class RecoveryStage:
    power_percent: int
    hold_seconds: int


@dataclass(frozen=True)
class CapacityResult:
    projected_daily_rpc: int
    usable_per_account: int
    required_accounts: int
    additional_accounts: int
    utilization_percent: int
    has_deficit: bool
```

`GovernorSnapshot` fields are fixed for v1:

```python
@dataclass(frozen=True)
class GovernorSnapshot:
    account_id: int
    state: GovernorState
    power_percent: int
    recommended_state: GovernorState
    recommended_power_percent: int
    severity: FloodSeverity | None
    cooldown_until: int | None
    stage_index: int | None
    stage_until: int | None
    stable_windows: int
    last_flood_at: int | None
    last_flood_seconds: int
    last_rpc_at: int | None
    continuous_started_at: int | None
```

Rules:

```python
SHORT = ((25, 600), (50, 900), (75, 1800), (100, 0))
MEDIUM = ((10, 900), (25, 1800), (50, 3600), (75, 7200), (100, 0))
LONG = ((10, 1800), (25, 3600), (50, 7200), (75, 14400), (100, 0))
```

`capacity_required` must use `ceil(projected / floor(safe_budget * (1-reserve)))`.
When `account_count == 0`, utilization is `100` and required count still returns
the mathematical requirement.

- [ ] **Step 4: Add exact configuration**

Add to `Settings`:

```python
userbot_safe_daily_budget: int = 4000
userbot_capacity_reserve_ratio: float = 0.30
userbot_poll_slice_size: int = 25
userbot_governor_soft_percent: int = 70
userbot_governor_hard_percent: int = 85
userbot_governor_stop_percent: int = 95
userbot_max_continuous_minutes: int = 45
userbot_recovery_stable_windows: int = 3
userbot_rpc_metrics_enabled: bool = True
userbot_governor_enforcing: bool = False
userbot_adaptive_polling_enabled: bool = False
```

Validate through tests that percentages are ordered and reserve is between
`0.0` and `0.9`; fail application startup on invalid values.

- [ ] **Step 5: Run targeted tests**

Run:

```bash
pytest tests/test_userbot_capacity.py tests/test_tariffs_v2_config.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit and tag**

```bash
git add app/userbot/capacity.py app/config.py .env.example tests/test_userbot_capacity.py
git commit -m "feat(userbot): add capacity governor model"
git tag userbot-governor-phase-1-done
```

---

### Task 2: Central RPC accounting and FloodWait governor

**Files:**
- Modify: `app/userbot/rate_limiter.py`
- Modify: `app/userbot/pool.py`
- Modify: `tests/test_rate_limiter.py`
- Modify: `tests/test_pool.py`
- Test: `tests/test_userbot_capacity.py`

**Interfaces:**
- Consumes: Task 1 capacity types.
- Produces: `GovernorBlocked(account_id: int, retry_at: int, state: GovernorState)`.
- Produces: `TelegramRateLimiter.acquire(account_id: int, rpc_kind: str) -> None`.
- Produces: `record_rpc_result(account_id: int, rpc_kind: str, outcome: str) -> None`.
- Produces: `get_governor_snapshot(account_id: int) -> GovernorSnapshot`.
- Produces: `refresh_governor(account_id: int, now: int | None = None) -> GovernorSnapshot`.

- [ ] **Step 1: Write failing Redis accounting tests**

Cover:

```python
@pytest.mark.asyncio
async def test_acquire_records_minute_hour_day_attempt_buckets(
    limiter: TelegramRateLimiter,
    redis: FakeRedis,
) -> None:
    await limiter.acquire(2, rpc_kind="get_history")
    minute = await redis.hgetall(limiter.minute_bucket_key)
    hour = await redis.hgetall(limiter.hour_bucket_key)
    day = await redis.hgetall(limiter.day_bucket_key)
    assert minute["attempt"] == "1"
    assert hour["get_history"] == "1"
    assert day["total"] == "1"


@pytest.mark.asyncio
async def test_any_flood_wait_enters_cooldown(
    limiter: TelegramRateLimiter,
    fixed_now: int,
) -> None:
    await limiter.report_flood_wait(
        seconds=17,
        context="poller:@chat",
        account_id=2,
        rpc_kind="get_history",
    )
    snapshot = await limiter.get_governor_snapshot(2)
    assert snapshot.state is GovernorState.COOLDOWN
    assert snapshot.power_percent == 0
    assert snapshot.cooldown_until > fixed_now + 17


@pytest.mark.asyncio
async def test_long_flood_expires_into_ten_percent_recovery(
    limiter: TelegramRateLimiter,
) -> None:
    await limiter.report_flood_wait(3600, "poller:@chat", 2, "get_history")
    stored = await limiter.get_governor_snapshot(2)
    assert stored.cooldown_until is not None
    snapshot = await limiter.refresh_governor(
        2,
        now=stored.cooldown_until + 1,
    )
    assert snapshot.state is GovernorState.RECOVERY
    assert snapshot.power_percent == 10
```

Reuse the test module's current Redis patching style. If no shared Redis fixture
exists, add a local `fakeredis.aioredis.FakeRedis(decode_responses=True)`
fixture; do not introduce a second limiter implementation for tests.

- [ ] **Step 2: Verify RED**

Run:

```bash
pytest tests/test_rate_limiter.py -q
```

Expected: failures for missing `rpc_kind`, snapshot and recovery interfaces.

- [ ] **Step 3: Store compact Redis buckets**

Use hashes:

```text
stats:tg_rpc:{account_id}:minute:{YYYYMMDDHHMM}
stats:tg_rpc:{account_id}:hour:{YYYYMMDDHH}
stats:tg_rpc:{account_id}:day:{YYYYMMDD}
```

Fields: `total`, `attempt`, `success`, `error`, `flood_wait`,
`get_history`, `resolve`, `health`.

TTL: minute 2 days, hour 8 days, day 30 days. Update all three buckets through
one Redis pipeline. Do not use key scans in hot path.
When `userbot_rpc_metrics_enabled=false`, retain existing rate limiting without
writing the new buckets.

- [ ] **Step 4: Persist governor in one Redis hash**

Key:

```text
userbot:governor:{account_id}
```

Fields:

```text
state, power_percent, recommended_state, recommended_power_percent,
severity, cooldown_until, stage_index,
stage_until, stable_windows, last_flood_at, last_flood_seconds,
last_rpc_at, continuous_started_at
```

Preserve existing `circuit:*`, `last_ban_at:*` and `ban_count:*` keys during
compatibility rollout. `is_circuit_open()` must consider governor COOLDOWN and
QUARANTINED.

- [ ] **Step 5: Make acquire fail fast**

`acquire` must:

1. call `refresh_governor`;
2. raise `GovernorBlocked` for COOLDOWN/QUARANTINED/OFFLINE or
   `power_percent == 0`;
3. apply effective interval `min_interval * (100 / power_percent)`;
4. update attempt buckets and existing budget;
5. never sleep for the entire FloodWait duration.

Redis failure must raise `GovernorBlocked` and prevent Telegram RPC.

- [ ] **Step 6: Expose all FloodWait to application**

In `UserbotAccount` set Telethon `flood_sleep_threshold=0`. Add a unit test
asserting the client constructor receives `0`.

Do not disable updates. Do not change device identity, connection mode or
session files.

- [ ] **Step 7: Route health checks through limiter**

`check_health()` must acquire with `rpc_kind="health"` before `get_me()`.
On governor block it returns the previous health state without calling Telegram;
it must not mark a cooling account unhealthy.

- [ ] **Step 8: Verify targeted regression**

Run:

```bash
pytest tests/test_rate_limiter.py tests/test_pool.py tests/test_pool_identity.py -q
```

Expected: all tests pass; no real network calls.

- [ ] **Step 9: Commit and tag**

```bash
git add app/userbot/rate_limiter.py app/userbot/pool.py tests/test_rate_limiter.py tests/test_pool.py
git commit -m "feat(userbot): centralize RPC governor and FloodWait handling"
git tag userbot-governor-phase-2-done
```

---

### Task 3: Adaptive schedule, bounded slices and exact geo gate

**Files:**
- Create: `app/userbot/poll_schedule.py`
- Create: `tests/test_poll_schedule.py`
- Modify: `app/userbot/poller.py`
- Modify: `app/cache/subscription_cache.py`
- Modify: `tests/test_poller_fixes.py`
- Modify: `tests/test_tier_geo.py`
- Modify: `tests/test_cache_invalidation.py`

**Interfaces:**
- Produces: `PollClass`, `PollScheduleState`, `PollOutcome`.
- Produces: `next_schedule(previous: PollScheduleState | None, outcome: PollOutcome, now: int) -> PollScheduleState`.
- Produces: `PollScheduleStore.load()`, `.save(chat_username, state)`,
  `.remove(chat_username)`, `.save_summary(summary)`.
- Consumes: `GovernorBlocked`, `refresh_governor`, geo eligibility from existing `_get_active_geo`.

- [ ] **Step 1: Write failing pure schedule tests**

```python
def test_new_chat_starts_standard() -> None:
    state = next_schedule(None, PollOutcome(new_messages=0, error_kind=None), now=1000)
    assert state.poll_class is PollClass.C
    assert state.next_poll_at == 1000 + 900


def test_message_promotes_to_realtime() -> None:
    previous = PollScheduleState(PollClass.E, empty_streak=100, next_poll_at=0)
    state = next_schedule(
        previous,
        PollOutcome(new_messages=1, error_kind=None),
        now=1000,
    )
    assert state.poll_class is PollClass.A
    assert state.empty_streak == 0
    assert state.next_poll_at == 1120


@pytest.mark.parametrize(
    ("start_class", "empty_streak", "expected_class", "seconds"),
    [
        (PollClass.A, 3, PollClass.B, 300),
        (PollClass.B, 10, PollClass.C, 900),
        (PollClass.C, 30, PollClass.D, 3600),
        (PollClass.D, 100, PollClass.E, 21600),
    ],
)
def test_empty_streak_backoff(
    start_class,
    empty_streak,
    expected_class,
    seconds,
) -> None:
    previous = PollScheduleState(
        poll_class=start_class,
        empty_streak=empty_streak - 1,
        error_streak=0,
        next_poll_at=0,
        last_message_at=None,
        is_quarantined=False,
    )
    state = next_schedule(
        previous,
        PollOutcome(new_messages=0, error_kind=None),
        now=1000,
    )
    assert state.poll_class is expected_class
    assert state.empty_streak == empty_streak
    assert state.next_poll_at == 1000 + seconds


def test_empty_new_standard_chat_never_promotes_without_messages() -> None:
    previous = PollScheduleState(
        poll_class=PollClass.C,
        empty_streak=2,
        error_streak=0,
        next_poll_at=0,
        last_message_at=None,
        is_quarantined=False,
    )
    state = next_schedule(
        previous,
        PollOutcome(new_messages=0, error_kind=None),
        now=1000,
    )
    assert state.poll_class is PollClass.C
    assert state.next_poll_at == 1900
```

Error backoff cases: 1h, 6h, 24h, 7d, then quarantine.

- [ ] **Step 2: Verify RED**

Run:

```bash
pytest tests/test_poll_schedule.py -q
```

Expected: module missing.

- [ ] **Step 3: Implement schedule policy and compact Redis state**

Persist all states in:

```text
poll:schedule:v1
poll:summary:v1
```

Field is normalized `chat_username`; value is compact JSON containing
`poll_class`, `empty_streak`, `error_streak`, `next_poll_at`,
`last_message_at`, `is_quarantined`.

`poll:summary:v1` is a small hash updated after eligibility rebuild and
distribution. Required fields: `eligible`, `parked`, `quarantined`,
`class:A`..`class:E`, and `assigned:{account_id}`. This is the read-only API
source; the API must not parse every schedule entry merely to render dashboard.

Load once at worker start; update individual fields after each poll. Redis
failure blocks new polling through governor fail-closed; do not silently reset
all chats to due.

- [ ] **Step 4: Return PollOutcome without touching matching behavior**

Change `_poll_channel` to return:

```python
@dataclass(frozen=True)
class PollOutcome:
    new_messages: int
    error_kind: str | None
```

`new_messages` is the count returned by Telegram before text/age filtering.
Matching, LLM, cursor and dispatch logic remain unchanged. On FloodWait, do not
advance cursor and re-raise. On invalid/private errors, return the exact stable
error kind used by schedule backoff.

- [ ] **Step 5: Replace full-cycle timing with one due-loop**

Inside the existing worker, not a new service:

1. Rebuild eligible channel list using existing DB queries.
2. Merge catalog and active manual watched channels by username.
3. Read in-memory schedule and select `next_poll_at <= now`.
4. Sort by `next_poll_at`, then A/B before C/D/E.
5. Distribute only due channels across available accounts.
6. Poll at most `userbot_poll_slice_size * power_percent / 100`, minimum 1.
7. Re-check session state and governor before every channel.
8. Sleep 5 seconds when due work remains, otherwise until nearest due with a
   maximum sleep of 30 seconds.

Delete obsolete “elapsed > interval → sleep 5s and repeat full tier” behavior.
Do not retain two schedulers for the same catalog channels.
Keep the existing tier loop behind
`userbot_adaptive_polling_enabled=false` during shadow rollout; only one path
may run in a process.

- [ ] **Step 6: Prevent failover overload**

When an account becomes unavailable:

- do not increase another account's slice;
- backlog remains due;
- capacity planner reports deficit;
- pinned chats for the unavailable account remain unpolled;
- A/B are selected before lower classes within the safe slice.

- [ ] **Step 7: Enforce exact geo eligibility**

Add integration tests:

```python
@pytest.mark.asyncio
async def test_country_without_subscribers_produces_zero_poll_calls(
    poller: ChannelPoller,
    inactive_country_id: int,
) -> None:
    await poller._rebuild_eligible_channels()
    assert all(
        channel["country_id"] != inactive_country_id
        for channel in poller._eligible_channels
    )


@pytest.mark.asyncio
async def test_city_channel_requires_city_intersection(
    poller: ChannelPoller,
    subscribed_city_id: int,
) -> None:
    await poller._rebuild_eligible_channels()
    city_channels = [
        channel
        for channel in poller._eligible_channels
        if channel["city_ids"]
    ]
    assert all(
        subscribed_city_id in channel["city_ids"]
        for channel in city_channels
    )


@pytest.mark.asyncio
async def test_countrywide_channel_is_eligible_for_city_subscriber(
    poller: ChannelPoller,
    countrywide_username: str,
) -> None:
    await poller._rebuild_eligible_channels()
    usernames = {
        channel["chat_username"]
        for channel in poller._eligible_channels
    }
    assert countrywide_username in usernames
```

Use the existing factories and `_rebuild` helper in `tests/test_tier_geo.py`;
the snippets define the assertions, not mandatory new fixture names.

Extend existing `invalidate_all_subscription_caches()` to increment
`poll:eligibility:generation`. The adaptive loop remembers the last value,
checks it before selecting due work and calls `_rebuild_eligible_channels()` on
change. Because all subscription CRUD already uses the common invalidation, do
not add repeated generation writes to individual handlers.

- [ ] **Step 8: Test the original incident shape**

Create a deterministic test with 753 due chats, two accounts and slice size 25:

- account 2 transitions to PAUSED after 10 polls;
- no 11th Telegram call occurs for account 2;
- account 1 performs no more than its own allowed slice;
- no full takeover;
- backlog remains scheduled;
- no cursor advances for unpolled chats.

- [ ] **Step 9: Run poller regression**

Run:

```bash
pytest tests/test_poll_schedule.py tests/test_poller_fixes.py tests/test_tier_geo.py tests/test_cache_invalidation.py tests/test_variant_b.py -q
```

Expected: all tests pass.

- [ ] **Step 10: Commit and tag**

```bash
git add app/userbot/poll_schedule.py app/userbot/poller.py app/cache/subscription_cache.py tests/test_poll_schedule.py tests/test_poller_fixes.py tests/test_tier_geo.py tests/test_cache_invalidation.py
git commit -m "feat(userbot): poll eligible chats with adaptive safe slices"
git tag userbot-governor-phase-3-done
```

---

### Task 4: Automatic throttle/recovery and Telegram alerts

**Files:**
- Modify: `app/userbot/rate_limiter.py`
- Modify: `app/userbot/poller.py`
- Modify: `app/worker/notify_admin.py` only if a small reusable formatter is necessary
- Modify: `scripts/watchdog.sh`
- Modify: `tests/test_rate_limiter.py`
- Modify: `tests/test_watchdog_integrity.py`

**Interfaces:**
- Consumes: Redis buckets and recovery plans.
- Produces: one idempotent `refresh_governor` transition per account.
- Produces: deduplicated alert keys `alert:last:userbot_governor:{account_id}:{event}`.

- [ ] **Step 1: Write failing proactive throttle tests**

Cover:

- projected/safe utilization >70% → `THROTTLED`, power 75%;
- >85% → power 50%;
- >95% → `THROTTLED` at 0%, block new RPC until next UTC day;
- continuous activity 45 minutes → mandatory randomized pause of 5–10 minutes;
- three safe 5-minute windows → one power step upward;
- unsafe window → step rollback;
- FloodWait during recovery → COOLDOWN and severity escalation.

- [ ] **Step 2: Implement one transition function**

All state changes go through
`refresh_governor(self, account_id: int, *, now: int | None = None) ->
GovernorSnapshot`. It loads the RPC window and persisted snapshot, calculates
exactly one next state, atomically persists changed fields, and returns the
persisted result.

Do not duplicate transition rules in poller, dashboard or watchdog.
When `userbot_governor_enforcing=false`, proactive thresholds are calculated
and stored only in `recommended_state/recommended_power_percent`; effective
`state/power_percent` do not change and do not block RPC. An actual FloodWait
and existing circuit breaker change the effective state and remain fail-closed
regardless of flag.

- [ ] **Step 3: Make recovery automatic**

At worker start and once per minute:

- refresh each account;
- persist stage and deadlines;
- after COOLDOWN use severity-specific stages;
- after proactive 0% stop use 50 → 75 → 100 only after three safe windows;
- ordinary 50%/75% THROTTLED also rises by one step after three safe windows;
- never jump directly from COOLDOWN to NORMAL;
- worker restart resumes the stored stage.

- [ ] **Step 4: Add deduplicated alerts**

Exact events:

```text
throttled
capacity_85
capacity_95
flood_wait
recovery_started
recovery_step
recovery_rollback
normal_restored
quarantined
fleet_deficit
```

Alert contains account ID, state, power, RPC 1h/24h, safe budget, cooldown or
stage deadline, eligible chat count and additional account recommendation.
Cooldown for repeated same event: 30 minutes; state transition alerts are sent
once per transition.

- [ ] **Step 5: Extend watchdog only for stale/missing governor**

Watchdog checks:

- Redis governor state exists for every configured account;
- `last_rpc_at`/heartbeat freshness;
- CRITICAL capacity deficit persists >15 minutes;
- no duplicate notifications for unchanged cumulative counters.

It must not mutate governor state.

- [ ] **Step 6: Run targeted tests**

```bash
pytest tests/test_rate_limiter.py tests/test_watchdog_integrity.py tests/test_poller_fixes.py -q
```

Expected: all pass.

- [ ] **Step 7: Commit and tag**

```bash
git add app/userbot/rate_limiter.py app/userbot/poller.py app/worker/notify_admin.py scripts/watchdog.sh tests/test_rate_limiter.py tests/test_watchdog_integrity.py
git commit -m "feat(userbot): automate throttling recovery and alerts"
git tag userbot-governor-phase-4-done
```

If `notify_admin.py` was not changed, omit it from `git add`.

---

### Task 5: Read-only capacity API and compact dashboard

**Files:**
- Create: `app/admin/api/userbot_capacity.py`
- Create: `tests/test_userbot_capacity_api.py`
- Create: `admin-panel/src/components/dashboard/UserbotCapacity.tsx`
- Modify: `app/admin/api/__init__.py`
- Modify: `admin-panel/src/pages/DashboardPage.tsx`

**Interfaces:**
- Produces: `GET /api/stats/userbots`.
- Consumes: configured account IDs, governor hashes, RPC buckets, schedule summary.
- UI refetch: 30 seconds.

- [ ] **Step 1: Write failing API contract tests**

Expected response:

```json
{
  "fleet": {
    "configured_accounts": 2,
    "available_accounts": 1,
    "required_accounts": 5,
    "additional_accounts": 4,
    "utilization_percent": 88,
    "projected_daily_rpc": 11200,
    "safe_daily_capacity": 2800,
    "eligible_chats": 753,
    "parked_chats": 1074,
    "has_deficit": true
  },
  "accounts": [
    {
      "account_id": 1,
      "state": "THROTTLED",
      "power_percent": 50,
      "recommended_state": "THROTTLED",
      "recommended_power_percent": 50,
      "rpc_5m": 80,
      "rpc_1h": 760,
      "rpc_6h": 2900,
      "rpc_24h": 3700,
      "safe_daily_budget": 4000,
      "utilization_percent": 92,
      "continuous_minutes": 42,
      "assigned_chats": 377,
      "cooldown_until": null,
      "stage_until": 1780000000,
      "last_flood_seconds": 0,
      "last_rpc_at": 1779999900
    }
  ],
  "rpc_minutes": [
    {"minute": "2026-07-24T05:15:00Z", "account_id": 1, "count": 25}
  ]
}
```

Missing Redis fields return `null`/zero plus `state="OFFLINE"`; endpoint still
returns HTTP 200. It never invokes Telegram.

- [ ] **Step 2: Implement API aggregation**

Use Redis pipelines and `poll:summary:v1`; no PostgreSQL query and no wildcard
scan over all Redis.
Account IDs come from `settings.userbot_sessions`. Aggregate only the last
60 minute keys and the necessary hour/day keys.

- [ ] **Step 3: Add compact UI**

`UserbotCapacity` contains:

1. fleet strip: utilization, reserve, accounts current/required, eligible/parked;
2. one card per account: state text+icon, power, RPC 1h/24h, budget,
   assigned chats, countdown;
3. one line chart RPC/minute with safe line;
4. red recommendation: `Подключить ещё N userbot-аккаунта`.

No buttons that mutate runtime state. Color is not the only status signal.

- [ ] **Step 4: Handle loading/stale/error states**

- skeleton while loading;
- last known React Query data remains visible on refresh error;
- explicit `Данные userbot недоступны` when first request fails;
- countdown uses server epoch, not browser-local assumptions.

- [ ] **Step 5: Run API and frontend verification**

```bash
pytest tests/test_userbot_capacity_api.py tests/test_admin_security.py -q
cd admin-panel
npm run lint
npm run build
```

Expected: pytest pass, lint exit 0, Vite build exit 0.

- [ ] **Step 6: Commit and tag**

```bash
git add app/admin/api/userbot_capacity.py app/admin/api/__init__.py tests/test_userbot_capacity_api.py admin-panel/src/components/dashboard/UserbotCapacity.tsx admin-panel/src/pages/DashboardPage.tsx app/admin/static
git commit -m "feat(admin): show userbot capacity and recovery"
git tag userbot-governor-phase-5-done
```

---

### Task 6: Full regression, incident replay and operational handoff

**Files:**
- Modify: `OPERATIONS.md`
- Modify: `TESTING.md`
- Modify: `AGENTS.md`
- Modify: `docs/SESSION_LOG.md`
- Create: `docs/ops/userbot_capacity_governor_ru.md`

**Interfaces:**
- Produces: rollout/rollback runbook.
- Consumes: all previous tasks.

- [ ] **Step 1: Run static safety checks**

```bash
rg -n "client\\.(get_me|get_messages|get_entity|get_input_entity)|GetHistoryRequest|ResolveUsernameRequest" app
rg -n "flood_sleep_threshold" app tests
rg -n "limiter\\.acquire" app/userbot
```

For every production Telegram RPC, record in the runbook whether it is governed.
No unexplained direct RPC remains in poller/pool.

- [ ] **Step 2: Run the incident replay suite**

```bash
pytest \
  tests/test_userbot_capacity.py \
  tests/test_poll_schedule.py \
  tests/test_rate_limiter.py \
  tests/test_pool.py \
  tests/test_poller_fixes.py \
  tests/test_tier_geo.py \
  tests/test_userbot_capacity_api.py \
  tests/test_watchdog_integrity.py -q
```

Expected: all pass, including 753-chat replay, natural CB expiry → RECOVERY and
zero polls for unsubscribed geography.

- [ ] **Step 3: Run full release gates**

```bash
pytest tests/ -q
cd admin-panel
npm run lint
npm run build
cd ..
python tools/eval_matching.py --help
git diff --check
```

Expected: all commands exit 0. Matching eval is not required against production
data because classifier/LLM rules are unchanged; CLI import must remain healthy.

- [ ] **Step 4: Write rollout runbook**

The runbook must require:

1. no production action without owner confirmation;
2. `pg_dump` even though no migration is added, preserving standard procedure;
3. worker stop before image/config changes;
4. shadow metrics with enforcement disabled for at least 24 hours;
5. compare projected vs actual RPC and SLO;
6. enable governor on one account at 25%;
7. observe 2 hours without FloodWait;
8. enable second account;
9. enable adaptive scheduler;
10. monitor logs for at least 5 minutes after every worker start;
11. rollback flags that disable enforcement but preserve metrics;
12. never delete circuit/governor keys to force recovery.

- [ ] **Step 5: Document configuration flags**

Use separate flags:

```text
USERBOT_RPC_METRICS_ENABLED=true
USERBOT_GOVERNOR_ENFORCING=false
USERBOT_ADAPTIVE_POLLING_ENABLED=false
```

Defaults in code remain safe for a fresh install. Production rollout toggles one
flag at a time after shadow evidence.

- [ ] **Step 6: Final review**

Run `/skill:phase-review` over the entire feature diff. Resolve all blockers and
repeat targeted/full gates after every fix.

- [ ] **Step 7: Commit and tag**

```bash
git add OPERATIONS.md TESTING.md AGENTS.md docs/SESSION_LOG.md docs/ops/userbot_capacity_governor_ru.md
git commit -m "docs(ops): add userbot governor rollout runbook"
git tag userbot-governor-phase-6-done
```

- [ ] **Step 8: Stop before production**

Push feature branch and open a draft PR only if the owner requests it. Do not
merge, deploy, restart worker, change env or clear Redis in this plan session.
