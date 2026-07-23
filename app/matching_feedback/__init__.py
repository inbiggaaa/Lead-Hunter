"""Closed matching feedback package — public types and helpers."""

from app.matching_feedback.domain import (
    FeedbackCallback,
    FeedbackReason,
    FeedbackSnapshot,
    FeedbackVerdict,
    decode_feedback_callback,
    encode_feedback_callback,
    is_matching_feedback_enabled_for,
    is_matching_feedback_tester,
    mask_message_text,
    validate_label,
)

__all__ = [
    "FeedbackCallback",
    "FeedbackReason",
    "FeedbackSnapshot",
    "FeedbackVerdict",
    "decode_feedback_callback",
    "encode_feedback_callback",
    "is_matching_feedback_enabled_for",
    "is_matching_feedback_tester",
    "mask_message_text",
    "validate_label",
]
