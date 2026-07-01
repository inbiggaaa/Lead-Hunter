"""Auto-discovery: search for new channels with geo-matching."""

import asyncio
import logging
import random
import re
from pathlib import Path

from telethon import TelegramClient
from telethon.errors import FloodWaitError

from app.config import settings
from app.db.session import async_session_factory
from app.db.models import CatalogChannel, Country, City
from app.userbot.rate_limiter import limiter
from sqlalchemy import select

logger = logging.getLogger(__name__)

DISCOVERY_PATH = Path("/app/DISCOVERY.md")

# Country flag → slug mapping (from DISCOVERY.md ## headers)
FLAG_TO_SLUG = {
    "🇹🇷": "tr", "🇻🇳": "vn", "🇹🇭": "th", "🇮🇩": "id", "🇪🇬": "eg",
    "🇦🇪": "ae", "🇬🇪": "ge", "🇪🇸": "es", "🇲🇪": "me", "🇵🇹": "pt",
    "🇱🇰": "lk", "🇧🇷": "br", "🇲🇽": "mx", "🇮🇳": "in", "🇦🇷": "ar",
    "🇨🇴": "co", "🇨🇱": "cl", "🇵🇪": "pe", "🇨🇷": "cr", "🇵🇦": "pa",
    "🇩🇴": "do", "🇨🇺": "cu", "🇵🇭": "ph", "🇲🇾": "my", "🇰🇷": "kr",
    "🇯🇵": "jp", "🇨🇳": "cn", "🇿🇦": "za", "🇰🇪": "ke",
    "🇲🇻": "mv", "🇳🇵": "np", "🇧🇩": "bd", "🇵🇰": "pk",
    "🇲🇲": "mm", "🇰🇭": "kh", "🇱🇦": "la", "🇲🇳": "mn",
    "🇶🇦": "qa", "🇰🇼": "kw", "🇴🇲": "om", "🇧🇭": "bh",
    "🇸🇦": "sa", "🇯🇴": "jo", "🇱🇧": "lb", "🇮🇱": "il",
    "🇩🇪": "de", "🇫🇷": "fr", "🇮🇹": "it", "🇬🇧": "gb",
    "🇦🇹": "at", "🇨🇭": "ch", "🇧🇪": "be", "🇳🇱": "nl",
    "🇸🇪": "se", "🇳🇴": "no", "🇫🇮": "fi", "🇩🇰": "dk",
    "🇮🇪": "ie", "🇬🇷": "gr", "🇨🇾": "cy", "🇧🇬": "bg",
    "🇭🇷": "hr", "🇷🇸": "rs", "🇦🇱": "al", "🇸🇮": "si",
    "🇸🇰": "sk", "🇨🇿": "cz", "🇵🇱": "pl", "🇭🇺": "hu",
    "🇷🇴": "ro", "🇱🇹": "lt", "🇱🇻": "lv", "🇪🇪": "ee",
    "🇺🇦": "ua", "🇧🇾": "by", "🇲🇩": "md", "🇷🇺": "ru",
    "🇦🇲": "am", "🇦🇿": "az", "🇰🇿": "kz", "🇺🇿": "uz", "🇰🇬": "kg",
    "🇺🇸": "us", "🇨🇦": "ca",
    "🇦🇺": "au", "🇳🇿": "nz",
    "🇲🇦": "ma", "🇹🇳": "tn",
}


async def parse_geo_queries() -> dict:
    """Parse DISCOVERY.md into {country_slug: {country_name, cities: {city_name: [queries]}}}."""
    if not DISCOVERY_PATH.exists():
        return {}

    text = DISCOVERY_PATH.read_text(encoding="utf-8")
    result = {}
    current_country = None
    current_city = None

    for line in text.split("\n"):
        # Country header: ## 🇹🇷 Турция
        if line.startswith("## "):
            for flag, slug in FLAG_TO_SLUG.items():
                if flag in line:
                    name = line.replace("## ", "").replace(flag, "").strip()
                    current_country = slug
                    if slug not in result:
                        result[slug] = {"name": name, "cities": {}}
                    current_city = None
                    break

        # City header: | Стамбул | Istanbul | ...
        elif line.startswith("| ") and "|" in line[2:] and current_country:
            parts = [p.strip() for p in line.split("|")[1:-1]]
            if len(parts) >= 4 and parts[3]:
                city_name = parts[0]  # Russian name
                queries_raw = parts[3]
                queries = [q.strip() for q in queries_raw.replace("`", "").split(",")]
                if city_name not in result[current_country]["cities"]:
                    result[current_country]["cities"][city_name] = []
                result[current_country]["cities"][city_name].extend(queries)

    logger.info("Parsed %d countries from DISCOVERY.md", len(result))
    return result


