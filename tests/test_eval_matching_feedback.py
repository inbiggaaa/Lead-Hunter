"""Canonical wiring tests for eval_matching feedback aggregation."""

from __future__ import annotations

from collections import defaultdict

from tools.eval_matching import aggregate_feedback, new_seg_stats


def test_eval_aggregate_accepts_correct_error_and_skips_uncertain():
    stats: dict[str, dict[str, int]] = defaultdict(new_seg_stats)
    feedback = [
        {
            "test_batch": "ru_matching_v1",
            "verdict": "correct",
            "message_text_masked": "ищу клининг [phone]",
            "delivered_segments": ["cleaning"],
            "confirmed_segments": ["cleaning"],
            "rule_segments": ["cleaning"],
            "legacy_llm_segments": ["cleaning"],
            "keyword_only": False,
        },
        {
            "test_batch": "ru_matching_v1",
            "verdict": "error",
            "reason_code": "provider_offer",
            "message_text_masked": "предлагаю клининг",
            "delivered_segments": ["cleaning"],
            "confirmed_segments": [],
            "rule_segments": ["cleaning"],
            "legacy_llm_segments": ["cleaning"],
            "keyword_only": False,
        },
        {
            "test_batch": "ru_matching_v1",
            "verdict": "uncertain",
            "message_text_masked": "хм",
            "delivered_segments": ["cleaning"],
            "confirmed_segments": [],
            "rule_segments": ["cleaning"],
            "legacy_llm_segments": [],
            "keyword_only": False,
        },
    ]
    totals = aggregate_feedback(feedback, stats, {"cleaning"})
    assert totals["relevant"] == 1
    assert totals["not_relevant"] == 1
    assert totals["uncertain"] == 1
    assert totals["closed_precision"] == 0.5
    assert stats["cleaning"]["fb_relevant"] == 1
    assert stats["cleaning"]["fb_not_relevant"] == 1


def test_eval_aggregate_still_accepts_legacy_thumbs():
    stats: dict[str, dict[str, int]] = defaultdict(new_seg_stats)
    feedback = [
        {
            "test_batch": "legacy",
            "verdict": "relevant",
            "message_text_masked": "text",
            "delivered_segments": ["cleaning"],
            "confirmed_segments": [],
            "rule_segments": ["cleaning"],
            "legacy_llm_segments": ["cleaning"],
            "keyword_only": False,
        }
    ]
    totals = aggregate_feedback(feedback, stats, {"cleaning"})
    assert totals["relevant"] == 1
    assert stats["cleaning"]["fb_relevant"] == 1
