"""Phase 11: staged blocking allowlist for segment-aware LLM profiles."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.config import settings
from app.userbot.llm_profiles import (
    SegmentLLMProfile,
    replace_profile_snapshot,
    reset_profile_runtime_state,
)
from app.userbot.llm_validator import (
    FIRST_WAVE_BLOCKING_SEGMENTS,
    LLMResult,
    LLMValidator,
    PendingMatch,
    merge_v2_blocking_result,
)


def _profile(slug: str) -> SegmentLLMProfile:
    return SegmentLLMProfile(
        segment_slug=slug,
        locale="ru",
        target_lead="t",
        accept_examples=("a",),
        reject_examples=("b",),
        conflict_slugs=(),
        requires_llm=True,
        version=1,
    )


@pytest.fixture(autouse=True)
def _reset_profiles():
    reset_profile_runtime_state()
    replace_profile_snapshot({
        "cleaning": _profile("cleaning"),
        "tennis": _profile("tennis"),
    })
    yield
    reset_profile_runtime_state()


def test_first_wave_matches_recommended_group():
    assert FIRST_WAVE_BLOCKING_SEGMENTS == frozenset({
        "cleaning", "plumber", "electrician", "accountant", "lawyer",
    })


def test_empty_allowlist_is_fail_safe():
    legacy = LLMResult(verdict="DEMAND", certainty="high")
    v2 = LLMResult(verdict="OTHER", certainty="high", relevant_segments=[])
    assert merge_v2_blocking_result(
        candidate_segments=["cleaning"],
        legacy=legacy,
        v2_legacy=v2,
        allowlist=frozenset(),
    ) is None


def test_allowlist_blocks_only_gated_segment():
    legacy = LLMResult(verdict="DEMAND", certainty="high", correlation_id="abc")
    v2 = LLMResult(
        verdict="OTHER",
        certainty="high",
        relevant_segments=[],
        reason="reject cleaning",
    )
    merged = merge_v2_blocking_result(
        candidate_segments=["cleaning"],
        legacy=legacy,
        v2_legacy=v2,
        allowlist=frozenset({"cleaning"}),
    )
    assert merged is not None
    assert merged.from_v2 is True
    assert merged.verdict == "OTHER"
    assert merged.relevant_segments == []


def test_ungated_segments_still_dispatch_when_gated_rejected():
    legacy = LLMResult(verdict="DEMAND", certainty="high")
    v2 = LLMResult(
        verdict="OTHER",
        certainty="high",
        relevant_segments=[],  # cleaning rejected
        reason="reject",
    )
    merged = merge_v2_blocking_result(
        candidate_segments=["cleaning", "tennis"],
        legacy=legacy,
        v2_legacy=v2,
        allowlist=frozenset({"cleaning"}),
    )
    assert merged is not None
    assert merged.verdict == "DEMAND"
    assert merged.relevant_segments == ["tennis"]
    assert merged.from_v2 is True


def test_star_allowlist_gates_all():
    legacy = LLMResult(verdict="DEMAND", certainty="high")
    v2 = LLMResult(
        verdict="DEMAND",
        certainty="high",
        relevant_segments=["cleaning"],
    )
    merged = merge_v2_blocking_result(
        candidate_segments=["cleaning", "tennis"],
        legacy=legacy,
        v2_legacy=v2,
        allowlist=frozenset({"*"}),
    )
    assert merged is not None
    assert merged.relevant_segments == ["cleaning"]


@pytest.mark.asyncio
async def test_blocking_without_allowlist_keeps_legacy(monkeypatch):
    monkeypatch.setattr(settings, "llm_enabled", True)
    monkeypatch.setattr(settings, "deepseek_api_key", "k")
    monkeypatch.setattr(settings, "llm_segment_profiles_enabled", True)
    monkeypatch.setattr(settings, "llm_segment_profiles_blocking", True)
    monkeypatch.setattr(settings, "llm_segment_profiles_blocking_segments", "")

    validator = LLMValidator()
    legacy = {0: LLMResult(verdict="DEMAND", certainty="high", reason="legacy")}
    v2 = {
        0: {
            "index": 0,
            "segments": [
                {
                    "slug": "cleaning",
                    "decision": "reject",
                    "intent": "provider_offer",
                    "certainty": "high",
                    "reason_code": "ad",
                    "reason": "ad",
                }
            ],
        }
    }
    with (
        patch.object(validator, "_call_llm_batch", AsyncMock(return_value=legacy)),
        patch.object(validator, "_call_llm_batch_v2", AsyncMock(return_value=v2)),
        patch("app.userbot.llm_validator._cache_get_verdicts", AsyncMock(return_value={})),
        patch("app.userbot.llm_validator._cache_put_verdicts", AsyncMock()),
        patch("app.userbot.llm_validator._record_llm_stats", AsyncMock()),
        patch("app.userbot.llm_validator.is_high_confidence_demand", return_value=False),
        patch("app.userbot.llm_validator._incr_llm_v2_stat", AsyncMock()),
        patch("app.userbot.llm_validator._record_llm_v2_message_metrics", AsyncMock()),
    ):
        results = await validator.validate_batch(
            [PendingMatch("c", 1, "нужна уборка", ["cleaning"])]
        )
    assert results[0].verdict == "DEMAND"
    assert results[0].from_v2 is False
    assert results[0].reason == "legacy"
