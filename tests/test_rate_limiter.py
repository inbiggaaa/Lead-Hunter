"""Tests for per-account rate limiter, budget, and capacity governor."""

from __future__ import annotations

import time
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import fakeredis.aioredis
import pytest

from app.userbot.capacity import GovernorState
from app.userbot.rate_limiter import (
    BudgetExceeded,
    GovernorBlocked,
    TelegramRateLimiter,
    _rpc_bucket_keys,
)


@pytest.fixture
async def fake_redis():
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield redis
    await redis.flushall()
    await redis.aclose()


@pytest.fixture
async def limiter(fake_redis, monkeypatch):
    async def _get_redis():
        return fake_redis

    monkeypatch.setattr("app.userbot.rate_limiter.get_redis", _get_redis)
    return TelegramRateLimiter(min_interval=0.01, daily_budget=0)


# ── Часть A: пер-аккаунтный интервал ──


async def test_accounts_do_not_share_interval(limiter: TelegramRateLimiter):
    t0 = time.monotonic()
    await limiter.acquire(account_id=1)
    t1 = time.monotonic()
    assert t1 - t0 < 0.2

    t2 = time.monotonic()
    await limiter.acquire(account_id=2)
    t3 = time.monotonic()
    assert t3 - t2 < 0.2
    assert 1 in limiter._account_last_call
    assert 2 in limiter._account_last_call


async def test_same_account_is_serialized(fake_redis, monkeypatch):
    async def _get_redis():
        return fake_redis

    monkeypatch.setattr("app.userbot.rate_limiter.get_redis", _get_redis)
    lim = TelegramRateLimiter(min_interval=0.5, daily_budget=0)

    t0 = time.monotonic()
    await lim.acquire(account_id=1)
    t1 = time.monotonic()
    await lim.acquire(account_id=1)
    t2 = time.monotonic()

    assert t1 - t0 < 0.2
    assert (t2 - t1) >= 0.4


async def test_internal_locks_are_per_account(limiter: TelegramRateLimiter):
    await limiter.acquire(account_id=1)
    await limiter.acquire(account_id=2)
    assert 1 in limiter._account_locks
    assert 2 in limiter._account_locks
    assert limiter._account_locks[1] is not limiter._account_locks[2]


# ── Часть B: суточный бюджет ──


async def test_budget_blocks_after_limit(fake_redis, monkeypatch):
    async def _get_redis():
        return fake_redis

    monkeypatch.setattr("app.userbot.rate_limiter.get_redis", _get_redis)
    lim = TelegramRateLimiter(min_interval=0.0, daily_budget=100)

    for _ in range(100):
        await lim.acquire(account_id=1)
    with pytest.raises(BudgetExceeded) as exc:
        await lim.acquire(account_id=1)
    assert "budget" in str(exc.value).lower() or "бюджет" in str(exc.value).lower()


async def test_budget_per_account_independent(fake_redis, monkeypatch):
    async def _get_redis():
        return fake_redis

    monkeypatch.setattr("app.userbot.rate_limiter.get_redis", _get_redis)
    lim = TelegramRateLimiter(min_interval=0.0, daily_budget=100)

    for _ in range(3):
        await lim.acquire(account_id=1)
    await lim.acquire(account_id=2)
    await lim.acquire(account_id=2)


@patch("app.userbot.rate_limiter._budget_key")
async def test_budget_resets_on_date_change(mock_budget_key, fake_redis, monkeypatch):
    async def _get_redis():
        return fake_redis

    monkeypatch.setattr("app.userbot.rate_limiter.get_redis", _get_redis)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")
    today_key = f"budget:used:1:{today}"
    tomorrow_key = f"budget:used:1:{tomorrow}"
    mock_budget_key.return_value = today_key

    lim = TelegramRateLimiter(min_interval=0.0, daily_budget=100)
    for _ in range(100):
        await lim.acquire(account_id=1)
    with pytest.raises(BudgetExceeded):
        await lim.acquire(account_id=1)

    mock_budget_key.return_value = tomorrow_key
    await lim.acquire(account_id=1)
    assert int(await fake_redis.get(tomorrow_key)) == 1


async def test_budget_exceeded_message_contains_account_id():
    exc = BudgetExceeded(account_id=5, used=101, limit=100)
    assert "5" in str(exc)
    assert "101" in str(exc)
    assert "100" in str(exc)


# ── Post-ban ──


async def test_post_ban_budget_halved(fake_redis, monkeypatch):
    async def _get_redis():
        return fake_redis

    monkeypatch.setattr("app.userbot.rate_limiter.get_redis", _get_redis)
    await fake_redis.set("post_ban_until:1", str(time.time() + 3600))
    await fake_redis.set("ban_count:1", "1")
    lim = TelegramRateLimiter(min_interval=0.0, daily_budget=100)

    for _ in range(50):
        await lim.acquire(account_id=1)
    with pytest.raises(BudgetExceeded):
        await lim.acquire(account_id=1)


