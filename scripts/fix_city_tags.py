"""One-off fix: auto-tag city from channel titles for all countries.

For each channel, counts how many active cities from its country
appear in the title. If exactly one → tag with that city.
If multiple → set city to NULL (country-level channel).
"""

import asyncio
from collections import Counter

from app.db.session import async_session_factory
from app.db.models import CatalogChannel, Country, City
from sqlalchemy import select, update


async def main():
    async with async_session_factory() as session:
        countries = (await session.execute(
            select(Country).where(Country.is_active == True)
        )).scalars().all()
        cities = (await session.execute(
            select(City).where(City.is_active == True, City.name_ru != "🌐 Вся страна")
        )).scalars().all()
        channels = (await session.execute(
            select(CatalogChannel).where(
                CatalogChannel.auto_matched_country_id.isnot(None),
                CatalogChannel.title.isnot(None),
            )
        )).scalars().all()

    # Index: country_id -> list of (city_id, city_name_ru)
    country_cities: dict[int, list[tuple[int, str]]] = {}
    for c in cities:
        country_cities.setdefault(c.country_id, []).append((c.id, c.name_ru.lower()))

    tagged = 0
    nullified = 0

    for ch in channels:
        if ch.auto_matched_country_id not in country_cities:
            continue

        title_lower = ch.title.lower()
        city_hits: list[int] = []

        for city_id, city_name in country_cities[ch.auto_matched_country_id]:
            if len(city_name) < 4:  # skip short names (false matches)
                continue
            if city_name in title_lower:
                city_hits.append(city_id)

        unique_hits = list(set(city_hits))

        if len(unique_hits) == 1:
            # Single city in title → tag it (if not already correct)
            if ch.auto_matched_city_id != unique_hits[0]:
                async with async_session_factory() as session:
                    await session.execute(
                        update(CatalogChannel)
                        .where(CatalogChannel.id == ch.id)
                        .values(auto_matched_city_id=unique_hits[0])
                    )
                    await session.commit()
                tagged += 1
        elif len(unique_hits) >= 2:
            # Multi-city in title → remove city tag (country-level only)
            if ch.auto_matched_city_id is not None:
                async with async_session_factory() as session:
                    await session.execute(
                        update(CatalogChannel)
                        .where(CatalogChannel.id == ch.id)
                        .values(auto_matched_city_id=None)
                    )
                    await session.commit()
                nullified += 1

    print(f"Tagged: {tagged} channels with detected city")
    print(f"Nullified: {nullified} multi-city channels (→ country-level)")
    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
