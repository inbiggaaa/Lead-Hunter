"""Inline keyboards for closed matching feedback."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.db.models import Feedback
from app.locales import get_text
from app.matching_feedback.domain import FeedbackReason, encode_feedback_callback

_REASON_ORDER: tuple[FeedbackReason, ...] = (
    FeedbackReason.WRONG_CATEGORY,
    FeedbackReason.PROVIDER_OFFER,
    FeedbackReason.JOB_VACANCY,
    FeedbackReason.JOB_SEARCH,
    FeedbackReason.SOCIAL_REQUEST,
    FeedbackReason.DISCUSSION_NEWS,
    FeedbackReason.WRONG_GEOGRAPHY,
    FeedbackReason.DUPLICATE,
    FeedbackReason.OTHER,
)

_REASON_LOCALE = {
    FeedbackReason.WRONG_CATEGORY: "mf_reason_wrong_category",
    FeedbackReason.PROVIDER_OFFER: "mf_reason_provider_offer",
    FeedbackReason.JOB_VACANCY: "mf_reason_job_vacancy",
    FeedbackReason.JOB_SEARCH: "mf_reason_job_search",
    FeedbackReason.SOCIAL_REQUEST: "mf_reason_social_request",
    FeedbackReason.DISCUSSION_NEWS: "mf_reason_discussion_news",
    FeedbackReason.WRONG_GEOGRAPHY: "mf_reason_wrong_geography",
    FeedbackReason.DUPLICATE: "mf_reason_duplicate",
    FeedbackReason.OTHER: "mf_reason_other",
}


def build_feedback_primary_keyboard(token: str, lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=get_text(lang, "mf_btn_correct"),
                    callback_data=encode_feedback_callback("correct", token),
                ),
                InlineKeyboardButton(
                    text=get_text(lang, "mf_btn_error"),
                    callback_data=encode_feedback_callback("error", token),
                ),
                InlineKeyboardButton(
                    text=get_text(lang, "mf_btn_uncertain"),
                    callback_data=encode_feedback_callback("uncertain", token),
                ),
            ]
        ]
    )


def build_feedback_reason_keyboard(token: str, lang: str) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=get_text(lang, _REASON_LOCALE[reason]),
                callback_data=encode_feedback_callback("reason", token, reason.value),
            )
        ]
        for reason in _REASON_ORDER
    ]
    rows.append(
        [
            InlineKeyboardButton(
                text=get_text(lang, "mf_btn_back"),
                callback_data=encode_feedback_callback("back", token),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_confirmed_segments_keyboard(
    feedback: Feedback,
    lang: str,
    selected: set[str],
) -> InlineKeyboardMarkup:
    rows = []
    delivered = list(feedback.delivered_segments or [])
    for idx, slug in enumerate(delivered):
        mark = "✅" if slug in selected else "⬜"
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{mark} {slug}",
                    callback_data=encode_feedback_callback("confirm_seg", token=feedback.public_token, value=str(idx)),
                )
            ]
        )
    if selected:
        rows.append(
            [
                InlineKeyboardButton(
                    text=get_text(lang, "mf_btn_confirm_done"),
                    callback_data=encode_feedback_callback("confirm_done", feedback.public_token),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text=get_text(lang, "mf_btn_back"),
                callback_data=encode_feedback_callback("back", feedback.public_token),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_wrong_category_keyboard(
    token: str,
    lang: str,
    candidates: list[tuple[str, str]],
) -> InlineKeyboardMarkup:
    """candidates: list of (segment_id_str, title)."""
    rows = []
    for seg_id, title in candidates[:4]:
        rows.append(
            [
                InlineKeyboardButton(
                    text=title,
                    callback_data=encode_feedback_callback("candidate", token, seg_id),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text=get_text(lang, "mf_btn_catalog"),
                callback_data=encode_feedback_callback("catalog", token),
            )
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                text=get_text(lang, "mf_btn_cat_missing"),
                callback_data=encode_feedback_callback("cat_missing", token),
            ),
            InlineKeyboardButton(
                text=get_text(lang, "mf_btn_skip"),
                callback_data=encode_feedback_callback("skip", token),
            ),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_catalog_categories_keyboard(
    token: str,
    lang: str,
    categories: list[tuple[int, str]],
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=title,
                callback_data=encode_feedback_callback("catalog", token, f"c{cid}"),
            )
        ]
        for cid, title in categories
    ]
    rows.append(
        [
            InlineKeyboardButton(
                text=get_text(lang, "mf_btn_back"),
                callback_data=encode_feedback_callback("back", token),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_catalog_segments_keyboard(
    token: str,
    lang: str,
    segments: list[tuple[int, str]],
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=title,
                callback_data=encode_feedback_callback("candidate", token, str(sid)),
            )
        ]
        for sid, title in segments
    ]
    rows.append(
        [
            InlineKeyboardButton(
                text=get_text(lang, "mf_btn_back"),
                callback_data=encode_feedback_callback("catalog", token),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_feedback_summary_keyboard(feedback: Feedback, lang: str) -> InlineKeyboardMarkup:
    verdict = feedback.verdict or "—"
    reason = feedback.reason_code or ""
    label = verdict
    if reason:
        label = f"{verdict}/{reason}"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=get_text(lang, "mf_summary_label", label=label),
                    callback_data=encode_feedback_callback("change", feedback.public_token),
                )
            ],
            [
                InlineKeyboardButton(
                    text=get_text(lang, "mf_btn_change"),
                    callback_data=encode_feedback_callback("change", feedback.public_token),
                )
            ],
        ]
    )
