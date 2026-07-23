"""Analytics unit tests for closed matching feedback."""

from __future__ import annotations

import pytest

from app.matching_feedback.analytics import (
    aggregate_feedback,
    assert_no_pii,
    export_feedback_jsonl_bytes,
    gold_export_rows,
)


def _row(**overrides):
    base = {
        "test_batch": "ru_matching_v1",
        "chat_username": "c",
        "message_id": 1,
        "message_text_masked": "ищу клининг [phone]",
        "delivered_segments": ["cleaning"],
        "rule_segments": ["cleaning"],
        "reality_segments": ["cleaning"],
        "legacy_llm_verdict": "DEMAND",
        "v2_intent": None,
        "verdict": None,
        "reason_code": None,
        "confirmed_segments": [],
        "expected_segment_slug": None,
        "expected_segment_missing": False,
        "model_name": "deepseek-chat",
        "prompt_version": 2,
        "schema_version": 2,
        "profile_versions": {},
        "keyword_only": False,
    }
    base.update(overrides)
    return base


def test_keyword_only_not_counted_as_missing_snapshot():
    rows = [
        _row(
            message_id=10,
            legacy_llm_verdict=None,
            v2_intent=None,
            rule_segments=[],
            keyword_only=True,
        ),
        _row(
            message_id=11,
            legacy_llm_verdict=None,
            v2_intent=None,
            rule_segments=[],
            keyword_only=False,
        ),
    ]
    summary = aggregate_feedback(rows)
    assert summary["missing_snapshot"] == 1


def test_aggregate_precision_excludes_uncertain():
    rows = [
        _row(verdict="correct", confirmed_segments=["cleaning"], message_id=1),
        _row(verdict="error", reason_code="provider_offer", message_id=2),
        _row(verdict="uncertain", message_id=3),
        _row(verdict=None, message_id=4),
    ]
    summary = aggregate_feedback(rows)
    assert summary["rated"] == 3
    assert summary["defined"] == 2
    assert summary["uncertain"] == 1
    assert summary["precision"] == 0.5
    assert summary["unrated"] == 1


def test_multi_segment_confirmed_attribution():
    rows = [
        _row(
            delivered_segments=["cleaning", "repair"],
            verdict="correct",
            confirmed_segments=["cleaning"],
            message_id=5,
        )
    ]
    summary = aggregate_feedback(rows)
    assert summary["per_segment"]["cleaning"]["correct"] == 1
    assert summary["per_segment"]["repair"]["error"] == 1
    assert summary["confusion"][0]["delivered"] == "repair"
    assert summary["confusion"][0]["expected"] == "cleaning"


def test_gold_export_rules_and_pii():
    rows = [
        _row(verdict="correct", confirmed_segments=["cleaning"], message_id=1),
        _row(verdict="uncertain", message_id=2),
        _row(
            verdict="error",
            reason_code="wrong_category",
            expected_segment_slug=None,
            message_id=3,
        ),
        _row(
            verdict="error",
            reason_code="wrong_category",
            expected_segment_slug="repair",
            message_id=4,
        ),
    ]
    gold = gold_export_rows(rows)
    assert len(gold) == 3
    intent = [g for g in gold if g["message_id"] == 3][0]
    assert intent["intent_only"] is True
    typed = [g for g in gold if g["message_id"] == 4][0]
    assert typed["intent_only"] is False
    assert_no_pii(gold)
    blob = export_feedback_jsonl_bytes(rows).decode("utf-8")
    assert "telegram_id" not in blob
    assert "uncertain" not in blob
    assert "sender" not in blob
