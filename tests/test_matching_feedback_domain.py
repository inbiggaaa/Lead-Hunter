"""Domain contract for closed matching feedback."""

from __future__ import annotations

import pytest

from app.config import settings
from app.matching_feedback.domain import (
    FeedbackReason,
    FeedbackVerdict,
    decode_feedback_callback,
    encode_feedback_callback,
    is_matching_feedback_enabled_for,
    is_matching_feedback_tester,
    parse_tester_ids,
    validate_label,
)


def test_error_requires_reason():
    with pytest.raises(ValueError):
        validate_label(FeedbackVerdict.ERROR, None, None, False)


def test_uncertain_rejects_reason():
    with pytest.raises(ValueError):
        validate_label(
            FeedbackVerdict.UNCERTAIN,
            FeedbackReason.OTHER,
            None,
            False,
        )


def test_correct_requires_confirmed_delivered_segment():
    with pytest.raises(ValueError):
        validate_label(
            FeedbackVerdict.CORRECT,
            None,
            confirmed_segments=("repair",),
            delivered_segments=("cleaning",),
        )


def test_correct_accepts_subset_of_delivered():
    validate_label(
        FeedbackVerdict.CORRECT,
        None,
        confirmed_segments=("cleaning",),
        delivered_segments=("cleaning", "repair"),
    )


def test_error_rejects_confirmed_segments():
    with pytest.raises(ValueError):
        validate_label(
            FeedbackVerdict.ERROR,
            FeedbackReason.PROVIDER_OFFER,
            confirmed_segments=("cleaning",),
            delivered_segments=("cleaning",),
        )


def test_expected_segment_only_for_wrong_category():
    with pytest.raises(ValueError):
        validate_label(
            FeedbackVerdict.ERROR,
            FeedbackReason.PROVIDER_OFFER,
            None,
            False,
            expected_segment_slug="cleaning",
        )


def test_expected_id_and_missing_conflict():
    with pytest.raises(ValueError):
        validate_label(
            FeedbackVerdict.ERROR,
            FeedbackReason.WRONG_CATEGORY,
            None,
            True,
            expected_segment_id=7,
        )


def test_callback_round_trip_stays_under_telegram_limit():
    data = encode_feedback_callback("reason", "AbCdEf123456", "wrong_category")
    assert len(data.encode()) <= 64
    assert decode_feedback_callback(data).value == "wrong_category"
    assert decode_feedback_callback(data).action == "reason"


def test_callback_rejects_oversized_payload():
    with pytest.raises(ValueError):
        encode_feedback_callback("reason", "x" * 50, "wrong_category")


def test_callback_rejects_unknown_action():
    with pytest.raises(ValueError):
        encode_feedback_callback("explode", "AbCdEf123456")


def test_empty_tester_allowlist_is_fail_closed(monkeypatch):
    monkeypatch.setattr(settings, "matching_feedback_tester_ids", "")
    monkeypatch.setattr(settings, "matching_feedback_enabled", True)
    monkeypatch.setattr(settings, "matching_feedback_batch", "ru_matching_v1")
    assert is_matching_feedback_tester(123) is False
    assert is_matching_feedback_enabled_for(123) is False


def test_tester_allowlist_requires_flag_and_batch(monkeypatch):
    monkeypatch.setattr(settings, "matching_feedback_tester_ids", "42")
    monkeypatch.setattr(settings, "matching_feedback_enabled", True)
    monkeypatch.setattr(settings, "matching_feedback_batch", "")
    assert is_matching_feedback_tester(42) is True
    assert is_matching_feedback_enabled_for(42) is False

    monkeypatch.setattr(settings, "matching_feedback_batch", "ru_matching_v1")
    assert is_matching_feedback_enabled_for(42) is True
    assert is_matching_feedback_enabled_for(99) is False


def test_parse_tester_ids_rejects_malformed():
    with pytest.raises(ValueError):
        parse_tester_ids("1,abc,2")
