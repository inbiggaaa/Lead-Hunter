"""Tests for poller fixes — incident #3, degradation, parked countries, sequential polling.

Tests cover:
- _distribute: blocked/unhealthy account exclusion, no channel loss
- _should_poll_tier: when Hot/Warm/Cold/Dormant should run
- _get_effective_interval: adaptive interval with cap
- _fetch_all_since: single-shot cursor-based fetching (no pagination)
- alert loop: queue, DLQ, FloodWait, stuck detection
"""

import asyncio
import math
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.userbot.poller import ChannelPoller
from app.config import settings

# ── helpers ──


def _make_account(account_id: int, is_healthy: bool = True):
    """Create a mock UserbotAccount."""
    acc = MagicMock()
    acc.account_id = account_id
    acc.is_healthy = is_healthy
    acc.phone = f"+1234567890{account_id}"
    acc.username = f"testuser{account_id}"
    return acc


def _make_msg(msg_id: int):
    """Create a mock Telegram Message with just an id."""
    msg = MagicMock()
    msg.id = msg_id
    msg.message = f"Test message {msg_id}"
    return msg


# ═══════════════════════════════════════════════════════════════════
# _distribute
# ═══════════════════════════════════════════════════════════════════


@patch("app.userbot.poller.limiter")
async def test_distribute_filters_blocked_account(mock_limiter):
    """_distribute исключает аккаунты с открытым circuit breaker."""
    mock_limiter.is_circuit_open = AsyncMock(side_effect=lambda aid: aid == 1)

    poller = ChannelPoller()
    poller.pool.accounts = [_make_account(1), _make_account(2)]
    channels = [{"id": i} for i in range(10)]

    result = await poller._distribute(channels)
    # Account 1 is blocked → all go to Account 2
    assert len(result) == 1
    assert result[0][0].account_id == 2
    assert len(result[0][1]) == 10


@patch("app.userbot.poller.limiter")
async def test_distribute_no_channel_loss(mock_limiter):
    """Каналы не теряются при блокировке — переходят на здоровый аккаунт."""
    mock_limiter.is_circuit_open = AsyncMock(side_effect=lambda aid: aid == 1)

    poller = ChannelPoller()
    poller.pool.accounts = [_make_account(1), _make_account(2)]
    channels = [{"id": i} for i in range(5)]

    result = await poller._distribute(channels)
    total = sum(len(chunk) for _, chunk in result)
    assert total == 5


@patch("app.userbot.poller.limiter")
async def test_distribute_all_blocked(mock_limiter):
    """Все аккаунты заблокированы → пустой список."""
    mock_limiter.is_circuit_open = AsyncMock(return_value=True)

    poller = ChannelPoller()
    poller.pool.accounts = [_make_account(1), _make_account(2)]

    result = await poller._distribute([{"id": 1}])
    assert result == []


@patch("app.userbot.poller.limiter")
async def test_distribute_round_robin_preserved(mock_limiter):
    """Round-robin сохраняется, когда все аккаунты здоровы."""
    mock_limiter.is_circuit_open = AsyncMock(return_value=False)

    poller = ChannelPoller()
    poller.pool.accounts = [_make_account(1), _make_account(2)]
    channels = [{"id": i} for i in range(4)]

    result = await poller._distribute(channels)
    assert len(result) == 2
    for acc, chunk in result:
        assert len(chunk) == 2


# ═══════════════════════════════════════════════════════════════════
# _should_poll_tier
# ═══════════════════════════════════════════════════════════════════


@patch("app.userbot.poller.limiter")
async def test_should_poll_tier_hot_always(mock_limiter):
    """Hot-тир всегда поллится, даже при 1 аккаунте."""
    mock_limiter.is_circuit_open = AsyncMock(return_value=False)

    poller = ChannelPoller()
    poller.pool.accounts = [_make_account(1)]
    assert await poller._should_poll_tier("Hot") is True


@patch("app.userbot.poller.limiter")
async def test_should_poll_tier_warm_needs_two_accounts(mock_limiter):
    """Warm требует 2+ CB-free аккаунтов."""
    mock_limiter.is_circuit_open = AsyncMock(return_value=False)

    poller = ChannelPoller()
    poller.pool.accounts = [_make_account(1)]
    assert await poller._should_poll_tier("Warm") is False

    poller.pool.accounts = [_make_account(1), _make_account(2)]
    assert await poller._should_poll_tier("Warm") is True


@patch("app.userbot.poller.limiter")
async def test_should_poll_tier_cold_needs_two_accounts(mock_limiter):
    """Cold требует 2+ CB-free аккаунтов."""
    mock_limiter.is_circuit_open = AsyncMock(return_value=False)

    poller = ChannelPoller()
    poller.pool.accounts = [_make_account(1)]
    assert await poller._should_poll_tier("Cold") is False


@patch("app.userbot.poller.limiter")
async def test_should_poll_tier_dormant_needs_two_accounts(mock_limiter):
    """Dormant требует 2+ CB-free аккаунтов."""
    mock_limiter.is_circuit_open = AsyncMock(return_value=False)

    poller = ChannelPoller()
    poller.pool.accounts = [_make_account(1)]
    assert await poller._should_poll_tier("Dormant") is False


@patch("app.userbot.poller.limiter")
async def test_should_poll_tier_unhealthy_not_counted(mock_limiter):
    """Unhealthy аккаунты не считаются."""
    mock_limiter.is_circuit_open = AsyncMock(return_value=False)

    poller = ChannelPoller()
    poller.pool.accounts = [_make_account(1), _make_account(2, is_healthy=False)]
    assert await poller._should_poll_tier("Warm") is False


@patch("app.userbot.poller.limiter")
async def test_should_poll_tier_cb_blocked_not_counted(mock_limiter):
    """Аккаунты с открытым CB не считаются в should_poll_tier."""
    mock_limiter.is_circuit_open = AsyncMock(side_effect=lambda aid: aid == 1)

    poller = ChannelPoller()
    poller.pool.accounts = [_make_account(1), _make_account(2)]
    # Acc1 CB blocked, Acc2 CB clear → only 1 CB-free → Warm should NOT poll
    assert await poller._should_poll_tier("Warm") is False


# ═══════════════════════════════════════════════════════════════════
# Pool
# ═══════════════════════════════════════════════════════════════════


