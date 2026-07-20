"""P0: BLMOVE claim/ack/reclaim notification queue + digest crash safety."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.cache.subscription_cache as sc
from app.worker import digest as digest_mod


class FakeRedis:
    """Minimal async Redis stub for LIST/SET queue operations."""

    def __init__(self):
        self.lists: dict[str, list[str]] = {}
        self.sets: dict[str, set[str]] = {}
        self.ttls: dict[str, int] = {}

    async def lpush(self, key, *values):
        lst = self.lists.setdefault(key, [])
        for v in reversed(values):
            lst.insert(0, v if isinstance(v, str) else v.decode())

    async def rpush(self, key, *values):
        lst = self.lists.setdefault(key, [])
        for v in values:
            lst.append(v if isinstance(v, str) else v.decode())

    async def blmove(self, source, dest, timeout, wherefrom, wheredest):
        src = self.lists.get(source) or []
        if not src:
            return None
        if wherefrom == "RIGHT":
            val = src.pop()
        else:
            val = src.pop(0)
        dest_list = self.lists.setdefault(dest, [])
        if wheredest == "LEFT":
            dest_list.insert(0, val)
        else:
            dest_list.append(val)
        return val

    async def lrem(self, key, count, value):
        lst = self.lists.get(key) or []
        removed = 0
        if count == 0:
            self.lists[key] = [x for x in lst if x != value]
            return len(lst) - len(self.lists[key])
        new = []
        for x in lst:
            if x == value and removed < abs(count):
                removed += 1
                continue
            new.append(x)
        self.lists[key] = new
        return removed

    async def lrange(self, key, start, end):
        lst = self.lists.get(key) or []
        if end == -1:
            return list(lst[start:])
        return list(lst[start:end + 1])

    async def lset(self, key, index, value):
        lst = self.lists.setdefault(key, [])
        if index < 0 or index >= len(lst):
            raise IndexError(index)
        lst[index] = value if isinstance(value, str) else value.decode()

    async def incr(self, key):
        # Counters live outside LIST/SET maps for this stub.
        if not hasattr(self, "counters"):
            self.counters = {}
        self.counters[key] = int(self.counters.get(key, 0)) + 1
        return self.counters[key]

    async def llen(self, key):
        return len(self.lists.get(key) or [])

    async def lpop(self, key):
        lst = self.lists.get(key) or []
        if not lst:
            return None
        return lst.pop(0)

    async def delete(self, *keys):
        n = 0
        for k in keys:
            if k in self.lists:
                del self.lists[k]
                n += 1
            if k in self.sets:
                del self.sets[k]
                n += 1
        return n

    async def exists(self, key):
        return int(key in self.lists or key in self.sets)

    async def rename(self, src, dst):
        if src not in self.lists:
            raise KeyError(src)
        self.lists[dst] = self.lists.pop(src)

    async def expire(self, key, ttl):
        self.ttls[key] = ttl

    async def ttl(self, key):
        if key not in self.lists and key not in self.sets:
            return -2
        return self.ttls.get(key, -1)

    async def sadd(self, key, *members):
        s = self.sets.setdefault(key, set())
        before = len(s)
        s.update(members)
        return len(s) - before

    async def srem(self, key, *members):
        s = self.sets.get(key) or set()
        n = 0
        for m in members:
            if m in s:
                s.discard(m)
                n += 1
        return n

    async def sismember(self, key, member):
        return member in (self.sets.get(key) or set())


@pytest.fixture
def fake_redis(monkeypatch):
    r = FakeRedis()
    monkeypatch.setattr(sc, "get_redis", AsyncMock(return_value=r))
    return r


@pytest.mark.asyncio
async def test_claim_crash_before_ack_then_reclaim(fake_redis):
    body = {"user_id": 1, "message_hash": "h1", "text": "lead"}
    await sc.push_notification(body)

    envelope = await sc.claim_notification(timeout=1)
    assert envelope is not None
    assert envelope["body"]["message_hash"] == "h1"
    assert await fake_redis.llen(sc.QUEUE_NOTIFICATIONS) == 0
    assert await fake_redis.llen(sc.QUEUE_PROCESSING) == 1

    # Simulate crash: no ack. Force claimed_at into the past.
    stale = dict(envelope)
    stale["claimed_at"] = (
        datetime.now(timezone.utc) - timedelta(seconds=sc.CLAIM_TTL_SEC + 10)
    ).isoformat()
    old_raw = sc._serialize_envelope(envelope)
    new_raw = sc._serialize_envelope(stale)
    await fake_redis.lrem(sc.QUEUE_PROCESSING, 1, old_raw)
    await fake_redis.lpush(sc.QUEUE_PROCESSING, new_raw)

    n = await sc.reclaim_stale_notifications()
    assert n == 1
    assert await fake_redis.llen(sc.QUEUE_PROCESSING) == 0
    assert await fake_redis.llen(sc.QUEUE_NOTIFICATIONS) == 1

    again = await sc.claim_notification(timeout=1)
    assert again["body"]["message_hash"] == "h1"


@pytest.mark.asyncio
async def test_ack_removes_from_processing(fake_redis):
    await sc.push_notification({"user_id": 2, "message_hash": "h2"})
    envelope = await sc.claim_notification(timeout=1)
    await sc.ack_notification(envelope)
    assert await fake_redis.llen(sc.QUEUE_PROCESSING) == 0
    assert await fake_redis.llen(sc.QUEUE_NOTIFICATIONS) == 0


@pytest.mark.asyncio
async def test_fail_to_dlq(fake_redis):
    await sc.push_notification({"user_id": 3, "message_hash": "h3"})
    envelope = await sc.claim_notification(timeout=1)
    await sc.fail_notification(envelope, to_dlq=True)
    assert await fake_redis.llen(sc.QUEUE_PROCESSING) == 0
    assert await fake_redis.llen(sc.QUEUE_NOTIFICATIONS) == 0
    assert await fake_redis.llen(sc.QUEUE_DEAD_LETTER) == 1
    raw = (await fake_redis.lrange(sc.QUEUE_DEAD_LETTER, 0, -1))[0]
    assert json.loads(raw)["message_hash"] == "h3"


@pytest.mark.asyncio
async def test_fail_requeues_until_max_attempts(fake_redis):
    await sc.push_notification({"user_id": 4, "message_hash": "h4"})
    for i in range(sc.MAX_DELIVERY_ATTEMPTS):
        envelope = await sc.claim_notification(timeout=1)
        assert envelope is not None
        await sc.fail_notification(envelope, to_dlq=False)
        if i < sc.MAX_DELIVERY_ATTEMPTS - 1:
            assert await fake_redis.llen(sc.QUEUE_NOTIFICATIONS) == 1
            assert await fake_redis.llen(sc.QUEUE_DEAD_LETTER) == 0
        else:
            assert await fake_redis.llen(sc.QUEUE_NOTIFICATIONS) == 0
            assert await fake_redis.llen(sc.QUEUE_DEAD_LETTER) == 1


@pytest.mark.asyncio
async def test_legacy_bare_payload_normalized(fake_redis):
    """Items pushed before the envelope wrapper still claim successfully."""
    await fake_redis.lpush(sc.QUEUE_NOTIFICATIONS, json.dumps({"user_id": 5, "message_hash": "legacy"}))
    envelope = await sc.claim_notification(timeout=1)
    assert envelope["body"]["message_hash"] == "legacy"
    await sc.ack_notification(envelope)


@pytest.mark.asyncio
async def test_digest_flush_restores_on_mid_failure(fake_redis, monkeypatch):
    """Send fails on 2nd of 3 → remaining two stay in digest buffer; first mark_sent."""
    user = MagicMock(id=77, telegram_id=70077, language="ru", digest_mode="hourly")

    payloads = [
        {"user_id": 77, "message_hash": f"h{i}", "text": f"t{i}",
         "chat_username": "c", "message_id": i, "matched_segments": []}
        for i in range(3)
    ]
    for p in payloads:
        await sc.buffer_digest(77, p)

    calls = {"n": 0}
    marked: list[str] = []

    async def fake_send(chat_id, text, reply_markup=None):
        calls["n"] += 1
        # 1 = header, 2 = first lead ok, 3 = second lead fails
        if calls["n"] == 3:
            raise RuntimeError("telegram down")

    mock_sender = MagicMock()
    mock_sender.bot = MagicMock()
    mock_sender.bot.send_message = AsyncMock(side_effect=fake_send)
    mock_sender.bot.session = AsyncMock()
    mock_sender.throttle_interval = 0
    mock_sender._format_notification = MagicMock(return_value="text")
    mock_sender._build_keyboard = MagicMock(return_value=None)

    async def capture_mark(uid, mh, *a, **k):
        marked.append(mh)

    class _S:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def execute(self, *_a, **_k):
            class R:
                def scalars(self):
                    return self

                def all(self):
                    return [user]
            return R()

    with (
        patch.object(digest_mod, "async_session_factory", return_value=_S()),
        patch("app.worker.sender.NotificationSender", return_value=mock_sender),
        patch("app.worker.digest.mark_sent", new=AsyncMock(side_effect=capture_mark)),
        patch("app.worker.digest.increment_daily_stats", new=AsyncMock()),
        patch("app.worker.digest.reclaim_stale_digests", new=AsyncMock(return_value=0)),
        patch("app.worker.digest.is_duplicate", new=AsyncMock(return_value=False)),
        patch("app.worker.digest.is_content_duplicate", new=AsyncMock(return_value=False)),
    ):
        await digest_mod.flush_digests()

    assert marked == ["h0"]
    # After restore, undelivered items are back on the live digest key
    key = sc.DIGEST_KEY.format(user_id=77)
    raw_items = await fake_redis.lrange(key, 0, -1)
    hashes = [json.loads(x)["message_hash"] for x in raw_items]
    assert hashes == ["h1", "h2"]
