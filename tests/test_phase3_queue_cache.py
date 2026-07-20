"""Phase 3 regression: claim stamp, deliverability, and City slug drift."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.cache import subscription_cache as cache
from app.db.models import City


def test_city_slug_is_not_globally_unique() -> None:
    slug_col = City.__table__.c.slug
    # SQLAlchemy stores unset unique as None (not False).
    assert not slug_col.unique
    names = {c.name for c in City.__table__.constraints if getattr(c, "name", None)}
    assert "uq_cities_country_slug" in names


def test_user_is_deliverable_respects_ban_and_suspension() -> None:
    now = datetime.now(timezone.utc)
    banned = SimpleNamespace(
        is_banned=True, is_blocked_bot=False, is_suspended=False, suspended_until=None,
    )
    blocked = SimpleNamespace(
        is_banned=False, is_blocked_bot=True, is_suspended=False, suspended_until=None,
    )
    suspended = SimpleNamespace(
        is_banned=False,
        is_blocked_bot=False,
        is_suspended=True,
        suspended_until=None,
    )
    expired_suspend = SimpleNamespace(
        is_banned=False,
        is_blocked_bot=False,
        is_suspended=True,
        suspended_until=now - timedelta(hours=1),
    )
    active = SimpleNamespace(
        is_banned=False, is_blocked_bot=False, is_suspended=False, suspended_until=None,
    )

    assert cache.user_is_deliverable(banned, now=now) is False
    assert cache.user_is_deliverable(blocked, now=now) is False
    assert cache.user_is_deliverable(suspended, now=now) is False
    assert cache.user_is_deliverable(expired_suspend, now=now) is True
    assert cache.user_is_deliverable(active, now=now) is True


@pytest.mark.asyncio
async def test_claim_notification_stamps_with_lset(monkeypatch) -> None:
    calls: list[tuple] = []

    class _Redis:
        async def blmove(self, *args):
            return cache._serialize_envelope(
                cache._wrap_envelope({"user_id": 1, "message_hash": "abc"})
            )

        async def lset(self, key, index, value):
            calls.append((key, index, value))

    monkeypatch.setattr(cache, "get_redis", AsyncMock(return_value=_Redis()))
    envelope = await cache.claim_notification(timeout=1)

    assert envelope["claimed_at"]
    assert envelope["id"]
    assert calls and calls[0][0] == cache.QUEUE_PROCESSING and calls[0][1] == 0


@pytest.mark.asyncio
async def test_sender_skips_undeliverable_user(monkeypatch) -> None:
    from app.worker.sender import NotificationSender

    with patch("app.worker.sender.Bot"):
        sender = NotificationSender()
    sender.bot = Mock()
    sender.bot.send_message = AsyncMock()

    monkeypatch.setattr(
        "app.worker.sender._user_may_receive", AsyncMock(return_value=False),
    )
    monkeypatch.setattr(
        "app.worker.sender.is_duplicate", AsyncMock(return_value=False),
    )
    result = await sender._send_notification({
        "user_id": 1,
        "telegram_id": 1,
        "lang": "ru",
        "plan": "pro",
        "chat_username": "c",
        "text": "x",
        "sender": "s",
        "message_id": 1,
        "message_hash": "h",
        "matched_segments": [],
    })
    assert result == "skipped"
    sender.bot.send_message.assert_not_awaited()