async def test_post_ban_expired_full_budget(fake_redis, monkeypatch):
    async def _get_redis():
        return fake_redis

    monkeypatch.setattr("app.userbot.rate_limiter.get_redis", _get_redis)
    await fake_redis.set("post_ban_until:1", str(time.time() - 3600))
    lim = TelegramRateLimiter(min_interval=0.0, daily_budget=100)

    for _ in range(100):
        await lim.acquire(account_id=1)
    with pytest.raises(BudgetExceeded):
        await lim.acquire(account_id=1)


async def test_post_ban_set_on_cb_close(fake_redis, monkeypatch):
    async def _get_redis():
        return fake_redis

    monkeypatch.setattr("app.userbot.rate_limiter.get_redis", _get_redis)
    lim = TelegramRateLimiter(min_interval=0.3, daily_budget=10000)
    waited = await lim.wait_if_circuit_open(account_id=1)
    assert not waited


async def test_post_ban_activated_at_startup(fake_redis, monkeypatch):
    async def _get_redis():
        return fake_redis

    monkeypatch.setattr("app.userbot.rate_limiter.get_redis", _get_redis)
    await fake_redis.set("last_ban_at:1", str(time.time() - 3600))
    lim = TelegramRateLimiter(min_interval=0.3, daily_budget=10000)
    result = await lim.activate_post_ban_if_recent(account_id=1)
    assert result is True
    assert await fake_redis.get("post_ban_until:1") is not None


async def test_post_ban_startup_idempotent(fake_redis, monkeypatch):
    async def _get_redis():
        return fake_redis

    monkeypatch.setattr("app.userbot.rate_limiter.get_redis", _get_redis)
    await fake_redis.set("post_ban_until:1", str(time.time() + 3600))
    lim = TelegramRateLimiter(min_interval=0.3, daily_budget=10000)
    result = await lim.activate_post_ban_if_recent(account_id=1)
    assert result is False


async def test_post_ban_startup_old_ban_ignored(fake_redis, monkeypatch):
    async def _get_redis():
        return fake_redis

    monkeypatch.setattr("app.userbot.rate_limiter.get_redis", _get_redis)
    await fake_redis.set("last_ban_at:1", str(time.time() - 50 * 3600))
    lim = TelegramRateLimiter(min_interval=0.3, daily_budget=10000)
    result = await lim.activate_post_ban_if_recent(account_id=1)
    assert result is False


# ── Governor / RPC accounting ──


async def test_acquire_records_minute_hour_day_attempt_buckets(
    limiter: TelegramRateLimiter,
    fake_redis,
) -> None:
    await limiter.acquire(2, rpc_kind="get_history")
    minute_key, hour_key, day_key = _rpc_bucket_keys(2)
    minute = await fake_redis.hgetall(minute_key)
    hour = await fake_redis.hgetall(hour_key)
    day = await fake_redis.hgetall(day_key)
    assert minute["attempt"] == "1"
    assert hour["get_history"] == "1"
    assert day["total"] == "1"


async def test_any_flood_wait_enters_cooldown(
    limiter: TelegramRateLimiter,
    monkeypatch,
) -> None:
    fixed_now = 1_700_000_000
    monkeypatch.setattr("app.userbot.rate_limiter.time.time", lambda: fixed_now)
    monkeypatch.setattr("app.userbot.rate_limiter.random.randint", lambda a, b: 0)
    monkeypatch.setattr(
        "app.worker.notify_admin.notify_admin",
        AsyncMock(),
    )
    await limiter.report_flood_wait(
        seconds=17,
        context="poller:@chat",
        account_id=2,
        rpc_kind="get_history",
    )
    snapshot = await limiter.get_governor_snapshot(2)
    assert snapshot.state is GovernorState.COOLDOWN
    assert snapshot.power_percent == 0
    assert snapshot.cooldown_until is not None
    assert snapshot.cooldown_until > fixed_now + 17


async def test_long_flood_expires_into_ten_percent_recovery(
    limiter: TelegramRateLimiter,
    monkeypatch,
) -> None:
    monkeypatch.setattr("app.worker.notify_admin.notify_admin", AsyncMock())
    monkeypatch.setattr("app.userbot.rate_limiter.random.randint", lambda a, b: 0)
    await limiter.report_flood_wait(3600, "poller:@chat", 2, "get_history")
    stored = await limiter.get_governor_snapshot(2)
    assert stored.cooldown_until is not None
    snapshot = await limiter.refresh_governor(2, now=stored.cooldown_until + 1)
    assert snapshot.state is GovernorState.RECOVERY
    assert snapshot.power_percent == 10


async def test_acquire_blocks_during_cooldown(limiter: TelegramRateLimiter, monkeypatch) -> None:
    monkeypatch.setattr("app.worker.notify_admin.notify_admin", AsyncMock())
    monkeypatch.setattr("app.userbot.rate_limiter.random.randint", lambda a, b: 0)
    await limiter.report_flood_wait(30, "poller:@chat", 2, "get_history")
    with pytest.raises(GovernorBlocked) as exc:
        await limiter.acquire(2, rpc_kind="get_history")
    assert exc.value.state is GovernorState.COOLDOWN