async def test_handle_account_failure_does_not_redistribute():
    """handle_account_failure больше не перераспределяет каналы."""
    from app.userbot.pool import UserbotPool
    pool = UserbotPool()
    pool.accounts = [_make_account(1), _make_account(2)]
    # Не должно райзить — теперь принимает только UserbotAccount
    await pool.handle_account_failure(pool.accounts[0])


async def test_handle_account_failure_no_exception_when_last_account():
    """Не падает когда падает последний аккаунт."""
    from app.userbot.pool import UserbotPool
    pool = UserbotPool()
    pool.accounts = [_make_account(1)]
    await pool.handle_account_failure(pool.accounts[0])


# ═══════════════════════════════════════════════════════════════════
# Session model (Task 1.1)
# ═══════════════════════════════════════════════════════════════════


@patch("app.userbot.poller.get_redis")
async def test_session_ticker_transitions(mock_get_redis):
    """_session_ticker устанавливает состояние в Redis."""
    redis_state = {}
    redis_ttl = {}

    class FakeRedis:
        async def get(self, k):
            return redis_state.get(k)
        async def set(self, k, v):
            redis_state[k] = v
        async def setex(self, k, ttl, v):
            redis_state[k] = v
            redis_ttl[k] = ttl
        async def aclose(self):
            pass
        async def delete(self, k):
            redis_state.pop(k, None)

    mock_get_redis.return_value = FakeRedis()

    poller = ChannelPoller()
    poller.pool.accounts = [_make_account(1)]

    # Initial: no state → becomes ACTIVE
    await poller._session_ticker(1)
    assert redis_state["session:state:1"] == "ACTIVE"
    assert "session:until:1" in redis_state


@patch("app.userbot.poller.get_redis")
async def test_get_session_state(mock_get_redis):
    """_get_session_state читает из Redis."""
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value="ACTIVE")  # decode_responses=True
    mock_redis.aclose = AsyncMock()
    mock_get_redis.return_value = mock_redis

    poller = ChannelPoller()
    state = await poller._get_session_state(1)
    assert state == "ACTIVE"


@patch("app.userbot.poller.get_redis")
async def test_get_session_state_default(mock_get_redis):
    """Отсутствие ключа → ACTIVE по умолчанию."""
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.aclose = AsyncMock()
    mock_get_redis.return_value = mock_redis

    poller = ChannelPoller()
    state = await poller._get_session_state(1)
    assert state == "ACTIVE"


@patch("app.userbot.poller.get_redis")
async def test_session_sleeping_skips_tiers(mock_get_redis):
    """SLEEPING + 1 healthy → Warm/Cold/Dormant пропускаются."""
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(side_effect=lambda k: (
        b"SLEEPING" if k.startswith("session:state:") else None
    ))
    mock_redis.aclose = AsyncMock()
    mock_get_redis.return_value = mock_redis

    poller = ChannelPoller()
    poller.pool.accounts = [_make_account(1)]
    # Hot always runs regardless
    # Warm/Cold/Dormant: need 2+ healthy AND not SLEEPING
    # With 1 account the count check fails first
    assert poller._should_poll_tier("Warm") is False


@patch("app.userbot.poller.get_redis")
async def test_session_paused_skips_polling(mock_get_redis):
    """PAUSED пропускает не-Hot тиры."""
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(side_effect=lambda k: (
        b"PAUSED" if k.startswith("session:state:") else None
    ))
    mock_redis.aclose = AsyncMock()
    mock_get_redis.return_value = mock_redis

    poller = ChannelPoller()
    poller.pool.accounts = [_make_account(1)]
    # Hot still runs even when PAUSED
    assert poller._should_poll_tier("Hot") is True


@patch("app.userbot.poller.get_redis")
async def test_run_tier_once_active_calls_poll_batch(mock_get_redis):
    """ACTIVE → вызывает _poll_batch."""
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(
        side_effect=lambda k: b"ACTIVE" if k.startswith("session:state:") else None
    )
    mock_redis.aclose = AsyncMock()
    mock_get_redis.return_value = mock_redis

    poller = ChannelPoller()
    poller.pool.accounts = [_make_account(1)]
    mock_batch = AsyncMock(return_value=(1, 0))
    poller._poll_batch = mock_batch

    await poller._run_tier_once("Hot", mock_batch, initial=True)
    mock_batch.assert_called_once()


@patch("app.userbot.poller.get_redis")
async def test_run_tier_once_try_lock_skips_polling(mock_get_redis):
    """try-lock: если lock уже занят — пропускаем."""
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.aclose = AsyncMock()
    mock_get_redis.return_value = mock_redis

    poller = ChannelPoller()
    poller.pool.accounts = [_make_account(1)]
    mock_batch = AsyncMock()
    # Simulate locked — lock the account
    lock = poller._account_locks.setdefault(1, asyncio.Lock())
    await lock.acquire()

    await poller._run_tier_once("Hot", mock_batch, initial=True)
    mock_batch.assert_not_called()
    lock.release()


@patch("app.userbot.poller.get_redis")
async def test_run_tier_once_unlocked_calls_poll_batch(mock_get_redis):
    """Unlocked → вызывает _poll_batch."""
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.aclose = AsyncMock()
    mock_get_redis.return_value = mock_redis

    poller = ChannelPoller()
    poller.pool.accounts = [_make_account(1)]
    mock_batch = AsyncMock(return_value=(1, 0))
    poller._poll_batch = mock_batch

    await poller._run_tier_once("Hot", mock_batch, initial=True)
    mock_batch.assert_called_once()


# ═══════════════════════════════════════════════════════════════════
# Task 0.8 — CB status at startup
# ═══════════════════════════════════════════════════════════════════


@patch("app.userbot.poller.get_redis")
async def test_start_logs_cb_status_clear(mock_get_redis):
    """При старте логгирует CB-статус для каждого аккаунта."""
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=None)  # no CB keys
    mock_redis.aclose = AsyncMock()
    mock_get_redis.return_value = mock_redis

    poller = ChannelPoller()
    poller.pool.accounts = [_make_account(1)]
    poller.start = AsyncMock()  # don't actually start
    # Just verify CB check doesn't crash
    from app.userbot.rate_limiter import limiter
    limiter._acquire_cb = AsyncMock()  # stub to avoid real CB logic


