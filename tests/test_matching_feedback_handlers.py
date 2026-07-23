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
from app.matching_feedback.repository import set_feedback_label
from app.bot.handlers import feedback as feedback_handlers


def _cb(data: str, tg_id: int = 100500):
    message = MagicMock()
    message.message_id = 55
    message.edit_reply_markup = AsyncMock()
    message.edit_text = AsyncMock()
    message.delete = AsyncMock()
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


def _patch_session(factory_patch, session, user):
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=session)
    cm.__aexit__ = AsyncMock(return_value=None)
    begin_cm = MagicMock()
    begin_cm.__aenter__ = AsyncMock(return_value=None)
    begin_cm.__aexit__ = AsyncMock(return_value=None)
    session.begin = MagicMock(return_value=begin_cm)
    session.scalar = AsyncMock(return_value=user)
    factory_patch.return_value = cm


@pytest.mark.asyncio
async def test_multi_correct_opens_selector_without_save(session, enable_mf):
    user = User(telegram_id=100500, language="ru")
    session.add(user)
    await session.flush()
    item = Feedback(
        public_token="TokMulti001",
        test_batch="ru_matching_v1",
        user_id=user.id,
        chat_username="c",
        message_id=10,
        delivered_segments=["cleaning", "repair"],
        verdict=None,
    )
    session.add(item)
    await session.flush()

    callback = _cb(encode_feedback_callback("correct", "TokMulti001"))
    with patch.object(
        feedback_handlers,
        "get_feedback_by_token_session",
        new=AsyncMock(return_value=item),
    ), patch.object(feedback_handlers, "async_session_factory") as factory:
        _patch_session(factory, session, user)
        await feedback_handlers.matching_feedback_callback(callback)

    await session.refresh(item)
    assert item.verdict is None
    markup = callback.message.edit_reply_markup.await_args.kwargs["reply_markup"]
    texts = [btn.text for row in markup.inline_keyboard for btn in row]
    assert any("cleaning" in t for t in texts)
    assert any("repair" in t for t in texts)
    assert not any("Готово" in t or "Done" in t for t in texts)


@pytest.mark.asyncio
async def test_confirm_done_requires_selection(session, enable_mf, monkeypatch):
    user = User(telegram_id=100500, language="ru")
    session.add(user)
    await session.flush()
    item = Feedback(
        public_token="TokMulti002",
        test_batch="ru_matching_v1",
        user_id=user.id,
        chat_username="c",
        message_id=11,
        delivered_segments=["cleaning", "repair"],
    )
    session.add(item)
    await session.flush()

    redis = FakeRedis()
    monkeypatch.setattr(
        "app.cache.get_redis",
        AsyncMock(return_value=redis),
    )

    callback = _cb(encode_feedback_callback("confirm_done", "TokMulti002"))
    with patch.object(
        feedback_handlers,
        "get_feedback_by_token_session",
        new=AsyncMock(return_value=item),
    ), patch.object(feedback_handlers, "async_session_factory") as factory:
        _patch_session(factory, session, user)
        await feedback_handlers.matching_feedback_callback(callback)

    await session.refresh(item)
    assert item.verdict is None
    assert "категор" in callback.answer.await_args.args[0].lower()


@pytest.mark.asyncio
async def test_confirm_done_saves_subset(session, enable_mf, monkeypatch):
    user = User(telegram_id=100500, language="ru")
    session.add(user)
    await session.flush()
    item = Feedback(
        public_token="TokMulti003",
        test_batch="ru_matching_v1",
        user_id=user.id,
        chat_username="c",
        message_id=12,
        delivered_segments=["cleaning", "repair"],
    )
    session.add(item)
    await session.flush()

    redis = FakeRedis()
    await redis.sadd("mf:confirm:TokMulti003", "0")
    monkeypatch.setattr(
        "app.cache.get_redis",
        AsyncMock(return_value=redis),
    )

    callback = _cb(encode_feedback_callback("confirm_done", "TokMulti003"))
    with patch.object(
        feedback_handlers,
        "get_feedback_by_token_session",
        new=AsyncMock(return_value=item),
    ), patch.object(feedback_handlers, "async_session_factory") as factory:
        _patch_session(factory, session, user)
        await feedback_handlers.matching_feedback_callback(callback)

    await session.refresh(item)
    assert item.verdict == "correct"
    assert item.confirmed_segments == ["cleaning"]


