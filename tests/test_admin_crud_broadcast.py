"""Regression tests for admin CRUD allowlists and broadcast confirmation."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException

from app.admin import broadcast
from app.admin.api import crud


def test_validate_fields_rejects_unknown_and_invalid_enums() -> None:
    with pytest.raises(HTTPException) as error:
        crud._validate_fields("segments", {"slug": "x", "extra": 1}, is_create=True)
    assert error.value.status_code == 422

    with pytest.raises(HTTPException) as error:
        crud._validate_fields(
            "segments",
            {"slug": "x", "lead_direction": "invalid"},
            is_create=True,
        )
    assert error.value.status_code == 422

    with pytest.raises(HTTPException) as error:
        crud._validate_fields(
            "segment_keywords",
            {"text": "x", "keyword_type": "invalid"},
            is_create=True,
        )
    assert error.value.status_code == 422

    clean = crud._validate_fields(
        "segments",
        {"slug": "x", "lead_direction": "demand"},
        is_create=True,
    )
    assert clean["lead_direction"] == "demand"


@pytest.mark.asyncio
async def test_broadcast_preview_rejects_empty_text() -> None:
    with pytest.raises(ValueError, match="empty"):
        await broadcast.create_broadcast_preview("all", "all", "   ")


@pytest.mark.asyncio
async def test_broadcast_send_requires_confirmation_token(monkeypatch) -> None:
    monkeypatch.setattr(broadcast, "_consume_confirmation", AsyncMock(return_value=False))
    result = await broadcast.broadcast_send(
        plan_filter="all",
        source_filter="all",
        text="hello",
        confirmation_token="bad",
    )
    assert result == {"error": "Invalid or expired confirmation token"}


@pytest.mark.asyncio
async def test_broadcast_send_uses_distributed_lock(monkeypatch) -> None:
    redis = Mock()
    redis.set = AsyncMock(return_value=True)
    redis.get = AsyncMock(return_value=b"lock-token")
    redis.delete = AsyncMock()
    redis.getdel = AsyncMock(
        return_value='{"plan": "all", "source": "all", "text": "hello"}'
    )
    monkeypatch.setattr(broadcast, "get_redis", AsyncMock(return_value=redis))
    monkeypatch.setattr(broadcast.secrets, "token_urlsafe", lambda n: "lock-token")

    session = Mock()
    session.execute = AsyncMock(
        return_value=SimpleNamespace(all=lambda: [(111, 1), (222, 2)])
    )

    class _SessionCtx:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *args):
            return None

    monkeypatch.setattr(broadcast, "async_session_factory", lambda: _SessionCtx())
    monkeypatch.setattr(broadcast.asyncio, "sleep", AsyncMock())

    bot = Mock()
    bot.send_message = AsyncMock()
    bot.session.close = AsyncMock()
    monkeypatch.setattr(
        "aiogram.Bot",
        lambda token: bot,
        raising=False,
    )
    import aiogram
    monkeypatch.setattr(aiogram, "Bot", lambda token: bot)

    result = await broadcast.broadcast_send(
        plan_filter="all",
        source_filter="all",
        text="hello",
        confirmation_token="token",
    )

    assert result == {"sent": 2, "failed": 0, "total": 2}
    redis.set.assert_awaited()
    redis.delete.assert_awaited_with(broadcast.BROADCAST_LOCK_KEY)
    assert bot.send_message.await_count == 2