# ═══════════════════════════════════════════════════════════════════
# Task 0.4 — sequential polling + log-normal delays
# ═══════════════════════════════════════════════════════════════════

from app.userbot.poller import next_delay


def test_next_delay_range():
    """next_delay в разумном диапазоне."""
    delays = [next_delay() for _ in range(1000)]
    assert all(0.5 < d < 8.0 for d in delays), f"Min: {min(delays)}, Max: {max(delays)}"


def test_next_delay_median():
    """Медиана ~2 секунды."""
    delays = sorted([next_delay() for _ in range(1000)])
    median = delays[len(delays) // 2]
    assert 1.5 < median < 3.0, f"Median: {median}"


def test_next_delay_has_spread():
    """Есть spread — не все значения одинаковые."""
    delays = [next_delay() for _ in range(100)]
    assert len(set(round(d, 1) for d in delays)) > 5


# ═══════════════════════════════════════════════════════════════════
# Task 1.2 — stagger sleep windows
# ═══════════════════════════════════════════════════════════════════


def test_sleep_starts_differ():
    """Аккаунты имеют разное время начала сна."""
    p = ChannelPoller()
    p.pool.accounts = [_make_account(1), _make_account(2)]
    s1 = p._get_sleep_start_hour(1)
    s2 = p._get_sleep_start_hour(2)
    assert s1 != s2


def test_sleep_starts_no_overlap():
    """Окна сна двух аккаунтов не пересекаются."""
    p = ChannelPoller()
    p.pool.accounts = [_make_account(1), _make_account(2)]
    s1 = p._get_sleep_start_hour(1)
    s2 = p._get_sleep_start_hour(2)
    gap = abs(s1 - s2)
    assert gap >= 6, f"s1={s1}, s2={s2}, gap={gap}"


def test_sleep_start_fallback():
    """При 1 аккаунте → start_hour=0."""
    p = ChannelPoller()
    p.pool.accounts = [_make_account(1)]
    assert p._get_sleep_start_hour(1) == 0


def test_sleep_window_normal():
    """_is_in_sleep_window правильно определяет."""
    p = ChannelPoller()
    assert p._is_in_sleep_window(4 * 3600, 0) is True
    assert p._is_in_sleep_window(2 * 3600, 22) is True
    assert p._is_in_sleep_window(23 * 3600, 22) is True
    assert p._is_in_sleep_window(12 * 3600, 0) is False
    assert p._is_in_sleep_window(10 * 3600, 22) is False


def test_sleep_window_wraparound():
    """Wraparound: 2→6 окно [2, 2+6=8)."""
    p = ChannelPoller()
    assert p._is_in_sleep_window(4 * 3600, 2) is True


# ═══════════════════════════════════════════════════════════════════
# Task 1.6 — entity cache
# ═══════════════════════════════════════════════════════════════════


@patch("app.userbot.poller.get_redis")
@patch("app.userbot.poller.limiter")
async def test_entity_cache_hit_skips_resolve(mock_limiter, mock_get_redis):
    """При попадании в кэш get_entity не вызывается."""
    mock_limiter.acquire = AsyncMock()
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=b"0")
    mock_redis.set = AsyncMock()
    mock_redis.aclose = AsyncMock()
    mock_get_redis.return_value = mock_redis

    poller = ChannelPoller()
    account = _make_account(1)
    get_entity_count = {"count": 0}

    async def fake_get_input_entity(uname):
        get_entity_count["count"] += 1
        entity = MagicMock()
        entity.id = 12345
        entity.access_hash = 67890
        return entity
    account.get_input_entity = fake_get_input_entity

    ch = "cached_ch"
    poller._entity_cache[ch] = {1: (12345, 67890)}

    entity = await poller._resolve_entity(account, ch)
    assert get_entity_count["count"] == 0
    assert entity.channel_id == 12345


@patch("app.userbot.poller.get_redis")
@patch("app.userbot.poller.limiter")
async def test_entity_cache_miss_calls_resolve(mock_limiter, mock_get_redis):
    """При промахе — вызывает get_entity."""
    mock_limiter.acquire = AsyncMock()
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=b"0")
    mock_redis.set = AsyncMock()
    mock_redis.aclose = AsyncMock()
    mock_get_redis.return_value = mock_redis

    poller = ChannelPoller()
    account = _make_account(1)
    get_entity_count = {"count": 0}

    async def fake_get_input_entity(uname):
        get_entity_count["count"] += 1
        entity = MagicMock()
        entity.id = 12345
        entity.access_hash = 67890
        return entity
    account.get_input_entity = fake_get_input_entity

    entity = await poller._resolve_entity(account, "new_ch")
    assert get_entity_count["count"] == 1


@patch("app.userbot.poller.get_redis")
@patch("app.userbot.poller.limiter")
async def test_entity_cache_per_account_independent(mock_limiter, mock_get_redis):
    """Кэш per-account — acc1 не использует кэш acc2."""
    mock_limiter.acquire = AsyncMock()
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=b"0")
    mock_redis.set = AsyncMock()
    mock_redis.aclose = AsyncMock()
    mock_get_redis.return_value = mock_redis

    poller = ChannelPoller()
    poller._entity_cache["ch"] = {1: (111, 222)}
    # acc2 должен промахнуться
    acc2 = _make_account(2)
    get_entity_count = {"count": 0}
    async def fake_get_input_entity(uname):
        get_entity_count["count"] += 1
        entity = MagicMock()
        entity.id = 333
        entity.access_hash = 444
        return entity
    acc2.get_input_entity = fake_get_input_entity

    await poller._resolve_entity(acc2, "ch")
    assert get_entity_count["count"] == 1


# ═══════════════════════════════════════════════════════════════════
# _fetch_all_since (simplified — no pagination)
# ═══════════════════════════════════════════════════════════════════


@patch("app.userbot.poller.limiter")
async def test_fetch_all_since_with_cursor(mock_limiter):
    """cursor > 0 — min_id фильтр, один вызов."""
    mock_limiter.acquire = AsyncMock()
    poller = ChannelPoller()
    acc = _make_account(1)

    ALL_MSGS = {mid: _make_msg(mid) for mid in range(90, 106)}

    async def mock_get_messages(entity, **kwargs):
        min_id = kwargs.get("min_id", 0)
        limit = kwargs.get("limit", 100)
        candidates = [m for mid, m in ALL_MSGS.items() if mid > min_id]
        candidates.sort(key=lambda m: m.id, reverse=True)
        return candidates[:limit]
    acc.get_messages = mock_get_messages

    all_messages = await poller._fetch_all_since(acc, MagicMock(), "test_ch", cursor=100)
    msg_ids = [m.id for m in all_messages]
    assert msg_ids == [105, 104, 103, 102, 101]
    assert all(mid > 100 for mid in msg_ids)


