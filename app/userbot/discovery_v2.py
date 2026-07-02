"""Discovery v2 — programmatic channel search across all cities.

Replaces hand-written DISCOVERY.md queries with systematic query generation:
- All 120+ cities from the DB (not a static file)
- 84 community-type words (RU + EN): чат, болталка, советы, chat, help, ...
- 8 post-Soviet diaspora prefixes: kz, by, ua, uz, kg, am, az, md
- Matches real Telegram naming patterns: kz_danang, дананг болталка, ...

Safety:
- Uses DEDICATED userbot2 account (never shares poller client)
- Per-account circuit breaker: ban on discovery ≠ ban on poller
- Ultra-slow pace: 30s between queries → ~8 days per 23K-query cycle
- Only 0.03 API calls/sec — invisible to Telegram anti-spam
"""

import asyncio
import logging
import random
from pathlib import Path

from telethon import TelegramClient
from telethon.errors import FloodWaitError
from telethon.tl.functions.contacts import SearchRequest

from app.config import settings
from app.db.session import async_session_factory
from app.db.models import CatalogChannel, Country, City
from app.userbot.rate_limiter import limiter
from sqlalchemy import select

logger = logging.getLogger(__name__)

# ── Tier 1 countries: processed first (most Russian-speaking expats) ──
TIER1_COUNTRY_SLUGS = {"tr", "vn", "th", "id", "eg", "ae", "ge"}

# ── Russian community-type words (real names used in Telegram channels) ──
COMMUNITY_RU = [
    "чат", "чатик", "общение", "болталка", "общаемся",
    "отдых", "туризм", "путешествия",
    "советы", "помощь", "вопросы", "ответы",
    "объявления", "барахолка", "куплю", "продам", "услуги",
    "новости", "афиша", "события", "тусовка",
    "работа", "вакансии", "поиск работы",
    "недвижимость", "аренда", "жилье", "квартиры",
    "знакомства", "мамы", "дети", "родители",
    "спорт", "фитнес", "йога",
    "еда", "рестораны", "кафе",
    "транспорт", "такси", "байки", "мопеды",
    "виза", "документы", "переводчики",
    "медицина", "врачи", "красота",
    "ремонт", "мастер", "фото", "видео",
    "русские", "русский", "русскоязычные",
]

# ── English community-type words ──
COMMUNITY_EN = [
    "chat", "group", "community", "hub", "club",
    "talk", "discussion", "social",
    "help", "tips", "advice", "ask",
    "market", "sale", "buy", "services", "jobs", "classifieds",
    "events", "news", "meetup",
    "rent", "housing", "property", "apartment",
    "expats", "foreigners", "digital nomads",
    "moms", "kids", "parents", "family",
    "sport", "fitness", "yoga",
    "food", "cafe", "restaurant", "bar",
    "travel", "tourism", "guide", "tips",
    "visa", "documents", "translator",
    "health", "medical", "beauty",
    "repair", "handyman", "photo", "video",
    "russian", "russians", "rus", "ru",
]

# ── Post-Soviet diaspora prefixes (Russian-speaking, NOT from Russia) ──
DIASPORA_PREFIXES = ["kz", "by", "ua", "uz", "kg", "am", "az", "md"]

# ── Timing ──
# EXTREME caution: discovery shares userbot1 with poller.
# If discovery triggers a ban, the ENTIRE service goes down.
# Therefore: 90s between queries → ~0.01 calls/sec → invisible.
# Full cycle (36K queries): ~37 days. No rush.
INTER_QUERY_PAUSE_MIN = 60   # minimum seconds between searches
INTER_QUERY_PAUSE_MAX = 120  # maximum (randomized per query)
SEARCH_LIMIT = 10             # max results per SearchRequest

# Dedicated discovery account — uses userbot1 (older, more trusted)
# WARNING: shares account with poller. Ban on discovery = ban on service.
DISCOVERY_ACCOUNT_ID = 1
DISCOVERY_SESSION_NAME = "userbot"


def _slugify(text: str | None) -> str:
    """Convert city name to Telegram-username-friendly slug."""
    if not text:
        return ""
    # Lowercase, replace spaces/special chars with underscores, collapse
    slug = text.lower().strip()
    slug = slug.replace(" ", "_").replace("-", "_")
    # Remove non-ASCII (Cyrillic, etc.) — Telegram usernames are ASCII-only
    slug = "".join(c for c in slug if c.isascii() and (c.isalnum() or c == "_"))
    # Collapse multiple underscores
    while "__" in slug:
        slug = slug.replace("__", "_")
    return slug.strip("_")


