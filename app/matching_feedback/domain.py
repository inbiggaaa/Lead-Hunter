"""Closed matching feedback domain: taxonomy, callbacks, tester gate."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from app.config import settings

TELEGRAM_CALLBACK_MAX_BYTES = 64
CALLBACK_PREFIX = "mf:v1"

# Wire action codes kept short so callbacks stay under 64 bytes.
_ACTION_TO_WIRE: dict[str, str] = {
    "correct": "ok",
    "error": "er",
    "uncertain": "un",
    "reason": "rs",
    "confirm_seg": "cs",
    "candidate": "cd",
    "catalog": "ct",
    "cat_missing": "cm",
    "skip": "sk",
    "back": "bk",
    "change": "ch",
}
_WIRE_TO_ACTION: dict[str, str] = {v: k for k, v in _ACTION_TO_WIRE.items()}


class FeedbackVerdict(StrEnum):
    CORRECT = "correct"
    ERROR = "error"
    UNCERTAIN = "uncertain"


class FeedbackReason(StrEnum):
    WRONG_CATEGORY = "wrong_category"
    PROVIDER_OFFER = "provider_offer"
    JOB_VACANCY = "job_vacancy"
    JOB_SEARCH = "job_search"
    SOCIAL_REQUEST = "social_request"
    DISCUSSION_NEWS = "discussion_news"
    WRONG_GEOGRAPHY = "wrong_geography"
    DUPLICATE = "duplicate"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class FeedbackCallback:
    action: str
    token: str
    value: str | None


@dataclass(frozen=True, slots=True)
class FeedbackSnapshot:
    test_batch: str
    user_id: int
    telegram_id: int
    chat_username: str
    message_id: int
    message_hash: str
    content_hash: str | None
    message_text_masked: str
    delivered_segments: tuple[str, ...]
    rule_segments: tuple[str, ...]
    reality_segments: tuple[str, ...]
    llm_snapshot: Mapping[str, object]


def parse_tester_ids(raw: str) -> frozenset[int]:
    """Parse comma-separated Telegram IDs; malformed values raise."""
    text = (raw or "").strip()
    if not text:
        return frozenset()
    ids: set[int] = set()
    for part in text.split(","):
        piece = part.strip()
        if not piece:
            continue
        if not piece.lstrip("-").isdigit():
            raise ValueError(f"Invalid MATCHING_FEEDBACK_TESTER_IDS entry: {piece!r}")
        ids.add(int(piece))
    return frozenset(ids)


def matching_feedback_tester_ids() -> frozenset[int]:
    return parse_tester_ids(settings.matching_feedback_tester_ids)


def is_matching_feedback_tester(telegram_id: int) -> bool:
    return telegram_id in matching_feedback_tester_ids()


def is_matching_feedback_enabled_for(telegram_id: int) -> bool:
    """Fail-closed gate: flag + allowlist + non-empty batch."""
    if not settings.matching_feedback_enabled:
        return False
    if not (settings.matching_feedback_batch or "").strip():
        return False
    return is_matching_feedback_tester(telegram_id)


def encode_feedback_callback(
    action: str,
    token: str,
    value: str | None = None,
) -> str:
    """Build ``mf:v1:<wire>:<token>[:<value>]`` within Telegram's 64-byte limit."""
    if action not in _ACTION_TO_WIRE:
        raise ValueError(f"Unknown feedback action: {action!r}")
    if not token or ":" in token:
        raise ValueError("Feedback token must be non-empty and colon-free")
    wire = _ACTION_TO_WIRE[action]
    parts = [CALLBACK_PREFIX, wire, token]
    if value is not None:
        if ":" in value:
            raise ValueError("Feedback callback value must not contain ':'")
        parts.append(value)
    data = ":".join(parts)
    if len(data.encode("utf-8")) > TELEGRAM_CALLBACK_MAX_BYTES:
        raise ValueError("Feedback callback exceeds Telegram 64-byte limit")
    return data


def decode_feedback_callback(data: str) -> FeedbackCallback:
    """Parse and validate a closed-feedback callback payload."""
    if len(data.encode("utf-8")) > TELEGRAM_CALLBACK_MAX_BYTES:
        raise ValueError("Feedback callback exceeds Telegram 64-byte limit")
    parts = data.split(":")
    if len(parts) < 3 or parts[0] != "mf" or parts[1] != "v1":
        raise ValueError("Malformed feedback callback")
    wire = parts[2]
    if wire not in _WIRE_TO_ACTION:
        raise ValueError(f"Unknown feedback wire action: {wire!r}")
    if len(parts) == 3:
        raise ValueError("Feedback callback missing token")
    token = parts[3]
    if not token:
        raise ValueError("Feedback callback missing token")
    value = parts[4] if len(parts) >= 5 else None
    if len(parts) > 5:
        raise ValueError("Malformed feedback callback")
    return FeedbackCallback(action=_WIRE_TO_ACTION[wire], token=token, value=value)


def validate_label(
    verdict: FeedbackVerdict,
    reason: FeedbackReason | None,
    confirmed_segments: tuple[str, ...] | None = None,
    expected_segment_missing: bool = False,
    *,
    delivered_segments: tuple[str, ...] = (),
    expected_segment_id: int | None = None,
    expected_segment_slug: str | None = None,
) -> None:
    """Enforce design constraints for the current label on a feedback row."""
    confirmed = confirmed_segments or ()
    has_expected = (
        expected_segment_id is not None
        or bool(expected_segment_slug)
        or expected_segment_missing
    )

    if verdict == FeedbackVerdict.ERROR:
        if reason is None:
            raise ValueError("error verdict requires reason_code")
        if confirmed:
            raise ValueError("error verdict cannot have confirmed_segments")
    elif verdict in (FeedbackVerdict.CORRECT, FeedbackVerdict.UNCERTAIN):
        if reason is not None:
            raise ValueError(f"{verdict} verdict cannot have reason_code")
        if verdict == FeedbackVerdict.UNCERTAIN and confirmed:
            raise ValueError("uncertain verdict cannot have confirmed_segments")
        if has_expected:
            raise ValueError(f"{verdict} verdict cannot set expected segment")
    else:
        raise ValueError(f"Unknown verdict: {verdict!r}")

    if verdict == FeedbackVerdict.CORRECT:
        if not confirmed:
            raise ValueError("correct verdict requires confirmed_segments")
        delivered = set(delivered_segments)
        if not set(confirmed).issubset(delivered):
            raise ValueError("confirmed_segments must be a subset of delivered_segments")

    if has_expected and reason != FeedbackReason.WRONG_CATEGORY:
        raise ValueError("expected segment is only allowed for wrong_category")

    if expected_segment_id is not None and expected_segment_missing:
        raise ValueError("expected_segment_id and expected_segment_missing conflict")

    if expected_segment_slug and expected_segment_missing:
        raise ValueError("expected_segment_slug and expected_segment_missing conflict")


def mask_message_text(text: str, *, max_len: int = 500) -> str:
    """Strip contacts/links and truncate for safe feedback storage."""
    import re

    masked = text or ""
    masked = re.sub(r"https?://\S+", "[link]", masked, flags=re.IGNORECASE)
    masked = re.sub(r"t\.me/\S+", "[link]", masked, flags=re.IGNORECASE)
    masked = re.sub(r"@\w{4,}", "[user]", masked)
    masked = re.sub(r"\+?\d[\d\s\-()]{7,}\d", "[phone]", masked)
    masked = re.sub(r"\s+", " ", masked).strip()
    if len(masked) > max_len:
        return masked[: max_len - 1] + "…"
    return masked
