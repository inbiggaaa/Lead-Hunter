"""Tests for catalog navigation: countries, cities, segments, flags, 2-column layout."""

import pytest
from app.config import settings
from app.db.crud import get_max_segments


class TestPlanLimits:
    """Verify plan limits read from settings matrix (тарифы v2, #81).
    Значения сверяются с settings (устойчиво к переопределению из .env)."""

    def test_free_limits(self):
        assert get_max_segments("free") == settings.max_segments_free

    def test_start_limits(self):
        assert get_max_segments("start") == settings.max_segments_start

    def test_pro_limits(self):
        assert get_max_segments("pro") == settings.max_segments_pro

    def test_trial_limits(self):
        # Trial = Business = кап 60
        assert get_max_segments("trial") == settings.business_hidden_cap_segments

    def test_business_limits(self):
        assert get_max_segments("business") == settings.business_hidden_cap_segments


class TestCountryFlags:
    """Verify all country slugs have corresponding flags."""

    def test_flag_map_coverage(self):
        from app.bot.handlers.catalog_nav import _country_flag
        # Critical slugs must have flags
        critical = ["vn", "id", "th", "ru", "tr", "ae", "ge", "kz",
                     "de", "es", "fr", "us", "gb", "in", "cn", "jp",
                     "br", "eg", "za", "it", "pt", "nl", "gr", "cy",
                     "pl", "cz", "ca", "mx", "ar", "au", "nz", "il",
                     "ch", "at", "be", "se", "no", "fi", "dk", "ie"]
        for slug in critical:
            flag = _country_flag(slug)
            assert flag != "🌍", f"No flag for critical country: {slug}"

    def test_unknown_country_gets_globe(self):
        from app.bot.handlers.catalog_nav import _country_flag
        assert _country_flag("zzz") == "🌍"

    def test_vietnam_flag(self):
        from app.bot.handlers.catalog_nav import _country_flag
        assert _country_flag("vn") == "🇻🇳"


class TestTwoColumnLayout:
    """Verify the 2-column layout logic produces correct button rows."""

    def test_even_items(self):
        """4 items → 2 rows of 2."""
        items = ["a", "b", "c", "d"]
        rows = _to_columns(items)
        assert len(rows) == 2
        assert len(rows[0]) == 2
        assert len(rows[1]) == 2

    def test_odd_items(self):
        """3 items → 2 rows: [2, 1]."""
        items = ["a", "b", "c"]
        rows = _to_columns(items)
        assert len(rows) == 2
        assert len(rows[0]) == 2
        assert len(rows[1]) == 1

    def test_single_item(self):
        """1 item → 1 row of 1."""
        items = ["a"]
        rows = _to_columns(items)
        assert len(rows) == 1
        assert len(rows[0]) == 1

    def test_empty(self):
        """0 items → 0 rows."""
        assert _to_columns([]) == []


def _to_columns(items: list) -> list[list]:
    """Simulate the 2-column layout used in catalog_nav.py."""
    result = []
    row = []
    for item in items:
        row.append(item)
        if len(row) == 2:
            result.append(row)
            row = []
    if row:
        result.append(row)
    return result


class TestCountryCityData:
    """Verify country/city data integrity in DB."""

    @pytest.mark.asyncio
    async def test_no_countries_with_city_names(self, session):
        """No country name should contain city-like patterns."""
        from app.db.models import Country
        from sqlalchemy import select
        result = await session.execute(select(Country))
        countries = result.scalars().all()
        bad = [c for c in countries if "—" in (c.name_ru or "")]
        assert len(bad) == 0, f"Countries with '—' in name: {[(c.name_ru, c.slug) for c in bad]}"

    @pytest.mark.asyncio
    async def test_countries_have_names(self, session):
        """Every country should have a name_ru."""
        from app.db.models import Country
        from sqlalchemy import select
        result = await session.execute(select(Country).where(Country.name_ru.is_(None)))
        assert len(result.scalars().all()) == 0

    @pytest.mark.asyncio
    async def test_cities_belong_to_country(self, session):
        """Every city should belong to a valid country."""
        from app.db.models import City, Country
        from sqlalchemy import select
        city_result = await session.execute(select(City))
        cities = city_result.scalars().all()
        country_ids = {c.id for c in (await session.execute(select(Country))).scalars().all()}
        orphans = [c for c in cities if c.country_id not in country_ids]
        assert len(orphans) == 0, f"Orphan cities: {[(c.name_ru, c.country_id) for c in orphans]}"

    @pytest.mark.asyncio
    async def test_flag_for_every_country(self, session):
        """Every country slug should be in the flag map or get 🌍."""
        from app.db.models import Country
        from app.bot.handlers.catalog_nav import _country_flag
        from sqlalchemy import select
        result = await session.execute(select(Country))
        countries = result.scalars().all()
        globe_count = 0
        for c in countries:
            flag = _country_flag(c.slug)
            if flag == "🌍":
                globe_count += 1
        # Some countries may legitimately not have flags (rare ones)
        # but the 40 critical ones must have flags (tested in TestCountryFlags)
        total = len(countries)
        assert globe_count <= total * 0.3, f"Too many countries without flags: {globe_count}/{total}"
