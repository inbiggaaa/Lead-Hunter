"""Telethon-based channel poller v2 — incremental, tiered, batched.

Key improvements over v1:
- Incremental: uses Redis cursor (min_id) — only fetches new messages
- Tiered: Hot (60s) / Warm (5min) / Cold (15min) based on demand
- Batched: asyncio.gather up to 50 channels per parallel batch
- Scales: N userbot accounts with per-account channel assignment
"""

import asyncio
import logging
import time

from telethon.errors import FloodWaitError
from telethon.tl.types import Message

from app.userbot.classifier import classify_message, _has_demand_signal, _match_keyword
from app.userbot.pool import UserbotPool
from app.userbot.rate_limiter import limiter
from app.db.session import async_session_factory
from app.db.models import SegmentKeyword, Segment
from sqlalchemy import select

logger = logging.getLogger(__name__)

# ── Tier configuration ──
# Intervals scale with number of accounts to avoid API abuse
HOT_INTERVAL = 60       # seconds — channels in active-subscription countries
WARM_INTERVAL = 300     # 5 minutes — channels > 1000 participants
COLD_INTERVAL = 900     # 15 minutes — everything else
PARALLEL_BATCH = 3       # channels per asyncio.gather batch (1 account)
# With 3 rps: 195 hot channels = ~65 sec initial sync, then incremental (fast)
INITIAL_HOT_LIMIT = 5
INITIAL_COLD_LIMIT = 2
BATCH_PAUSE = 0.3        # seconds between batches

# ── Cursor Redis keys ──
CURSOR_PREFIX = "cursor:msg:"