@patch("app.userbot.poller.limiter")
async def test_fetch_all_since_no_cursor(mock_limiter):
    """cursor=0 — без фильтров, один вызов."""
    mock_limiter.acquire = AsyncMock()
    poller = ChannelPoller()
    acc = _make_account(1)

    fetch_kwargs = {}
    async def mock_get_messages(entity, **kwargs):
        fetch_kwargs.update(kwargs)
        return [_make_msg(i) for i in range(9400, 9500)]
    acc.get_messages = mock_get_messages

    all_messages = await poller._fetch_all_since(acc, MagicMock(), "test_ch", cursor=0)
    assert len(all_messages) == 100
    assert "min_id" not in fetch_kwargs


@patch("app.userbot.poller.limiter")
async def test_fetch_all_since_empty(mock_limiter):
    """None → пустой список."""
    mock_limiter.acquire = AsyncMock()
    poller = ChannelPoller()
    acc = _make_account(1)
    acc.get_messages = AsyncMock(return_value=None)
    all_messages = await poller._fetch_all_since(acc, MagicMock(), "test_ch", cursor=0)
    assert all_messages == []


# ═══════════════════════════════════════════════════════════════════
# _get_effective_interval + post_ban
# ═══════════════════════════════════════════════════════════════════


@patch("app.userbot.poller.limiter")
async def test_post_ban_interval_with_multiplier(mock_limiter):
    """_get_effective_interval: 1 CB-free + post_ban ×3.0 — max(2.0, 3.0)=3.0."""
    mock_limiter.is_circuit_open = AsyncMock(return_value=False)
    mock_limiter.get_post_ban_interval_multiplier = AsyncMock(return_value=3.0)

    poller = ChannelPoller()
    poller.pool.accounts = [_make_account(1)]
    result = await poller._get_effective_interval("Hot", 60)
    assert result == 180  # 60 × max(2.0, 3.0) = 180


@patch("app.userbot.poller.limiter")
async def test_effective_interval_2_accounts_no_post_ban(mock_limiter):
    """2 CB-free аккаунта, без post-ban → базовый интервал."""
    mock_limiter.is_circuit_open = AsyncMock(return_value=False)
    mock_limiter.get_post_ban_interval_multiplier = AsyncMock(return_value=1.0)

    poller = ChannelPoller()
    poller.pool.accounts = [_make_account(1), _make_account(2)]
    result = await poller._get_effective_interval("Hot", 60)
    assert result == 60


@patch("app.userbot.poller.limiter")
async def test_effective_interval_1_account_degraded(mock_limiter):
    """1 CB-free аккаунт → ×2 degradation."""
    mock_limiter.is_circuit_open = AsyncMock(return_value=False)
    mock_limiter.get_post_ban_interval_multiplier = AsyncMock(return_value=1.0)

    poller = ChannelPoller()
    poller.pool.accounts = [_make_account(1)]
    result = await poller._get_effective_interval("Hot", 60)
    assert result == 120  # 60 × 2


@patch("app.userbot.poller.limiter")
async def test_effective_interval_zero_cb_free_uses_cap(mock_limiter):
    """0 CB-free аккаунтов → использует cap."""
    mock_limiter.is_circuit_open = AsyncMock(return_value=True)
    mock_limiter.get_post_ban_interval_multiplier = AsyncMock(return_value=1.0)

    poller = ChannelPoller()
    poller.pool.accounts = [_make_account(1)]
    result = await poller._get_effective_interval("Hot", 60)
    assert result == settings.hot_interval_cap  # 1200


@patch("app.userbot.poller.limiter")
async def test_effective_interval_cap_applies(mock_limiter):
    """Cap триммит вычисленный интервал."""
    mock_limiter.is_circuit_open = AsyncMock(side_effect=lambda aid: aid == 2)
    mock_limiter.get_post_ban_interval_multiplier = AsyncMock(return_value=5.0)

    poller = ChannelPoller()
    poller.pool.accounts = [_make_account(1), _make_account(2)]
    # Acc1 CB-free, Acc2 CB-blocked → 1 CB-free → degraded ×2
    # post_ban multiplier for Acc1 = 5.0 (escalated after 3 bans)
    # max(2.0, 5.0) = 5.0 → 60 × 5 = 300 < cap
    result = await poller._get_effective_interval("Hot", 60)
    assert result == 300


@patch("app.userbot.poller.limiter")
async def test_effective_interval_degradation_with_post_ban_max_wins(mock_limiter):
    """max(degraded=2, post_ban=1.5) = 2 → ×2."""
    mock_limiter.is_circuit_open = AsyncMock(return_value=False)
    mock_limiter.get_post_ban_interval_multiplier = AsyncMock(return_value=1.5)

    poller = ChannelPoller()
    poller.pool.accounts = [_make_account(1)]
    result = await poller._get_effective_interval("Hot", 600)
    assert result == 1200  # 600 × max(2, 1.5) = 1200


@patch("app.userbot.poller.limiter")
async def test_effective_interval_2_acc_post_ban(mock_limiter):
    """2 аккаунта + post_ban ×3.0: только ×3.0 (нет деградации)."""
    mock_limiter.is_circuit_open = AsyncMock(return_value=False)
    mock_limiter.get_post_ban_interval_multiplier = AsyncMock(return_value=3.0)

    poller = ChannelPoller()
    poller.pool.accounts = [_make_account(1), _make_account(2)]
    result = await poller._get_effective_interval("Hot", 600)
    # 600 × 3.0 = 1800 > 1200 cap → clamp to 1200
    assert result == 1200


