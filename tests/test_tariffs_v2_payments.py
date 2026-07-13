"""T2.1 — платёжный поток тарифов v2 (#81): _calc для 9 комбинаций план×период.

PLANS собирается из settings при импорте; monkeypatch-им usd_monthly, чтобы
таблица сумм была детерминирована независимо от прод-.env.
"""

import pytest

import app.bot.handlers.plan as plan_mod
from app.bot.handlers.plan import _calc, PLANS, PERIODS, STARS_PER_USD


@pytest.fixture
def canonical_prices(monkeypatch):
    monkeypatch.setitem(PLANS["start"], "usd_monthly", 9)
    monkeypatch.setitem(PLANS["pro"], "usd_monthly", 19)
    monkeypatch.setitem(PLANS["business"], "usd_monthly", 39)


# Итоговые суммы, $ (base × months × (1 − discount)); 3м −10%, год −20%
EXPECTED_TOTALS = {
    ("start", "1m"): 9.0,   ("start", "3m"): 24.3,  ("start", "1y"): 86.4,
    ("pro", "1m"): 19.0,    ("pro", "3m"): 51.3,    ("pro", "1y"): 182.4,
    ("business", "1m"): 39.0, ("business", "3m"): 105.3, ("business", "1y"): 374.4,
}


def test_nine_price_combos(canonical_prices):
    for (plan, period), total in EXPECTED_TOTALS.items():
        info = _calc(plan, period)
        assert round(info["total"], 2) == total, (plan, period)
        assert info["stars"] == int(total * STARS_PER_USD), (plan, period)
        assert info["months"] == PERIODS[period]["months"]


def test_all_three_plans_present():
    assert set(PLANS) == {"start", "pro", "business"}


def test_plan_names_russian():
    assert PLANS["start"]["name"] == "Старт"
    assert PLANS["pro"]["name"] == "Профи"
    assert PLANS["business"]["name"] == "Бизнес"


def test_calc_per_month_reflects_discount(canonical_prices):
    # Годовой Профи: $182.4 / 12 ≈ $15.2/мес — дешевле месячного $19.
    info = _calc("pro", "1y")
    assert round(info["per_month"], 1) == 15.2
    assert info["per_month"] < PLANS["pro"]["usd_monthly"]
