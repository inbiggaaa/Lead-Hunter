"""Import channels from SEED.md into catalog_channels table."""

import asyncio
import re
import sys
from pathlib import Path

from sqlalchemy import select

from app.db.session import async_session_factory
from app.db.models import Country, City, CatalogChannel

SEED_PATH = Path("/app/SEED.md")


async def import_channels():
    if not SEED_PATH.exists():
        print(f"ERROR: {SEED_PATH} not found")
        return

    text = SEED_PATH.read_text(encoding="utf-8")

    # Parse structure: ## Country → ### City → | @username | desc |
    country_pattern = re.compile(r"^## (.+?)(?:\s*\(\d+\s*(?:канала|каналов)?\))?$", re.MULTILINE)
    city_pattern = re.compile(r"^### (.+?)(?:\s*\(\d+\))?$", re.MULTILINE)
    channel_pattern = re.compile(r"^\| @(\w+) \| (.+?) \|$", re.MULTILINE)

    # Country name mapping: normalized → slug
    # Based on SEED.md structure
    country_map = {
        "Турция": "tr", "Вьетнам": "vn", "Индонезия": "id", "Таиланд": "th",
        "ОАЭ": "ae", "Грузия": "ge", "Казахстан": "kz", "Киргизия": "kg",
        "Узбекистан": "uz", "Азербайджан": "az", "Армения": "am",
        "Беларусь": "by", "Сербия": "rs", "Черногория": "me",
        "Германия": "de", "Испания": "es", "Италия": "it", "Франция": "fr",
        "Португалия": "pt", "Нидерланды": "nl", "Греция": "gr",
        "Кипр": "cy", "Болгария": "bg", "Румыния": "ro", "Хорватия": "hr",
        "Чехия": "cz", "Польша": "pl", "Венгрия": "hu",
        "Великобритания": "gb", "Ирландия": "ie", "Швеция": "se",
        "Норвегия": "no", "Финляндия": "fi", "Дания": "dk",
        "США": "us", "Канада": "ca", "Мексика": "mx",
        "Бразилия": "br", "Аргентина": "ar", "Колумбия": "co",
        "Египет": "eg", "Марокко": "ma", "Тунис": "tn",
        "Индия": "in", "Китай": "cn", "Япония": "jp", "Корея": "kr",
        "Филиппины": "ph", "Малайзия": "my", "Сингапур": "sg",
        "Австралия": "au", "Новая Зеландия": "nz",
        "Израиль": "il", "Ливан": "lb",
        "ЮАР": "za", "Кения": "ke",
        "Бали": "id",  # Бали → Индонезия
        "Шри-Ланка": "lk", "Непал": "np", "Мальдивы": "mv",
        "Камбоджа": "kh", "Лаос": "la", "Мьянма": "mm",
        "Монголия": "mn", "Пакистан": "pk", "Бангладеш": "bd",
        "Чили": "cl", "Перу": "pe", "Эквадор": "ec",
        "Коста-Рика": "cr", "Панама": "pa", "Доминикана": "do", "Куба": "cu",
        "Катар": "qa", "Кувейт": "kw", "Бахрейн": "bh", "Оман": "om",
        "Саудовская Аравия": "sa", "Иордания": "jo",
        "Швейцария": "ch", "Австрия": "at", "Бельгия": "be",
        "Литва": "lt", "Латвия": "lv", "Эстония": "ee",
        "Словакия": "sk", "Словения": "si",
        "Албания": "al", "Македония": "mk", "Босния": "ba",
        "Молдова": "md", "Украина": "ua",
    }

    # City name mapping: normalized → slug
    city_map = {
        # Turkey
        "Стамбул": "istanbul", "Анталья": "antalya", "Аланья": "alanya",
        "Бодрум": "bodrum", "Фетхие": "fethiye", "Измир": "izmir",
        "Мерсин": "mersin", "Кемер": "kemer", "Мармарис": "marmaris",
        "Анкара": "ankara", "Бурса": "bursa", "Трабзон": "trabzon",
        "Кушадасы": "kusadasi", "Белек": "belek", "Сиде": "side",
        "Каппадокия": "cappadocia", "Олюдениз": "oludeniz", "Самсун": "samsun",
        "Газиантеп": "gaziantep", "Диярбакыр": "diyarbakir",
        "Конья": "konya", "Кайсери": "kayseri",
        # Vietnam
        "Нячанг": "nha-trang", "Дананг": "da-nang", "Фукуок": "phu-quoc",
        "Хошимин": "ho-chi-minh", "Ханой": "hanoi", "Муйне": "mui-ne",
        "Далат": "da-lat",
        # Indonesia / Bali
        "Бали": "bali", "Джакарта": "jakarta", "Ломбок": "lombok",
        # Thailand
        "Бангкок": "bangkok", "Пхукет": "phuket", "Паттайя": "pattaya",
        "Самуи": "koh-samui", "Чиангмай": "chiang-mai", "Краби": "krabi",
        "Хуахин": "hua-hin",
        # UAE
        "Дубай": "dubai", "Абу-Даби": "abu-dhabi", "Шарджа": "sharjah",
        "Рас-эль-Хайма": "ras-al-khaimah",
        # Georgia
        "Тбилиси": "tbilisi", "Батуми": "batumi", "Кутаиси": "kutaisi",
        # Armenia
        "Ереван": "yerevan",
        # Kazakhstan
        "Алматы": "almaty", "Астана": "astana",
        # Russia
        "Москва": "moscow", "Санкт-Петербург": "spb", "Сочи": "sochi",
    }

    # Helper: find or create country
    async def get_or_create_country(session, name_ru: str, slug: str) -> Country:
        result = await session.execute(select(Country).where(Country.slug == slug))
        c = result.scalar_one_or_none()
        if c is None:
            c = Country(slug=slug, name_ru=name_ru, name_en=name_ru)
            session.add(c)
            await session.flush()
        return c

    # Helper: find or create city
    async def get_or_create_city(session, name_ru: str, slug: str, country_id: int) -> City:
        result = await session.execute(select(City).where(City.slug == slug))
        c = result.scalar_one_or_none()
        if c is None:
            c = City(slug=slug, name_ru=name_ru, name_en=name_ru, country_id=country_id)
            session.add(c)
            await session.flush()
        return c

    async with async_session_factory() as session:
        current_country = None
        current_city = None
        imported = 0
        skipped = 0

        for line in text.split("\n"):
            line = line.strip()

            # Country header: ## Турция (107 каналов)
            cm = country_pattern.match(line)
            if cm:
                name = cm.group(1).strip()
                slug = country_map.get(name, name.lower().replace(" ", "-"))
                current_country = await get_or_create_country(session, name, slug)
                # Reset city when country changes
                current_city = None
                continue

            # City header: ### Istanbul (10)
            cm2 = city_pattern.match(line)
            if cm2:
                name = cm2.group(1).strip()
                slug = city_map.get(name, name.lower().replace(" ", "-"))
                if current_country:
                    current_city = await get_or_create_city(session, name, slug, current_country.id)
                continue

            # Channel: | @username | description |
            cm3 = channel_pattern.match(line)
            if cm3:
                username = cm3.group(1).strip().lower()
                description = cm3.group(2).strip()

                # Check if already exists
                existing = await session.execute(
                    select(CatalogChannel).where(CatalogChannel.chat_username == username)
                )
                if existing.scalar_one_or_none():
                    skipped += 1
                    continue

                channel = CatalogChannel(
                    chat_username=username,
                    title=description[:200] if description else username,
                    is_verified=True,
                )
                if current_country:
                    channel.auto_matched_country_id = current_country.id
                if current_city:
                    channel.auto_matched_city_id = current_city.id

                session.add(channel)
                imported += 1

                # Commit every 100 channels
                if imported % 100 == 0:
                    await session.commit()
                    print(f"  Imported {imported} channels...")

        await session.commit()
        print(f"\n✅ Done! Imported: {imported}, Skipped (duplicates): {skipped}")


if __name__ == "__main__":
    asyncio.run(import_channels())