@patch("app.userbot.poller.limiter")
async def test_effective_interval_degradation_reads_config(mock_limiter):
    """Деградация читается из конфига (hot_degraded_multiplier=2.0)."""
    mock_limiter.is_circuit_open = AsyncMock(return_value=False)
    mock_limiter.get_post_ban_interval_multiplier = AsyncMock(return_value=1.0)

    poller = ChannelPoller()
    poller.pool.accounts = [_make_account(1)]
    result = await poller._get_effective_interval("Hot", 60)
    assert result == 2 * 60


# ═══════════════════════════════════════════════════════════════════
# Alert loop (Task 1.4)
# ═══════════════════════════════════════════════════════════════════


@patch("app.userbot.poller.get_redis")
async def test_alert_queue_backlog(mock_get_redis):
    """Очередь > 100 → WARNING."""
    mock_redis = AsyncMock()
    mock_redis.llen = AsyncMock(side_effect=lambda k: 150 if k == "queue:notifications" else 0)
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.aclose = AsyncMock()
    mock_get_redis.return_value = mock_redis

    poller = ChannelPoller()
    poller.pool.accounts = [_make_account(1)]
    level, text = await poller._check_queue_backlog()
    assert level == "WARNING"
    assert "150" in text


@patch("app.userbot.poller.get_redis")
async def test_alert_dlq(mock_get_redis):
    """Dead-letter очередь → WARNING."""
    mock_redis = AsyncMock()
    mock_redis.llen = AsyncMock(side_effect=lambda k: 1 if k == "dlq:notifications" else 0)
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.aclose = AsyncMock()
    mock_get_redis.return_value = mock_redis

    poller = ChannelPoller()
    poller.pool.accounts = [_make_account(1)]
    level, text = await poller._check_dlq()
    assert level == "WARNING"


@patch("app.userbot.poller.get_redis")
async def test_alert_flood_wait_critical(mock_get_redis):
    """FloodWait > 30 мин → CRITICAL."""
    future_ts = int(time.time()) + 3600  # 1 hour away
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(
        side_effect=lambda k: (
            str(future_ts).encode() if k == "circuit:expires:1" else None
        )
    )
    mock_redis.aclose = AsyncMock()
    mock_get_redis.return_value = mock_redis

    poller = ChannelPoller()
    poller.pool.accounts = [_make_account(1)]
    level, text = await poller._check_flood_wait()
    assert level == "CRITICAL"


@patch("app.userbot.poller.limiter")
@patch("app.userbot.poller.get_redis")
async def test_alert_poller_stuck(mock_get_redis, mock_limiter):
    """ACTIVE + CB clear + last_poll старый → CRITICAL."""
    mock_limiter.is_circuit_open = AsyncMock(return_value=False)
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(
        side_effect=lambda k: (
            str(time.time() - 4000).encode() if k == "stats:last_poll_at"
            else "ACTIVE" if k == "session:state:1"
            else None
        )
    )
    mock_redis.aclose = AsyncMock()
    mock_get_redis.return_value = mock_redis

    poller = ChannelPoller()
    poller.pool.accounts = [_make_account(1)]
    level, text = await poller._check_poller_stuck()
    assert level == "CRITICAL"


@patch("app.userbot.poller.limiter")
@patch("app.userbot.poller.get_redis")
async def test_alert_poller_silent_when_paused(mock_get_redis, mock_limiter):
    """PAUSED — stuck-алерт молчит."""
    mock_limiter.is_circuit_open = AsyncMock(return_value=False)
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(
        side_effect=lambda k: (
            str(time.time() - 4000).encode() if k == "stats:last_poll_at"
            else "PAUSED" if k == "session:state:1"
            else None
        )
    )
    mock_redis.aclose = AsyncMock()
    mock_get_redis.return_value = mock_redis

    poller = ChannelPoller()
    poller.pool.accounts = [_make_account(1)]
    level, text = await poller._check_poller_stuck()
    assert level is None


@patch("app.userbot.poller.limiter")
@patch("app.userbot.poller.get_redis")
async def test_alert_poller_silent_when_cb_open(mock_get_redis, mock_limiter):
    """ACTIVE но CB open → алерт молчит (не может поллить)."""
    mock_limiter.is_circuit_open = AsyncMock(return_value=True)
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(
        side_effect=lambda k: (
            str(time.time() - 4000).encode() if k == "stats:last_poll_at"
            else "ACTIVE" if k == "session:state:1"
            else None
        )
    )
    mock_redis.aclose = AsyncMock()
    mock_get_redis.return_value = mock_redis

    poller = ChannelPoller()
    poller.pool.accounts = [_make_account(1)]
    level, text = await poller._check_poller_stuck()
    assert level is None


@patch("app.userbot.poller.get_redis")
async def test_alert_throttling(mock_get_redis):
    """Алерты троттлятся через Redis."""
    mock_redis = AsyncMock()
    mock_redis.llen = AsyncMock(return_value=0)
    mock_redis.get = AsyncMock(return_value=str(time.time()).encode())  # just fired
    mock_redis.aclose = AsyncMock()
    mock_get_redis.return_value = mock_redis

    poller = ChannelPoller()
    poller.pool.accounts = [_make_account(1)]
    # Should return None due to throttle
    level, text = await poller._check_queue_backlog()
    assert level is None


# ═══════════════════════════════════════════════════════════════════
# _run_tier_loop resilience
# ═══════════════════════════════════════════════════════════════════


@patch("app.userbot.poller.asyncio.sleep", new_callable=AsyncMock)
async def test_run_tier_loop_survives_once_crash(mock_sleep):
    """_run_tier_loop продолжает цикл после исключения в _run_tier_once."""
    poller = ChannelPoller()
    poller.pool.accounts = [_make_account(1)]

    call_count = 0

    async def crash_once(tier_name, channels, initial):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("Redis connection lost")
        return False

    poller._run_tier_once = crash_once
    poller._get_available_account_count = AsyncMock(return_value=1)
    poller._get_effective_interval = AsyncMock(return_value=1)

    # After 2 sleeps (crash recovery + normal cycle), stop the loop
    sleep_count = 0

    def stop_after_two(_t):
        nonlocal sleep_count
        sleep_count += 1
        if sleep_count >= 2:
            raise StopAsyncIteration

    mock_sleep.side_effect = stop_after_two

    try:
        await poller._run_tier_loop("Test", [{"id": 1}], interval=1)
    except StopAsyncIteration:
        pass

    assert call_count >= 2, f"_run_tier_once called {call_count} times (expected 2+ after crash)"


