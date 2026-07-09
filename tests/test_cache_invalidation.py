"""Tests for task A4 (fable_audit.md) — subscription cache invalidation.

Bug C4: rebuild_subscription_cache was only called lazily on cache miss
(TTL 1h). No CRUD path invalidated the cache, so a new subscription/keyword
took up to an hour to reach the poller, and a deleted one kept delivering.
"""

from unittest.mock import AsyncMock, patch

import fakeredis.aioredis

from app.cache.subscription_cache import (
    invalidate_all_subscription_caches,
    get_interested_users,
)


def _fake_redis():
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


@patch("app.cache.subscription_cache.get_redis")
async def test_invalidate_drops_only_subscription_keys(mock_get_redis):
    """Удаляются все sub:by_chat:*, посторонние ключи не тронуты."""
    fake = _fake_redis()
    mock_get_redis.return_value = fake

    await fake.set("sub:by_chat:chat_a", "[]")
    await fake.set("sub:by_chat:chat_b", "[]")
    await fake.set("cursor:msg:chat_a", "42")
    await fake.set("budget:used:1:2026-07-09", "10")

    await invalidate_all_subscription_caches()

    assert await fake.get("sub:by_chat:chat_a") is None
    assert await fake.get("sub:by_chat:chat_b") is None
    assert await fake.get("cursor:msg:chat_a") == "42"
    assert await fake.get("budget:used:1:2026-07-09") == "10"


@patch("app.cache.subscription_cache.get_redis")
async def test_invalidate_handles_many_keys(mock_get_redis):
    """SCAN-цикл проходит больше одной страницы (count=200)."""
    fake = _fake_redis()
    mock_get_redis.return_value = fake

    for i in range(450):
        await fake.set(f"sub:by_chat:chat_{i}", "[]")

    await invalidate_all_subscription_caches()

    remaining = [k async for k in fake.scan_iter(match="sub:by_chat:*")]
    assert remaining == []


@patch("app.cache.subscription_cache.get_redis")
async def test_get_interested_users_empty_after_invalidation(mock_get_redis):
    """После инвалидации get_interested_users видит пустой кэш →
    _dispatch запустит lazy rebuild со свежими данными из БД."""
    fake = _fake_redis()
    mock_get_redis.return_value = fake

    await fake.set(
        "sub:by_chat:some_chat",
        '[{"user_id": 1, "keyword_texts": ["старое слово"]}]',
    )
    assert await get_interested_users("some_chat") != []

    await invalidate_all_subscription_caches()

    assert await get_interested_users("some_chat") == []
