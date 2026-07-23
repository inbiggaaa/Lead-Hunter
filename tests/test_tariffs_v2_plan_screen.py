"""T3.1 — экран «Тариф и оплата»: единый рендер, 3 карточки, отметка текущего плана."""

from types import SimpleNamespace

import pytest

from app.bot.handlers.plan import build_plan_screen, plan_display_name


def _btns(kb):
    return [(b.text, b.callback_data) for row in kb.inline_keyboard for b in row]


def test_free_user_sees_three_tariff_buttons():
    user = SimpleNamespace(plan="free", language="ru")
    text, kb = build_plan_screen(user, "ru")
    cbs = [cb for _, cb in _btns(kb)]
    assert "pay_plan:start" in cbs
    assert "pay_plan:pro" in cbs
    assert "pay_plan:business" in cbs
    assert "menu:main" in cbs
    # все три карточки на экране
    assert "Start" in text and "Pro" in text and "Business" in text


def test_current_plan_marked():
    user = SimpleNamespace(plan="pro", language="ru")
    _, kb = build_plan_screen(user, "ru")
    labels = [t for t, _ in _btns(kb)]
    # у текущего плана — галочка «твой», у остальных обычные кнопки
    assert any("✅" in l and "Pro" in l for l in labels)
    assert any("Start" in l and "✅" not in l for l in labels)


def test_display_names_localized():
    assert plan_display_name("start", "ru") == "Start"
    assert plan_display_name("start", "en") == "Start"
    assert plan_display_name("business", "ru") == "Business"


def test_en_screen_renders():
    user = SimpleNamespace(plan="start", language="en")
    text, kb = build_plan_screen(user, "en")
    assert "Plan & payment" in text
    # Business v2.2 (#89): unlimited services, 20 countries
    assert "unlimited services" in text
    assert "20 countries" in text
    assert "unlimited cities" in text