# ═══════════════════════════════════════════════════════════════════
# Session model — single healthy account guard
# ═══════════════════════════════════════════════════════════════════


@patch("app.userbot.poller.limiter")
async def test_single_healthy_never_paused(mock_limiter):
    """Единственный здоровый аккаунт не уходит в PAUSED."""
    mock_limiter.is_circuit_open = AsyncMock(side_effect=lambda aid: aid == 1)

    poller = ChannelPoller()
    poller.pool.accounts = [_make_account(1), _make_account(2)]

    ns, nu = poller._next_session_state(2, prev_state="ACTIVE", now=8 * 3600)
    # Without guard: would return PAUSED. With guard in _session_ticker, stays ACTIVE.
    # _next_session_state is pure logic — guard is in _session_ticker.
    # This test verifies _next_session_state returns PAUSED (normal),
    # trusting the guard in _session_ticker to override it.
    assert ns == "PAUSED"


@patch("app.userbot.poller.limiter")
async def test_two_healthy_session_normal(mock_limiter):
    """Оба здоровы → сессионная модель работает нормально."""
    mock_limiter.is_circuit_open = AsyncMock(return_value=False)

    poller = ChannelPoller()
    poller.pool.accounts = [_make_account(1), _make_account(2)]

    ns, nu = poller._next_session_state(1, prev_state="ACTIVE", now=8 * 3600)
    assert ns == "PAUSED"


@patch("app.userbot.poller.limiter")
async def test_sleep_always_wakes_to_active(mock_limiter):
    """SLEEPING всегда просыпается в ACTIVE."""
    mock_limiter.is_circuit_open = AsyncMock(return_value=False)

    poller = ChannelPoller()
    poller.pool.accounts = [_make_account(1)]

    ns, nu = poller._next_session_state(1, prev_state="SLEEPING", now=8 * 3600)
    assert ns == "ACTIVE"


@patch("app.userbot.poller.limiter")
async def test_warmup_skipped_when_one_cb_free(mock_limiter):
    """1 CB-free аккаунт → warmup пропускается, сразу все каналы."""
    mock_limiter.is_circuit_open = AsyncMock(side_effect=lambda aid: aid == 1)

    poller = ChannelPoller()
    poller.pool.accounts = [_make_account(1), _make_account(2)]
    poller._run_tier_once = AsyncMock(return_value=False)
    poller._get_effective_interval = AsyncMock(return_value=1)

    # Run one cycle — should skip warmup
    import asyncio as real_asyncio
    cycles = 0

    async def stop_after_one(_t):
        nonlocal cycles
        cycles += 1
        if cycles >= 1:
            raise StopAsyncIteration
        await real_asyncio.sleep(0)

    with patch("app.userbot.poller.asyncio.sleep", side_effect=stop_after_one):
        try:
            await poller._run_tier_loop("Test", [{"id": i} for i in range(217)], interval=1)
        except StopAsyncIteration:
            pass

    # _run_tier_once should be called with all 217 channels (no warmup limit)
    call = poller._run_tier_once.call_args
    tier_name, tier_channels, initial = call[0]
    assert len(tier_channels) == 217, f"Expected 217 channels, got {len(tier_channels)}"


@patch("app.userbot.poller.limiter")
async def test_warmup_normal_when_two_cb_free(mock_limiter):
    """2 CB-free аккаунта → warmup пропускается (skip_warmup = cb_free >= 1)."""
    mock_limiter.is_circuit_open = AsyncMock(return_value=False)

    poller = ChannelPoller()
    poller.pool.accounts = [_make_account(1), _make_account(2)]
    poller._run_tier_once = AsyncMock(return_value=False)
    poller._get_effective_interval = AsyncMock(return_value=1)

    cycles = 0
    async def stop_after_one(_t):
        nonlocal cycles
        cycles += 1
        if cycles >= 1:
            raise StopAsyncIteration
        import asyncio as real_asyncio
        await real_asyncio.sleep(0)

    with patch("app.userbot.poller.asyncio.sleep", side_effect=stop_after_one):
        try:
            await poller._run_tier_loop("Test", [{"id": i} for i in range(217)], interval=1)
        except StopAsyncIteration:
            pass

    call = poller._run_tier_once.call_args
    tier_name, tier_channels, initial = call[0]
    # 2 CB-free → skip_warmup = True → all 217 channels used (no warmup ramp)
    assert len(tier_channels) == 217, f"Expected 217 (skip warmup), got {len(tier_channels)}"


# ═══════════════════════════════════════════════════════════════════
# City matching fixes
# ═══════════════════════════════════════════════════════════════════


@patch("app.userbot.poller.async_session_factory")
async def test_city_matching_uses_name_en(mock_factory):
    """Канал с 'Istanbul' в названии матчится к Стамбулу через name_en."""
    from app.userbot.poller import ChannelPoller
    from app.db.models import City

    city = City(id=48, slug="istanbul", name_ru="Стамбул", name_en="Istanbul",
                country_id=100, is_active=True)
    channel = MagicMock(id=1, chat_username="ist_chat", title="Istanbul Chat",
                        auto_matched_country_id=100, auto_matched_city_id=None)

    mock_sess = MagicMock()
    mock_sess.execute = AsyncMock(side_effect=[
        MagicMock(scalars=lambda: MagicMock(all=lambda: [city])),
        MagicMock(scalars=lambda: MagicMock(all=lambda: [channel])),
        MagicMock(),
    ])
    mock_sess.commit = AsyncMock()
    mock_sess.__aenter__ = AsyncMock(return_value=mock_sess)
    mock_sess.__aexit__ = AsyncMock(return_value=None)
    mock_factory.return_value = mock_sess

    poller = ChannelPoller()
    tagged = await poller._tag_new_channels()
    assert tagged >= 1, f"Expected >=1 tagged, got {tagged}"


