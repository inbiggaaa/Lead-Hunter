"""Phase 5: LLM response schema v2 parse + legacy adapter tests."""

from __future__ import annotations

import logging

from app.userbot.llm_response import (
    CommercialIntent,
    LLMDecision,
    SegmentVerdict,
    parse_segment_aware_message,
    to_legacy_llm_result,
)


def test_valid_accept_and_reject_per_segment():
    raw = {
        "index": 0,
        "segments": [
            {
                "slug": "tennis",
                "decision": "reject",
                "intent": "social_request",
                "certainty": "high",
                "reason_code": "looking_for_play_partner",
                "reason": "Ищет партнёра для игры",
            },
            {
                "slug": "fitness",
                "decision": "accept",
                "intent": "commercial_demand",
                "certainty": "high",
                "reason_code": "needs_trainer",
                "reason": "Ищет тренера",
            },
        ],
    }
    parsed = parse_segment_aware_message(
        raw,
        expected_index=0,
        candidate_segments=["tennis", "fitness"],
    )
    assert parsed.malformed is False
    by_slug = {v.segment_slug: v for v in parsed.verdicts}
    assert by_slug["tennis"].decision is LLMDecision.REJECT
    assert by_slug["tennis"].intent is CommercialIntent.SOCIAL_REQUEST
    assert by_slug["fitness"].decision is LLMDecision.ACCEPT
    legacy = to_legacy_llm_result(
        candidate_segments=["tennis", "fitness"],
        verdicts=parsed.verdicts,
        fail_open_segments=parsed.fail_open_segments,
    )
    assert legacy.verdict == "DEMAND"
    assert legacy.relevant_segments == ["fitness"]
    assert legacy.certainty == "high"


def test_unknown_slug_ignored():
    raw = {
        "index": 0,
        "segments": [
            {
                "slug": "tennis",
                "decision": "accept",
                "intent": "commercial_demand",
                "certainty": "high",
                "reason_code": "ok",
                "reason": "ok",
            },
            {
                "slug": "ghost-segment",
                "decision": "accept",
                "intent": "commercial_demand",
                "certainty": "high",
                "reason_code": "ok",
                "reason": "ok",
            },
        ],
    }
    parsed = parse_segment_aware_message(
        raw,
        expected_index=0,
        candidate_segments=["tennis"],
    )
    assert [v.segment_slug for v in parsed.verdicts] == ["tennis"]
    assert "ghost-segment" not in parsed.fail_open_segments


def test_duplicate_segment_is_malformed_fail_open(caplog):
    raw = {
        "index": 0,
        "segments": [
            {
                "slug": "cleaning",
                "decision": "accept",
                "intent": "commercial_demand",
                "certainty": "high",
                "reason_code": "a",
                "reason": "a",
            },
            {
                "slug": "cleaning",
                "decision": "reject",
                "intent": "provider_offer",
                "certainty": "high",
                "reason_code": "b",
                "reason": "b",
            },
        ],
    }
    with caplog.at_level(logging.WARNING):
        parsed = parse_segment_aware_message(
            raw,
            expected_index=0,
            candidate_segments=["cleaning"],
        )
    assert parsed.malformed is True
    legacy = to_legacy_llm_result(
        candidate_segments=["cleaning"],
        verdicts=parsed.verdicts,
        fail_open_segments=parsed.fail_open_segments,
        malformed=True,
    )
    assert legacy.verdict == "DEMAND"
    assert legacy.relevant_segments == ["cleaning"]
    assert legacy.error == "malformed_v2"
    assert not LLMValidator_should_block(legacy)


