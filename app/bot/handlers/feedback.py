"""Feedback handlers — legacy 👍/👎 plus closed matching review (mf:v1)."""

from __future__ import annotations

import logging
import secrets

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery
from sqlalchemy import select

from app.config import settings
from app.db import crud
from app.db.models import Feedback, Segment, User
from app.db.session import async_session_factory
from app.locales import get_text, normalize_language
from app.matching_feedback.domain import (
    FeedbackReason,
    FeedbackVerdict,
    decode_feedback_callback,
    is_matching_feedback_enabled_for,
)
from app.matching_feedback.keyboards import (
    build_catalog_categories_keyboard,
    build_catalog_segments_keyboard,
    build_confirmed_segments_keyboard,
    build_feedback_primary_keyboard,
    build_feedback_reason_keyboard,
    build_feedback_summary_keyboard,
    build_wrong_category_keyboard,
)
from app.matching_feedback.repository import (
    get_feedback_by_token_session,
    set_feedback_label,
)

logger = logging.getLogger(__name__)

router = Router(name="feedback")


def _confirm_key(token: str) -> str:
    return f"mf:confirm:{token}"


async def _selected_slugs(token: str, delivered: list[str]) -> set[str]:
    try:
        from app.cache import get_redis

        redis = await get_redis()
        raw = await redis.smembers(_confirm_key(token))
        selected: set[str] = set()
        for item in raw:
            text = item.decode() if isinstance(item, bytes) else str(item)
            if text.isdigit():
                idx = int(text)
                if 0 <= idx < len(delivered):
                    selected.add(delivered[idx])
        return selected
    except Exception:
        return set()


async def _toggle_confirm(token: str, index: int) -> None:
    from app.cache import get_redis

    redis = await get_redis()
    key = _confirm_key(token)
    member = str(index)
    if await redis.sismember(key, member):
        await redis.srem(key, member)
    else:
        await redis.sadd(key, member)
    await redis.expire(key, 3600)


async def _clear_confirm(token: str) -> None:
    try:
        from app.cache import get_redis

        redis = await get_redis()
        await redis.delete(_confirm_key(token))
    except Exception:
        return


async def _safe_edit_markup(callback: CallbackQuery, markup) -> None:
    try:
        await callback.message.edit_reply_markup(reply_markup=markup)
    except Exception:
        logger.warning("feedback keyboard edit failed (label kept if saved)")


async def _safe_answer(callback: CallbackQuery, text: str | None = None) -> None:
    try:
        await callback.answer(text)
    except Exception:
        return


def _summary_text(lang: str, feedback: Feedback) -> str:
    verdict = feedback.verdict or "—"
    reason = feedback.reason_code or ""
    confirmed = ", ".join(feedback.confirmed_segments or []) or "—"
    expected = feedback.expected_segment_slug or (
        "missing" if feedback.expected_segment_missing else "—"
    )
    return get_text(
        lang,
        "mf_saved_summary",
        verdict=verdict,
        reason=reason or "—",
        confirmed=confirmed,
        expected=expected,
    )


# ── Legacy thumbs (non-tester UI) ──────────────────────────────────────────


@router.callback_query(F.data.startswith("fb:"))
async def feedback_callback(callback: CallbackQuery):
    """Handle legacy feedback. Writes verdict with batch=legacy."""
    try:
        parts = callback.data.split(":")
        if len(parts) != 4:
            await callback.answer(get_text("ru", "error_generic"))
            return

        _, chat_username, message_id_str, verdict = parts
        message_id = int(message_id_str)

        async with async_session_factory() as sess:
            result = await sess.execute(
                select(User.id, User.language).where(
                    User.telegram_id == callback.from_user.id
                )
            )
            user_row = result.one_or_none()
            lang = normalize_language(user_row.language if user_row else None)

        if user_row is None:
            await callback.answer(get_text(lang, "error_user_not_found"))
            return

        async with async_session_factory() as sess:
            fb = Feedback(
                public_token=secrets.token_urlsafe(9),
                test_batch="legacy",
                user_id=user_row.id,
                chat_username=chat_username,
                message_id=message_id,
                verdict="correct" if verdict == "relevant" else "error",
                reason_code=None if verdict == "relevant" else "other",
            )
            sess.add(fb)
            await sess.commit()

        if verdict == "not_relevant":
            bot = Bot(token=settings.bot_token)
            try:
                await bot.delete_message(
                    chat_id=callback.from_user.id,
                    message_id=callback.message.message_id,
                )
            except Exception:
                try:
                    await callback.message.edit_text(
                        get_text(lang, "feedback_not_relevant")
                    )
                except Exception:
                    pass
            finally:
                await bot.session.close()
        else:
            await callback.answer(get_text(lang, "feedback_thanks"))

    except (ValueError, IndexError):
        await callback.answer(get_text("ru", "error_generic"))
    except Exception as e:
        logger.warning("Feedback save failed: %s", type(e).__name__)
        await callback.answer(get_text("ru", "error_generic"))