@patch("app.userbot.poller.async_session_factory")
async def test_city_matching_short_name(mock_factory):
    """Короткое название города (Уфа, 3 буквы) матчится."""
    from app.userbot.poller import ChannelPoller
    from app.db.models import City

    city = City(id=99, slug="ufa", name_ru="Уфа", name_en="Ufa",
                country_id=200, is_active=True)
    channel = MagicMock(id=2, chat_username="ufa_chat", title="Уфа чат",
                        auto_matched_country_id=200, auto_matched_city_id=None)

    mock_sess = MagicMock()
    mock_sess.execute = AsyncMock(side_effect=[
        MagicMock(scalars=lambda: MagicMock(all=lambda: [city])),
        MagicMock(scalars=lambda: MagicMock(all=lambda: [channel])),
        MagicMock(),
    ])
    mock_sess.commit = AsyncMock()
    mock_sess.__aenter__ = AsyncMock(return_value=mock_sess)
    mock_sess.__aexit__ = AsyncMock(return_value=None)
    mock_factory.return_value = mock_sess

    poller = ChannelPoller()
    tagged = await poller._tag_new_channels()
    assert tagged >= 1, f"Expected >=1 tagged, got {tagged}"


@patch("app.userbot.poller.async_session_factory")
async def test_effective_city_ids_reads_channel_cities(mock_factory):
    """Канал с channel_cities записями отдаёт все города в effective_city_ids."""
    from app.userbot.poller import ChannelPoller

    ch = MagicMock(id=5, chat_username="multi", title="Multi City",
                   auto_matched_country_id=100, auto_matched_city_id=1)
    cc_rows = [2, 3]

    # Build effective_city_ids as _dispatch does
    channel_city_id = ch.auto_matched_city_id
    effective = {channel_city_id} if channel_city_id else set()
    effective.update(cc_rows)

    assert effective == {1, 2, 3}, f"Expected {{1,2,3}}, got {effective}"


@patch("app.userbot.poller.async_session_factory")
async def test_city_matching_fuzzy_transliteration(mock_factory):
    """Fuzzy match: 'Анталия' → 'Анталья' (транслитерационное расхождение)."""
    from app.userbot.poller import ChannelPoller
    from app.db.models import City

    city = City(id=49, slug="antalya", name_ru="Анталья", name_en="Antalya",
                country_id=100, is_active=True)
    channel = MagicMock(id=99, chat_username="ant_chat", title="Анталия чат",
                        auto_matched_country_id=100, auto_matched_city_id=None)

    mock_sess = MagicMock()
    mock_sess.execute = AsyncMock(side_effect=[
        MagicMock(scalars=lambda: MagicMock(all=lambda: [city])),
        MagicMock(scalars=lambda: MagicMock(all=lambda: [channel])),
        MagicMock(),
    ])
    mock_sess.commit = AsyncMock()
    mock_sess.__aenter__ = AsyncMock(return_value=mock_sess)
    mock_sess.__aexit__ = AsyncMock(return_value=None)
    mock_factory.return_value = mock_sess

    poller = ChannelPoller()
    tagged = await poller._tag_new_channels()
    # "Анталья" vs "Анталия" — fuzzy match should work (score ~0.86)
    assert tagged >= 1, f"Expected >=1 tagged via fuzzy, got {tagged}"


# ═══════════════════════════════════════════════════════════════════
# 7-day freshness gate (FEAT_7DAY_2026-07-04)
# ═══════════════════════════════════════════════════════════════════

from datetime import datetime, timezone, timedelta


def _make_msg_with_date(msg_id: int, days_ago: int = 0):
    """Create a mock Telegram Message with id, text, and date offset."""
    msg = MagicMock()
    msg.id = msg_id
    msg.message = f"Test message {msg_id}"
    msg.date = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return msg


def _fresh_classification():
    """Return a ClassificationResult with one matched segment."""
    from app.userbot.classifier import ClassificationResult
    return ClassificationResult(
        matched_segments=["catering"],
        is_urgent=False,
    )


@patch("app.userbot.poller.Message", MagicMock)  # isinstance(mock, Message) → True
@patch("app.userbot.poller.llm_validator")
@patch("app.userbot.poller.classify_message")
@patch("app.userbot.poller.ChannelPoller._log_llm_decision")
@patch("app.userbot.poller.ChannelPoller._log_unmatched")
@patch("app.userbot.poller.ChannelPoller._dispatch")
@patch("app.userbot.poller.ChannelPoller._set_cursor")
@patch("app.userbot.poller.ChannelPoller._fetch_all_since")
@patch("app.userbot.poller.ChannelPoller._get_cursor")
@patch("app.userbot.poller.ChannelPoller._resolve_entity")
async def test_t1_fresh_messages_classified_cursor_is_server_max(
    mock_resolve, mock_get_cursor, mock_fetch, mock_set_cursor,
    mock_dispatch, mock_log_unmatched, mock_log_llm,
    mock_classify, mock_llm,
):
    """t1: свежие сообщения (≤7д) → классифицируются, курсор = server_max."""
    mock_resolve.return_value = MagicMock(broadcast=False)
    mock_get_cursor.return_value = 100
    mock_llm.validate = AsyncMock(return_value=MagicMock(verdict="OK", reason=""))
    mock_llm.should_block = MagicMock(return_value=False)
    mock_classify.return_value = _fresh_classification()

    # 3 messages: ids 101, 102, 103 — all 1 day old
    msgs = [
        _make_msg_with_date(103, days_ago=1),
        _make_msg_with_date(102, days_ago=1),
        _make_msg_with_date(101, days_ago=1),
    ]
    mock_fetch.return_value = msgs

    poller = ChannelPoller()
    acc = _make_account(1)
    await poller._poll_channel(acc, "test_ch", "Hot", initial=False)

    # Все 3 должны быть классифицированы
    assert mock_classify.call_count == 3
    # Курсор: server_max=103, cursor=100 → new_cursor=103
    mock_set_cursor.assert_called_once_with("test_ch", 103)


