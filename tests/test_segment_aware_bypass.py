"""Phase 7: segment-aware high-confidence LLM bypass gate."""

from __future__ import annotations

import pytest

from app.userbot.llm_profiles import SegmentLLMProfile
from app.userbot.llm_validator import may_bypass_llm


def _profile(
    slug: str,
    *,
    requires_llm: bool = True,
) -> SegmentLLMProfile:
    return SegmentLLMProfile(
        segment_slug=slug,
        locale="ru",
        target_lead="t",
        accept_examples=("a",),
        reject_examples=("b",),
        conflict_slugs=(),
        requires_llm=requires_llm,
        version=1,
    )


def test_missing_profile_false():
    assert (
        may_bypass_llm(
            text="нужен сантехник сегодня",
            candidate_segments=("plumber",),
            profiles={},
            lead_directions={"plumber": "demand"},
        )
        is False
    )


def test_requires_llm_true_false():
    assert (
        may_bypass_llm(
            text="нужен сантехник сегодня",
            candidate_segments=("plumber",),
            profiles={"plumber": _profile("plumber", requires_llm=True)},
            lead_directions={"plumber": "demand"},
        )
        is False
    )


def test_any_candidate_requires_llm_blocks_bypass():
    profiles = {
        "plumber": _profile("plumber", requires_llm=False),
        "electrician": _profile("electrician", requires_llm=True),
    }
    assert (
        may_bypass_llm(
            text="нужен мастер сегодня",
            candidate_segments=("plumber", "electrician"),
            profiles=profiles,
            lead_directions={"plumber": "demand", "electrician": "demand"},
        )
        is False
    )


def test_safe_case_all_requires_llm_false():
    assert (
        may_bypass_llm(
            text="нужен сантехник сегодня",
            candidate_segments=("plumber",),
            profiles={"plumber": _profile("plumber", requires_llm=False)},
            lead_directions={"plumber": "demand"},
        )
        is True
    )


def test_regression_social_tennis_partner():
    assert (
        may_bypass_llm(
            text="ищу партнёра по теннису",
            candidate_segments=("tennis",),
            profiles={"tennis": _profile("tennis", requires_llm=False)},
            lead_directions={"tennis": "demand"},
        )
        is False
    )


def test_regression_social_football():
    assert (
        may_bypass_llm(
            text="кто хочет поиграть в футбол",
            candidate_segments=("football",),
            profiles={"football": _profile("football", requires_llm=False)},
            lead_directions={"football": "demand"},
        )
        is False
    )


def test_regression_vacancy_courier():
    assert (
        may_bypass_llm(
            text="требуется курьер в штат",
            candidate_segments=("courier",),
            profiles={"courier": _profile("courier", requires_llm=False)},
            lead_directions={"courier": "demand"},
        )
        is False
    )


def test_regression_accountant_one_off_still_needs_llm_if_requires_flag():
    # Even a real demand stays gated while requires_llm=true (v1 default).
    assert (
        may_bypass_llm(
            text="нужен бухгалтер на разовую консультацию",
            candidate_segments=("accountant",),
            profiles={"accountant": _profile("accountant", requires_llm=True)},
            lead_directions={"accountant": "demand"},
        )
        is False
    )


def test_regression_job_search_accountant():
    assert (
        may_bypass_llm(
            text="ищу работу бухгалтером",
            candidate_segments=("accountant",),
            profiles={"accountant": _profile("accountant", requires_llm=False)},
            lead_directions={"accountant": "demand"},
        )
        is False
    )


def test_regression_sell_on_demand_segment():
    assert (
        may_bypass_llm(
            text="продам байк",
            candidate_segments=("scooter-rental",),
            profiles={"scooter-rental": _profile("scooter-rental", requires_llm=False)},
            lead_directions={"scooter-rental": "demand"},
        )
        is False
    )


def test_regression_buy_on_supply_segment():
    assert (
        may_bypass_llm(
            text="куплю байк",
            candidate_segments=("moto-purchase",),
            profiles={"moto-purchase": _profile("moto-purchase", requires_llm=False)},
            lead_directions={"moto-purchase": "supply"},
        )
        is False
    )


def test_regression_provider_cleaning():
    assert (
        may_bypass_llm(
            text="предлагаю услуги клининга",
            candidate_segments=("cleaning",),
            profiles={"cleaning": _profile("cleaning", requires_llm=False)},
            lead_directions={"cleaning": "demand"},
        )
        is False
    )


def test_regression_emoji_prefix_still_requires_llm_by_default():
    assert (
        may_bypass_llm(
            text="🤖 ищем подрядчика для автоматизации",
            candidate_segments=("automation",),
            profiles={"automation": _profile("automation", requires_llm=True)},
            lead_directions={"automation": "demand"},
        )
        is False
    )


def test_emoji_does_not_break_safe_demand():
    assert (
        may_bypass_llm(
            text="🔧 нужен сантехник сегодня",
            candidate_segments=("plumber",),
            profiles={"plumber": _profile("plumber", requires_llm=False)},
            lead_directions={"plumber": "demand"},
        )
        is True
    )


def test_sell_ok_on_supply_without_other_markers():
    assert (
        may_bypass_llm(
            text="продам байк с документами",
            candidate_segments=("moto-purchase",),
            profiles={"moto-purchase": _profile("moto-purchase", requires_llm=False)},
            lead_directions={"moto-purchase": "supply"},
        )
        is True
    )


@pytest.mark.asyncio
async def test_validate_batch_no_longer_skips_unsafe_high_conf():
    """Empty profile snapshot → may_bypass false → short social 'ищу…' goes to LLM."""
    from unittest.mock import AsyncMock, patch

    from app.userbot import llm_profiles as lp
    from app.userbot.llm_validator import LLMResult, LLMValidator, PendingMatch

    lp.reset_profile_runtime_state()
    validator = LLMValidator()

    with patch.object(type(validator), "enabled", property(lambda self: True)):
        with patch.object(
            validator,
            "_call_llm_batch",
            AsyncMock(
                return_value={
                    0: LLMResult(verdict="OTHER", certainty="high", reason="social"),
                }
            ),
        ) as call_mock:
            results = await validator.validate_batch(
                [
                    PendingMatch(
                        "c",
                        1,
                        "ищу партнёра по теннису",
                        ["tennis"],
                        skip_llm=True,
                    )
                ]
            )
    assert call_mock.await_count == 1
    assert results[0].verdict == "OTHER"
    assert "skipped LLM" not in results[0].reason.lower()