async def test_redis_failure_blocks_telegram_rpc(monkeypatch) -> None:
    async def _boom():
        raise ConnectionError("redis down")

    monkeypatch.setattr("app.userbot.rate_limiter.get_redis", _boom)
    lim = TelegramRateLimiter(min_interval=0.01, daily_budget=0)
    with pytest.raises(GovernorBlocked) as exc:
        await lim.acquire(1, rpc_kind="get_history")
    assert exc.value.state is GovernorState.OFFLINE


async def test_metrics_disabled_skips_buckets(fake_redis, monkeypatch) -> None:
    async def _get_redis():
        return fake_redis

    monkeypatch.setattr("app.userbot.rate_limiter.get_redis", _get_redis)
    monkeypatch.setattr(
        "app.userbot.rate_limiter.settings.userbot_rpc_metrics_enabled",
        False,
    )
    lim = TelegramRateLimiter(min_interval=0.0, daily_budget=0)
    await lim.acquire(1, rpc_kind="get_history")
    keys = [k async for k in fake_redis.scan_iter(match="stats:tg_rpc:*")]
    assert keys == []


async def test_governor_persists_across_limiter_instances(
    fake_redis,
    monkeypatch,
) -> None:
    async def _get_redis():
        return fake_redis

    monkeypatch.setattr("app.userbot.rate_limiter.get_redis", _get_redis)
    monkeypatch.setattr("app.worker.notify_admin.notify_admin", AsyncMock())
    monkeypatch.setattr("app.userbot.rate_limiter.random.randint", lambda a, b: 0)
    first = TelegramRateLimiter(min_interval=0.0, daily_budget=0)
    await first.report_flood_wait(120, "poller:@x", 2, "resolve")
    second = TelegramRateLimiter(min_interval=0.0, daily_budget=0)
    snapshot = await second.get_governor_snapshot(2)
    assert snapshot.state is GovernorState.COOLDOWN
    assert snapshot.power_percent == 0


async def test_proactive_soft_throttle_when_enforcing(
    limiter: TelegramRateLimiter,
    monkeypatch,
) -> None:
    monkeypatch.setattr("app.worker.notify_admin.notify_admin", AsyncMock())
    monkeypatch.setattr(
        "app.userbot.rate_limiter.settings.userbot_governor_enforcing", True,
    )
    snapshot = await limiter.refresh_governor(
        1, now=1_700_000_000, day_rpc_total=2800,  # 70% of 4000
    )
    assert snapshot.state is GovernorState.THROTTLED
    assert snapshot.power_percent == 75


async def test_proactive_stop_blocks_until_next_day(
    limiter: TelegramRateLimiter,
    monkeypatch,
) -> None:
    monkeypatch.setattr("app.worker.notify_admin.notify_admin", AsyncMock())
    monkeypatch.setattr(
        "app.userbot.rate_limiter.settings.userbot_governor_enforcing", True,
    )
    frozen = 1_700_000_000
    monkeypatch.setattr("app.userbot.rate_limiter.time.time", lambda: frozen)
    snapshot = await limiter.refresh_governor(
        1, now=frozen, day_rpc_total=3900,  # 97.5%
    )
    assert snapshot.state is GovernorState.THROTTLED
    assert snapshot.power_percent == 0
    with pytest.raises(GovernorBlocked):
        await limiter.acquire(1, rpc_kind="get_history")


async def test_dry_run_updates_recommendation_only(
    limiter: TelegramRateLimiter,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "app.userbot.rate_limiter.settings.userbot_governor_enforcing", False,
    )
    snapshot = await limiter.refresh_governor(
        1, now=1_700_000_000, day_rpc_total=3600,  # 90%
    )
    assert snapshot.state is GovernorState.NORMAL
    assert snapshot.power_percent == 100
    assert snapshot.recommended_state is GovernorState.THROTTLED
    assert snapshot.recommended_power_percent == 50


async def test_recovery_advances_after_stable_windows(
    limiter: TelegramRateLimiter,
    monkeypatch,
) -> None:
    monkeypatch.setattr("app.worker.notify_admin.notify_admin", AsyncMock())
    monkeypatch.setattr("app.userbot.rate_limiter.random.randint", lambda a, b: 0)
    await limiter.report_flood_wait(120, "x", 2, "get_history")
    stored = await limiter.get_governor_snapshot(2)
    after = await limiter.refresh_governor(2, now=stored.cooldown_until + 1)
    assert after.state is GovernorState.RECOVERY
    # Force stage deadline passed + 3 safe windows
    stepped = after
    for _ in range(3):
        stepped = await limiter.refresh_governor(
            2,
            now=(stepped.stage_until or 0) + 1,
            window_safe=True,
            day_rpc_total=0,
        )
    assert stepped.power_percent >= after.power_percent
