"""Discovery v3 — autonomous background channel search with full poller isolation.

Key improvements over v2:
- Separate TelegramRateLimiter + circuit breaker (does NOT share with poller)
- Redis cursor for progress (survives restart)
- Human-like pauses (time-of-day aware, random breaks, jitter)
- Daily budget (configurable, default 500)
- Metrics in Redis + throttled admin notifications
- Manual/test mode without dedicated account (polls only when poller inactive)

Management (no bot commands):
- ENV: DISCOVERY_ENABLED=true        → enable at container start
- Redis: SET discovery:pause 1      → pause without restart
- Redis: DEL discovery:pause        → resume
"""

import asyncio
import logging
import random
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

from telethon import TelegramClient
from telethon.errors import FloodWaitError
from telethon.tl.functions.contacts import SearchRequest

from app.config import settings
from app.db.session import async_session_factory
from app.db.models import CatalogChannel, Country, City
from app.userbot.rate_limiter import TelegramRateLimiter
from app.cache import get_redis
from sqlalchemy import select

logger = logging.getLogger(__name__)

# ── Query generation (kept from v2) ──

TIER1_COUNTRY_SLUGS = {"tr", "vn", "th", "id", "eg", "ae", "ge", "ph", "in", "cn", "lk", "es", "it", "me", "cy", "north-cyprus", "kz", "ar", "am", "fr", "kr"}

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
    "куплю-продам",
    "соседи", "жильцы", "новостройка",
    "мамочки",
    "туса", "движ", "наши",
]

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

DIASPORA_PREFIXES = ["kz", "by", "ua", "uz", "kg", "am", "az", "md"]

SEARCH_LIMIT = 10


def _slugify(text: str | None) -> str:
    """Convert city name to Telegram-username-friendly slug."""
    if not text:
        return ""
    slug = text.lower().strip()
    slug = slug.replace(" ", "_").replace("-", "_")
    slug = "".join(c for c in slug if c.isascii() and (c.isalnum() or c == "_"))
    while "__" in slug:
        slug = slug.replace("__", "_")
    return slug.strip("_")


async def _generate_queries() -> list[dict]:
    """Generate all search queries from cities in the DB."""
    async with async_session_factory() as session:
        countries = (await session.execute(
            select(Country).where(Country.is_active == True)
        )).scalars().all()
        cities = (await session.execute(
            select(City).where(City.is_active == True)
        )).scalars().all()

    country_map = {c.id: c for c in countries}
    queries: list[dict] = []
    seen: set[str] = set()

    def _add(query: str, country_id: int, city_id: int, country_name: str, city_name: str):
        q = query.strip().lower()
        if q and q not in seen and len(q) >= 2:
            seen.add(q)
            queries.append({
                "query": q, "country_id": country_id, "city_id": city_id,
                "country_name": country_name, "city_name": city_name,
            })

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

        if city_en and len(city_en) >= 2:
            for word in COMMUNITY_RU:
                _add(f"{city_en} {word}", cid, ciid, country_name, city_name)
        if city_ru and len(city_ru) >= 2:
            for word in COMMUNITY_RU:
                _add(f"{city_ru} {word}", cid, ciid, country_name, city_name)
        if city_en and len(city_en) >= 2:
            for word in COMMUNITY_EN:
                _add(f"{city_en} {word}", cid, ciid, country_name, city_name)
        if city_slug:
            for prefix in DIASPORA_PREFIXES:
                _add(f"{prefix}_{city_slug}", cid, ciid, country_name, city_name)
                _add(f"{city_slug}_{prefix}", cid, ciid, country_name, city_name)
        if city_en and len(city_en) >= 2:
            for prefix in DIASPORA_PREFIXES:
                _add(f"{prefix} {city_en}", cid, ciid, country_name, city_name)
        if city_ru and len(city_ru) >= 2:
            for prefix in DIASPORA_PREFIXES:
                _add(f"{prefix} {city_ru}", cid, ciid, country_name, city_name)

    logger.info("Discovery: generated %d queries for %d cities", len(queries), len(tier1_cities) + len(other_cities))
    return queries


