"""Phase 1: segment_llm_profiles model + CRUD + migration scope."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.db import crud
from app.db.models import Category, Segment, SegmentLLMProfile


async def _segment(session, slug: str = "tennis") -> Segment:
    cat = Category(slug=f"cat-{slug}", title_ru="Тест")
    session.add(cat)
    await session.flush()
    seg = Segment(slug=slug, title_ru=slug, category_id=cat.id)
    session.add(seg)
    await session.flush()
    return seg


@pytest.mark.asyncio
class TestSegmentLLMProfileModel:
    async def test_create_profile(self, session):
        seg = await _segment(session)
        profile = await crud.create_segment_llm_profile(
            session,
            segment_id=seg.id,
            target_lead="Клиент ищет тренера или корт",
            accept_examples=["Ищу тренера по теннису"],
            reject_examples=["Ищу партнёра поиграть"],
            conflict_slugs=["fitness"],
        )
        assert profile.id is not None
        assert profile.segment_id == seg.id
        assert profile.locale == "ru"
        assert profile.requires_llm is True
        assert profile.version == 1
        assert profile.accept_examples == ["Ищу тренера по теннису"]
        assert profile.reject_examples == ["Ищу партнёра поиграть"]
        assert profile.conflict_slugs == ["fitness"]

    async def test_unique_segment_locale(self, session):
        seg = await _segment(session, "plumber")
        await crud.create_segment_llm_profile(
            session,
            segment_id=seg.id,
            target_lead="Заказчик ищет сантехника",
            accept_examples=["Нужен сантехник"],
            reject_examples=["Предлагаю услуги сантехника"],
            conflict_slugs=[],
            locale="ru",
        )
        with pytest.raises(IntegrityError):
            await crud.create_segment_llm_profile(
                session,
                segment_id=seg.id,
                target_lead="Другой профиль",
                accept_examples=["Нужен мастер"],
                reject_examples=["Вакансия сантехника"],
                conflict_slugs=[],
                locale="ru",
            )

    async def test_update_bumps_version(self, session):
        seg = await _segment(session, "cleaning")
        profile = await crud.create_segment_llm_profile(
            session,
            segment_id=seg.id,
            target_lead="Клиент ищет клининг",
            accept_examples=["Нужна уборка"],
            reject_examples=["Предлагаем клининг"],
            conflict_slugs=[],
        )
        assert profile.version == 1
        updated = await crud.update_segment_llm_profile(
            session,
            profile_id=profile.id,
            target_lead="Клиент ищет клининг квартиры",
            accept_examples=["Нужна уборка квартиры"],
            reject_examples=["Предлагаем клининг"],
            conflict_slugs=["nanny"],
        )
        assert updated.version == 2
        assert updated.target_lead == "Клиент ищет клининг квартиры"
        assert updated.conflict_slugs == ["nanny"]

    async def test_empty_target_rejected(self, session):
        seg = await _segment(session, "lawyer")
        with pytest.raises(crud.SegmentLLMProfileValidationError):
            await crud.create_segment_llm_profile(
                session,
                segment_id=seg.id,
                target_lead="   ",
                accept_examples=["Нужен юрист"],
                reject_examples=["Вакансия юриста"],
                conflict_slugs=[],
            )

    async def test_invalid_json_lists_rejected(self, session):
        seg = await _segment(session, "electrician")
        with pytest.raises(crud.SegmentLLMProfileValidationError):
            await crud.create_segment_llm_profile(
                session,
                segment_id=seg.id,
                target_lead="Клиент ищет электрика",
                accept_examples="не список",  # type: ignore[arg-type]
                reject_examples=["Предлагаю услуги электрика"],
                conflict_slugs=[],
            )
        with pytest.raises(crud.SegmentLLMProfileValidationError):
            await crud.create_segment_llm_profile(
                session,
                segment_id=seg.id,
                target_lead="Клиент ищет электрика",
                accept_examples=["Нужен электрик"],
                reject_examples=[""],
                conflict_slugs=[],
            )
        with pytest.raises(crud.SegmentLLMProfileValidationError):
            await crud.create_segment_llm_profile(
                session,
                segment_id=seg.id,
                target_lead="Клиент ищет электрика",
                accept_examples=["Нужен электрик"],
                reject_examples=["Предлагаю услуги"],
                conflict_slugs=[123],  # type: ignore[list-item]
            )

    async def test_locale_normalized(self, session):
        seg = await _segment(session, "accountant")
        profile = await crud.create_segment_llm_profile(
            session,
            segment_id=seg.id,
            target_lead="Клиент ищет бухгалтера",
            accept_examples=["Нужен бухгалтер"],
            reject_examples=["Ищу работу бухгалтером"],
            conflict_slugs=[],
            locale=" RU ",
        )
        assert profile.locale == "ru"

    async def test_cascade_delete_with_segment(self, session):
        seg = await _segment(session, "pets")
        profile = await crud.create_segment_llm_profile(
            session,
            segment_id=seg.id,
            target_lead="Клиент ищет зооуслугу",
            accept_examples=["Нужен грумер"],
            reject_examples=["Предлагаю груминг"],
            conflict_slugs=[],
        )
        profile_id = profile.id
        await session.delete(seg)
        await session.flush()
        result = await session.execute(
            select(SegmentLLMProfile).where(SegmentLLMProfile.id == profile_id)
        )
        assert result.scalar_one_or_none() is None

    async def test_different_locales_allowed(self, session):
        seg = await _segment(session, "driver")
        ru = await crud.create_segment_llm_profile(
            session,
            segment_id=seg.id,
            target_lead="Клиент ищет водителя",
            accept_examples=["Нужен водитель"],
            reject_examples=["Ищу работу водителем"],
            conflict_slugs=[],
            locale="ru",
        )
        en = await crud.create_segment_llm_profile(
            session,
            segment_id=seg.id,
            target_lead="Client needs a driver",
            accept_examples=["Looking for a driver"],
            reject_examples=["Hiring a full-time driver"],
            conflict_slugs=[],
            locale="en",
        )
        assert ru.id != en.id
        assert ru.locale == "ru"
        assert en.locale == "en"


class TestSegmentLLMProfileMigration:
    def test_downgrade_drops_only_new_table(self):
        """Migration downgrade must drop segment_llm_profiles only."""
        path = Path("migrations/versions/segment_profiles01.py")
        assert path.exists()
        tree = ast.parse(path.read_text(encoding="utf-8"))
        upgrade_drops: list[str] = []
        downgrade_drops: list[str] = []
        creates: list[str] = []

        class Visitor(ast.NodeVisitor):
            def __init__(self) -> None:
                self._fn: str | None = None

            def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
                prev = self._fn
                self._fn = node.name
                self.generic_visit(node)
                self._fn = prev

            def visit_Call(self, node: ast.Call) -> None:
                name = ""
                if isinstance(node.func, ast.Attribute):
                    name = node.func.attr
                if name == "create_table" and node.args:
                    arg0 = node.args[0]
                    if isinstance(arg0, ast.Constant) and isinstance(arg0.value, str):
                        creates.append(arg0.value)
                if name == "drop_table" and node.args:
                    arg0 = node.args[0]
                    if isinstance(arg0, ast.Constant) and isinstance(arg0.value, str):
                        if self._fn == "upgrade":
                            upgrade_drops.append(arg0.value)
                        elif self._fn == "downgrade":
                            downgrade_drops.append(arg0.value)
                self.generic_visit(node)

        Visitor().visit(tree)
        assert creates == ["segment_llm_profiles"]
        assert upgrade_drops == []
        assert downgrade_drops == ["segment_llm_profiles"]

    def test_revision_chain(self):
        path = Path("migrations/versions/segment_profiles01.py")
        src = path.read_text(encoding="utf-8")
        assert 'revision = "segment_profiles01"' in src
        assert 'down_revision = "stability_referral01"' in src
