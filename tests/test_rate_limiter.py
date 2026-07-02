"""Tests for per-account rate limiter and daily request budget (Task 0.5)."""

import asyncio
import time
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from app.userbot.rate_limiter import TelegramRateLimiter, BudgetExceeded


# ── Часть A: пер-аккаунтный интервал ──


async def test_accounts_do_not_share_interval():
    """Два аккаунта не делят один интервал: acquire для acc2 не ждёт из-за acc1."""
    lim = TelegramRateLimiter(min_interval=1.0, daily_budget=0)

    # Первый вызов acc1 — проходит мгновенно (нет предыдущего)
    t0 = time.monotonic()
    await lim.acquire(account_id=1)
    t1 = time.monotonic()
    assert t1 - t0 < 0.1  # первый вызов без ожидания

    # Первый вызов acc2 — тоже мгновенно (свой last_call)
    t2 = time.monotonic()
    await lim.acquire(account_id=2)
    t3 = time.monotonic()
    assert t3 - t2 < 0.1  # НЕ ждёт интервал acc1

    # Проверяем, что last_call независимы
    assert 1 in lim._account_last_call
    assert 2 in lim._account_last_call
    assert lim._account_last_call[1] != lim._account_last_call[2]


async def test_same_account_is_serialized():
    """Последовательные вызовы одного аккаунта ждут min_interval."""
    lim = TelegramRateLimiter(min_interval=0.5, daily_budget=0)

    t0 = time.monotonic()
    await lim.acquire(account_id=1)
    t1 = time.monotonic()
    await lim.acquire(account_id=1)
    t2 = time.monotonic()

    assert t1 - t0 < 0.1  # первый мгновенно
    assert (t2 - t1) >= 0.4  # второй ждал ~0.5 сек (с допуском на precision)


async def test_internal_locks_are_per_account():
    """У каждого аккаунта свой asyncio.Lock."""
    lim = TelegramRateLimiter(min_interval=0.1, daily_budget=0)

    await lim.acquire(account_id=1)
    await lim.acquire(account_id=2)

    # У каждого аккаунта — своя запись в словаре локов
    assert 1 in lim._account_locks
    assert 2 in lim._account_locks
    assert lim._account_locks[1] is not lim._account_locks[2]


# ── Часть B: суточный бюджет ──


@patch("app.userbot.rate_limiter.get_redis")
async def test_budget_blocks_after_limit(mock_get_redis):
    """При budget=100 101-й запрос аккаунта → BudgetExceeded."""
    fake_redis = AsyncMock()
    # Настраиваем мок: первые 100 вызовов incr возвращают ≤100, 101-й > 100
    incr_values = list(range(1, 102))  # 1, 2, ..., 101
    fake_redis.incr = AsyncMock(side_effect=incr_values)
    fake_redis.expire = AsyncMock()
    fake_redis.close = AsyncMock()
    mock_get_redis.return_value = fake_redis

    lim = TelegramRateLimiter(min_interval=0.01, daily_budget=100)

    # 100 вызовов проходят
    for _ in range(100):
        await lim.acquire(account_id=1)

    # 101-й — исключение
    with pytest.raises(BudgetExceeded) as exc:
        await lim.acquire(account_id=1)
    assert "бюджет" in str(exc.value).lower() or "budget" in str(exc.value).lower()
    assert fake_redis.incr.call_count == 101


@patch("app.userbot.rate_limiter.get_redis")
async def test_budget_per_account_independent(mock_get_redis):
    """Бюджет аккаунта 1 не влияет на аккаунт 2."""
    fake_redis_1 = AsyncMock()
    fake_redis_1.incr = AsyncMock(side_effect=[1, 2, 3, 101])  # 101 на 4-м вызове
    fake_redis_1.expire = AsyncMock()

    fake_redis_2 = AsyncMock()
    fake_redis_2.incr = AsyncMock(side_effect=[1, 2])  # всегда ≤100
    fake_redis_2.expire = AsyncMock()

    # Разные Redis-инстансы для разных аккаунтов (каждый вызов get_redis() — новый)
    mock_get_redis.side_effect = [fake_redis_1, fake_redis_1, fake_redis_1,
                                   fake_redis_2, fake_redis_2]

    lim = TelegramRateLimiter(min_interval=0.01, daily_budget=100)

    # Аккаунт 1: 3 вызова проходят
    await lim.acquire(account_id=1)
    await lim.acquire(account_id=1)
    await lim.acquire(account_id=1)

    # Аккаунт 2: работает независимо
    await lim.acquire(account_id=2)
    await lim.acquire(account_id=2)


@patch("app.userbot.rate_limiter.get_redis")
@patch("app.userbot.rate_limiter._budget_key")
async def test_budget_resets_on_date_change(mock_budget_key, mock_get_redis):
    """Смена даты в имени ключа обнуляет счётчик — завтра новый ключ."""
    fake_redis = AsyncMock()
    call_count = {"count": 0}

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")
    today_key = f"budget:used:1:{today}"
    tomorrow_key = f"budget:used:1:{tomorrow}"

    # Сегодня: _budget_key возвращает today_key
    mock_budget_key.return_value = today_key

    async def incr_side_effect(key):
        call_count["count"] += 1
        return call_count["count"]

    fake_redis.incr = AsyncMock(side_effect=incr_side_effect)
    fake_redis.expire = AsyncMock()
    fake_redis.aclose = AsyncMock()
    mock_get_redis.return_value = fake_redis

    lim = TelegramRateLimiter(min_interval=0.01, daily_budget=100)

    # Исчерпываем бюджет сегодня
    for _ in range(100):
        await lim.acquire(account_id=1)
    with pytest.raises(BudgetExceeded):
        await lim.acquire(account_id=1)
    assert call_count["count"] == 101  # 100 OK + 1 превышение

    # «Наступило завтра»: _budget_key возвращает tomorrow_key
    mock_budget_key.return_value = tomorrow_key

    # Сбрасываем счётчик и проверяем — новый ключ, счётчик с 1
    captured_keys = []
    async def record_and_return(key):
        captured_keys.append(key)
        return 1
    fake_redis.incr = AsyncMock(side_effect=record_and_return)

    await lim.acquire(account_id=1)
    assert len(captured_keys) == 1
    assert captured_keys[0] == tomorrow_key, f"Expected {tomorrow_key}, got {captured_keys[0]}"


async def test_budget_exceeded_message_contains_account_id():
    """BudgetExceeded содержит account_id в сообщении."""
    exc = BudgetExceeded(account_id=5, used=101, limit=100)
    assert "5" in str(exc)
    assert "101" in str(exc)
    assert "100" in str(exc)