@pytest.mark.asyncio
async def test_error_opens_reasons_without_save(session, enable_mf):
    user = User(telegram_id=100500, language="ru")
    session.add(user)
    await session.flush()
    item = Feedback(
        public_token="TokErrOpen1",
        test_batch="ru_matching_v1",
        user_id=user.id,
        chat_username="c",
        message_id=13,
        delivered_segments=["cleaning"],
    )
    session.add(item)
    await session.flush()

    callback = _cb(encode_feedback_callback("error", "TokErrOpen1"))
    with patch.object(
        feedback_handlers,
        "get_feedback_by_token_session",
        new=AsyncMock(return_value=item),
    ), patch.object(feedback_handlers, "async_session_factory") as factory:
        _patch_session(factory, session, user)
        await feedback_handlers.matching_feedback_callback(callback)

    await session.refresh(item)
    assert item.verdict is None
    markup = callback.message.edit_reply_markup.await_args.kwargs["reply_markup"]
    texts = [btn.text for row in markup.inline_keyboard for btn in row]
    assert any("Не та категория" in t for t in texts)
    callback.message.delete.assert_not_called()


@pytest.mark.asyncio
async def test_wrong_category_saves_then_shows_candidates(session, enable_mf):
    from app.db.models import Category, Segment

    user = User(telegram_id=100500, language="ru")
    session.add(user)
    await session.flush()
    category = Category(slug="home", title_ru="Дом", title_en="Home", emoji="🏠")
    session.add(category)
    await session.flush()
    alt = Segment(
        slug="repair",
        title_ru="Ремонт",
        title_en="Repair",
        emoji="🔧",
        category_id=category.id,
        is_active=True,
    )
    session.add(alt)
    await session.flush()
    item = Feedback(
        public_token="TokWrongCat",
        test_batch="ru_matching_v1",
        user_id=user.id,
        chat_username="c",
        message_id=14,
        delivered_segments=["cleaning"],
        rule_segments=["cleaning", "repair", "plumber", "electrician", "lawyer", "accountant"],
        reality_segments=["cleaning", "repair"],
    )
    session.add(item)
    await session.flush()

    callback = _cb(
        encode_feedback_callback("reason", "TokWrongCat", "wrong_category")
    )
    with patch.object(
        feedback_handlers,
        "get_feedback_by_token_session",
        new=AsyncMock(return_value=item),
    ), patch.object(feedback_handlers, "async_session_factory") as factory:
        _patch_session(factory, session, user)
        await feedback_handlers.matching_feedback_callback(callback)

    await session.refresh(item)
    assert item.verdict == "error"
    assert item.reason_code == "wrong_category"
    markup = callback.message.edit_reply_markup.await_args.kwargs["reply_markup"]
    rows = markup.inline_keyboard
    assert len(rows) <= 6
    texts = [btn.text for row in rows for btn in row]
    assert any("каталог" in t.lower() or "catalog" in t.lower() for t in texts)
    assert any("нет" in t.lower() or "missing" in t.lower() for t in texts)
    assert any("пропуст" in t.lower() or "skip" in t.lower() for t in texts)


@pytest.mark.asyncio
async def test_cat_missing_and_skip(session, enable_mf):
    user = User(telegram_id=100500, language="ru")
    session.add(user)
    await session.flush()
    item = Feedback(
        public_token="TokCatMiss1",
        test_batch="ru_matching_v1",
        user_id=user.id,
        chat_username="c",
        message_id=15,
        delivered_segments=["cleaning"],
        verdict="error",
        reason_code="wrong_category",
    )
    session.add(item)
    await session.flush()

    callback = _cb(encode_feedback_callback("cat_missing", "TokCatMiss1"))
    with patch.object(
        feedback_handlers,
        "get_feedback_by_token_session",
        new=AsyncMock(return_value=item),
    ), patch.object(feedback_handlers, "async_session_factory") as factory:
        _patch_session(factory, session, user)
        await feedback_handlers.matching_feedback_callback(callback)

    await session.refresh(item)
    assert item.expected_segment_missing is True
    assert item.expected_segment_slug is None

    item2 = Feedback(
        public_token="TokSkip0001",
        test_batch="ru_matching_v1",
        user_id=user.id,
        chat_username="c",
        message_id=16,
        delivered_segments=["cleaning"],
        verdict="error",
        reason_code="wrong_category",
    )
    session.add(item2)
    await session.flush()
    callback2 = _cb(encode_feedback_callback("skip", "TokSkip0001"))
    with patch.object(
        feedback_handlers,
        "get_feedback_by_token_session",
        new=AsyncMock(return_value=item2),
    ), patch.object(feedback_handlers, "async_session_factory") as factory:
        _patch_session(factory, session, user)
        await feedback_handlers.matching_feedback_callback(callback2)

    await session.refresh(item2)
    assert item2.expected_segment_slug is None
    assert item2.expected_segment_missing is False
    from app.matching_feedback.analytics import gold_export_rows

    gold = gold_export_rows(
        [
            {
                "test_batch": "ru_matching_v1",
                "chat_username": "c",
                "message_id": 16,
                "message_text_masked": "x",
                "delivered_segments": ["cleaning"],
                "verdict": "error",
                "reason_code": "wrong_category",
                "expected_segment_slug": None,
                "expected_segment_missing": False,
                "confirmed_segments": [],
            }
        ]
    )
    assert gold[0]["intent_only"] is True


