"""T4.1 — контекстные пейволлы: маршрут апгрейда, кнопка на pay_plan, локали."""

import pytest

from app.bot.handlers.plan import next_plan_for, build_paywall, paywall_text


def _cbs(kb):
    return [b.callback_data for row in kb.inline_keyboard for b in row if b.callback_data]


def test_upgrade_path_keyword():
    # keyword: free→start (10 слов), start→pro (50), pro→business (∞)
    assert next_plan_for("keyword", "free") == "start"
    assert next_plan_for("keyword", "start") == "pro"
    assert next_plan_for("keyword", "pro") == "business"


def test_upgrade_path_widen_coverage():
    # направление/гео/канал: у free и start лимит одинаков → сразу pro
    for trigger in ("direction", "country", "city", "channel"):
        assert next_plan_for(trigger, "free") == "pro", trigger
        assert next_plan_for(trigger, "start") == "pro", trigger
        assert next_plan_for(trigger, "pro") == "business", trigger


def test_paywall_button_leads_to_next_plan():
    _, kb = build_paywall("channel", "start", "ru")
    assert "pay_plan:pro" in _cbs(kb)   # Старт → Профи для каналов
    assert "menu:main" in _cbs(kb)


def test_paywall_pro_hits_business():
    _, kb = build_paywall("direction", "pro", "ru")
    assert "pay_plan:business" in _cbs(kb)


@pytest.mark.parametrize("lang", ["ru", "en"])
def test_paywall_text_localized_and_priced(lang):
    text = paywall_text("keyword", "start", lang)
    assert text and "paywall_keyword" not in text  # ключ не протёк
    assert "$" in text                              # цена подставлена


def test_paywall_full_screen_has_title_and_line():
    text, _ = build_paywall("city", "free", "ru")
    assert "Лимит текущего тарифа" in text
    assert "Города без лимита" in text
