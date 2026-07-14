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


# ── Города в одной подписке ──

def test_cities_start_caps_at_1(fixed_geo):
    assert cities_within_limit("start", 1) is True
    assert cities_within_limit("start", 2) is False


def test_cities_free_same_as_start(fixed_geo):
    assert cities_within_limit("free", 1) is True
    assert cities_within_limit("free", 2) is False


def test_cities_pro_caps_at_9(fixed_geo):
    assert cities_within_limit("pro", 9) is True
    assert cities_within_limit("pro", 10) is False


def test_cities_business_unlimited_and_trial_uses_pro_limit(fixed_geo):
    assert cities_within_limit("business", 50) is True
    assert cities_within_limit("trial", 9) is True
    assert cities_within_limit("trial", 10) is False


# ── Режим всей страны ──

def test_all_country_only_business(fixed_geo):
    assert plan_has_unlimited_cities("free") is False
    assert plan_has_unlimited_cities("start") is False
    assert plan_has_unlimited_cities("pro") is False
    assert plan_has_unlimited_cities("business") is True
    assert plan_has_unlimited_cities("trial") is False


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
