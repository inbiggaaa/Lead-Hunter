"""Layer snapshot capture for closed matching feedback."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.config import settings
from app.matching_feedback.snapshot import build_matching_feedback_snapshot
from app.userbot.llm_profiles import SegmentLLMProfile, replace_profile_snapshot, reset_profile_runtime_state
from app.userbot.llm_validator import LLMResult, LLMValidator, PendingMatch


def _profile(slug: str, version: int = 1) -> SegmentLLMProfile:
    return SegmentLLMProfile(
        segment_slug=slug,
        locale="ru",
        target_lead="t",
        accept_examples=("a",),
        reject_examples=("b",),
        conflict_slugs=(),
        requires_llm=True,
        version=version,
    )


@pytest.fixture(autouse=True)
def _reset_profiles():
    reset_profile_runtime_state()
    replace_profile_snapshot({"cleaning": _profile("cleaning"), "repair": _profile("repair")})
    yield
    reset_profile_runtime_state()


def test_build_snapshot_shadow_preserves_legacy_and_v2():
    match = PendingMatch(
        chat_username="c",
        message_id=1,
        text="ищу клининг",
        candidate_segments=["cleaning"],
        rule_segments=["cleaning", "repair"],
    )
    llm = LLMResult(
        verdict="DEMAND",
        relevant_segments=["cleaning"],
        layer_snapshot={
            "legacy_llm_verdict": "DEMAND",
            "legacy_llm_segments": ["cleaning"],
            "v2_intent": "commercial_demand",
            "v2_segment_verdicts": {"cleaning": "accept"},
            "model_name": "deepseek-chat",
            "prompt_version": 2,
            "schema_version": 2,
            "profile_versions": {"cleaning": 1},
        },
    )
    snapshot = build_matching_feedback_snapshot(
        match=match,
        llm_result=llm,
        delivered_segments=["cleaning"],
    )
    assert snapshot["delivered_segments"] == ["cleaning"]
    assert snapshot["rule_segments"] == ["cleaning", "repair"]
    assert snapshot["reality_segments"] == ["cleaning"]
    assert snapshot["legacy_llm_verdict"] == "DEMAND"
    assert snapshot["v2_intent"] == "commercial_demand"
    assert snapshot["profile_versions"]["cleaning"] == 1
    assert "text" not in snapshot
    assert "raw_response" not in snapshot


def test_build_snapshot_keyword_only():
    match = PendingMatch(
        chat_username="c",
        message_id=2,
        text="kw",
        candidate_segments=[],
        rule_segments=[],
        keyword_only=True,
    )
    snapshot = build_matching_feedback_snapshot(
        match=match,
        llm_result=LLMResult(verdict="DEMAND", reason="kw"),
        delivered_segments=[],
    )
    assert snapshot["keyword_only"] is True
    assert snapshot["delivered_segments"] == []
    assert snapshot["legacy_llm_verdict"] == "DEMAND"


def test_build_snapshot_legacy_only_without_v2():
    match = PendingMatch(
        chat_username="c",
        message_id=3,
        text="x",
        candidate_segments=["cleaning"],
        rule_segments=["cleaning"],
    )
    snapshot = build_matching_feedback_snapshot(
        match=match,
        llm_result=LLMResult(verdict="OFFER", relevant_segments=[]),
        delivered_segments=["cleaning"],
    )
    assert snapshot["legacy_llm_verdict"] == "OFFER"
    assert snapshot["v2_intent"] is None
    assert snapshot["v2_segment_verdicts"] == {}


@pytest.mark.asyncio
async def test_validate_batch_attaches_v2_layer_snapshot(monkeypatch):
    monkeypatch.setattr(settings, "llm_enabled", True)
    monkeypatch.setattr(settings, "deepseek_api_key", "k")
    monkeypatch.setattr(settings, "llm_segment_profiles_enabled", True)
    monkeypatch.setattr(settings, "llm_segment_profiles_blocking", False)

    validator = LLMValidator()
    legacy = {0: LLMResult(verdict="DEMAND", relevant_segments=["cleaning"], certainty="high")}
    v2 = {
        0: {
            "index": 0,
            "segments": [
                {
                    "slug": "cleaning",
                    "decision": "accept",
                    "intent": "commercial_demand",
                    "certainty": "high",
                    "reason_code": "needs_cleaner",
                    "reason": "ok",
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
        patch("app.userbot.llm_validator._record_llm_v2_message_metrics", AsyncMock()),
        patch("app.userbot.llm_validator.is_high_confidence_demand", return_value=False),
    ):
        results = await validator.validate_batch(
            [
                PendingMatch(
                    "c",
                    1,
                    "ищу клининг",
                    ["cleaning"],
                    rule_segments=["cleaning", "repair"],
                )
            ]
        )
    layer = results[0].layer_snapshot
    assert layer["legacy_llm_verdict"] == "DEMAND"
    assert layer["v2_intent"] == "commercial_demand"
    assert layer["v2_segment_verdicts"]["cleaning"] == "accept"
    assert layer["profile_versions"]["cleaning"] == 1
    assert results[0].from_v2 is False


@pytest.mark.asyncio
async def test_dispatch_payload_includes_snapshot_and_slugs():
    from app.userbot.poller import ChannelPoller

    poller = ChannelPoller.__new__(ChannelPoller)
    poller._seg_by_slug = {"cleaning": 1}
    poller._seg_info = {"cleaning": {"emoji": "✨", "ru": "Клининг", "en": "Cleaning"}}
    poller._quarantined_slugs = set()

    pushed = []

    async def fake_push(payload):
        pushed.append(payload)

    with (
        patch(
            "app.cache.subscription_cache.get_interested_users",
            AsyncMock(
                return_value=[
                    {
                        "user_id": 1,
                        "telegram_id": 100,
                        "lang": "ru",
                        "plan": "pro",
                        "subscriptions": [{"segment_id": 1, "country_id": 1, "city_ids": []}],
                        "keyword_texts": [],
                        "source": "direct",
                    }
                ]
            ),
        ),
        patch("app.cache.subscription_cache.rebuild_subscription_cache", AsyncMock()),
        patch("app.cache.subscription_cache.push_notification", fake_push),
        patch("app.cache.subscription_cache.build_message_hash", return_value="h" * 64),
        patch("app.cache.subscription_cache.compute_content_hash", return_value="c" * 64),
        patch("app.cache.subscription_cache.increment_daily_stats", AsyncMock()),
        patch("app.cache.subscription_cache.increment_segment_stat", AsyncMock()),
        patch("app.analytics.record_once_event", AsyncMock()),
        patch.object(poller, "_get_channel_geo", AsyncMock(return_value=(1, set(), True))),
        patch.object(poller, "_ensure_seg_maps", AsyncMock()),
    ):
        await ChannelPoller._dispatch(
            poller,
            chat_username="chat",
            message_text="ищу клининг",
            message_id=9,
            matched_segments=["cleaning"],
            is_urgent=False,
            sender=None,
            chat_title="Chat",
            matching_feedback_snapshot={
                "delivered_segments": ["cleaning"],
                "rule_segments": ["cleaning", "repair"],
                "reality_segments": ["cleaning"],
                "legacy_llm_verdict": "DEMAND",
                "v2_intent": "commercial_demand",
                "keyword_only": False,
            },
        )

    assert len(pushed) == 1
    assert pushed[0]["matched_segment_slugs"] == ["cleaning"]
    assert pushed[0]["matched_segments"][0]["title"] == "Клининг"
    assert pushed[0]["matching_feedback_snapshot"]["rule_segments"] == ["cleaning", "repair"]
    assert "ищу" not in str(pushed[0]["matching_feedback_snapshot"])
