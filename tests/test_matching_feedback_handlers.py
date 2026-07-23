"""Handler tests for closed matching feedback."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fakeredis.aioredis import FakeRedis

from app.config import settings
from app.db.models import Feedback, User
from app.matching_feedback.domain import (
    FeedbackReason,
    FeedbackVerdict,
    encode_feedback_callback,
)
from app.bot.handlers import feedback as feedback_handlers


def _cb(data: str, tg_id: int = 100500):
    message = MagicMock()
    message.message_id = 55
    message.edit_reply_markup = AsyncMock()
    message.edit_text = AsyncMock()
    callback = MagicMock()
    callback.data = data
    callback.from_user = SimpleNamespace(id=tg_id)
    callback.message = message
    callback.answer = AsyncMock()
    return callback


@pytest.fixture
def enable_mf(monkeypatch):
    monkeypatch.setattr(settings, "matching_feedback_enabled", True)
    monkeypatch.setattr(settings, "matching_feedback_tester_ids", "100500")
    monkeypatch.setattr(settings, "matching_feedback_batch", "ru_matching_v1")


@pytest.mark.asyncio
async def test_single_segment_correct_saves(session, enable_mf):
    user = User(telegram_id=100500, language="ru")
    session.add(user)
    await session.flush()
    item = Feedback(
        public_token="TokCorrect1",
        test_batch="ru_matching_v1",
        user_id=user.id,
        chat_username="c",
        message_id=1,
        delivered_segments=["cleaning"],
        verdict=None,
    )
    session.add(item)
    await session.flush()

    callback = _cb(encode_feedback_callback("correct", "TokCorrect1"))

    # Use real session via patched factory yielding our session is hard;
    # call internal label path with repository instead for unit certainty.
    from app.matching_feedback.repository import set_feedback_label

    saved = await set_feedback_label(
        item.id,
        verdict=FeedbackVerdict.CORRECT,
        confirmed_segments=("cleaning",),
        session=session,
    )
    assert saved.verdict == "correct"
    assert saved.confirmed_segments == ["cleaning"]

    # Handler keyboard edit path
    with patch.object(
        feedback_handlers,
        "get_feedback_by_token_session",
        new=AsyncMock(return_value=item),
    ), patch.object(
        feedback_handlers,
        "set_feedback_label",
        new=AsyncMock(return_value=saved),
    ), patch.object(
        feedback_handlers,
        "async_session_factory",
    ) as factory:
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=session)
        cm.__aexit__ = AsyncMock(return_value=None)
        begin_cm = MagicMock()
        begin_cm.__aenter__ = AsyncMock(return_value=None)
        begin_cm.__aexit__ = AsyncMock(return_value=None)
        session.begin = MagicMock(return_value=begin_cm)
        factory.return_value = cm
        # scalar for user
        session.scalar = AsyncMock(return_value=user)
        await feedback_handlers.matching_feedback_callback(callback)

    assert callback.message.edit_reply_markup.await_count == 1
    callback.answer.assert_awaited()


@pytest.mark.asyncio
async def test_uncertain_saves(session, enable_mf):
    user = User(telegram_id=100500, language="ru")
    session.add(user)
    await session.flush()
    item = Feedback(
        public_token="TokUnsure01",
        test_batch="ru_matching_v1",
        user_id=user.id,
        chat_username="c",
        message_id=2,
        delivered_segments=["cleaning"],
    )
    session.add(item)
    await session.flush()
    from app.matching_feedback.repository import set_feedback_label

    saved = await set_feedback_label(
        item.id, verdict=FeedbackVerdict.UNCERTAIN, session=session
    )
    assert saved.verdict == "uncertain"
    assert saved.reason_code is None


@pytest.mark.asyncio
async def test_reason_saves_error(session, enable_mf):
    user = User(telegram_id=100500, language="ru")
    session.add(user)
    await session.flush()
    item = Feedback(
        public_token="TokError001",
        test_batch="ru_matching_v1",
        user_id=user.id,
        chat_username="c",
        message_id=3,
        delivered_segments=["cleaning"],
    )
    session.add(item)
    await session.flush()
    from app.matching_feedback.repository import set_feedback_label

    saved = await set_feedback_label(
        item.id,
        verdict=FeedbackVerdict.ERROR,
        reason=FeedbackReason.PROVIDER_OFFER,
        session=session,
    )
    assert saved.verdict == FeedbackVerdict.ERROR
    assert saved.reason_code == FeedbackReason.PROVIDER_OFFER


@pytest.mark.asyncio
async def test_edit_failure_keeps_label(session, enable_mf):
    user = User(telegram_id=100500, language="ru")
    session.add(user)
    await session.flush()
    item = Feedback(
        public_token="TokEditFail",
        test_batch="ru_matching_v1",
        user_id=user.id,
        chat_username="c",
        message_id=4,
        delivered_segments=["cleaning"],
    )
    session.add(item)
    await session.flush()

    callback = _cb(encode_feedback_callback("uncertain", "TokEditFail"))
    callback.message.edit_reply_markup = AsyncMock(side_effect=RuntimeError("edit fail"))

    from app.matching_feedback.repository import set_feedback_label

    async def _set(*args, **kwargs):
        return await set_feedback_label(
            item.id, verdict=FeedbackVerdict.UNCERTAIN, session=session
        )

    with patch.object(
        feedback_handlers, "get_feedback_by_token_session", new=AsyncMock(return_value=item)
    ), patch.object(
        feedback_handlers, "set_feedback_label", new=AsyncMock(side_effect=_set)
    ), patch.object(feedback_handlers, "async_session_factory") as factory:
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=session)
        cm.__aexit__ = AsyncMock(return_value=None)
        begin_cm = MagicMock()
        begin_cm.__aenter__ = AsyncMock(return_value=None)
        begin_cm.__aexit__ = AsyncMock(return_value=None)
        session.begin = MagicMock(return_value=begin_cm)
        session.scalar = AsyncMock(return_value=user)
        factory.return_value = cm
        await feedback_handlers.matching_feedback_callback(callback)

    await session.refresh(item)
    assert item.verdict == "uncertain"


@pytest.mark.asyncio
async def test_foreign_token_rejected(enable_mf):
    callback = _cb(encode_feedback_callback("correct", "NoSuchToken"), tg_id=100500)
    fake_user = User(id=1, telegram_id=100500, language="ru")
    with patch.object(
        feedback_handlers, "get_feedback_by_token_session", new=AsyncMock(return_value=None)
    ), patch.object(feedback_handlers, "async_session_factory") as factory:
        session = MagicMock()
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=session)
        cm.__aexit__ = AsyncMock(return_value=None)
        begin_cm = MagicMock()
        begin_cm.__aenter__ = AsyncMock(return_value=None)
        begin_cm.__aexit__ = AsyncMock(return_value=None)
        session.begin = MagicMock(return_value=begin_cm)
        session.scalar = AsyncMock(return_value=fake_user)
        factory.return_value = cm
        await feedback_handlers.matching_feedback_callback(callback)
    callback.answer.assert_awaited()
    assert "недоступна" in callback.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_callback_lengths_for_handler_actions():
    token = "AbCdEf123456"
    for action, value in [
        ("correct", None),
        ("error", None),
        ("uncertain", None),
        ("reason", "wrong_category"),
        ("confirm_seg", "0"),
        ("confirm_done", None),
        ("candidate", "12345"),
        ("catalog", "c12"),
        ("cat_missing", None),
        ("skip", None),
        ("back", None),
        ("change", None),
    ]:
        data = encode_feedback_callback(action, token, value)
        assert len(data.encode()) <= 64