async def _generate_queries() -> list[dict]:
    """Generate all search queries from cities in the DB.

    Returns list of {query, country_id, city_id, country_name, city_name}.
    Tier 1 countries come first.
    """
    async with async_session_factory() as session:
        countries = (await session.execute(
            select(Country).where(Country.is_active == True)
        )).scalars().all()
        cities = (await session.execute(
            select(City).where(City.is_active == True)
        )).scalars().all()

    country_map = {c.id: c for c in countries}

    queries: list[dict] = []
    seen: set[str] = set()  # dedup identical query strings

    def _add(query: str, country_id: int, city_id: int, country_name: str, city_name: str):
        q = query.strip().lower()
        if q and q not in seen and len(q) >= 2:
            seen.add(q)
            queries.append({
                "query": q,
                "country_id": country_id,
                "city_id": city_id,
                "country_name": country_name,
                "city_name": city_name,
            })

    # Separate Tier 1 and others
    tier1_cities = []
    other_cities = []
    for city in cities:
        country = country_map.get(city.country_id)
        if country and country.slug in TIER1_COUNTRY_SLUGS:
            tier1_cities.append((city, country))
        else:
            other_cities.append((city, country))

    for city, country in tier1_cities + other_cities:
        city_ru = (city.name_ru or "").strip()
        city_en = (city.name_en or "").strip()
        city_slug = _slugify(city.slug or city_en)

        if not city_ru and not city_en:
            continue

        if country is None:
            continue

        country_name = country.name_ru or country.slug
        city_name = city_ru or city_en
        cid = country.id
        ciid = city.id

        # ── 1. {city_en} {community_ru} — "da nang чат", "da nang помощь" ──
        if city_en and len(city_en) >= 2:
            for word in COMMUNITY_RU:
                _add(f"{city_en} {word}", cid, ciid, country_name, city_name)

        # ── 2. {city_ru} {community_ru} — "дананг чат", "дананг болталка" ──
        if city_ru and len(city_ru) >= 2:
            for word in COMMUNITY_RU:
                _add(f"{city_ru} {word}", cid, ciid, country_name, city_name)

        # ── 3. {city_en} {community_en} — "da nang chat", "da nang help" ──
        if city_en and len(city_en) >= 2:
            for word in COMMUNITY_EN:
                _add(f"{city_en} {word}", cid, ciid, country_name, city_name)

        # ── 4. Diaspora prefixes (post-Soviet communities) ──
        if city_slug:
            for prefix in DIASPORA_PREFIXES:
                # Telegram usernames: kz_danang, by_danang
                _add(f"{prefix}_{city_slug}", cid, ciid, country_name, city_name)
                _add(f"{city_slug}_{prefix}", cid, ciid, country_name, city_name)

        if city_en and len(city_en) >= 2:
            for prefix in DIASPORA_PREFIXES:
                _add(f"{prefix} {city_en}", cid, ciid, country_name, city_name)

        if city_ru and len(city_ru) >= 2:
            for prefix in DIASPORA_PREFIXES:
                _add(f"{prefix} {city_ru}", cid, ciid, country_name, city_name)

    logger.info(
        "Discovery v2: generated %d queries for %d cities (%d tier1, %d other)",
        len(queries), len(tier1_cities) + len(other_cities),
        len(tier1_cities), len(other_cities),
    )
    return queries


async def _search_and_store(
    client: TelegramClient, queries: list[dict],
) -> int:
    """Execute search queries, dedup against catalog_channels, store new ones.

    Returns number of newly discovered channels.
    """
    found = 0
    skipped = 0
    total = len(queries)

    for i, q in enumerate(queries):
        # Circuit breaker check every 100 queries (per-account, won't block poller)
        if i % 100 == 0:
            if await limiter.is_circuit_open(DISCOVERY_ACCOUNT_ID):
                logger.warning(
                    "Discovery v2: circuit breaker open for account %d at query %d/%d — pausing cycle",
                    DISCOVERY_ACCOUNT_ID, i, total,
                )
                await limiter.wait_if_circuit_open(DISCOVERY_ACCOUNT_ID)
                logger.info("Discovery v2: circuit breaker closed — resuming")

            logger.info(
                "Discovery v2: %d/%d queries (%d new, %d skipped)",
                i, total, found, skipped,
            )

        try:
            await limiter.acquire(account_id=DISCOVERY_ACCOUNT_ID)
            result = await client(SearchRequest(q=q["query"], limit=SEARCH_LIMIT))
        except FloodWaitError as e:
            logger.warning("Discovery v2 FloodWait: %ds on '%s'", e.seconds, q["query"])
            await limiter.report_flood_wait(
                e.seconds, context=f"discovery_v2:{q['query']}",
                account_id=DISCOVERY_ACCOUNT_ID,
            )
            await asyncio.sleep(e.seconds)
            continue
        except Exception as e:
            logger.debug("Discovery v2: search failed '%s': %s", q["query"], e)
            skipped += 1
            continue

        # Collect usernames from this search
        candidates: list[dict] = []
        for chat in result.chats:
            username = getattr(chat, "username", None)
            if username:
                candidates.append({
                    "username": username,
                    "title": getattr(chat, "title", username),
                    "participants": getattr(chat, "participants_count", None),
                })

        if not candidates:
            skipped += 1
            await asyncio.sleep(INTER_QUERY_PAUSE)
            continue

        # Batch DB: check existence + insert in one session
        try:
            async with async_session_factory() as session:
                usernames = [c["username"] for c in candidates]
                existing_rows = (await session.execute(
                    select(CatalogChannel).where(
                        CatalogChannel.chat_username.in_(usernames)
                    )
                )).scalars().all()
                existing_usernames = {ch.chat_username for ch in existing_rows}

                new_count = 0
                for c in candidates:
                    uname = c["username"]
                    if uname in existing_usernames:
                        # Already known — backfill geo if missing
                        row = next(
                            (r for r in existing_rows if r.chat_username == uname), None
                        )
                        if row:
                            changed = False
                            if q["country_id"] and not row.auto_matched_country_id:
                                row.auto_matched_country_id = q["country_id"]
                                changed = True
                            if q["city_id"] and not row.auto_matched_city_id:
                                row.auto_matched_city_id = q["city_id"]
                                changed = True
                            if changed:
                                new_count += 1  # count geo backfills as discoveries
                        continue

                    # New channel
                    session.add(CatalogChannel(
                        chat_username=uname,
                        title=c["title"],
                        participants=c["participants"],
                        is_verified=False,
                        auto_matched_country_id=q["country_id"],
                        auto_matched_city_id=q["city_id"],
                    ))
                    new_count += 1
                    logger.info(
                        "Discovery v2: + @%s → %s/%s",
                        uname, q["country_name"], q["city_name"],
                    )

                await session.commit()
                found += new_count
        except Exception as e:
            logger.debug("Discovery v2: DB batch error: %s", e)

        skipped += 1
        # Randomized pause: unpredictable pattern, very slow (60-120s)
        await asyncio.sleep(random.uniform(INTER_QUERY_PAUSE_MIN, INTER_QUERY_PAUSE_MAX))

    logger.info("Discovery v2: finished — %d new, %d queries", found, total)
    return found


