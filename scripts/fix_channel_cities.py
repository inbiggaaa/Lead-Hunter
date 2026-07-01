"""Populate channel_cities table: detect city names in channel titles.

For each channel, find all cities (same country) mentioned in title
and add to channel_cities. Single-city channels get auto_matched_city_id
set; multi-city channels get channel_cities entries with NULL city_id.
"""

import asyncio

from app.db.session import async_session_factory
from app.db.models import CatalogChannel, Country, City, ChannelCity
from sqlalchemy import select, delete, update


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
        name = (c.name_ru or "").lower()
        if len(name) >= 4:
            country_cities.setdefault(c.country_id, []).append((c.id, name))

    single_tagged = 0
    multi_tagged = 0
    channels_processed = 0
    skipped_existing = 0

    # Pre-load channels that already have city entries (to skip them)
    async with async_session_factory() as session:
        existing_cc = (await session.execute(
            select(ChannelCity.channel_id).distinct()
        )).scalars().all()
    channels_with_city_entries = set(existing_cc)

    for ch in channels:
        # Skip channels already tagged with a city OR already in channel_cities
        if ch.auto_matched_city_id is not None:
            skipped_existing += 1
            continue
        if ch.id in channels_with_city_entries:
            skipped_existing += 1
            continue

        if ch.auto_matched_country_id not in country_cities:
            continue

        title_lower = ch.title.lower()
        city_hits: list[int] = []

        for city_id, city_name in country_cities[ch.auto_matched_country_id]:
            if city_name in title_lower:
                city_hits.append(city_id)

        unique_hits = list(dict.fromkeys(city_hits))  # preserve order, dedup

        if not unique_hits:
            continue

        channels_processed += 1

        if len(unique_hits) == 1:
            # Single city → set auto_matched_city_id
            city_id = unique_hits[0]
            if ch.auto_matched_city_id != city_id:
                async with async_session_factory() as s:
                    await s.execute(
                        update(CatalogChannel)
                        .where(CatalogChannel.id == ch.id)
                        .values(auto_matched_city_id=city_id)
                    )
                    await s.commit()
                single_tagged += 1
        else:
            # Multi-city → add ALL to channel_cities, set city_id=NULL
            async with async_session_factory() as s:
                # Remove old entries
                await s.execute(
                    delete(ChannelCity).where(ChannelCity.channel_id == ch.id)
                )
                # Insert all detected cities
                for city_id in unique_hits:
                    s.add(ChannelCity(channel_id=ch.id, city_id=city_id))
                # Set auto_matched_city_id to first detected city
                if ch.auto_matched_city_id != unique_hits[0]:
                    await s.execute(
                        update(CatalogChannel)
                        .where(CatalogChannel.id == ch.id)
                        .values(auto_matched_city_id=unique_hits[0])
                    )
                await s.commit()
            multi_tagged += 1
            print(f"  Multi: @{ch.chat_username} → {unique_hits} cities")

    print(f"\nChannels skipped (already tagged): {skipped_existing}")
    print(f"Channels processed: {channels_processed}")
    print(f"Single-city tagged: {single_tagged}")
    print(f"Multi-city (channel_cities): {multi_tagged}")


if __name__ == "__main__":
    asyncio.run(main())