# ── DiscoveryWorker ──

class DiscoveryWorker:
    """Autonomous discovery loop with full poller isolation.

    Uses a dedicated Telegram account (DISCOVERY_ACCOUNT_ID=3) with its own
    rate limiter and circuit breaker. Falls back to manual/test mode if the
    dedicated account is unavailable (polls only when poller is inactive).
    """

    def __init__(self):
        self._account_id = settings.discovery_account_id
        self._is_dedicated = (self._account_id == 3)
        self._daily_limit = (
            settings.discovery_daily_limit if self._is_dedicated
            else settings.discovery_manual_daily_limit
        )
        self._limiter = TelegramRateLimiter(
            min_interval=2.0,
            daily_budget=self._daily_limit,
        )
        self._client: TelegramClient | None = None
        self._stop_flag = False

    # ── Client setup ──

    async def _init_client(self) -> TelegramClient:
        """Create and start a dedicated Telethon client for discovery."""
        api_id, api_hash, phone = settings.get_userbot_creds(self._account_id)
        session_path = str(Path("/app/sessions") / f"{settings.discovery_session_name}.session")
        client = TelegramClient(
            session_path, api_id, api_hash,
            flood_sleep_threshold=settings.discovery_flood_sleep_threshold,
        )
        await client.start(phone=phone or None)
        me = await client.get_me()
        logger.info("Discovery: account %d authorised as @%s", self._account_id, me.username)
        return client

    # ── Pause helpers ──

    async def _is_paused(self) -> bool:
        """Check Redis pause flag."""
        try:
            redis = await get_redis()
            val = await redis.get("discovery:pause")
            await redis.aclose()
            return val == b"1"
        except Exception:
            return False

    async def _is_poller_active(self) -> bool:
        """Check if poller is currently polling (for manual mode)."""
        try:
            redis = await get_redis()
            state = await redis.get("session:state:1")
            await redis.aclose()
            return state and state.decode() == "ACTIVE"
        except Exception:
            return True  # assume active if can't check

    # ── Human-like pause ──

    def _get_pause_seconds(self) -> float:
        """Return pause duration based on simulated time-of-day patterns."""
        hour = datetime.now(timezone.utc).hour
        is_weekend = datetime.now(timezone.utc).weekday() >= 5

        if 2 <= hour < 5:
            base_min, base_max = 3600, 7200      # deep sleep: 1-2h
        elif 5 <= hour < 8:
            base_min, base_max = 1800, 3600      # early morning: 30-60m
        elif 8 <= hour < 20:
            base_min, base_max = 60, 180          # daytime: 1-3m
        else:
            base_min, base_max = 300, 900         # evening: 5-15m

        if is_weekend:
            base_min = int(base_min * 1.3)
            base_max = int(base_max * 1.3)

        if not self._is_dedicated:
            base_min = int(base_min * 2.5)
            base_max = int(base_max * 2.5)

        pause = random.uniform(base_min, base_max)
        pause *= random.uniform(0.8, 1.2)  # jitter ±20%
        return max(10.0, pause)

    # ── Progress cursor ──

    async def _load_cursor(self, queries_hash: str) -> int:
        """Restore saved query index, reset if query set changed."""
        redis = await get_redis()
        saved_hash = await redis.get("discovery:queries_hash")
        await redis.aclose()
        if saved_hash and saved_hash.decode() == queries_hash:
            redis = await get_redis()
            val = await redis.get("discovery:cursor:query_index")
            await redis.aclose()
            return int(val) if val else 0
        return 0  # queries changed — reset

    async def _save_cursor(self, index: int) -> None:
        """Save current query index to Redis."""
        try:
            redis = await get_redis()
            await redis.set("discovery:cursor:query_index", str(index))
            await redis.aclose()
        except Exception:
            pass

    # ── Metrics ──

    async def _incr_metric(self, name: str) -> None:
        """Increment a daily metric counter."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        try:
            redis = await get_redis()
            await redis.incr(f"discovery:metrics:{today}:{name}")
            await redis.expire(f"discovery:metrics:{today}:{name}", 7 * 86400)
            await redis.aclose()
        except Exception:
            pass

    # ── Throttled notifications ──

    async def _notify(self, text: str, alert_type: str) -> None:
        """Send admin notification with Redis-backed throttling (15 min cooldown)."""
        key = f"alert:last:discovery:{alert_type}"
        redis = await get_redis()
        last = await redis.get(key)
        now = time.time()
        if not last or (now - float(last)) >= 900:
            await redis.setex(key, 900, str(now))
            from app.worker.notify_admin import notify_admin
            await notify_admin(text)
        await redis.aclose()

    # ── Main loop ──

    async def run(self) -> None:
        """Main discovery loop. Blocks until stopped."""
        if not settings.discovery_enabled:
            logger.info("Discovery: disabled (DISCOVERY_ENABLED=false)")
            return

        # ── Init client ──
        try:
            self._client = await self._init_client()
        except Exception as e:
            logger.error("Discovery: failed to init client: %s", e)
            await self._notify(
                f"🔍 Discovery: не удалось запустить клиент — {e}",
                "startup_failed",
            )
            return

        if not self._is_dedicated:
            logger.warning(
                "Discovery: MANUAL/TEST MODE — account %d is not dedicated (expected #3). "
                "Will poll only when poller is inactive.",
                self._account_id,
            )
            await self._notify(
                f"⚠️ Discovery запущен в ручном режиме на аккаунте #{self._account_id}. "
                "Опрос только при неактивном пуллере.",
                "manual_mode",
            )
        else:
            await self._notify("🔍 Discovery: запущен (выделенный аккаунт #3)", "started")

        # ── Generate queries once, use cursor for progress ──
        queries = await _generate_queries()
        if not queries:
            logger.warning("Discovery: no queries generated")
            return

        random.shuffle(queries)
        import hashlib
        queries_hash = hashlib.md5(
            ",".join(q["query"] for q in queries[:100]).encode()
        ).hexdigest()

        cursor = await self._load_cursor(queries_hash)
        if cursor > 0:
            logger.info("Discovery: resuming from query %d/%d", cursor, len(queries))
        redis = await get_redis()
        await redis.set("discovery:queries_hash", queries_hash)
        await redis.aclose()

        consecutive_errors = 0
        consecutive_flood = 0
        query_count = 0

        try:
            idx = cursor
            while not self._stop_flag:
                # ── Check pause flag ──
                if await self._is_paused():
                    await asyncio.sleep(60)
                    continue

                # ── Manual mode: check poller ──
                if not self._is_dedicated and await self._is_poller_active():
                    await asyncio.sleep(random.uniform(300, 600))
                    continue

                # ── Check daily budget ──
                remaining = await self._limiter.budget_remaining(self._account_id)
                if remaining <= 0:
                    logger.info("Discovery: daily budget exhausted — sleeping 1h")
                    await self._notify(
                        f"🔍 Discovery: суточный лимит исчерпан ({self._daily_limit} запросов). "
                        "Ожидание следующих суток.",
                        "budget_exhausted",
                    )
                    await asyncio.sleep(3600)
                    continue

                # ── Wrap-around ──
                if idx >= len(queries):
                    idx = 0
                    logger.info("Discovery: full cycle complete — restarting")
                    await self._notify(
                        f"🔍 Discovery: полный цикл завершён ({len(queries)} запросов). "
                        f"Найдено каналов за цикл: {query_count}.",
                        "cycle_done",
                    )
                    query_count = 0

                q = queries[idx]

                # ── Circuit breaker check (per-account, isolated from poller) ──
                if await self._limiter.is_circuit_open(self._account_id):
                    logger.warning("Discovery: circuit breaker OPEN — sleeping 1h")
                    await self._notify(
                        "🔍 Discovery: circuit breaker OPEN — остановка на 1 час",
                        "cb_open",
                    )
                    await asyncio.sleep(3600)
                    continue

                # ── Rate limit + search ──
                try:
                    await self._limiter.acquire(account_id=self._account_id)
                    result = await self._client(SearchRequest(q=q["query"], limit=SEARCH_LIMIT))
                    consecutive_errors = 0
                    consecutive_flood = 0

                    # ── Process results ──
                    await self._store_results(result, q)
                    await self._incr_metric("requests")
                    query_count += 1

                    # ── Random long break (3% chance) ──
                    if random.random() < 0.03:
                        break_sec = random.uniform(600, 3600)
                        logger.debug("Discovery: taking a break for %.0fs", break_sec)
                        await asyncio.sleep(break_sec)

                except FloodWaitError as e:
                    consecutive_flood += 1
                    logger.warning("Discovery FloodWait: %ds on '%s'", e.seconds, q["query"])
                    await self._limiter.report_flood_wait(
                        e.seconds, context=f"discovery:{q['query']}",
                        account_id=self._account_id,
                    )
                    await self._incr_metric("floodwait")
                    if e.seconds > 3600:
                        await self._notify(
                            f"🚨 Discovery FloodWait {e.seconds // 3600}ч на '{q['query']}'",
                            "floodwait_long",
                        )
                    backoff = min(e.seconds * (2 ** (consecutive_flood - 1)), 86400)
                    await asyncio.sleep(backoff)
                    continue  # retry same query

                except Exception as e:
                    consecutive_errors += 1
                    logger.warning("Discovery: search failed '%s': %s", q["query"], type(e).__name__)
                    await self._incr_metric("errors")
                    if consecutive_errors >= 10:
                        logger.warning("Discovery: %d consecutive errors — long pause", consecutive_errors)
                        await asyncio.sleep(random.uniform(1800, 3600))
                        consecutive_errors = 0

                # ── Advance cursor + save progress ──
                idx += 1
                if idx % 10 == 0:
                    await self._save_cursor(idx)
                    if idx % 100 == 0:
                        logger.info(
                            "Discovery: %d/%d queries done, %d in this run",
                            idx, len(queries), query_count,
                        )

                # ── Human-like pause ──
                pause = self._get_pause_seconds()
                await asyncio.sleep(pause)

        except asyncio.CancelledError:
            logger.info("Discovery: cancelled — saving progress (idx=%d)", idx)
            await self._save_cursor(idx)
            raise
        finally:
            if self._client:
                await self._client.disconnect()
            logger.info("Discovery: stopped")

    async def _store_results(self, result, q: dict) -> None:
        """Store newly found channels in catalog_channels with geo-matching."""
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
            return

        try:
            async with async_session_factory() as session:
                usernames = [c["username"] for c in candidates]
                existing_rows = (await session.execute(
                    select(CatalogChannel).where(
                        CatalogChannel.chat_username.in_(usernames),
                        CatalogChannel.is_ignored == False,
                    )
                )).scalars().all()
                existing_usernames = {ch.chat_username for ch in existing_rows}

                new_count = 0
                for c in candidates:
                    uname = c["username"]
                    if uname in existing_usernames:
                        row = next((r for r in existing_rows if r.chat_username == uname), None)
                        if row:
                            changed = False
                            if q["country_id"] and not row.auto_matched_country_id:
                                row.auto_matched_country_id = q["country_id"]
                                changed = True
                            if q["city_id"] and not row.auto_matched_city_id:
                                row.auto_matched_city_id = q["city_id"]
                                changed = True
                            if changed:
                                new_count += 1
                        continue

                    session.add(CatalogChannel(
                        chat_username=uname, title=c["title"],
                        participants=c["participants"], is_verified=False,
                        auto_matched_country_id=q["country_id"],
                        auto_matched_city_id=q["city_id"],
                    ))
                    new_count += 1
                    logger.info("Discovery: + @%s → %s/%s", uname, q["country_name"], q["city_name"])

                await session.commit()
                if new_count:
                    await self._incr_metric("found")
                    await self._incr_metric("geo_linked")

        except Exception as e:
            logger.debug("Discovery: DB batch error: %s", e)
