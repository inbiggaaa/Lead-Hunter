"""Phase 3: runtime LLM profile snapshot loader."""

from __future__ import annotations

from types import MappingProxyType
from unittest.mock import AsyncMock, patch

import pytest

from app.db import crud
from app.db.models import Category, Segment
from app.userbot import llm_profiles as lp


async def _active_segment(session, slug: str = "tennis") -> Segment:
    cat = Category(slug=f"cat-{slug}", title_ru="t")
    session.add(cat)
    await session.flush()
    seg = Segment(slug=slug, title_ru=slug, category_id=cat.id, is_active=True)
    session.add(seg)
    await session.flush()
    return seg


async def _inactive_segment(session, slug: str = "ghost") -> Segment:
    cat = Category(slug=f"cat-{slug}", title_ru="t")
    session.add(cat)
    await session.flush()
    seg = Segment(slug=slug, title_ru=slug, category_id=cat.id, is_active=False)
    session.add(seg)
    await session.flush()
    return seg


class TestSelectCandidateProfiles:
    def test_empty_profiles(self):
        lp.reset_profile_runtime_state()
        selected = lp.select_candidate_profiles(["tennis"], {})
        assert selected == ()
        assert lp.profile_missing_total() == 1

    def test_one_profile(self):
        lp.reset_profile_runtime_state()
        profile = lp.SegmentLLMProfile(
            segment_slug="tennis",
            locale="ru",
            target_lead="клиент ищет тренера",
            accept_examples=("ищу тренера",),
            reject_examples=("ищу партнёра",),
            conflict_slugs=("fitness",),
            requires_llm=True,
            version=1,
        )
        selected = lp.select_candidate_profiles(["tennis"], {"tennis": profile})
        assert selected == (profile,)
        assert lp.profile_missing_total() == 0

    def test_duplicate_candidates_deduped(self):
        lp.reset_profile_runtime_state()
        profile = lp.SegmentLLMProfile(
            segment_slug="cleaning",
            locale="ru",
            target_lead="клиент ищет клининг",
            accept_examples=("нужна уборка",),
            reject_examples=("предлагаем клининг",),
            conflict_slugs=(),
            requires_llm=True,
            version=1,
        )
        selected = lp.select_candidate_profiles(
            ["cleaning", "cleaning", "cleaning"],
            {"cleaning": profile},
        )
        assert selected == (profile,)

    def test_unknown_candidate_slug_metric(self):
        lp.reset_profile_runtime_state()
        profile = lp.SegmentLLMProfile(
            segment_slug="plumber",
            locale="ru",
            target_lead="заказчик ищет сантехника",
            accept_examples=("нужен сантехник",),
            reject_examples=("вакансия сантехника",),
            conflict_slugs=(),
            requires_llm=True,
            version=1,
        )
        selected = lp.select_candidate_profiles(
            ["plumber", "unknown-seg"],
            {"plumber": profile},
        )
        assert selected == (profile,)
        assert lp.profile_missing_total() == 1


@pytest.mark.asyncio
class TestLoadAndSnapshot:
    async def test_empty_table(self, session):
        lp.reset_profile_runtime_state()
        await _active_segment(session, "tennis")
        loaded = await lp.load_segment_llm_profiles(session=session, locale="ru")
        assert loaded == {}
        lp.replace_profile_snapshot(loaded)
        assert dict(lp.get_profile_snapshot()) == {}

    async def test_one_profile_loaded(self, session):
        lp.reset_profile_runtime_state()
        seg = await _active_segment(session, "electrician")
        await crud.create_segment_llm_profile(
            session,
            segment_id=seg.id,
            target_lead="клиент ищет электрика",
            accept_examples=["нужен электрик"],
            reject_examples=["предлагаю услуги электрика"],
            conflict_slugs=[],
        )
        loaded = await lp.load_segment_llm_profiles(session=session, locale="ru")
        assert set(loaded) == {"electrician"}
        assert loaded["electrician"].target_lead == "клиент ищет электрика"
        assert loaded["electrician"].accept_examples == ("нужен электрик",)
        assert loaded["electrician"].requires_llm is True
        assert loaded["electrician"].version == 1

    async def test_inactive_segment_excluded(self, session):
        lp.reset_profile_runtime_state()
        active = await _active_segment(session, "lawyer")
        inactive = await _inactive_segment(session, "legacy-lawyer")
        await crud.create_segment_llm_profile(
            session,
            segment_id=active.id,
            target_lead="клиент ищет юриста",
            accept_examples=["нужен юрист"],
            reject_examples=["вакансия юриста"],
            conflict_slugs=[],
        )
        await crud.create_segment_llm_profile(
            session,
            segment_id=inactive.id,
            target_lead="legacy",
            accept_examples=["a"],
            reject_examples=["b"],
            conflict_slugs=[],
        )
        loaded = await lp.load_segment_llm_profiles(session=session, locale="ru")
        assert set(loaded) == {"lawyer"}

    async def test_atomic_replacement(self):
        lp.reset_profile_runtime_state()
        first = {
            "a": lp.SegmentLLMProfile(
                segment_slug="a",
                locale="ru",
                target_lead="t",
                accept_examples=("x",),
                reject_examples=("y",),
                conflict_slugs=(),
                requires_llm=True,
                version=1,
            )
        }
        lp.replace_profile_snapshot(first)
        snap1 = lp.get_profile_snapshot()
        second = {
            "b": lp.SegmentLLMProfile(
                segment_slug="b",
                locale="ru",
                target_lead="t2",
                accept_examples=("x",),
                reject_examples=("y",),
                conflict_slugs=(),
                requires_llm=True,
                version=1,
            )
        }
        lp.replace_profile_snapshot(second)
        snap2 = lp.get_profile_snapshot()
        assert dict(snap1) == first
        assert dict(snap2) == second
        assert isinstance(snap2, MappingProxyType)

    async def test_db_error_keeps_previous_snapshot(self):
        lp.reset_profile_runtime_state()
        previous = {
            "cleaning": lp.SegmentLLMProfile(
                segment_slug="cleaning",
                locale="ru",
                target_lead="клиент ищет клининг",
                accept_examples=("нужна уборка",),
                reject_examples=("предлагаем клининг",),
                conflict_slugs=(),
                requires_llm=True,
                version=1,
            )
        }
        lp.replace_profile_snapshot(previous)

        with patch(
            "app.userbot.llm_profiles.load_segment_llm_profiles",
            new=AsyncMock(side_effect=RuntimeError("db down")),
        ):
            ok = await lp.reload_profile_snapshot(locale="ru")
        assert ok is False
        assert dict(lp.get_profile_snapshot()) == previous
