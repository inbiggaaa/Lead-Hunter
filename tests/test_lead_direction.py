"""Tests for task B4 (fable_audit.md) — lead direction from DB.

M4: PURCHASE_SEGMENTS был хардкодом в classifier.py, инверсия DEMAND/OFFER —
хардкодом в LLM-промпте; новые moto-sale/car-sale не были учтены нигде,
а housing-buy ошибочно стоял в инвертированном блоке промпта (его реальные
demand-keywords — «куплю квартиру», лид = покупатель).
"""

from app.userbot.classifier import classify_message
from app.userbot.llm_validator import (
    DEFAULT_SUPPLY_SEGMENTS,
    LLMValidator,
    build_system_prompt,
)


# ── classify_message: purchase_segments параметр ──

_OFFER_SHAPED_LEAD = "куплю байк до 2000$, рассмотрю варианты, whatsapp +84123456789"
_KWMAP = {"moto-sale": {"demand": ["куплю байк"], "stop": [], "synonym": []}}


def test_pass3_skipped_for_db_driven_segment():
    """Сегмент из переданного set минует Pass 3 — цена+контакт не гасят лид.

    До B4 moto-sale не входил в константу PURCHASE_SEGMENTS."""
    result = classify_message(
        "рассмотрю байк с документами, бюджет 2000$, whatsapp +84123456789",
        _KWMAP | {"moto-sale": {"demand": ["рассмотрю байк"], "stop": [], "synonym": []}},
        purchase_segments={"moto-sale"},
    )
    assert result.matched_segments == ["moto-sale"]


def test_pass3_active_without_db_set():
    """Тот же текст без сегмента в set → Pass 3 гасит (оффер-сигнал, нет
    сильного глагола в начале)."""
    result = classify_message(
        "рассмотрю байк с документами, бюджет 2000$, whatsapp +84123456789",
        {"moto-sale": {"demand": ["рассмотрю байк"], "stop": [], "synonym": []}},
        purchase_segments=set(),
    )
    assert result.matched_segments == []


def test_default_none_keeps_legacy_constant():
    """purchase_segments=None → старая константа PURCHASE_SEGMENTS (обратная
    совместимость: housing-rent в ней есть)."""
    result = classify_message(
        "бюджет 500$ на квартиру, звоните +84123456789, сниму квартиру надолго",
        {"housing-rent": {"demand": ["сниму квартиру"], "stop": [], "synonym": []}},
    )
    assert result.matched_segments == ["housing-rent"]


# ── LLM prompt generation ──

def test_prompt_contains_db_slugs():
    prompt = build_system_prompt({"moto-purchase", "car-purchase", "boat-purchase"})
    assert "boat-purchase, car-purchase, moto-purchase" in prompt
    assert "seller = LEAD" in prompt


def test_prompt_default_excludes_housing_buy():
    """Фикс попутного бага: housing-buy (лид = покупатель, «куплю квартиру»)
    больше не в инвертированном блоке."""
    prompt = build_system_prompt(DEFAULT_SUPPLY_SEGMENTS)
    assert "housing-buy" not in prompt
    assert "moto-purchase, car-purchase" in prompt or "car-purchase, moto-purchase" in prompt


def test_prompt_without_supply_segments_omits_block():
    prompt = build_system_prompt(set())
    assert "SUPPLY-DIRECTION" not in prompt
    assert "DEMAND" in prompt  # базовый промпт цел


def test_validator_rebuilds_prompt_on_change():
    v = LLMValidator()
    before = v._system_prompt
    v.set_supply_segments({"moto-purchase"})
    assert "car-purchase" not in v._system_prompt
    assert v._system_prompt != before
    # idempotent: same set → no rebuild needed, prompt stays consistent
    cached = v._system_prompt
    v.set_supply_segments({"moto-purchase"})
    assert v._system_prompt is cached


# ── ORM default ──

async def test_segment_model_default_direction(session):
    """Новый сегмент без явного lead_direction получает 'demand' (server_default)."""
    from app.db.models import Category, Segment

    cat = Category(slug="b4-cat", title_ru="B4", sort_order=0)
    session.add(cat)
    await session.flush()
    seg = Segment(slug="b4-seg", title_ru="B4", category_id=cat.id)
    session.add(seg)
    await session.flush()
    await session.refresh(seg)
    assert seg.lead_direction == "demand"