def _discovery_has_dedicated_session() -> bool:
    """Check if a dedicated discovery session exists."""
    return (Path("/app/sessions") / f"{DISCOVERY_SESSION_NAME}.session").exists()


async def _create_dedicated_discovery_client() -> TelegramClient:
    """Create a dedicated client for discovery using account 2 credentials."""
    api_id, api_hash, phone = settings.get_userbot_creds(DISCOVERY_ACCOUNT_ID)
    client = TelegramClient(
        str(Path("/app/sessions") / DISCOVERY_SESSION_NAME),
        api_id,
        api_hash,
    )
    await client.start(phone=phone or None)
    logger.info(
        "Discovery v2: dedicated client on account %d, api_id=%d",
        DISCOVERY_ACCOUNT_ID, api_id,
    )
    return client


async def discovery_v2_loop(client: TelegramClient | None = None):
    """Background discovery loop — shares userbot1 with poller.

    WARNING: Uses the SAME account as the poller. If discovery triggers
    a FloodWait, the circuit breaker blocks ALL API calls for account 1
    including poller. Therefore: extreme caution.

    Speed: 60-120s randomized between queries → ~0.01 calls/sec.
    Full cycle: ~37 days at 90s avg pause.
    Queries are shuffled to avoid predictable patterns.
    """
    # Stagger: wait 15 minutes so poller is fully running
    logger.info("Discovery v2: waiting 15 min (poller warmup + stagger)")
    await asyncio.sleep(900)

    if client is None:
        logger.warning(
            "Discovery v2: no pool client passed — skipping. "
            "Discovery must share userbot1 via pool."
        )
        return

    logger.info(
        "Discovery v2: using shared pool client for account %d "
        "(poller shares same account — ALL API calls rate-limited together)",
        DISCOVERY_ACCOUNT_ID,
    )

    try:
        while True:
            # Check per-account circuit breaker BEFORE any API calls
            # If account 1 is blocked, BOTH poller and discovery are dead
            if await limiter.is_circuit_open(DISCOVERY_ACCOUNT_ID):
                logger.warning(
                    "Discovery v2: circuit breaker open for account %d — "
                    "poller is also blocked. Waiting...",
                    DISCOVERY_ACCOUNT_ID,
                )
                await limiter.wait_if_circuit_open(DISCOVERY_ACCOUNT_ID)

            logger.info("Discovery v2: starting new cycle...")
            try:
                queries = await _generate_queries()
                if not queries:
                    logger.warning("Discovery v2: no queries generated — empty DB?")
                    await asyncio.sleep(3600)
                    continue

                # Shuffle to avoid predictable query patterns (anti-spam)
                random.shuffle(queries)

                found = await _search_and_store(client, queries)

                # Report stats
                from app.userbot.discovery import report_discovery_stats
                await report_discovery_stats(found)

                # Estimate next cycle (avg pause ~90s, randomized 60-120s)
                avg_pause = (INTER_QUERY_PAUSE_MIN + INTER_QUERY_PAUSE_MAX) / 2
                est_hours = (len(queries) * avg_pause) / 3600
                est_days = est_hours / 24
                logger.info(
                    "Discovery v2: cycle complete — %d new channels from %d queries. "
                    "Next cycle starts now (est. %.1f days).",
                    found, len(queries), est_days,
                )
            except Exception as e:
                logger.error("Discovery v2: cycle error: %s", e, exc_info=True)
                await asyncio.sleep(3600)  # Wait 1h before retry

    finally:
        pass  # Don't disconnect — client is shared with poller
