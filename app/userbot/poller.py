"""Telethon-based channel poller v2 — incremental, tiered, sequential.

Key improvements over v1:
- Incremental: uses Redis cursor (min_id) — only fetches new messages
- Tiered: Hot (60s) / Warm (5min) / Cold (15min) based on demand
- Sequential: channels polled one-by-one with log-normal pauses (human-like)
- Scales: N userbot accounts with per-account channel assignment
"""

import asyncio
import logging
import random
import time
from datetime import datetime, timedelta, timezone

from telethon.errors import FloodWaitError, ChannelInvalidError
from telethon.tl.types import Message, InputPeerChannel

from app.userbot.classifier import classify_message, _has_demand_signal, _match_keyword
from app.userbot.pool import UserbotPool
from app.userbot.rate_limiter import limiter, BudgetExceeded
from app.config import settings
from app.cache import get_redis
from app.db.session import async_session_factory
from app.db.models import SegmentKeyword, Segment
from sqlalchemy import select

logger = logging.getLogger(__name__)

# ── Tier configuration ──
# Intervals scale with number of accounts to avoid API abuse
HOT_INTERVAL = 60       # seconds — channels in active-subscription countries
WARM_INTERVAL = 300     # 5 minutes — channels > 1000 participants
COLD_INTERVAL = 900     # 15 minutes — everything else
DORMANT_INTERVAL = 43200  # 12 hours — channels from countries with no subscriptions
# Tier-specific message fetch limits — per API call.
# Pagination auto-triggers if a full batch is returned (rare in practice).
TIER_LIMITS = {
    "Hot": 30,    # 60s cycle — 30 msgs/min is extremely active
    "Warm": 80,   # 5min cycle
    "Cold": 150,  # 15min cycle
    "Dormant": 500,  # 12h cycle — catch up on missed messages
}
MAX_PAGINATION_ROUNDS = 5  # absolute safety cap for pagination
INITIAL_LIMIT = 5           # first-ever poll: just set cursor (no pagination)

# ── Anti-ban protections ──
# Staggered startup: tiers don't fire all at once (prevents initial API storm)
HOT_STARTUP_DELAY = 0     # seconds — Hot starts immediately
WARM_STARTUP_DELAY = 60   # seconds — Warm waits 1 min
COLD_STARTUP_DELAY = 180  # seconds — Cold waits 3 min

# Channel warmup: gradual ramp-up to full load (prevents new-account detection)
# Each step = (channels per cycle as fraction of total)
WARMUP_STEPS = [0.08, 0.16, 0.25, 0.35, 0.50, 0.70, 1.0]  # 7 cycles to full speed

# Random jitter: adds unpredictability to polling pattern (±15%)
INTERVAL_JITTER = 0.15

# ── Cursor Redis keys ──
CURSOR_PREFIX = "cursor:msg:"


