"""T1.1 — матрица лимитов тарифов v2 (#81), детерминированно (monkeypatch settings).

Не зависит от прод-.env: подставляем известные значения и проверяем разводку по планам.
"""

import pytest

from app.config import settings
from app.db.crud import (
    get_max_segments,
    get_max_channels,
    get_max_keywords,
    get_max_countries,
    get_max_cities_per_sub,
)


@pytest.fixture
def fixed_limits(monkeypatch):
    vals = {
        "max_segments_free": 1, "max_segments_start": 1, "max_segments_pro": 5,
        "max_channels_free": 1, "max_channels_start": 1, "max_channels_pro": 10,
        "max_keywords_free": 1, "max_keywords_start": 10, "max_keywords_pro": 50,
        "max_countries_start": 1, "max_cities_start": 3, "max_countries_pro": 5,
        "business_hidden_cap_segments": 60, "business_hidden_cap_channels": 60,
        "business_hidden_cap_keywords": 60,
    }
    for k, v in vals.items():
        monkeypatch.setattr(settings, k, v)
    return vals


def test_segments_by_plan(fixed_limits):
    assert get_max_segments("free") == 1
    assert get_max_segments("start") == 1
    assert get_max_segments("pro") == 5
    assert get_max_segments("business") == 60
    assert get_max_segments("trial") == 60


def test_keywords_by_plan(fixed_limits):
    assert get_max_keywords("free") == 1
    assert get_max_keywords("start") == 10
    assert get_max_keywords("pro") == 50
    assert get_max_keywords("business") == 60
    assert get_max_keywords("trial") == 60


def test_channels_by_plan(fixed_limits):
    assert get_max_channels("free") == 1
    assert get_max_channels("start") == 1
    assert get_max_channels("pro") == 10
    assert get_max_channels("business") == 60
    assert get_max_channels("trial") == 60


def test_geo_countries_by_plan(fixed_limits):
    # free = start по гео; pro ограничивает страны; business/trial — без гео-лимита
    assert get_max_countries("free") == 1
    assert get_max_countries("start") == 1
    assert get_max_countries("pro") == 5
    assert get_max_countries("business") > 60
    assert get_max_countries("trial") > 60


def test_geo_cities_per_sub_by_plan(fixed_limits):
    assert get_max_cities_per_sub("free") == 3
    assert get_max_cities_per_sub("start") == 3
    assert get_max_cities_per_sub("pro") > 60  # города без лимита у pro
    assert get_max_cities_per_sub("business") > 60


def test_unknown_plan_falls_back_to_free(fixed_limits):
    # Least privilege: неизвестный slug → лимиты free, не business.
    assert get_max_segments("garbage") == get_max_segments("free")
    assert get_max_keywords("garbage") == get_max_keywords("free")
