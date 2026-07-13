"""T5.3 — digest-режим: буферизация не-срочных, срочные мгновенно, round-trip буфера."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.worker.sender import NotificationSender


def _payload(**over):
    p = {
        "user_id": 7, "telegram_id": 700, "lang": "ru", "plan": "business",
        "chat_username": "chat", "text": "Ищу повара", "sender": "author",
        "message_id": 5, "message_hash": "h5", "content_hash": "c5",
        "is_urgent": False, "digest_mode": "instant", "matched_segments": [],
    }
    p.update(over)
    return p


def _sender():
    with patch("app.worker.sender.Bot"):
        s = NotificationSender()
    s.bot = MagicMock()
    s.bot.send_message = AsyncMock()
    return s


async def _run(sender, payload, **extra_patches):
    patches = [
        patch("app.worker.sender.is_duplicate", new=AsyncMock(return_value=False)),
        patch("app.worker.sender.is_content_duplicate", new=AsyncMock(return_value=False)),
        patch("app.worker.sender.mark_sent", new=AsyncMock()),
        patch("app.worker.sender.increment_daily_stats", new=AsyncMock()),
        patch("app.cache.subscription_cache.buffer_digest", new=AsyncMock()),
    ]
    started = [p.start() for p in patches]
    try:
        await sender._send_notification(payload)
    finally:
        for p in patches:
            p.stop()
    return started[-1]  # buffer_digest mock


async def test_non_urgent_digest_is_buffered():
    sender = _sender()
    buf = await _run(sender, _payload(digest_mode="hourly", is_urgent=False))
    sender.bot.send_message.assert_not_awaited()   # не отправлено сразу
    buf.assert_awaited_once()                       # положено в буфер


async def test_urgent_bypasses_digest():
    sender = _sender()
    buf = await _run(sender, _payload(digest_mode="hourly", is_urgent=True))
    sender.bot.send_message.assert_awaited_once()   # 🔥 доставлено мгновенно
    buf.assert_not_awaited()


async def test_instant_mode_sends_immediately():
    sender = _sender()
    buf = await _run(sender, _payload(digest_mode="instant"))
    sender.bot.send_message.assert_awaited_once()
    buf.assert_not_awaited()


async def test_buffer_roundtrip(monkeypatch):
    import app.cache.subscription_cache as sc

    store = {}
    redis = MagicMock()
    async def rpush(k, v): store.setdefault(k, []).append(v)
    async def lrange(k, a, b): return store.get(k, [])
    async def delete(k): store.pop(k, None)
    async def expire(k, t): pass
    redis.rpush, redis.lrange, redis.delete, redis.expire = rpush, lrange, delete, expire
    monkeypatch.setattr(sc, "get_redis", AsyncMock(return_value=redis))

    await sc.buffer_digest(7, {"message_hash": "a"})
    await sc.buffer_digest(7, {"message_hash": "b"})
    items = await sc.pop_all_digest(7)
    assert [i["message_hash"] for i in items] == ["a", "b"]
    assert await sc.pop_all_digest(7) == []   # очищен
