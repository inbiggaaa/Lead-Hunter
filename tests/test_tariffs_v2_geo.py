"""T1.3 — гео-лимиты тарифов v2 (#81): предикаты cities/countries_within_limit.

Детерминированно (monkeypatch settings), независимо от прод-.env.
Предикаты — чистые, тестируются напрямую без FSM/aiogram.
"""

import pytest

from app.config import settings
from app.db.crud import cities_within_limit, countries_within_limit


@pytest.fixture
def fixed_geo(monkeypatch):
    vals = {
        "max_countries_start": 1, "max_cities_start": 3, "max_countries_pro": 5,
        "business_hidden_cap_segments": 60,
    }
    for k, v in vals.items():
        monkeypatch.setattr(settings, k, v)


# ── Города в одной подписке ──

def test_cities_start_caps_at_3(fixed_geo):
    assert cities_within_limit("start", 3) is True
    assert cities_within_limit("start", 4) is False


def test_cities_free_same_as_start(fixed_geo):
    assert cities_within_limit("free", 3) is True
    assert cities_within_limit("free", 4) is False


def test_cities_pro_unlimited(fixed_geo):
    assert cities_within_limit("pro", 50) is True


def test_cities_business_unlimited(fixed_geo):
    assert cities_within_limit("business", 50) is True
    assert cities_within_limit("trial", 50) is True


# ── Distinct-страны по подпискам ──

def test_countries_start_one_country(fixed_geo):
    # Первая страна — ок; вторая (новая) — нет.
    assert countries_within_limit("start", set(), 1) is True
    assert countries_within_limit("start", {1}, 2) is False


def test_countries_start_same_country_ok(fixed_geo):
    # Повторный выбор уже используемой страны не увеличивает счётчик.
    assert countries_within_limit("start", {1}, 1) is True


def test_countries_pro_up_to_5(fixed_geo):
    assert countries_within_limit("pro", {1, 2, 3, 4}, 5) is True   # 5-я страна
    assert countries_within_limit("pro", {1, 2, 3, 4, 5}, 6) is False  # 6-я


def test_countries_business_unlimited(fixed_geo):
    assert countries_within_limit("business", set(range(1, 60)), 100) is True
    assert countries_within_limit("trial", set(range(1, 60)), 100) is True
