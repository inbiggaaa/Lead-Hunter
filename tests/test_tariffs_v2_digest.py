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
    buf_mock = AsyncMock()
    patches = [
        patch("app.worker.sender.is_duplicate", new=AsyncMock(return_value=False)),
        patch("app.worker.sender.is_content_duplicate", new=AsyncMock(return_value=False)),
        patch("app.worker.sender.mark_sent", new=AsyncMock()),
        patch("app.worker.sender.increment_daily_stats", new=AsyncMock()),
        patch("app.worker.sender._user_may_receive", new=AsyncMock(return_value=True)),
        patch("app.cache.subscription_cache.buffer_digest", new=buf_mock),
        patch("app.cache.subscription_cache.is_digest_inflight", new=AsyncMock(return_value=False)),
    ]
    for p in patches:
        p.start()
    try:
        await sender._send_notification(payload)
    finally:
        for p in patches:
            p.stop()
    return buf_mock


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

    lists: dict[str, list] = {}
    sets: dict[str, set] = {}
    redis = MagicMock()

    async def rpush(k, *vals):
        lists.setdefault(k, []).extend(vals)

    async def lrange(k, a, b):
        return lists.get(k, [])

    async def delete(k):
        lists.pop(k, None)
        sets.pop(k, None)

    async def expire(k, t):
        pass

    async def exists(k):
        return int(k in lists)

    async def rename(src, dst):
        lists[dst] = lists.pop(src)

    async def sadd(k, *members):
        sets.setdefault(k, set()).update(members)
        return len(members)

    async def srem(k, *members):
        s = sets.get(k) or set()
        for m in members:
            s.discard(m)

    async def sismember(k, m):
        return m in (sets.get(k) or set())

    redis.rpush = rpush
    redis.lrange = lrange
    redis.delete = delete
    redis.expire = expire
    redis.exists = exists
    redis.rename = rename
    redis.sadd = sadd
    redis.srem = srem
    redis.sismember = sismember
    monkeypatch.setattr(sc, "get_redis", AsyncMock(return_value=redis))

    await sc.buffer_digest(7, {"message_hash": "a"})
    await sc.buffer_digest(7, {"message_hash": "b"})
    items = await sc.claim_digest(7)
    assert [i["message_hash"] for i in items] == ["a", "b"]
    assert await sc.claim_digest(7) == []   # буфер перенесён в processing
