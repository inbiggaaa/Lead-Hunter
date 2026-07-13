"""T0.2 — тарифы v2 (#81): новые поля конфигурации присутствуют и типизированы.

Абсолютные значения намеренно НЕ проверяются: прод-.env переопределяет часть полей
(server = dev + prod). Поведенческая матрица лимитов по планам — в T1.1 (get_max_* с monkeypatch).
"""

from app.config import settings


def test_start_plan_limit_fields_exist():
    for field in (
        "max_segments_start",
        "max_channels_start",
        "max_keywords_start",
    ):
        assert isinstance(getattr(settings, field), int), field


def test_geo_limit_fields_exist():
    for field in ("max_countries_start", "max_cities_start", "max_countries_pro"):
        assert isinstance(getattr(settings, field), int), field


def test_start_price_field_exists():
    assert isinstance(settings.price_start_monthly_usd, int)
    assert settings.price_start_monthly_usd > 0


def test_legacy_free_limits_preserved():
    # Free остаётся 1/1/1 — воронка не расширяется тарифами v2.
    assert settings.max_segments_free == 1
    assert settings.max_channels_free == 1
    assert settings.max_keywords_free == 1