@pytest.mark.asyncio
async def test_candidate_sets_expected_segment(session, enable_mf):
    from app.db.models import Category, Segment

    user = User(telegram_id=100500, language="ru")
    session.add(user)
    await session.flush()
    category = Category(slug="home2", title_ru="Дом", title_en="Home")
    session.add(category)
    await session.flush()
    seg = Segment(
        slug="repair",
        title_ru="Ремонт",
        title_en="Repair",
        category_id=category.id,
        is_active=True,
    )
    session.add(seg)
    await session.flush()
    item = Feedback(
        public_token="TokCand0001",
        test_batch="ru_matching_v1",
        user_id=user.id,
        chat_username="c",
        message_id=17,
        delivered_segments=["cleaning"],
        verdict="error",
        reason_code="wrong_category",
    )
    session.add(item)
    await session.flush()

    callback = _cb(encode_feedback_callback("candidate", "TokCand0001", str(seg.id)))
    with patch.object(
        feedback_handlers,
        "get_feedback_by_token_session",
        new=AsyncMock(return_value=item),
    ), patch.object(feedback_handlers, "async_session_factory") as factory:
        _patch_session(factory, session, user)
        await feedback_handlers.matching_feedback_callback(callback)

    await session.refresh(item)
    assert item.expected_segment_slug == "repair"
    assert item.expected_segment_id == seg.id


@pytest.mark.asyncio
async def test_change_restores_primary_keyboard(session, enable_mf):
    user = User(telegram_id=100500, language="ru")
    session.add(user)
    await session.flush()
    item = Feedback(
        public_token="TokChange01",
        test_batch="ru_matching_v1",
        user_id=user.id,
        chat_username="c",
        message_id=18,
        delivered_segments=["cleaning"],
        verdict="correct",
        confirmed_segments=["cleaning"],
    )
    session.add(item)
    await session.flush()

    callback = _cb(encode_feedback_callback("change", "TokChange01"))
    with patch.object(
        feedback_handlers,
        "get_feedback_by_token_session",
        new=AsyncMock(return_value=item),
    ), patch.object(feedback_handlers, "async_session_factory") as factory:
        _patch_session(factory, session, user)
        await feedback_handlers.matching_feedback_callback(callback)

    markup = callback.message.edit_reply_markup.await_args.kwargs["reply_markup"]
    texts = [btn.text for row in markup.inline_keyboard for btn in row]
    assert any("Верно" in t for t in texts)
    assert any("Ошибка" in t for t in texts)


@pytest.mark.asyncio
async def test_flag_off_is_fail_closed(monkeypatch):
    monkeypatch.setattr(settings, "matching_feedback_enabled", False)
    monkeypatch.setattr(settings, "matching_feedback_tester_ids", "100500")
    monkeypatch.setattr(settings, "matching_feedback_batch", "ru_matching_v1")
    callback = _cb(encode_feedback_callback("correct", "TokAny00001"))
    await feedback_handlers.matching_feedback_callback(callback)
    assert "недоступ" in callback.answer.await_args.args[0].lower()
    callback.message.edit_reply_markup.assert_not_awaited()


@pytest.mark.asyncio
async def test_wrong_batch_is_fail_closed(session, enable_mf, monkeypatch):
    monkeypatch.setattr(settings, "matching_feedback_batch", "other_batch")
    user = User(telegram_id=100500, language="ru")
    session.add(user)
    await session.flush()
    item = Feedback(
        public_token="TokBatch001",
        test_batch="ru_matching_v1",
        user_id=user.id,
        chat_username="c",
        message_id=19,
        delivered_segments=["cleaning"],
    )
    session.add(item)
    await session.flush()
    callback = _cb(encode_feedback_callback("correct", "TokBatch001"))
    with patch.object(
        feedback_handlers,
        "get_feedback_by_token_session",
        new=AsyncMock(return_value=item),
    ), patch.object(feedback_handlers, "async_session_factory") as factory:
        _patch_session(factory, session, user)
        await feedback_handlers.matching_feedback_callback(callback)
    assert "недоступ" in callback.answer.await_args.args[0].lower()


def test_mf_locale_keys_ru_en_parity():
    from app.locales import en, ru

    ru_keys = {k for k in ru.TEXTS if k.startswith("mf_")}
    en_keys = {k for k in en.TEXTS if k.startswith("mf_")}
    assert ru_keys == en_keys
    assert ru_keys  # non-empty