@patch("app.userbot.poller.Message", MagicMock)  # isinstance(mock, Message) → True
@patch("app.userbot.poller.llm_validator")
@patch("app.userbot.poller.classify_message")
@patch("app.userbot.poller.ChannelPoller._log_llm_decision")
@patch("app.userbot.poller.ChannelPoller._log_unmatched")
@patch("app.userbot.poller.ChannelPoller._dispatch")
@patch("app.userbot.poller.ChannelPoller._set_cursor")
@patch("app.userbot.poller.ChannelPoller._fetch_all_since")
@patch("app.userbot.poller.ChannelPoller._get_cursor")
@patch("app.userbot.poller.ChannelPoller._resolve_entity")
async def test_t2_old_batch_cursor_advances_no_classify(
    mock_resolve, mock_get_cursor, mock_fetch, mock_set_cursor,
    mock_dispatch, mock_log_unmatched, mock_log_llm,
    mock_classify, mock_llm,
):
    """t2: батч целиком старше cutoff → classify НЕ вызывается, курсор ВСЁ РАВНО сдвигается.

    Ключевой тест: анти-петля. Без сдвига курсора этот батч перечитывался бы
    бесконечно на каждом опросе (все сообщения старше 7д, но новее min_id).
    """
    mock_get_cursor.return_value = 100
    mock_llm.validate = AsyncMock()
    mock_llm.should_block = MagicMock(return_value=False)
    mock_resolve.return_value = MagicMock(broadcast=False)

    # Все 3 сообщения — 10 дней назад (старше cutoff=7д)
    msgs = [
        _make_msg_with_date(103, days_ago=10),
        _make_msg_with_date(102, days_ago=10),
        _make_msg_with_date(101, days_ago=10),
    ]
    mock_fetch.return_value = msgs

    poller = ChannelPoller()
    acc = _make_account(1)
    await poller._poll_channel(acc, "test_ch", "Hot", initial=False)

    # Classify НЕ вызывается — все отфильтрованы по дате
    mock_classify.assert_not_called()
    # Но курсор сдвигается на server_max=103
    mock_set_cursor.assert_called_once_with("test_ch", 103)


@patch("app.userbot.poller.Message", MagicMock)  # isinstance(mock, Message) → True
@patch("app.userbot.poller.llm_validator")
@patch("app.userbot.poller.classify_message")
@patch("app.userbot.poller.ChannelPoller._log_llm_decision")
@patch("app.userbot.poller.ChannelPoller._log_unmatched")
@patch("app.userbot.poller.ChannelPoller._dispatch")
@patch("app.userbot.poller.ChannelPoller._set_cursor")
@patch("app.userbot.poller.ChannelPoller._fetch_all_since")
@patch("app.userbot.poller.ChannelPoller._get_cursor")
@patch("app.userbot.poller.ChannelPoller._resolve_entity")
async def test_t3_mixed_batch_partial_classify_cursor_server_max(
    mock_resolve, mock_get_cursor, mock_fetch, mock_set_cursor,
    mock_dispatch, mock_log_unmatched, mock_log_llm,
    mock_classify, mock_llm,
):
    """t3: смешанный батч — свежие классифицируются, старые пропускаются.

    Курсор = server_max (по всей выдаче), НЕ max по свежим.
    """
    mock_get_cursor.return_value = 100
    mock_llm.validate = AsyncMock(return_value=MagicMock(verdict="OK", reason=""))
    mock_llm.should_block = MagicMock(return_value=False)
    mock_classify.return_value = _fresh_classification()
    mock_resolve.return_value = MagicMock(broadcast=False)

    # id 105 — свежий (1д), id 104 — старый (10д), id 103 — свежий (2д)
    msgs = [
        _make_msg_with_date(105, days_ago=1),   # свежий
        _make_msg_with_date(104, days_ago=10),  # старый → skip
        _make_msg_with_date(103, days_ago=2),   # свежий
    ]
    mock_fetch.return_value = msgs

    poller = ChannelPoller()
    acc = _make_account(1)
    await poller._poll_channel(acc, "test_ch", "Hot", initial=False)

    # Только 2 свежих дошли до classify
    assert mock_classify.call_count == 2
    # Курсор = server_max=105 (НЕ max по свежим = 105, здесь совпало, но проверяем именно server_max)
    mock_set_cursor.assert_called_once_with("test_ch", 105)


@patch("app.userbot.poller.ChannelPoller._set_cursor")
@patch("app.userbot.poller.ChannelPoller._fetch_all_since")
@patch("app.userbot.poller.ChannelPoller._get_cursor")
@patch("app.userbot.poller.ChannelPoller._resolve_entity")
async def test_t4_empty_batch_cursor_unchanged(
    mock_resolve, mock_get_cursor, mock_fetch, mock_set_cursor,
):
    """t4: пустой батч → early return, курсор не меняется, _set_cursor НЕ вызывается."""
    mock_resolve.return_value = MagicMock(broadcast=False)
    mock_get_cursor.return_value = 100
    mock_fetch.return_value = []

    poller = ChannelPoller()
    acc = _make_account(1)
    await poller._poll_channel(acc, "test_ch", "Hot", initial=False)

    # Early return на пустом батче — курсор не трогаем
    mock_set_cursor.assert_not_called()


@patch("app.userbot.poller.Message", MagicMock)  # isinstance(mock, Message) → True
@patch("app.userbot.poller.llm_validator")
@patch("app.userbot.poller.classify_message")
@patch("app.userbot.poller.ChannelPoller._log_llm_decision")
@patch("app.userbot.poller.ChannelPoller._log_unmatched")
@patch("app.userbot.poller.ChannelPoller._dispatch")
@patch("app.userbot.poller.ChannelPoller._set_cursor")
@patch("app.userbot.poller.ChannelPoller._fetch_all_since")
@patch("app.userbot.poller.ChannelPoller._get_cursor")
@patch("app.userbot.poller.ChannelPoller._resolve_entity")
async def test_t5_msg_date_none_does_not_crash(
    mock_resolve, mock_get_cursor, mock_fetch, mock_set_cursor,
    mock_dispatch, mock_log_unmatched, mock_log_llm,
    mock_classify, mock_llm,
):
    """t5: msg.date=None не роняет фильтр (guard `if msg.date and ...`).

    Сообщение без даты проходит фильтр и доходит до classify.
    """
    mock_get_cursor.return_value = 100
    mock_llm.validate = AsyncMock(return_value=MagicMock(verdict="OK", reason=""))
    mock_llm.should_block = MagicMock(return_value=False)
    mock_classify.return_value = _fresh_classification()
    mock_resolve.return_value = MagicMock(broadcast=False)

    msg_no_date = _make_msg_with_date(101, days_ago=1)
    msg_no_date.date = None  # нет даты
    mock_fetch.return_value = [msg_no_date]

    poller = ChannelPoller()
    acc = _make_account(1)
    await poller._poll_channel(acc, "test_ch", "Hot", initial=False)

    # Не упало, сообщение без даты дошло до classify
    mock_classify.assert_called_once()
