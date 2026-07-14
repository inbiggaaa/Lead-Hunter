"""T1.3 — гео-лимиты тарифов v2 (#81): предикаты cities/countries_within_limit.

Детерминированно (monkeypatch settings), независимо от прод-.env.
Предикаты — чистые, тестируются напрямую без FSM/aiogram.
"""

import pytest

from app.config import settings
from app.db.crud import cities_within_limit, countries_within_limit, plan_has_unlimited_cities


@pytest.fixture
def fixed_geo(monkeypatch):
    vals = {
        "max_cities_free": 1, "max_countries_start": 1, "max_cities_start": 1,
        "max_countries_pro": 3, "max_cities_pro": 9, "max_countries_business": 9,
        "max_segments_business": 12, "max_channels_business": 50,
        "max_keywords_business": 50,
    }
    for k, v in vals.items():
        monkeypatch.setattr(settings, k, v)


# ── Города не лимитируются; режим всей страны доступен всем ──

def test_cities_and_all_country_are_unlimited_for_every_plan(fixed_geo):
    for plan in ("free", "start", "pro", "business", "trial"):
        assert cities_within_limit(plan, 10_000) is True
        assert plan_has_unlimited_cities(plan) is True


# ── Distinct-страны по подпискам ──

def test_countries_start_one_country(fixed_geo):
    # Первая страна — ок; вторая (новая) — нет.
    assert countries_within_limit("start", set(), 1) is True
    assert countries_within_limit("start", {1}, 2) is False


def test_countries_start_same_country_ok(fixed_geo):
    # Повторный выбор уже используемой страны не увеличивает счётчик.
    assert countries_within_limit("start", {1}, 1) is True


def test_countries_pro_up_to_3(fixed_geo):
    assert countries_within_limit("pro", {1, 2}, 3) is True
    assert countries_within_limit("pro", {1, 2, 3}, 4) is False


def test_countries_business_caps_at_9(fixed_geo):
    assert countries_within_limit("business", set(range(1, 9)), 9) is True
    assert countries_within_limit("business", set(range(1, 10)), 10) is False
    assert countries_within_limit("trial", {1, 2}, 3) is True
    assert countries_within_limit("trial", {1, 2, 3}, 4) is False
