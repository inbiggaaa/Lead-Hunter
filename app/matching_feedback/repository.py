"""Persistence for closed matching feedback items."""

from __future__ import annotations

import datetime
import logging
import secrets

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Feedback, User
from app.db.session import async_session_factory
from app.matching_feedback.domain import (
    FeedbackReason,
    FeedbackSnapshot,
    FeedbackVerdict,
    validate_label,
)

logger = logging.getLogger(__name__)

_TOKEN_BYTES = 9
_MAX_TOKEN_RETRIES = 5


def _new_token() -> str:
    return secrets.token_urlsafe(_TOKEN_BYTES)


def _llm_list(value: object) -> list[str] | None:
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value]
    return None


def _llm_dict(value: object) -> dict | None:
    return value if isinstance(value, dict) else None


def _llm_int(value: object) -> int | None:
    return value if isinstance(value, int) else None


def _llm_str(value: object) -> str | None:
    return value if isinstance(value, str) else None


async def get_or_create_feedback_item(
    snapshot: FeedbackSnapshot,
    *,
    session: AsyncSession | None = None,
) -> Feedback:
    """Idempotent create by (batch, user, chat, message)."""
    if session is not None:
        return await _get_or_create(session, snapshot)

    async with async_session_factory() as owned:
        async with owned.begin():
            item = await _get_or_create(owned, snapshot)
            await owned.refresh(item)
            return item


async def _get_or_create(session: AsyncSession, snapshot: FeedbackSnapshot) -> Feedback:
    existing = await session.scalar(
        select(Feedback).where(
            Feedback.test_batch == snapshot.test_batch,
            Feedback.user_id == snapshot.user_id,
            Feedback.chat_username == snapshot.chat_username,
            Feedback.message_id == snapshot.message_id,
        )
    )
    if existing is not None:
        return existing

    llm = dict(snapshot.llm_snapshot or {})
    for _ in range(_MAX_TOKEN_RETRIES):
        row = Feedback(
            public_token=_new_token(),
            test_batch=snapshot.test_batch,
            user_id=snapshot.user_id,
            chat_username=snapshot.chat_username,
            message_id=snapshot.message_id,
            message_hash=snapshot.message_hash,
            content_hash=snapshot.content_hash,
            message_text_masked=snapshot.message_text_masked,
            delivered_segments=list(snapshot.delivered_segments),
            rule_segments=list(snapshot.rule_segments),
            reality_segments=list(snapshot.reality_segments),
            legacy_llm_verdict=_llm_str(llm.get("legacy_llm_verdict")),
            legacy_llm_segments=_llm_list(llm.get("legacy_llm_segments")),
            v2_intent=_llm_str(llm.get("v2_intent")),
            v2_segment_verdicts=_llm_dict(llm.get("v2_segment_verdicts")),
            model_name=_llm_str(llm.get("model_name")),
            prompt_version=_llm_int(llm.get("prompt_version")),
            schema_version=_llm_int(llm.get("schema_version")),
            profile_versions=_llm_dict(llm.get("profile_versions")),
            keyword_only=bool(llm.get("keyword_only")),
            verdict=None,
            reason_code=None,
        )
        try:
            async with session.begin_nested():
                session.add(row)
                await session.flush()
            return row
        except IntegrityError:
            logger.warning("feedback token collision; retrying")
            continue
    raise RuntimeError("Unable to allocate unique feedback token")


async def get_feedback_by_token(token: str, telegram_id: int) -> Feedback | None:
    """Load feedback only when token belongs to the Telegram user."""
    async with async_session_factory() as session:
        return await get_feedback_by_token_session(session, token, telegram_id)


async def get_feedback_by_token_session(
    session: AsyncSession,
    token: str,
    telegram_id: int,
) -> Feedback | None:
    return await session.scalar(
        select(Feedback)
        .join(User, User.id == Feedback.user_id)
        .where(Feedback.public_token == token, User.telegram_id == telegram_id)
    )


async def set_feedback_label(
    feedback_id: int,
    *,
    verdict: FeedbackVerdict,
    reason: FeedbackReason | None = None,
    confirmed_segments: tuple[str, ...] = (),
    expected_segment_id: int | None = None,
    expected_segment_slug: str | None = None,
    expected_segment_missing: bool = False,
    session: AsyncSession | None = None,
) -> Feedback:
    if session is not None:
        return await _set_label(
            session,
            feedback_id,
            verdict=verdict,
            reason=reason,
            confirmed_segments=confirmed_segments,
            expected_segment_id=expected_segment_id,
            expected_segment_slug=expected_segment_slug,
            expected_segment_missing=expected_segment_missing,
        )

    async with async_session_factory() as owned:
        async with owned.begin():
            return await _set_label(
                owned,
                feedback_id,
                verdict=verdict,
                reason=reason,
                confirmed_segments=confirmed_segments,
                expected_segment_id=expected_segment_id,
                expected_segment_slug=expected_segment_slug,
                expected_segment_missing=expected_segment_missing,
            )


async def _set_label(
    session: AsyncSession,
    feedback_id: int,
    *,
    verdict: FeedbackVerdict,
    reason: FeedbackReason | None,
    confirmed_segments: tuple[str, ...],
    expected_segment_id: int | None,
    expected_segment_slug: str | None,
    expected_segment_missing: bool,
) -> Feedback:
    row = await session.get(Feedback, feedback_id)
    if row is None:
        raise ValueError(f"Feedback {feedback_id} not found")

    delivered = tuple(row.delivered_segments or ())
    validate_label(
        verdict,
        reason,
        confirmed_segments or None,
        expected_segment_missing,
        delivered_segments=delivered,
        expected_segment_id=expected_segment_id,
        expected_segment_slug=expected_segment_slug,
    )

    row.verdict = verdict.value
    row.reason_code = reason.value if reason else None
    row.confirmed_segments = list(confirmed_segments) if confirmed_segments else None
    row.expected_segment_id = expected_segment_id
    row.expected_segment_slug = expected_segment_slug
    row.expected_segment_missing = expected_segment_missing
    now = datetime.datetime.now(datetime.timezone.utc)
    row.rated_at = now
    row.updated_at = now
    await session.flush()
    return row
