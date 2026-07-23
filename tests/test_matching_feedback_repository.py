"""Repository tests for closed matching feedback."""

from __future__ import annotations

import pytest
import pytest_asyncio

from app.db.models import User
from app.matching_feedback.domain import (
    FeedbackReason,
    FeedbackSnapshot,
    FeedbackVerdict,
)
from app.matching_feedback.repository import (
    get_feedback_by_token_session,
    get_or_create_feedback_item,
    set_feedback_label,
)


@pytest_asyncio.fixture
async def feedback_user(session):
    user = User(telegram_id=91_000_001, username="fb_tester", language="ru")
    session.add(user)
    await session.flush()
    return user


@pytest.fixture
def feedback_snapshot(feedback_user):
    return FeedbackSnapshot(
        test_batch="ru_matching_v1",
        user_id=feedback_user.id,
        telegram_id=feedback_user.telegram_id,
        chat_username="test_chat",
        message_id=42,
        message_hash="a" * 64,
        content_hash="b" * 64,
        message_text_masked="ищу клининг [phone]",
        delivered_segments=("cleaning",),
        rule_segments=("cleaning", "repair"),
        reality_segments=("cleaning",),
        llm_snapshot={
            "legacy_llm_verdict": "DEMAND",
            "legacy_llm_segments": ["cleaning"],
            "v2_intent": "commercial_demand",
            "v2_segment_verdicts": {"cleaning": "accept"},
            "model_name": "deepseek-chat",
            "prompt_version": 2,
            "schema_version": 2,
            "profile_versions": {"cleaning": 1},
        },
    )


@pytest.mark.asyncio
async def test_get_or_create_is_idempotent(session, feedback_snapshot):
    first = await get_or_create_feedback_item(feedback_snapshot, session=session)
    second = await get_or_create_feedback_item(feedback_snapshot, session=session)
    assert first.id == second.id
    assert first.public_token == second.public_token
    assert first.verdict is None
    assert first.delivered_segments == ["cleaning"]
    assert first.rule_segments == ["cleaning", "repair"]
    assert first.v2_intent == "commercial_demand"


@pytest.mark.asyncio
async def test_last_confirmed_label_replaces_current_value(session, feedback_snapshot):
    item = await get_or_create_feedback_item(feedback_snapshot, session=session)
    row = await set_feedback_label(
        item.id,
        verdict=FeedbackVerdict.ERROR,
        reason=FeedbackReason.PROVIDER_OFFER,
        session=session,
    )
    assert row.verdict == "error"
    assert row.reason_code == "provider_offer"

    changed = await set_feedback_label(
        item.id,
        verdict=FeedbackVerdict.CORRECT,
        confirmed_segments=("cleaning",),
        session=session,
    )
    assert changed.verdict == "correct"
    assert changed.reason_code is None
    assert changed.confirmed_segments == ["cleaning"]


@pytest.mark.asyncio
async def test_foreign_user_cannot_load_token(session, feedback_snapshot):
    item = await get_or_create_feedback_item(feedback_snapshot, session=session)
    other = User(telegram_id=91_000_002, username="other")
    session.add(other)
    await session.flush()

    assert (
        await get_feedback_by_token_session(
            session, item.public_token, other.telegram_id
        )
        is None
    )
    owned = await get_feedback_by_token_session(
        session, item.public_token, feedback_snapshot.telegram_id
    )
    assert owned is not None
    assert owned.id == item.id