# ── Closed matching feedback ───────────────────────────────────────────────


@router.callback_query(F.data.startswith("mf:v1:"))
async def matching_feedback_callback(callback: CallbackQuery):
    lang = "ru"
    try:
        parsed = decode_feedback_callback(callback.data)
    except ValueError:
        await _safe_answer(callback, get_text("ru", "mf_invalid"))
        return

    if not is_matching_feedback_enabled_for(callback.from_user.id):
        await _safe_answer(callback, get_text("ru", "mf_closed"))
        return

    async with async_session_factory() as session:
        async with session.begin():
            user = await session.scalar(
                select(User).where(User.telegram_id == callback.from_user.id)
            )
            lang = normalize_language(user.language if user else None)
            if user is None:
                await _safe_answer(callback, get_text(lang, "error_user_not_found"))
                return

            feedback = await get_feedback_by_token_session(
                session, parsed.token, callback.from_user.id
            )
            if feedback is None:
                await _safe_answer(callback, get_text(lang, "mf_stale"))
                return
            if feedback.test_batch != (settings.matching_feedback_batch or "").strip():
                await _safe_answer(callback, get_text(lang, "mf_closed"))
                return

            await _handle_mf_action(callback, session, feedback, parsed.action, parsed.value, lang)


async def _handle_mf_action(
    callback: CallbackQuery,
    session,
    feedback: Feedback,
    action: str,
    value: str | None,
    lang: str,
) -> None:
    delivered = list(feedback.delivered_segments or [])

    if action == "correct":
        if len(delivered) <= 1:
            confirmed = tuple(delivered) if delivered else ()
            if not confirmed:
                await _safe_answer(callback, get_text(lang, "mf_invalid"))
                return
            await set_feedback_label(
                feedback.id,
                verdict=FeedbackVerdict.CORRECT,
                confirmed_segments=confirmed,
                session=session,
            )
            await session.refresh(feedback)
            await _safe_edit_markup(callback, build_feedback_summary_keyboard(feedback, lang))
            await _safe_answer(callback, get_text(lang, "mf_saved"))
            return
        selected = await _selected_slugs(feedback.public_token, delivered)
        await _safe_edit_markup(
            callback,
            build_confirmed_segments_keyboard(feedback, lang, selected),
        )
        await _safe_answer(callback)
        return

    if action == "confirm_seg":
        if value is None or not value.isdigit():
            await _safe_answer(callback, get_text(lang, "mf_invalid"))
            return
        await _toggle_confirm(feedback.public_token, int(value))
        selected = await _selected_slugs(feedback.public_token, delivered)
        await _safe_edit_markup(
            callback,
            build_confirmed_segments_keyboard(feedback, lang, selected),
        )
        await _safe_answer(callback)
        return

    if action == "confirm_done":
        selected = await _selected_slugs(feedback.public_token, delivered)
        if not selected:
            await _safe_answer(callback, get_text(lang, "mf_need_segment"))
            return
        await set_feedback_label(
            feedback.id,
            verdict=FeedbackVerdict.CORRECT,
            confirmed_segments=tuple(selected),
            session=session,
        )
        await _clear_confirm(feedback.public_token)
        await session.refresh(feedback)
        await _safe_edit_markup(callback, build_feedback_summary_keyboard(feedback, lang))
        await _safe_answer(callback, get_text(lang, "mf_saved"))
        return

    if action == "uncertain":
        await set_feedback_label(
            feedback.id,
            verdict=FeedbackVerdict.UNCERTAIN,
            session=session,
        )
        await session.refresh(feedback)
        await _safe_edit_markup(callback, build_feedback_summary_keyboard(feedback, lang))
        await _safe_answer(callback, get_text(lang, "mf_saved"))
        return

    if action == "error":
        await _safe_edit_markup(callback, build_feedback_reason_keyboard(feedback.public_token, lang))
        await _safe_answer(callback)
        return

    if action == "reason":
        try:
            reason = FeedbackReason(value or "")
        except ValueError:
            await _safe_answer(callback, get_text(lang, "mf_invalid"))
            return
        await set_feedback_label(
            feedback.id,
            verdict=FeedbackVerdict.ERROR,
            reason=reason,
            session=session,
        )
        await session.refresh(feedback)
        if reason == FeedbackReason.WRONG_CATEGORY:
            candidates = await _wrong_category_candidates(session, feedback, lang)
            await _safe_edit_markup(
                callback,
                build_wrong_category_keyboard(feedback.public_token, lang, candidates),
            )
        else:
            await _safe_edit_markup(callback, build_feedback_summary_keyboard(feedback, lang))
        await _safe_answer(callback, get_text(lang, "mf_saved"))
        return

    if action == "candidate":
        if not value or not value.isdigit():
            await _safe_answer(callback, get_text(lang, "mf_invalid"))
            return
        seg = await session.get(Segment, int(value))
        if seg is None:
            await _safe_answer(callback, get_text(lang, "mf_invalid"))
            return
        await set_feedback_label(
            feedback.id,
            verdict=FeedbackVerdict.ERROR,
            reason=FeedbackReason.WRONG_CATEGORY,
            expected_segment_id=seg.id,
            expected_segment_slug=seg.slug,
            session=session,
        )
        await session.refresh(feedback)
        await _safe_edit_markup(callback, build_feedback_summary_keyboard(feedback, lang))
        await _safe_answer(callback, get_text(lang, "mf_saved"))
        return

    if action == "catalog":
        if value and value.startswith("c") and value[1:].isdigit():
            category_id = int(value[1:])
            segments = await crud.get_segments_by_category(session, category_id)
            items = [
                (s.id, f"{s.emoji or ''} {s.title_ru if lang == 'ru' else s.title_en}".strip())
                for s in segments
                if s.is_active
            ]
            await _safe_edit_markup(
                callback,
                build_catalog_segments_keyboard(feedback.public_token, lang, items),
            )
        else:
            categories = await crud.get_categories(session)
            items = [
                (c.id, f"{c.emoji or ''} {c.title_ru if lang == 'ru' else c.title_en}".strip())
                for c in categories
            ]
            await _safe_edit_markup(
                callback,
                build_catalog_categories_keyboard(feedback.public_token, lang, items),
            )
        await _safe_answer(callback)
        return

    if action == "cat_missing":
        await set_feedback_label(
            feedback.id,
            verdict=FeedbackVerdict.ERROR,
            reason=FeedbackReason.WRONG_CATEGORY,
            expected_segment_missing=True,
            session=session,
        )
        await session.refresh(feedback)
        await _safe_edit_markup(callback, build_feedback_summary_keyboard(feedback, lang))
        await _safe_answer(callback, get_text(lang, "mf_saved"))
        return

    if action == "skip":
        await session.refresh(feedback)
        await _safe_edit_markup(callback, build_feedback_summary_keyboard(feedback, lang))
        await _safe_answer(callback, get_text(lang, "mf_saved"))
        return

    if action in {"back", "change"}:
        await _safe_edit_markup(
            callback,
            build_feedback_primary_keyboard(feedback.public_token, lang),
        )
        await _safe_answer(callback)
        return

    await _safe_answer(callback, get_text(lang, "mf_invalid"))


async def _wrong_category_candidates(
    session,
    feedback: Feedback,
    lang: str,
) -> list[tuple[str, str]]:
    delivered = set(feedback.delivered_segments or [])
    alts: list[str] = []
    for slug in list(feedback.rule_segments or []) + list(feedback.reality_segments or []):
        if slug not in delivered and slug not in alts:
            alts.append(slug)
    if not alts:
        return []
    result = await session.execute(select(Segment).where(Segment.slug.in_(alts[:8])))
    rows = result.scalars().all()
    by_slug = {s.slug: s for s in rows}
    out: list[tuple[str, str]] = []
    for slug in alts:
        seg = by_slug.get(slug)
        if seg is None:
            continue
        title = seg.title_ru if lang == "ru" else seg.title_en
        out.append((str(seg.id), f"{seg.emoji or ''} {title}".strip()))
        if len(out) >= 4:
            break
    return out