class ChannelPoller:
    """Polls Telegram channels using a pool of userbot accounts.

    v2 features:
    - Incremental polling via Redis message-id cursors
    - Tiered scheduling (Hot/Warm/Cold)
    - Parallel batched API calls
    """

    def __init__(self):
        self.pool = UserbotPool()
        self._keyword_map: dict[str, dict[str, list[str]]] = {}
        self._universal_stops: list[str] = []
        self._channel_segments: dict[str, list[str]] = {}
        self._active_countries: set[int] = set()  # country IDs with subscribers
        # Per-tier channel lists — rebuilt on keyword reload and periodically
        self._hot_channels: list[dict] = []
        self._warm_channels: list[dict] = []
        self._cold_channels: list[dict] = []

    # ═══════════════ INIT ═══════════════

    async def start(self):
        """Initialize pool, load keywords, build tier lists. Idempotent."""
        if not self.pool.accounts:
            await self.pool.initialize()
        if not self._keyword_map:
            self._keyword_map, self._universal_stops = await self._load_keywords()
            await self._load_channel_segments()
            await self._rebuild_tiers()

    async def _rebuild_tiers(self):
        """Recompute channel tiers: Hot/Warm/Cold based on active subscriptions."""
        self._active_countries = await self._get_active_countries()
        channels = await self._get_all_channels()

        hot, warm, cold = [], [], []
        for ch in channels:
            country_id = ch.get("country_id")
            participants = ch.get("participants", 0) or 0
            is_active_country = country_id in self._active_countries

            if is_active_country:
                hot.append(ch)
            elif participants >= 1000:
                warm.append(ch)
            else:
                cold.append(ch)

        self._hot_channels = hot
        self._warm_channels = warm
        self._cold_channels = cold

        logger.info(
            "Tiers rebuilt: %d hot (active countries), %d warm (≥1K), %d cold (rest). "
            "Active countries: %s",
            len(hot), len(warm), len(cold),
            sorted(self._active_countries) if len(self._active_countries) < 20
            else f"{len(self._active_countries)} countries",
        )

    async def _get_active_countries(self) -> set[int]:
        """Return country IDs that have at least one active user subscription."""
        try:
            from app.db.models import UserSubscription
            async with async_session_factory() as session:
                result = await session.execute(
                    select(UserSubscription.country_id).distinct()
                )
                return {row[0] for row in result.all()}
        except Exception:
            return set()

    async def _get_all_channels(self) -> list[dict]:
        """Return all channels with country_id and participant count."""
        from app.db.models import CatalogChannel, WatchedChat
        try:
            async with async_session_factory() as session:
                cat_result = await session.execute(
                    select(
                        CatalogChannel.chat_username,
                        CatalogChannel.auto_matched_country_id,
                        CatalogChannel.participants,
                    )
                )
                watched_result = await session.execute(
                    select(WatchedChat.chat_username).where(
                        WatchedChat.status == "approved"
                    ).distinct()
                )

                seen = set()
                channels = []
                for row in cat_result.all():
                    channels.append({
                        "chat_username": row[0],
                        "country_id": row[1],
                        "participants": row[2],
                    })
                    seen.add(row[0])
                for row in watched_result.all():
                    username = row[0]
                    if username not in seen:
                        channels.append({
                            "chat_username": username,
                            "country_id": None,
                            "participants": None,
                        })
                        seen.add(username)
                return channels
        except Exception as e:
            logger.warning("Failed to load channels: %s", e)
            return []

    # ═══════════════ CURSOR MANAGEMENT ═══════════════

    @staticmethod
    async def _get_cursor(chat_username: str) -> int:
        """Get last processed message_id for a channel (0 if new)."""
        try:
            from app.cache import get_redis
            redis = await get_redis()
            val = await redis.get(f"{CURSOR_PREFIX}{chat_username}")
            await redis.close()
            return int(val) if val else 0
        except Exception:
            return 0

    @staticmethod
    async def _set_cursor(chat_username: str, msg_id: int) -> None:
        """Update cursor to the latest processed message_id."""
        try:
            from app.cache import get_redis
            redis = await get_redis()
            await redis.set(f"{CURSOR_PREFIX}{chat_username}", str(msg_id))
            # TTL: 30 days — stale cursors auto-clean
            await redis.expire(f"{CURSOR_PREFIX}{chat_username}", 30 * 86400)
            await redis.close()
        except Exception:
            pass

    # ═══════════════ CHANNEL POLLING ═══════════════

    async def _poll_channel(
        self, account, channel_username: str, initial: bool = False, limit: int = 3,
    ) -> None:
        """Poll a single channel: get new messages since cursor, classify, dispatch.

        Args:
            account: UserbotAccount to use
            channel_username: @username of the channel
            initial: True on first-ever poll (get last N messages, set cursor)
            limit: max messages to fetch (higher for initial catch-up)
        """
        try:
            await limiter.acquire()
            entity = await account.get_entity(channel_username)
        except FloodWaitError:
            raise
        except Exception:
            return

        cursor = await self._get_cursor(channel_username) if not initial else 0

        await limiter.acquire()
        try:
            if cursor > 0:
                messages = await account.get_messages(entity, min_id=cursor, limit=limit)
            else:
                messages = await account.get_messages(entity, limit=limit)
        except FloodWaitError:
            raise
        except Exception:
            return  # Channel became inaccessible

        if not messages:
            return

        # Update channel title (async, best-effort)
        new_title = getattr(entity, "title", None)
        if new_title:
            asyncio.create_task(_update_channel_title(channel_username, new_title))

        # Process messages OLDEST-FIRST so cursor advances correctly
        # get_messages returns newest-first, so iterate reversed
        max_msg_id = cursor
        for msg in reversed(messages):
            if not isinstance(msg, Message) or not msg.message:
                continue

            msg_id = msg.id
            if msg_id > max_msg_id:
                max_msg_id = msg_id

            result = classify_message(msg.message, self._keyword_map, self._universal_stops)

            # Channel pre-tagging boost
            channel_segs = self._channel_segments.get(channel_username, [])
            if channel_segs and not result.matched_segments:
                if _has_demand_signal(msg.message):
                    result = result._replace(matched_segments=channel_segs)
            elif channel_segs and result.matched_segments:
                extra = [s for s in channel_segs if s not in result.matched_segments]
                if extra:
                    result = result._replace(
                        matched_segments=result.matched_segments + extra
                    )

            if result.matched_segments:
                urgency = "🔥 " if result.is_urgent else ""
                logger.info(
                    "%s[Acc %d] Match in @%s (msg %d): segments=%s",
                    urgency, account.account_id, channel_username, msg_id,
                    result.matched_segments,
                )
                await self._dispatch(
                    chat_username=channel_username,
                    message_text=msg.message,
                    message_id=msg_id,
                    matched_segments=result.matched_segments,
                    is_urgent=result.is_urgent,
                    sender=getattr(msg.sender, "username", None) if msg.sender else None,
                )
            else:
                await self._log_unmatched(channel_username, msg.message, msg_id)

        # Update cursor to latest processed message
        if max_msg_id > cursor:
            await self._set_cursor(channel_username, max_msg_id)

    # ═══════════════ BATCH & TIER LOOPS ═══════════════

    async def _poll_batch(
        self, account, channels: list[dict], initial: bool = False,
    ) -> tuple[int, int]:
        """Poll a batch of channels in parallel. Returns (ok_count, error_count)."""
        if not channels:
            return 0, 0

        # Check circuit breaker before starting batch
        await limiter.wait_if_circuit_open()

        limit = 3 if not initial else INITIAL_HOT_LIMIT

        async def _poll_one(ch: dict) -> bool:
            """Poll one channel, return True on success."""
            try:
                await self._poll_channel(
                    account, ch["chat_username"].strip().lstrip("@"),
                    initial=initial, limit=limit,
                )
                return True
            except FloodWaitError as e:
                logger.warning(
                    "FloodWait for account %d: %ds — pausing batch",
                    account.account_id, e.seconds,
                )
                await limiter.report_flood_wait(
                    e.seconds, context=f"poller:@{ch['chat_username']}"
                )
                await asyncio.sleep(e.seconds)
                return False
            except Exception as e:
                logger.debug("Poll error @%s: %s", ch.get('chat_username', '?'), e)
                return False

        ok, errors = 0, 0
        for i in range(0, len(channels), PARALLEL_BATCH):
            batch = channels[i:i + PARALLEL_BATCH]
            results = await asyncio.gather(*[_poll_one(ch) for ch in batch])
            ok += sum(1 for r in results if r)
            errors += sum(1 for r in results if not r)
            # Small breath between batches to avoid rate-limit buildup
            await asyncio.sleep(BATCH_PAUSE)

        return ok, errors

    async def _run_tier_loop(
        self, tier_name: str, channels: list[dict], interval: int,
    ):
        """Run a continuous loop polling a specific tier every `interval` seconds."""
        logger.info("Tier '%s' loop started: %d channels, every %ds", tier_name, len(channels), interval)

        # First run: initial catch-up (get last N messages, set cursors)
        initial = True

        while True:
            start = time.time()

            # Distribute channels across healthy accounts
            account_chunks = self._distribute(channels)

            for account, chunk in account_chunks:
                if not account.is_healthy:
                    continue
                limit_tag = f"(initial, limit={INITIAL_HOT_LIMIT})" if initial else "(incremental)"
                ok, err = await self._poll_batch(account, chunk, initial=initial)
                elapsed = time.time() - start
                if ok + err > 0:
                    logger.info(
                        "%s tier: %d ok, %d errors in %.1fs %s",
                        tier_name, ok, err, elapsed, limit_tag,
                    )

            initial = False  # After first pass, switch to incremental

            # Sleep until next interval
            elapsed = time.time() - start
            await asyncio.sleep(max(0, interval - elapsed))

    def _distribute(self, channels: list[dict]) -> list[tuple]:
        """Distribute channels across healthy accounts evenly."""
        healthy = [a for a in self.pool.accounts if a.is_healthy]
        if not healthy:
            return []

        chunks = []
        n = len(healthy)
        for i, acc in enumerate(healthy):
            chunk = channels[i::n]  # Every n-th channel to this account
            chunks.append((acc, chunk))
        return chunks

    # ═══════════════ MAIN LOOP ═══════════════

    async def run_forever(self):
        """Main entry point: start tiers, health checks, periodic rebuilds."""
        await self.start()

        # Start health check in background
        asyncio.create_task(self.pool.health_check_loop())

        WEEK = 7 * 24 * 3600
        TIER_REBUILD = 3600  # Rebuild tiers every hour
        _last_reload = time.time()
        _last_tier_rebuild = time.time()

        # Launch all three tier loops in parallel
        await asyncio.gather(
            self._run_tier_loop("Hot", self._hot_channels, HOT_INTERVAL),
            self._run_tier_loop("Warm", self._warm_channels, WARM_INTERVAL),
            self._run_tier_loop("Cold", self._cold_channels, COLD_INTERVAL),
            self._maintenance_loop(WEEK, TIER_REBUILD, _last_reload, _last_tier_rebuild),
        )

    async def _maintenance_loop(
        self, keyword_reload_interval: int, tier_rebuild_interval: int,
        last_reload: float, last_tier_rebuild: float,
    ):
        """Periodic maintenance: reload keywords, rebuild tiers."""
        while True:
            now = time.time()

            if now - last_reload > keyword_reload_interval:
                try:
                    self._keyword_map, self._universal_stops = await self._load_keywords()
                    await self._load_channel_segments()
                    last_reload = now
                except Exception as e:
                    logger.warning("Keyword reload failed, using cached: %s", e)

            if now - last_tier_rebuild > tier_rebuild_interval:
                try:
                    await self._rebuild_tiers()
                    last_tier_rebuild = now
                except Exception as e:
                    logger.warning("Tier rebuild failed: %s", e)

            await asyncio.sleep(300)  # Check every 5 minutes

    # ═══════════════ DISPATCH ═══════════════

    async def _dispatch(
        self, chat_username, message_text, message_id,
        matched_segments, is_urgent, sender,
    ):
        """Find interested users matching BOTH segment AND geo, push to queue."""
        from app.cache.subscription_cache import (
            get_interested_users, push_notification, build_message_hash,
            rebuild_subscription_cache,
        )
        from app.db.models import CatalogChannel, Segment
        from sqlalchemy import select as sa_select

        message_hash = build_message_hash(chat_username, message_id)
        users = await get_interested_users(chat_username)

        if not users:
            await rebuild_subscription_cache(chat_username)
            users = await get_interested_users(chat_username)

        async with async_session_factory() as session:
            ch = (await session.execute(
                sa_select(CatalogChannel).where(
                    CatalogChannel.chat_username == chat_username
                )
            )).scalar_one_or_none()
        channel_country_id = ch.auto_matched_country_id if ch else None
        channel_city_id = ch.auto_matched_city_id if ch else None

        async with async_session_factory() as session:
            segs = (await session.execute(sa_select(Segment))).scalars().all()
        seg_by_slug = {s.slug: s.id for s in segs}
        matched_segment_ids = {seg_by_slug.get(s) for s in matched_segments}
        matched_segment_ids.discard(None)

        for user in users:
            subscriptions = user.get("subscriptions", [])
            personal_kws = user.get("keyword_texts", [])

            interested = False
            for sub in subscriptions:
                if sub["country_id"] != channel_country_id:
                    continue
                if sub.get("city_ids") and channel_city_id:
                    if channel_city_id not in sub["city_ids"]:
                        continue
                if sub["segment_id"] in matched_segment_ids:
                    interested = True
                    break

            if not interested:
                for sub in subscriptions:
                    if sub["country_id"] != channel_country_id:
                        continue
                    if sub.get("city_ids") and channel_city_id:
                        if channel_city_id not in sub["city_ids"]:
                            continue
                    if personal_kws and any(
                        kw.lower() in message_text.lower() for kw in personal_kws
                    ):
                        interested = True
                        break

            if not interested:
                continue

            await push_notification({
                "user_id": user["user_id"],
                "telegram_id": user["telegram_id"],
                "lang": user.get("lang", "ru"),
                "plan": user.get("plan", "free"),
                "chat_username": chat_username,
                "text": message_text,
                "sender": sender,
                "message_id": message_id,
                "message_hash": message_hash,
                "is_urgent": is_urgent,
            })

    # ═══════════════ KEYWORD LOADING ═══════════════

    async def _load_keywords(self) -> tuple[dict[str, dict[str, list[str]]], list[str]]:
        """Load all segment keywords from DB into memory."""
        async with async_session_factory() as session:
            result = await session.execute(
                select(SegmentKeyword).where(SegmentKeyword.is_active == True)
            )
            keywords = result.scalars().all()

        async with async_session_factory() as session:
            seg_result = await session.execute(select(Segment))
            segments = {s.id: s.slug for s in seg_result.scalars().all()}

        keyword_map: dict[str, dict[str, list[str]]] = {}
        universal_stops: list[str] = []
        for kw in keywords:
            if kw.segment_id is None:
                if kw.keyword_type == "stop":
                    universal_stops.append(kw.text)
                continue
            slug = segments.get(kw.segment_id)
            if not slug:
                continue
            if slug not in keyword_map:
                keyword_map[slug] = {"demand": [], "stop": [], "synonym": []}
            keyword_map[slug][kw.keyword_type].append(kw.text)

        logger.info(
            "Loaded %d keywords across %d segments, %d universal stops",
            len(keywords), len(keyword_map), len(universal_stops),
        )
        return keyword_map, universal_stops

    async def _load_channel_segments(self) -> None:
        """Pre-tag channels with segments based on their titles."""
        try:
            from app.db.models import CatalogChannel

            async with async_session_factory() as session:
                channels = (await session.execute(
                    select(CatalogChannel.chat_username, CatalogChannel.title)
                )).all()

            self._channel_segments.clear()
            tagged = 0
            for chat_username, title in channels:
                if not title:
                    continue
                title_lower = title.lower()
                matched_segs = []
                for slug, kws_by_type in self._keyword_map.items():
                    all_kws = (
                        kws_by_type.get("demand", [])
                        + kws_by_type.get("synonym", [])
                    )
                    for kw in all_kws:
                        if _match_keyword(kw, title_lower):
                            matched_segs.append(slug)
                            break
                if matched_segs:
                    self._channel_segments[chat_username] = matched_segs
                    tagged += 1

            logger.info("Pre-tagged %d channels with segments from titles", tagged)
        except Exception as e:
            logger.warning("Channel segment pre-tagging failed: %s", e)

    # ═══════════════ LOGGING ═══════════════

    @staticmethod
    async def _log_unmatched(chat_username: str, text: str, msg_id: int) -> None:
        """Log unmatched messages to Redis (deduplicated, last 10000)."""
        try:
            from app.cache.subscription_cache import build_message_hash
            from app.cache import get_redis

            redis = await get_redis()
            msg_hash = build_message_hash(chat_username, msg_id)
            if await redis.sadd("stats:unmatched:seen", msg_hash) == 0:
                await redis.close()
                return
            await redis.expire("stats:unmatched:seen", 7 * 86400)

            import json
            from datetime import datetime, timezone

            entry = json.dumps({
                "ts": datetime.now(timezone.utc).isoformat(),
                "chat": chat_username,
                "msg_id": msg_id,
                "text": text[:500],
            }, ensure_ascii=False)
            await redis.lpush("stats:unmatched", entry)
            await redis.ltrim("stats:unmatched", 0, 9999)
            await redis.close()
        except Exception:
            pass


# ── Module-level helpers ──

async def _update_channel_title(chat_username: str, new_title: str) -> None:
    """Update channel title in DB if it changed. Best-effort, never raises."""
    try:
        from app.db.session import async_session_factory
        from app.db.models import CatalogChannel
        from sqlalchemy import select, update

        async with async_session_factory() as session:
            ch = (await session.execute(
                select(CatalogChannel.title).where(
                    CatalogChannel.chat_username == chat_username
                )
            )).scalar_one_or_none()
            if ch and ch != new_title:
                await session.execute(
                    update(CatalogChannel)
                    .where(CatalogChannel.chat_username == chat_username)
                    .values(title=new_title)
                )
                await session.commit()
    except Exception:
        pass