async def search_channels(client: TelegramClient, geo_queries: dict, limit: int = 10):
    """Search for channels with geo context, auto-assigning country/city."""
    # Load country/city ID maps from DB
    async with async_session_factory() as session:
        countries = (await session.execute(select(Country))).scalars().all()
        country_by_slug = {c.slug: c for c in countries}
        cities = (await session.execute(select(City))).scalars().all()
        city_by_name: dict[str, list[City]] = {}
        for c in cities:
            key = (c.name_ru or "").lower()
            if key not in city_by_name:
                city_by_name[key] = []
            city_by_name[key].append(c)

    found = 0
    for country_slug, data in geo_queries.items():
        country = country_by_slug.get(country_slug)
        for city_name, queries in data["cities"].items():
            city = None
            # Match city by name
            for c in (city_by_name.get(city_name.lower(), []) or []):
                if c.country_id == country.id if country else True:
                    city = c
                    break

            for query in queries:
                try:
                    # Hard Rule #1: limiter before every API call
                    await limiter.acquire()
                    from telethon.tl.functions.contacts import SearchRequest
                    result = await client(SearchRequest(q=query, limit=limit))
                    for chat in result.chats:
                        username = getattr(chat, "username", None)
                        if not username:
                            continue

                        async with async_session_factory() as session:
                            existing = (await session.execute(
                                select(CatalogChannel).where(CatalogChannel.chat_username == username)
                            )).scalar_one_or_none()
                            if existing:
                                continue

                            title = getattr(chat, "title", username)
                            participants = getattr(chat, "participants_count", None)

                            session.add(CatalogChannel(
                                chat_username=username, title=title,
                                participants=participants, is_verified=False,
                                auto_matched_country_id=country.id if country else None,
                                auto_matched_city_id=city.id if city else None,
                            ))
                            await session.commit()
                            found += 1
                            logger.info("Discovered: @%s → %s/%s", username,
                                       country.name_ru if country else "?",
                                       city.name_ru if city else "?")

                    # Brief pause between searches (rate limiter handles minimum interval)
                    await asyncio.sleep(1.5)

                except FloodWaitError as e:
                    logger.warning("Discovery FloodWait: %ds", e.seconds)
                    # Hard Rule #7: open circuit breaker, don't just sleep locally
                    await limiter.report_flood_wait(e.seconds, context="discovery:search", account_id=0)
                except Exception as e:
                    logger.warning("Search failed '%s': %s", query, e)

    logger.info("Discovery: %d new channels", found)
    return found

async def report_discovery_stats(new_found: int):
    """Send discovery stats to admin."""
    from app.db.session import async_session_factory
    from app.db.models import CatalogChannel, DiscoveredChat
    from sqlalchemy import func, select as sa_sel

    async with async_session_factory() as s:
        total = (await s.execute(sa_sel(func.count(CatalogChannel.id)))).scalar() or 0
        with_geo = (await s.execute(
            sa_sel(func.count(CatalogChannel.id)).where(CatalogChannel.auto_matched_country_id.isnot(None))
        )).scalar() or 0

    from app.worker.notify_admin import notify_admin
    await notify_admin(
        f"📊 Отчёт поиска каналов\n\n"
        f"Найдено новых: {new_found}\n"
        f"Всего в каталоге: {total}\n"
        f"С гео-привязкой: {with_geo}"
    )


async def notify_new_trial(username: str, telegram_id: int, source: str):
    from app.worker.notify_admin import notify_admin
    name = f"@{username}" if username else f"ID:{telegram_id}"
    await notify_admin(f"🆕 Новый пользователь!\n\n👤 {name}\n🎁 Триал (5 дн Business)\n📡 {source}")


async def notify_new_subscription(username: str, telegram_id: int, plan: str, period: str, source: str, amount: float = 0):
    from app.worker.notify_admin import notify_admin
    name = f"@{username}" if username else f"ID:{telegram_id}"
    period_labels = {"1m": "1 мес", "3m": "3 мес", "1y": "1 год"}
    await notify_admin(
        f"💰 Новая оплата!\n\n👤 {name}\n📋 {plan.title()}\n"
        f"📅 {period_labels.get(period, period)}\n💵 ${amount:.0f}\n📡 {source}"
    )


def _discovery_has_dedicated_account() -> bool:
    """Check if a dedicated discovery account (userbot2) session exists."""
    return (Path("/app/sessions") / "userbot2.session").exists()


async def _create_dedicated_client() -> TelegramClient:
    """Create a dedicated client for discovery using account 2 credentials."""
    api_id, api_hash, phone = settings.get_userbot_creds(2)
    client = TelegramClient(
        str(Path("/app/sessions/userbot2")),
        api_id,
        api_hash,
    )
    await client.start(phone=phone or None)
    logger.info("Discovery using dedicated session 'userbot2' (api_id=%d)", api_id)
    return client


async def discovery_loop(client: TelegramClient | None = None):
    """Background discovery loop.

    If a dedicated account 2 session exists, creates its own client.
    Otherwise, uses the client passed from the pool (shared with poller).
    """
    # Stagger startup: wait 10 minutes so poller establishes a calm rhythm first
    await asyncio.sleep(600)
    geo = await parse_geo_queries()
    if not geo:
        return

    own_client = None
    if client is None:
        if _discovery_has_dedicated_account():
            client = await _create_dedicated_client()
            own_client = client
        else:
            logger.warning("Discovery: no dedicated account and no client passed — skipping")
            return
    else:
        logger.info("Discovery using shared pool client (api_id from pool)")
        # Check if ALL accounts are blocked — if so, skip this cycle
        if await limiter.is_any_circuit_open():
            logger.info("Discovery: at least one account blocked, skipping cycle")
            return
        logger.info("Starting geo-aware discovery...")
        found = 0
        try:
            found = await search_channels(client, geo)
        except FloodWaitError as e:
            logger.warning("Discovery FloodWait: %ds", e.seconds)
            # Hard Rule #7: report to circuit breaker system (account unknown, use 0)
            await limiter.report_flood_wait(e.seconds, context="discovery:loop", account_id=0)
        await report_discovery_stats(found)
        await asyncio.sleep(86400)  # 24 hours — enough for 195 queries × ~5.5 min
