"""Phase 8: segment-profile LLM shadow / blocking mode."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fakeredis.aioredis import FakeRedis

from app.config import settings
from app.userbot.llm_profiles import SegmentLLMProfile, replace_profile_snapshot, reset_profile_runtime_state
from app.userbot.llm_validator import LLMResult, LLMValidator, PendingMatch


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
    replace_profile_snapshot({"tennis": _profile("tennis")})
    yield
    reset_profile_runtime_state()


@pytest.mark.asyncio
async def test_profiles_disabled_does_not_call_v2(monkeypatch):
    monkeypatch.setattr(settings, "llm_enabled", True)
    monkeypatch.setattr(settings, "deepseek_api_key", "k")
    monkeypatch.setattr(settings, "llm_segment_profiles_enabled", False)
    monkeypatch.setattr(settings, "llm_segment_profiles_blocking", False)

    validator = LLMValidator()
    legacy = {0: LLMResult(verdict="DEMAND", certainty="high", reason="legacy")}
    with (
        patch.object(validator, "_call_llm_batch", AsyncMock(return_value=legacy)),
        patch.object(validator, "_call_llm_batch_v2", AsyncMock(return_value={})) as v2,
        patch("app.userbot.llm_validator._cache_get_verdicts", AsyncMock(return_value={})),
        patch("app.userbot.llm_validator._cache_put_verdicts", AsyncMock()),
        patch("app.userbot.llm_validator._record_llm_stats", AsyncMock()),
        patch("app.userbot.llm_validator.is_high_confidence_demand", return_value=False),
    ):
        results = await validator.validate_batch(
            [PendingMatch("c", 1, "нужен тренер", ["tennis"])]
        )
    assert v2.await_count == 0
    assert results[0].verdict == "DEMAND"
    assert results[0].from_v2 is False


@pytest.mark.asyncio
async def test_shadow_keeps_legacy_delivery_on_disagreement(monkeypatch):
    monkeypatch.setattr(settings, "llm_enabled", True)
    monkeypatch.setattr(settings, "deepseek_api_key", "k")
    monkeypatch.setattr(settings, "llm_segment_profiles_enabled", True)
    monkeypatch.setattr(settings, "llm_segment_profiles_blocking", False)

    redis = FakeRedis()
    validator = LLMValidator()
    legacy = {0: LLMResult(verdict="OFFER", certainty="high", reason="legacy-offer")}
    v2 = {
        0: {
            "index": 0,
            "segments": [
                {
                    "slug": "tennis",
                    "decision": "accept",
                    "intent": "commercial_demand",
                    "certainty": "high",
                    "reason_code": "needs_coach",
                    "reason": "ищет тренера",
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
        patch("app.cache.get_redis", AsyncMock(return_value=redis)),
    ):
        results = await validator.validate_batch(
            [PendingMatch("c", 1, "нужен тренер по теннису", ["tennis"])]
        )
    assert results[0].verdict == "OFFER"
    assert results[0].from_v2 is False
    assert results[0].correlation_id
    # disagreement: old reject(accept? OFFER=block) vs new accept
    keys = [k async for k in redis.scan_iter(match="stats:llm_v2:disagreement_old_reject_new_accept:*")]
    assert keys


@pytest.mark.asyncio
async def test_blocking_applies_v2_result(monkeypatch):
    monkeypatch.setattr(settings, "llm_enabled", True)
    monkeypatch.setattr(settings, "deepseek_api_key", "k")
    monkeypatch.setattr(settings, "llm_segment_profiles_enabled", True)
    monkeypatch.setattr(settings, "llm_segment_profiles_blocking", True)

    redis = FakeRedis()
    validator = LLMValidator()
    legacy = {0: LLMResult(verdict="DEMAND", certainty="high", reason="legacy")}
    v2 = {
        0: {
            "index": 0,
            "segments": [
                {
                    "slug": "tennis",
                    "decision": "reject",
                    "intent": "social_request",
                    "certainty": "high",
                    "reason_code": "play_partner",
                    "reason": "партнёр",
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
        patch("app.cache.get_redis", AsyncMock(return_value=redis)),
    ):
        results = await validator.validate_batch(
            [PendingMatch("c", 1, "ищу партнёра по теннису", ["tennis"])]
        )
    assert results[0].from_v2 is True
    assert results[0].verdict == "OTHER"
    assert results[0].relevant_segments == []
    assert validator.should_block(results[0]) is True


@pytest.mark.asyncio
async def test_v2_error_keeps_legacy_delivery(monkeypatch):
    monkeypatch.setattr(settings, "llm_enabled", True)
    monkeypatch.setattr(settings, "deepseek_api_key", "k")
    monkeypatch.setattr(settings, "llm_segment_profiles_enabled", True)
    monkeypatch.setattr(settings, "llm_segment_profiles_blocking", True)

    redis = FakeRedis()
    validator = LLMValidator()
    legacy = {0: LLMResult(verdict="DEMAND", certainty="high", reason="legacy-ok")}
    with (
        patch.object(validator, "_call_llm_batch", AsyncMock(return_value=legacy)),
        patch.object(
            validator,
            "_call_llm_batch_v2",
            AsyncMock(side_effect=RuntimeError("v2 down")),
        ),
        patch("app.userbot.llm_validator._cache_get_verdicts", AsyncMock(return_value={})),
        patch("app.userbot.llm_validator._cache_put_verdicts", AsyncMock()),
        patch("app.userbot.llm_validator._record_llm_stats", AsyncMock()),
        patch("app.userbot.llm_validator.is_high_confidence_demand", return_value=False),
        patch("app.cache.get_redis", AsyncMock(return_value=redis)),
    ):
        results = await validator.validate_batch(
            [PendingMatch("c", 1, "нужен тренер", ["tennis"])]
        )
    assert results[0].verdict == "DEMAND"
    assert results[0].reason == "legacy-ok"
    assert results[0].from_v2 is False


def test_dispatch_segments_respect_v2_relevant_when_blocking(monkeypatch):
    from app.userbot.poller import ChannelPoller

    monkeypatch.setattr(settings, "llm_segment_profiles_enabled", True)
    monkeypatch.setattr(settings, "llm_segment_profiles_blocking", True)
    match = PendingMatch("c", 1, "text", ["tennis", "fitness"])
    result = LLMResult(
        verdict="DEMAND",
        relevant_segments=["tennis"],
        from_v2=True,
    )
    poller = ChannelPoller()
    poller._quarantined_slugs = set()
    assert poller._segments_for_dispatch(match, result) == ["tennis"]
