"""Insert @mill_sofi's private TravelAsk groups into watched_chats with geo-mapping.

Usage: docker compose exec worker python tools/insert_sofi_groups.py
"""
import asyncio
import os
import sys
import re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from telethon import TelegramClient
from telethon.tl.types import PeerChannel, InputPeerChannel
from sqlalchemy import select, text
from app.config import settings
from app.db.session import async_session_factory
from app.db.models import WatchedChat, Country, City

SESSIONS_DIR = "/app/sessions"

# ── Country emoji mapping (from group titles like "Черногория 🇲🇪 TravelAsk") ──
EMOJI_TO_COUNTRY = {
    "🇻🇳": "vn",
    "🇪🇬": "eg",
    "🇨🇳": "cn",
    "🇬🇪": "ge",
    "🇮🇩": "id",
    "🇱🇰": "lk",
    "🇰🇿": "kz",
    "🇪🇸": "es",
    "🇮🇱": "il",
    "🇩🇪": "de",
    "🇨🇾": "cy",
    "🇦🇲": "am",
    "🇲🇪": "me",
    "🇰🇭": "kh",
    "🇭🇰": "hk",
    "🇶🇦": "qa",
    "🇮🇳": "in",
    "🇹🇷": "tr",
    "🇹🇭": "th",
    "🇦🇪": "ae",
}

# ── City name → slug mapping (Russian names from group titles) ──
CITY_NAME_RU_TO_SLUG = {
    "Нячанг": "nha-trang",
    "Дананг": "da-nang",
    "Фукуок": "phu-quoc",
    "Хошимин": "ho-chi-minh",
    "Ханой": "ha-noi",
    "Далат": "da-lat",
    "Хургада": "hurgada",
    "Шарм-Эль-Шейх": "sharm-el-sheikh",
    "Дахаб": "dahab",
    "Макади Бей": "makadi-bay",
    "Александрия": "alexandria",
    "Каир": "cairo",
    "Шанхай": "shanghai",
    "Хайнань": "hainan",
    "Гуанчжоу": "guangzhou",
    "Пекин": "beijing",
    "Тбилиси": "tbilisi",
    "Батуми": "batumi",
    "Кутаиси": "kutaisi",
    "Мцхета": "mtskheta",
    "Гудаури": "gudauri",
    "Бали": "bali",
    "Ломбок": "lombok",
    "Чангу": "changu",
    "Джакарта": "jakarta",
    "Убуд": "ubud",
    "Букит": "bukit",
    "Санур": "sanur",
    "Мумбаи": "mumbai",
    "Керала": "kerala",
    "Гоа": "goa",
    "Нью-Дели": "new-delhi",
    "Гималаи": "himalayas",
    "Арамболь": "arambol",
    "Бангалор": "bangalore",
    "Унаватуна": "unawatuna",
    "Коломбо": "colombo",
    "Хиккадува": "hikkaduwa",
    "Бентота": "bentota",
    "Галле": "galle",
    "Астана": "astana",
    "Актау": "aktau",
    "Алматы": "almaty",
    "Костанай": "kostanay",
    "Актобе": "aktobe",
    "Шымкент": "shymkent",
    "Барселона": "barcelona",
    "Тенерифе": "tenerife",
    "Мадрид": "madrid",
    "Хайфа": "haifa",
    "Тель-Авив": "tel-aviv",
    "Эйлат": "eilat",
    "Мюнхен": "munich",
    "Дюссельдорф": "dusseldorf",
    "Берлин": "berlin",
    "Ереван": "yerevan",
    "Подгорица": "podgorica",
    "Гонконг": "hong-kong",
    "Катар": "qatar",
    "Камбоджа": "cambodia",
}


async def get_or_create_watched(
    session, user_id: int, chat_username: str, title: str,
    country_id: int | None, city_id: int | None,
) -> bool:
    """Insert if not exists. Returns True if inserted, False if skipped."""
    existing = await session.execute(
        select(WatchedChat).where(
            WatchedChat.user_id == user_id,
            WatchedChat.chat_username == chat_username,
        )
    )
    if existing.scalar_one_or_none():
        return False

    session.add(WatchedChat(
        user_id=user_id,
        chat_username=chat_username,
        source="manual",
        title=title,
        is_private=True,
        status="approved",
        country_id=country_id,
        city_id=city_id,
    ))
    return True


