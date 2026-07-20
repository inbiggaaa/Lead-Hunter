"""Phase 6: real DB+Redis critical-path checks (Telegram/LLM faked)."""

from __future__ import annotations

import datetime as dt
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.cache import get_redis
from app.cache import subscription_cache as sc
from app.config import settings
from app.db.models import Base, User
from app.payments.activate import activate_paid_subscription
from app.worker.sender import NotificationSender


@pytest_asyncio.fixture
async def db_engine():
    engine = create_async_engine(settings.database_url, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.mark.asyncio
async def test_queue_roundtrip_real_redis():
    """push → claim (BLMOVE+LSET) → ack against live Redis."""
    redis = await get_redis()
    # Isolate keys for this process
    await redis.delete(sc.QUEUE_NOTIFICATIONS, sc.QUEUE_PROCESSING, sc.QUEUE_DEAD_LETTER)

    body = {
        "user_id": 9001,
        "telegram_id": 9001,
        "message_hash": "phase6-hash",
        "text": "нужен электрик",
        "plan": "pro",
        "lang": "ru",
        "chat_username": "phase6_chat",
        "matched_segments": [],
    }
    await sc.push_notification(body)
    envelope = await sc.claim_notification(timeout=2)
    assert envelope is not None
    assert envelope["body"]["message_hash"] == "phase6-hash"
    assert envelope["claimed_at"]
    assert await redis.llen(sc.QUEUE_PROCESSING) == 1
    await sc.ack_notification(envelope)
    assert await redis.llen(sc.QUEUE_PROCESSING) == 0
    assert await redis.llen(sc.QUEUE_NOTIFICATIONS) == 0


@pytest.mark.asyncio
async def test_digest_reclaim_stale_processing_real_redis():
    import json

    redis = await get_redis()
    uid = 9002
    key = sc.DIGEST_KEY.format(user_id=uid)
    proc = sc.DIGEST_PROCESSING_KEY.format(user_id=uid)
    await redis.delete(key, proc)
    await redis.rpush(proc, json.dumps({"message_hash": "d1", "text": "x"}))
    # Force "nearly expired" claim: TTL below DIGEST_CLAIM_TTL_SEC // 2
    await redis.expire(proc, 10)

    n = await sc.reclaim_stale_digests([uid])
    assert n == 1
    assert await redis.exists(key) == 1
    assert await redis.exists(proc) == 0
    await redis.delete(key)


@pytest.mark.asyncio
async def test_sender_expired_plan_hides_contacts():
    """Immediate expiry: cached paid plan past plan_expires_at → free format."""
    past = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=1)).isoformat()
    payload = {
        "user_id": 42,
        "telegram_id": 42,
        "lang": "ru",
        "plan": "pro",
        "plan_expires_at": past,
        "chat_username": "phase6_chat",
        "text": "ищу мастера",
        "sender": "lead_author",
        "message_id": 11,
        "message_hash": "phase6-exp-42",
        "content_hash": "phase6-exp-c-42",
        "is_urgent": False,
        "matched_segments": [],
        "digest_mode": "instant",
    }

    with patch("app.worker.sender.Bot"):
        sender = NotificationSender()
    sender.bot = MagicMock()
    sender.bot.send_message = AsyncMock()

    with (
        patch("app.worker.sender._user_may_receive", new=AsyncMock(return_value=True)),
        patch("app.worker.sender.is_duplicate", new=AsyncMock(return_value=False)),
        patch("app.worker.sender.is_content_duplicate", new=AsyncMock(return_value=False)),
        patch("app.worker.sender.mark_sent", new=AsyncMock()),
        patch("app.worker.sender.increment_daily_stats", new=AsyncMock()),
        patch("app.cache.subscription_cache.is_digest_inflight", new=AsyncMock(return_value=False)),
        patch("app.lifecycle.claim_free_teaser", new=AsyncMock(return_value=(True, 0))),
        patch("app.lifecycle.increment_lifecycle_matches", new=AsyncMock()),
    ):
        result = await sender._send_notification(payload)

    assert result == "ok"
    sender.bot.send_message.assert_awaited_once()
    kb = sender.bot.send_message.call_args.kwargs.get("reply_markup")
    # Free paywall button — not the paid «Ответить» contact actions.
    buttons = []
    if kb is not None:
        for row in kb.inline_keyboard:
            buttons.extend(btn.text for btn in row)
    assert any("контакт" in t.lower() or "contact" in t.lower() or "$" in t for t in buttons)