def next_delay() -> float:
    """Log-normal delay between channel polls — human-like rhythm.

    median ≈ e^0.7 ≈ 2.0s, range clamped to [0.8, 6.0]s.
    Heavy right tail prevents uniform-periodicity detection.
    """
    d = random.lognormvariate(0.7, 0.5)
    return min(max(d, 0.8), 6.0)


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
        self._dormant_channels: list[dict] = []
        self._parked_count: int = 0  # channels from inactive countries (not polled)
        # Per-account locks — prevent multiple tiers from polling same account simultaneously
        self._account_locks: dict[int, asyncio.Lock] = {}
        # Entity cache: {chat_username: {account_id: (channel_id, access_hash)}}
        # access_hash is per-account — avoids ResolveUsername on every poll cycle
        self._entity_cache: dict[str, dict[int, tuple[int, int]]] = {}

    # ═══════════════ INIT ═══════════════

    async def start(self):
        """Initialize pool, load keywords, build tier lists. Idempotent."""
        if not self.pool.accounts:
            await self.pool.initialize()

        # Log circuit breaker status for visibility after worker restart.
        # CB keys survive Redis restart (AOF from Task 0.6).
        # Actual blocking happens in _distribute() + _poll_batch() —
        # this log just makes the state visible at startup.
        for acc in self.pool.accounts:
            if await limiter.is_circuit_open(acc.account_id):
                from app.cache import get_redis
                redis = await get_redis()
                expires_raw = await redis.get(f"circuit:expires:{acc.account_id}")
                await redis.aclose()
                if expires_raw:
                    until_ts = int(expires_raw)
                    remaining = until_ts - int(time.time())
                    logger.warning(
                        "Account %d: circuit breaker OPEN — blocked for ~%ds (until %s UTC)",
                        acc.account_id, max(0, remaining),
                        time.strftime("%H:%M:%S", time.gmtime(until_ts)),
                    )
                else:
                    logger.warning("Account %d: circuit breaker OPEN", acc.account_id)
            else:
                logger.info("Account %d: circuit breaker clear — ready to poll", acc.account_id)
        if not self._keyword_map:
            self._keyword_map, self._universal_stops = await self._load_keywords()
            await self._load_channel_segments()
            await self._rebuild_tiers()
            await self._tag_new_channels()  # tag any new channels from discovery

    async def _rebuild_tiers(self):
        """Recompute channel tiers: Hot/Warm/Cold/Dormant based on subscriptions.

        - Active country (has subscriptions) → Hot (60s)
        - Watched channel (manual) → Warm/Cold by participants
        - Inactive country, catalog channel → Dormant (12h)
        """
        self._active_countries = await self._get_active_countries()
        channels = await self._get_all_channels()

        hot, warm, cold, dormant, parked = [], [], [], [], 0
        for ch in channels:
            country_id = ch.get("country_id")
            participants = ch.get("participants", 0) or 0
            is_active_country = country_id in self._active_countries
            is_watched = country_id is None  # manually added by user, always monitor

            if is_active_country:
                hot.append(ch)
            elif is_watched:
                # User explicitly monitors — keep in active tiers
                if participants >= 1000:
                    warm.append(ch)
                else:
                    cold.append(ch)
            elif settings.poll_parked_countries:
                # Legacy behaviour: poll inactive-country channels lazily
                dormant.append(ch)
            else:
                # Inactive country, catalog channel — skip entirely (parked)
                parked += 1

        self._hot_channels = hot
        self._warm_channels = warm
        self._cold_channels = cold
        self._dormant_channels = dormant
        self._parked_count = parked

        logger.info(
            "Tiers rebuilt: %d hot (active countries), %d warm (watched ≥1K), "
            "%d cold (watched <1K), %d dormant (inactive, 12h), "
            "%d parked (inactive countries, not polled). "
            "Active countries: %s",
            len(hot), len(warm), len(cold), len(dormant), parked,
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

    async def _resolve_entity(self, account, channel_username: str):
        """Return entity for channel_username — from cache or via ResolveUsername.

        Caches (channel_id, access_hash) per account since access_hash differs
        between accounts. On cache hit, constructs InputPeerChannel directly —
        no API call, no limiter.acquire().
        """
        per_account = self._entity_cache.setdefault(channel_username, {})
        cached = per_account.get(account.account_id)
        if cached is not None:
            return InputPeerChannel(*cached)

        # Cache miss — resolve once per account lifetime
        await limiter.acquire(account.account_id)
        entity = await account.get_entity(channel_username)
        per_account[account.account_id] = (entity.id, entity.access_hash)
        return entity

    async def _poll_channel(
        self, account, channel_username: str, tier_name: str, initial: bool = False,
    ) -> None:
        """Poll a single channel: get all new messages since cursor, classify, dispatch.

        Uses tier-specific limits with automatic pagination — if a batch returns
        exactly TIER_LIMITS[tier] messages, we keep fetching until caught up.
        Guarantees no message loss while adding API calls only for busy channels.

        Args:
            account: UserbotAccount to use
            channel_username: @username of the channel
            tier_name: "Hot" | "Warm" | "Cold" — picks TIER_LIMITS[tier]
            initial: True on first-ever poll (get last N messages, set cursor, no pagination)
        """
        try:
            entity = await self._resolve_entity(account, channel_username)
        except FloodWaitError:
            raise
        except Exception:
            return

        cursor = await self._get_cursor(channel_username) if not initial else 0

        # Fetch ALL messages since cursor, paginating if needed
        all_messages = await self._fetch_all_since(
            account, entity, channel_username, cursor,
            tier_limit=INITIAL_LIMIT if initial else TIER_LIMITS[tier_name],
            paginate=not initial,  # initial poll is just to set cursor
        )

        if not all_messages:
            return

        # Update channel title and participants (async, best-effort)
        new_title = getattr(entity, "title", None)
        new_participants = getattr(entity, "participants_count", None)
        if new_title or new_participants:
            asyncio.create_task(
                _update_channel_info(channel_username, new_title, new_participants)
            )

        # Process messages OLDEST-FIRST so cursor advances correctly
        # all_messages is accumulated newest-first, so iterate reversed
        max_msg_id = cursor
        for msg in reversed(all_messages):
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

    async def _fetch_all_since(
        self, account, entity, channel_username: str, cursor: int, tier_limit: int, paginate: bool = True,
    ) -> list:
        """Fetch all messages since `cursor`, paginating if a batch is full.

        When paginate=True and a batch returns exactly tier_limit messages,
        continues fetching older messages between cursor and the batch's
        oldest message until the gap is exhausted or MAX_PAGINATION_ROUNDS.

        Returns messages newest-first (same order as Telethon's get_messages).
        """
        all_messages = []
        fetch_min_id = cursor
        rounds = 0

        while rounds < (MAX_PAGINATION_ROUNDS if paginate else 1):
            await limiter.acquire(account.account_id)
            try:
                if fetch_min_id > 0 and rounds > 0:
                    # Pagination: narrow the window to messages between
                    # the original cursor and just below the oldest message
                    # we already fetched.
                    oldest_in_prev = min(m.id for m in all_messages)
                    batch = await account.get_messages(
                        entity,
                        min_id=cursor,
                        max_id=oldest_in_prev - 1,
                        limit=tier_limit,
                    )
                elif fetch_min_id > 0:
                    batch = await account.get_messages(
                        entity, min_id=fetch_min_id, limit=tier_limit,
                    )
                else:
                    batch = await account.get_messages(entity, limit=tier_limit)
            except FloodWaitError:
                raise
            except ChannelInvalidError:
                # access_hash is stale for this account — invalidate only this account's cache
                self._entity_cache.get(channel_username, {}).pop(account.account_id, None)
                raise
            except Exception:
                break  # Channel became inaccessible

            if not batch:
                break

            all_messages.extend(batch)
            rounds += 1

            if len(batch) < tier_limit:
                break  # got everything — partial batch means no more messages

            if not paginate:
                break

            # Full batch means there may be more older messages.
            # Next iteration will use max_id to fetch the gap.
            logger.debug(
                "@%s: full batch (%d msgs) — paginating round %d/%d",
                getattr(entity, 'username', '?'),
                len(batch), rounds, MAX_PAGINATION_ROUNDS,
            )

        if rounds > 1:
            logger.info(
                "@%s: paginated %d rounds, total %d messages fetched",
                getattr(entity, 'username', '?'), rounds, len(all_messages),
            )

        return all_messages

    # ═══════════════ BATCH & TIER LOOPS ═══════════════

    async def _poll_batch(
        self, account, channels: list[dict], tier_name: str, initial: bool = False,
    ) -> tuple[int, int]:
        """Poll channels sequentially with log-normal pauses — human-like rhythm.

        Channels are shuffled each cycle to break predictable order.
        Log-normal delay between channels (median ~2s) is the primary pacing;
        rate limiter (min_interval=1.5s) acts as a safety floor.
        """
        if not channels:
            return 0, 0

        # Check circuit breaker for this specific account before starting batch
        await limiter.wait_if_circuit_open(account.account_id)

        async def _poll_one(ch: dict) -> bool:
            """Poll one channel, return True on success."""
            try:
                await self._poll_channel(
                    account, ch["chat_username"].strip().lstrip("@"),
                    tier_name=tier_name, initial=initial,
                )
                return True
            except FloodWaitError as e:
                logger.warning(
                    "FloodWait for account %d: %ds — pausing batch",
                    account.account_id, e.seconds,
                )
                await limiter.report_flood_wait(
                    e.seconds, context=f"poller:@{ch['chat_username']}",
                    account_id=account.account_id,
                )
                await asyncio.sleep(e.seconds)
                return False
            except BudgetExceeded:
                logger.warning(
                    "Budget exceeded for account %d — stopping batch",
                    account.account_id,
                )
                from app.worker.notify_admin import notify_admin
                await notify_admin(
                    f"📊 Аккаунт #{account.account_id} исчерпал суточный бюджет "
                    f"API-запросов. Поллинг остановлен до следующих суток."
                )
                return False
            except Exception as e:
                logger.debug("Poll error @%s: %s", ch.get('chat_username', '?'), e)
                return False

        # Shuffle channel order to break predictable patterns
        shuffled = list(channels)
        random.shuffle(shuffled)

        ok, errors = 0, 0
        for i, ch in enumerate(shuffled):
            result = await _poll_one(ch)
            if result:
                ok += 1
            else:
                errors += 1
            # Log-normal pause between channels (skip after last)
            if i < len(shuffled) - 1:
                delay = next_delay()
                await asyncio.sleep(delay)

        return ok, errors

    async def _run_tier_loop(
        self, tier_name: str, channels: list[dict], interval: int,
        startup_delay: int = 0,
    ):
        """Continuous loop — thin wrapper around _run_tier_once + timing."""
        total_channels = len(channels)

        if startup_delay > 0:
            logger.info(
                "Tier '%s': staggered start — waiting %ds before first cycle",
                tier_name, startup_delay,
            )
            await asyncio.sleep(startup_delay)

        logger.info(
            "Tier '%s' loop started: %d channels, every %ds (stagger=%ds, warmup=%d steps)",
            tier_name, total_channels, interval, startup_delay, len(WARMUP_STEPS),
        )

        initial = True
        cycle_num = 0

        while True:
            start = time.time()
            cycle_num += 1

            # Warmup: limit channels during first N cycles
            if cycle_num <= len(WARMUP_STEPS):
                fraction = WARMUP_STEPS[cycle_num - 1]
                limit = max(1, int(total_channels * fraction))
                tier_channels = channels[:limit]
                logger.info(
                    "Tier '%s' warmup %d/%d: %d/%d channels (%.0f%%)",
                    tier_name, cycle_num, len(WARMUP_STEPS),
                    len(tier_channels), total_channels, fraction * 100,
                )
            else:
                tier_channels = channels

            # Delegate to testable once()-method
            initial = await self._run_tier_once(
                tier_name, tier_channels, initial,
            )

            # Dynamic interval + jitter + sleep
            effective_interval = self._get_effective_interval(tier_name, interval)
            jitter = effective_interval * INTERVAL_JITTER
            jittered = effective_interval + random.uniform(-jitter, jitter)
            elapsed = time.time() - start
            await asyncio.sleep(max(0, jittered - elapsed))

    async def _run_tier_once(
        self, tier_name: str, tier_channels: list[dict], initial: bool,
    ) -> bool:
        """One polling cycle: distribute → guards → poll. Returns new `initial`.

        Extracted for testability — real _run_tier_once is the integration
        test target for session skip, try-lock skip, and degradation.
        """
        start = time.time()

        # Distribute channels across available accounts
        account_chunks = await self._distribute(tier_channels)

        # Guard: pause Warm/Cold/Dormant when only 1 account is healthy
        if not self._should_poll_tier(tier_name):
            logger.debug(
                "%s tier: paused (only %d healthy account(s) — need 2+)",
                tier_name, self._get_available_account_count(),
            )
            return initial  # skip this cycle, initial unchanged

        for account, chunk in account_chunks:
            if not chunk:
                continue

            # Per-account try-lock: skip if another tier is already polling
            lock = self._get_account_lock(account.account_id)
            if lock.locked():
                logger.debug(
                    "Account %d busy — skipping %s tier this cycle (%d channels)",
                    account.account_id, tier_name, len(chunk),
                )
                continue

            # Session check: skip if account is not in active window
            state = await self._get_session_state(account.account_id)
            if state != "ACTIVE":
                logger.debug(
                    "Account %d: %s — skipping %s tier",
                    account.account_id, state, tier_name,
                )
                continue

            async with lock:
                limit_tag = "(initial)" if initial else "(incremental + pagination)"
                ok, err = await self._poll_batch(account, chunk, tier_name=tier_name, initial=initial)
                elapsed = time.time() - start
                if ok + err > 0:
                    logger.info(
                        "%s tier: %d ok, %d errors in %.1fs %s",
                        tier_name, ok, err, elapsed, limit_tag,
                    )

        return False  # after first real cycle, initial becomes False

    async def _distribute(self, channels: list[dict]) -> list[tuple]:
        """Distribute channels across available accounts (healthy + circuit breaker closed).

        Filters out blocked accounts BEFORE distribution so no channels are lost.
        """
        available = []
        for a in self.pool.accounts:
            if not a.is_healthy:
                continue
            if await limiter.is_circuit_open(a.account_id):
                logger.debug(
                    "Account %d excluded from distribution — circuit breaker open",
                    a.account_id,
                )
                continue
            available.append(a)

        if not available:
            logger.warning("No available accounts for distribution — all blocked or unhealthy")
            return []

        chunks = []
        n = len(available)
        for i, acc in enumerate(available):
            chunk = channels[i::n]  # Every n-th channel to this account
            chunks.append((acc, chunk))
        return chunks

    def _get_account_lock(self, account_id: int) -> asyncio.Lock:
        """Get or create a per-account lock for tier serialization."""
        if account_id not in self._account_locks:
            self._account_locks[account_id] = asyncio.Lock()
        return self._account_locks[account_id]

    # ═══════════════ SESSION MANAGEMENT ═══════════════

    async def _session_ticker(self, account_id: int):
        """Sole owner of session state transitions for one account.

        Sleeps until session:until, then transitions ACTIVE↔PAUSED↔SLEEPING.
        Survives worker restart via Redis keys (AOF from Task 0.6).
        """
        while True:
            redis = await get_redis()
            state = await redis.get(f"session:state:{account_id}")
            until_raw = await redis.get(f"session:until:{account_id}")
            await redis.aclose()

            now = time.time()

            if state and until_raw:
                until = float(until_raw)
                if now < until:
                    remaining = until - now
                    logger.info(
                        "Account %d: %s — sleeping %.0fs until transition",
                        account_id, state, remaining,
                    )
                    await asyncio.sleep(remaining)
                    continue

            # State expired or missing — transition
            new_state, new_until = self._next_session_state(
                account_id, prev_state=state, now=now,
            )

            redis = await get_redis()
            await redis.set(f"session:state:{account_id}", new_state)
            await redis.set(f"session:until:{account_id}", str(new_until))
            await redis.aclose()

            logger.info(
                "Account %d: transitioned to %s (until %s UTC)",
                account_id, new_state,
                time.strftime("%H:%M:%S", time.gmtime(new_until)),
            )

    async def _get_session_state(self, account_id: int) -> str:
        """Read current session state. Tiers call this — no side effects."""
        redis = await get_redis()
        state = await redis.get(f"session:state:{account_id}")
        await redis.aclose()
        return state if state else "ACTIVE"  # decode_responses=True → already str

    def _next_session_state(
        self, account_id: int, prev_state: str | None, now: float,
    ) -> tuple[str, float]:
        """Compute next session state and its expiry. Pure logic, no I/O."""
        sleep_start = self._get_sleep_start_hour(account_id)

        # 1. SLEEPING always wakes to ACTIVE — no re-sleep loop
        if prev_state == "SLEEPING":
            until = now + random.uniform(20 * 60, 60 * 60)
            # Extend past current sleep window to avoid immediate re-sleep
            sleep_end = self._sleep_window_end_ts(now, sleep_start)
            if sleep_end is not None and until < sleep_end:
                until = sleep_end + random.uniform(15 * 60, 30 * 60)
            return ("ACTIVE", until)

        # 2. Enter SLEEPING if now falls in sleep window (any prev_state)
        if self._is_in_sleep_window(now, sleep_start):
            duration = random.uniform(4 * 3600, 6 * 3600)
            return ("SLEEPING", now + duration)

        # 3. ACTIVE ↔ PAUSED outside sleep window
        if prev_state == "PAUSED" or prev_state is None:
            return ("ACTIVE", now + random.uniform(20 * 60, 60 * 60))

        return ("PAUSED", now + random.uniform(15 * 60, 60 * 60))

    def _is_in_sleep_window(self, now_ts: float, sleep_start_hour: int) -> bool:
        """Check if now falls in the 6h sleep window. Handles wraparound."""
        now = time.gmtime(now_ts)
        hour = now.tm_hour + now.tm_min / 60.0
        end = (sleep_start_hour + 6) % 24

        if sleep_start_hour < end:
            return sleep_start_hour <= hour < end
        else:
            return hour >= sleep_start_hour or hour < end

    def _sleep_window_end_ts(
        self, now_ts: float, sleep_start_hour: int,
    ) -> float | None:
        """Return UTC timestamp of the sleep window end containing now_ts, or None."""
        if not self._is_in_sleep_window(now_ts, sleep_start_hour):
            return None

        now = time.gmtime(now_ts)
        hour = now.tm_hour + now.tm_min / 60.0
        end_hour = (sleep_start_hour + 6) % 24

        end_dt = datetime(
            now.tm_year, now.tm_mon, now.tm_mday,
            int(end_hour), 0, 0, tzinfo=timezone.utc,
        )

        if sleep_start_hour < end_hour:
            return end_dt.timestamp()
        else:
            if hour >= sleep_start_hour:
                end_dt += timedelta(days=1)
            return end_dt.timestamp()

    def _get_sleep_start_hour(self, account_id: int) -> int:
        """Return UTC hour when this account's sleep window starts.

        Hardcoded to 2 UTC for now. Task 1.2 will make this per-account.
        """
        return 2

    def _get_available_account_count(self) -> int:
        """Count accounts that are healthy.

        Note: circuit breaker state is checked async in _distribute.
        This is a fast synchronous estimate for interval calculation.
        """
        return sum(1 for a in self.pool.accounts if a.is_healthy)

    def _should_poll_tier(self, tier_name: str) -> bool:
        """Check if this tier should be polled given current account availability.

        Hot tier always runs. Warm/Cold/Dormant require 2+ healthy accounts —
        a single account must not bear the full load to avoid repeat bans.
        """
        if tier_name == "Hot":
            return True
        available = self._get_available_account_count()
        return available >= 2

    def _get_effective_interval(self, tier_name: str, base_interval: int) -> int:
        """Calculate effective interval based on available accounts.

        With fewer accounts, increase interval to reduce sustained API load:
        - 2+ accounts: base interval (60s Hot, 300s Warm, etc.)
        - 1 account:  2x base interval (120s Hot, 600s Warm, etc.)

        Only Hot tier is affected — Warm/Cold/Dormant are low-frequency anyway.
        """
        if tier_name != "Hot":
            return base_interval
        available = self._get_available_account_count()
        if available >= 2:
            return base_interval
        # Single account — double the interval to reduce sustained load
        return base_interval * 2

    # ═══════════════ MAIN LOOP ═══════════════

    async def run_forever(self):
        """Main entry point: start tiers, health checks, periodic rebuilds."""
        await self.start()

        # Start health check in background
        asyncio.create_task(self.pool.health_check_loop())

        # Launch session tickers — one per account (sole owner of state transitions)
        for acc in self.pool.accounts:
            asyncio.create_task(self._session_ticker(acc.account_id))

        KEYWORD_RELOAD = 300  # Reload keywords from DB every 5 minutes (live admin changes)
        TIER_REBUILD = 3600  # Rebuild tiers every hour
        _last_reload = time.time()
        _last_tier_rebuild = time.time()

        # Launch all tier loops with staggered startup
        await asyncio.gather(
            self._run_tier_loop("Hot", self._hot_channels, HOT_INTERVAL, startup_delay=HOT_STARTUP_DELAY),
            self._run_tier_loop("Warm", self._warm_channels, WARM_INTERVAL, startup_delay=WARM_STARTUP_DELAY),
            self._run_tier_loop("Cold", self._cold_channels, COLD_INTERVAL, startup_delay=COLD_STARTUP_DELAY),
            self._run_tier_loop("Dormant", self._dormant_channels, DORMANT_INTERVAL, startup_delay=COLD_STARTUP_DELAY),
            self._maintenance_loop(KEYWORD_RELOAD, TIER_REBUILD, _last_reload, _last_tier_rebuild),
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
                    await self._tag_new_channels()  # tag channels added by discovery
                    last_tier_rebuild = now
                except Exception as e:
                    logger.warning("Tier rebuild failed: %s", e)

            await asyncio.sleep(300)  # Check every 5 minutes

    # ═══════════════ GEO AUTO-TAGGING ═══════════════

    async def _tag_new_channels(self) -> int:
        """Auto-detect city from title for channels without geo tags.

        Only processes channels that have NO city_id and NO channel_cities
        entries. Already-tagged channels are skipped (idempotent).
        Returns number of newly tagged channels.
        """
        from app.db.models import Country, City, ChannelCity, CatalogChannel
        from sqlalchemy import select as sa_select, delete as sa_delete, update as sa_update

        async with async_session_factory() as session:
            cities = (await session.execute(
                sa_select(City).where(
                    City.is_active == True, City.name_ru != "🌐 Вся страна"
                )
            )).scalars().all()
            # Only channels with NO city tag and NOT in channel_cities
            existing_cc = (await session.execute(
                sa_select(ChannelCity.channel_id).distinct()
            )).scalars().all()
            channels_with_entries = set(existing_cc)

            channels = (await session.execute(
                sa_select(CatalogChannel).where(
                    CatalogChannel.auto_matched_country_id.isnot(None),
                    CatalogChannel.auto_matched_city_id.is_(None),
                    CatalogChannel.title.isnot(None),
                )
            )).scalars().all()

        country_cities: dict[int, list[tuple[int, str]]] = {}
        for c in cities:
            name = (c.name_ru or "").lower()
            if len(name) >= 4:
                country_cities.setdefault(c.country_id, []).append((c.id, name))

        tagged = 0
        for ch in channels:
            if ch.id in channels_with_entries:
                continue
            if ch.auto_matched_country_id not in country_cities:
                continue

            title_lower = ch.title.lower()
            city_hits: list[int] = []
            for city_id, city_name in country_cities[ch.auto_matched_country_id]:
                if city_name in title_lower:
                    city_hits.append(city_id)

            unique = list(dict.fromkeys(city_hits))
            if not unique:
                continue

            if len(unique) == 1:
                async with async_session_factory() as s:
                    await s.execute(
                        sa_update(CatalogChannel)
                        .where(CatalogChannel.id == ch.id)
                        .values(auto_matched_city_id=unique[0])
                    )
                    await s.commit()
                tagged += 1
            else:
                async with async_session_factory() as s:
                    await s.execute(
                        sa_delete(ChannelCity).where(ChannelCity.channel_id == ch.id)
                    )
                    for city_id in unique:
                        s.add(ChannelCity(channel_id=ch.id, city_id=city_id))
                    if not ch.auto_matched_city_id:
                        await s.execute(
                            sa_update(CatalogChannel)
                            .where(CatalogChannel.id == ch.id)
                            .values(auto_matched_city_id=unique[0])
                        )
                    await s.commit()
                tagged += 1

        if tagged:
            logger.info("Geo auto-tag: %d new channels tagged", tagged)
        return tagged

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
        effective_city_ids = {channel_city_id} if channel_city_id else set()

        async with async_session_factory() as session:
            segs = (await session.execute(sa_select(Segment))).scalars().all()
        seg_by_slug = {s.slug: s.id for s in segs}
        seg_info = {
            s.slug: {
                "emoji": (s.emoji or ""),
                "ru": (s.title_ru or s.slug),
                "en": (s.title_en or s.slug),
            }
            for s in segs
        }
        matched_segment_ids = {seg_by_slug.get(s) for s in matched_segments}
        matched_segment_ids.discard(None)

        for user in users:
            subscriptions = user.get("subscriptions", [])
            personal_kws = user.get("keyword_texts", [])
            lang = user.get("lang", "ru")

            interested = False
            match_type = None  # "segment" or "keyword"
            for sub in subscriptions:
                if sub["country_id"] != channel_country_id:
                    continue
                if sub.get("city_ids") and effective_city_ids:
                    if not (effective_city_ids & set(sub["city_ids"])):
                        continue
                if sub["segment_id"] in matched_segment_ids:
                    interested = True
                    match_type = "segment"
                    break

            if not interested:
                for sub in subscriptions:
                    if sub["country_id"] != channel_country_id:
                        continue
                    if sub.get("city_ids") and effective_city_ids:
                        if not (effective_city_ids & set(sub["city_ids"])):
                            continue
                    if personal_kws and any(
                        kw.lower() in message_text.lower() for kw in personal_kws
                    ):
                        interested = True
                        match_type = "keyword"
                        break

            if not interested:
                continue

            # Build human-readable segment names for the notification footer
            if match_type == "segment":
                matched_names = [
                    {"emoji": seg_info[s]["emoji"], "title": seg_info[s][lang]}
                    for s in matched_segments
                    if s in seg_info
                ]
            else:
                # Personal keyword match — generic label
                matched_names = [
                    {"emoji": "🔑", "title": "Персональное ключевое слово" if lang == "ru" else "Personal keyword"}
                ]

            await push_notification({
                "user_id": user["user_id"],
                "telegram_id": user["telegram_id"],
                "lang": lang,
                "plan": user.get("plan", "free"),
                "chat_username": chat_username,
                "text": message_text,
                "sender": sender,
                "message_id": message_id,
                "message_hash": message_hash,
                "is_urgent": is_urgent,
                "matched_segments": matched_names,
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

async def _update_channel_info(
    chat_username: str, new_title: str | None, new_participants: int | None,
) -> None:
    """Update channel title and/or participant count in DB. Best-effort."""
    try:
        from app.db.session import async_session_factory
        from app.db.models import CatalogChannel
        from sqlalchemy import select, update

        async with async_session_factory() as session:
            ch = (await session.execute(
                select(CatalogChannel).where(
                    CatalogChannel.chat_username == chat_username
                )
            )).scalar_one_or_none()

            updates = {}
            if new_title and ch and ch.title != new_title:
                updates["title"] = new_title
            if new_participants is not None and new_participants > 0:
                if not ch or (ch.participants or 0) != new_participants:
                    updates["participants"] = new_participants

            if updates:
                await session.execute(
                    update(CatalogChannel)
                    .where(CatalogChannel.chat_username == chat_username)
                    .values(**updates)
                )
                await session.commit()
    except Exception:
        pass