def extract_country_city(title: str) -> tuple[str | None, str | None]:
    """Parse country emoji and city name from group title.

    Examples:
        "Нячанг 🇻🇳 Чат TravelAsk" → ("vn", "nha-trang")
        "Черногория 🇲🇪 TravelAsk" → ("me", None)  # country-level group
        "Тбилиси — обмен денег, карты, крипта. Чат TravelAsk" → ("ge", "tbilisi")
        "Грузия. Авто — легализация, покупка, права 🇬🇪 Чат TravelAsk" → ("ge", None)
    """
    country_slug = None
    city_slug = None

    # Find country emoji
    for emoji, slug in EMOJI_TO_COUNTRY.items():
        if emoji in title:
            country_slug = slug
            break

    # Find city name (check before dash/em dash)
    title_clean = re.sub(r'[—–-].*', '', title).strip()
    title_clean = re.sub(r'\s*[🇦-🇿]{2,}\s*', ' ', title_clean).strip()

    for name_ru, slug in CITY_NAME_RU_TO_SLUG.items():
        if name_ru.lower() in title_clean.lower():
            city_slug = slug
            break

    # If no emoji found, try keyword-based country detection
    if not country_slug:
        keyword_to_country = {
            "грузия": "ge", "армения": "am", "израиль": "il",
            "индия": "in", "индонезия": "id", "вьетнам": "vn",
            "черногория": "me", "казахстан": "kz", "испания": "es",
            "германия": "de", "кипр": "cy", "египет": "eg",
            "шри": "lk", "китай": "cn", "гонконг": "hk",
        }
        title_lower = title.lower()
        for kw, slug in keyword_to_country.items():
            if kw in title_lower:
                country_slug = slug
                break

    return country_slug, city_slug


async def main():
    # ── Step 1: get groups from @mill_sofi ──
    api_id, api_hash, phone = settings.get_userbot_creds(2)
    client = TelegramClient('/tmp/userbot2_copy', api_id, api_hash)
    await client.start(phone=phone or None)
    me = await client.get_me()
    print(f"Connected: @{me.username}")

    groups = []
    async for dialog in client.iter_dialogs():
        entity = dialog.entity
        is_group = getattr(entity, 'megagroup', False) or (
            getattr(entity, 'broadcast', False) and not getattr(entity, 'username', None)
        )
        if not is_group:
            continue

        username = getattr(entity, 'username', None) or ''
        title = getattr(entity, 'title', '')
        entity_id = getattr(entity, 'id', 0)

        # For groups without username, use negative peer ID as identifier
        if username:
            chat_username = username
        else:
            chat_username = f"-100{entity_id}"

        # Verify we can resolve this group
        try:
            if chat_username.startswith("-"):
                peer = await client.get_input_entity(PeerChannel(entity_id))
            else:
                peer = await client.get_input_entity(username)
        except Exception as e:
            print(f"  SKIP {title}: can't resolve — {e}")
            continue

        groups.append({
            "chat_username": chat_username,
            "title": title,
            "entity_id": entity_id,
        })

    await client.disconnect()
    print(f"Found {len(groups)} groups\n")

    # ── Step 2: load country/city lookup from DB ──
    country_map = {}  # slug → id
    city_map = {}     # slug → (id, country_id)
    async with async_session_factory() as session:
        countries = await session.execute(select(Country.slug, Country.id))
        for slug, cid in countries.all():
            country_map[slug] = cid

        cities = await session.execute(
            select(City.slug, City.id, City.country_id)
        )
        for slug, cid, country_id in cities.all():
            city_map[slug] = (cid, country_id)

    print(f"DB: {len(country_map)} countries, {len(city_map)} cities\n")

    # ── Step 3: Map groups to countries/cities and resolve IDs ──
    # Get the owner user_id
    owner_tg_id = settings.owner_telegram_id
    async with async_session_factory() as session:
        user_result = await session.execute(
            text("SELECT id FROM users WHERE telegram_id = :tid"),
            {"tid": owner_tg_id},
        )
        user_row = user_result.fetchone()
        if not user_row:
            # Create user record for owner if missing
            from app.db.models import User
            user = User(
                telegram_id=owner_tg_id,
                username="leadhunterai",
                language="ru",
                plan="business",
            )
            session.add(user)
            await session.flush()
            user_id = user.id
            print(f"Created user record for owner (id={user_id})")
        else:
            user_id = user_row[0]
            print(f"Owner user_id={user_id}")

    # ── Step 4: Insert groups ──
    inserted = 0
    skipped = 0
    no_geo = 0
    by_country = {}

    async with async_session_factory() as session:
        for g in groups:
            country_slug, city_slug = extract_country_city(g["title"])

            country_id = country_map.get(country_slug) if country_slug else None
            city_id = None
            if city_slug and city_slug in city_map:
                city_id = city_map[city_slug][0]

            if not country_id:
                print(f"  NO GEO: {g['title']}")
                no_geo += 1
                # Still insert — will be tiered as legacy watched (warm/cold)
                country_id = None

            inserted_flag = await get_or_create_watched(
                session, user_id, g["chat_username"], g["title"],
                country_id, city_id,
            )
            if inserted_flag:
                inserted += 1
                by_country[country_slug or "no_geo"] = by_country.get(country_slug or "no_geo", 0) + 1
                geo = f"{country_slug}"
                if city_slug:
                    geo += f"/{city_slug}"
                print(f"  + [{geo}] {g['title']}")
            else:
                skipped += 1

        await session.commit()

    print(f"\n--- Done: {inserted} inserted, {skipped} skipped, {no_geo} without geo ---")
    print("By country:")
    for slug, count in sorted(by_country.items(), key=lambda x: -x[1]):
        print(f"  {slug}: {count}")


if __name__ == "__main__":
    asyncio.run(main())