def test_missing_candidate_fail_open():
    raw = {
        "index": 0,
        "segments": [
            {
                "slug": "plumber",
                "decision": "reject",
                "intent": "provider_offer",
                "certainty": "high",
                "reason_code": "ad",
                "reason": "реклама",
            },
        ],
    }
    parsed = parse_segment_aware_message(
        raw,
        expected_index=0,
        candidate_segments=["plumber", "electrician"],
    )
    assert "electrician" in parsed.fail_open_segments
    legacy = to_legacy_llm_result(
        candidate_segments=["plumber", "electrician"],
        verdicts=parsed.verdicts,
        fail_open_segments=parsed.fail_open_segments,
    )
    assert "electrician" in legacy.relevant_segments
    assert "plumber" not in legacy.relevant_segments
    assert legacy.verdict == "DEMAND"  # fail-open keeps message alive


def test_unknown_intent_fail_open():
    raw = {
        "index": 0,
        "segments": [
            {
                "slug": "lawyer",
                "decision": "accept",
                "intent": "space_alien",
                "certainty": "high",
                "reason_code": "weird",
                "reason": "???",
            },
        ],
    }
    parsed = parse_segment_aware_message(
        raw,
        expected_index=0,
        candidate_segments=["lawyer"],
    )
    assert parsed.verdicts == []
    assert parsed.fail_open_segments == ["lawyer"]


def test_accept_only_for_demand_or_mixed():
    raw = {
        "index": 0,
        "segments": [
            {
                "slug": "massage",
                "decision": "accept",
                "intent": "provider_offer",
                "certainty": "high",
                "reason_code": "bad_combo",
                "reason": "accept+offer",
            },
        ],
    }
    parsed = parse_segment_aware_message(
        raw,
        expected_index=0,
        candidate_segments=["massage"],
    )
    assert "massage" in parsed.fail_open_segments


def test_all_reject_maps_to_blockable_legacy():
    raw = {
        "index": 0,
        "segments": [
            {
                "slug": "delivery",
                "decision": "reject",
                "intent": "provider_offer",
                "certainty": "high",
                "reason_code": "service_ad",
                "reason": "реклама службы",
            },
        ],
    }
    parsed = parse_segment_aware_message(
        raw,
        expected_index=0,
        candidate_segments=["delivery"],
    )
    legacy = to_legacy_llm_result(
        candidate_segments=["delivery"],
        verdicts=parsed.verdicts,
        fail_open_segments=parsed.fail_open_segments,
    )
    assert legacy.verdict == "OFFER"
    assert legacy.relevant_segments == []
    assert legacy.certainty == "high"
    assert LLMValidator_should_block(legacy) is True


def test_reason_code_and_reason_sanitized():
    raw = {
        "index": 0,
        "segments": [
            {
                "slug": "courier",
                "decision": "accept",
                "intent": "commercial_demand",
                "certainty": "medium",
                "reason_code": "Bad-Code!!",
                "reason": "x" * 500,
            },
        ],
    }
    parsed = parse_segment_aware_message(
        raw,
        expected_index=0,
        candidate_segments=["courier"],
    )
    assert len(parsed.verdicts) == 1
    assert parsed.verdicts[0].reason_code == "invalid_reason_code"
    assert len(parsed.verdicts[0].reason) <= 160


def test_top_level_not_list_or_wrong_index_malformed():
    parsed = parse_segment_aware_message(
        {"index": 5, "segments": []},
        expected_index=0,
        candidate_segments=["pets"],
    )
    assert parsed.malformed is True
    legacy = to_legacy_llm_result(
        candidate_segments=["pets"],
        verdicts=[],
        fail_open_segments=["pets"],
        malformed=True,
    )
    assert legacy.verdict == "DEMAND"
    assert legacy.error == "malformed_v2"


def test_segment_verdict_types():
    v = SegmentVerdict(
        segment_slug="accountant",
        decision=LLMDecision.REJECT,
        intent=CommercialIntent.JOB_VACANCY,
        certainty="high",
        reason_code="staff_hire",
        reason="вакансия",
    )
    assert v.decision.value == "reject"
    assert v.intent.value == "job_vacancy"


def LLMValidator_should_block(result) -> bool:
    from app.userbot.llm_validator import LLMValidator

    return LLMValidator().should_block(result)
