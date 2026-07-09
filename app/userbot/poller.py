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

from app.userbot.classifier import (
    classify_message, _has_strong_demand_signal, _match_keyword, _lemmatize_text,
)
from app.userbot.llm_validator import (
    llm_validator, sanitize_text, PendingMatch, is_high_confidence_demand,
    LLMResult,
)
from app.userbot.discovery_v2 import is_discovery_window
from app.userbot.pool import UserbotPool
from app.userbot.rate_limiter import limiter, BudgetExceeded
from app.config import settings
from app.cache import get_redis
from app.db.session import async_session_factory
from app.db.models import LLMDecision, SegmentKeyword, Segment
from sqlalchemy import select

logger = logging.getLogger(__name__)

# ── Tier configuration ──
# All intervals moved to config.py (settings.hot_interval_base, warm_interval, etc.)
# Module-level constants below are only for non-tier defaults (limits, jitter, delays)
# Tier-specific message fetch limits — per API call.
# Pagination auto-triggers if a full batch is returned (rare in practice).
FETCH_LIMIT = 100  # max messages per channel per poll cycle
TIER_LIMITS = {
    "Hot": 30,    # (kept for reference, fetch uses FETCH_LIMIT)
    "Warm": 80,
    "Cold": 150,
    "Dormant": 500,
}

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


def _personal_keyword_hits(keyword: str, text_lower: str, text_lemma: str) -> bool:
    """Word-boundary match of a personal keyword, tolerant to Russian inflection.

    Same strategy as the classifier's _match_kw: exact form first, then the
    lemmatized text, then the lemmatized keyword against the lemmatized text
    («фотограф» matches «фотографа»). Word boundaries prevent substring false
    positives («кот» does not match «который»).
    """
    if _match_keyword(keyword, text_lower):
        return True
    if text_lemma != text_lower and _match_keyword(keyword, text_lemma):
        return True
    kw_lemma = _lemmatize_text(keyword)
    if kw_lemma != keyword and _match_keyword(kw_lemma, text_lemma):
        return True
    return False


def next_delay() -> float:
    """Log-normal delay between channel polls — human-like rhythm.

    median ≈ e^0.7 ≈ 2.0s, range clamped to [0.8, 6.0]s.
    Heavy right tail prevents uniform-periodicity detection.
    """
    d = random.lognormvariate(0.7, 0.5)
    return min(max(d, 0.8), 6.0)


# ── Batch flush tuning: balance token savings vs notification speed ──
FLUSH_EVERY_N_CHANNELS = 20  # flush pending LLM matches every ~40s (20 channels × 2s)


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
        self._personal_keywords: list[str] = []  # active user keywords (Вариант Б)
        self._domain_word_map: dict[str, list[str]] = {}  # reality filter
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
        # Pending matches queued for batch LLM validation (flushed after each poll batch)
        self._pending_matches: list[PendingMatch] = []

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
            # Activate post-ban if recently unbanned while worker was down (layer 3)
            await limiter.activate_post_ban_if_recent(acc.account_id)
        if not self._keyword_map:
            self._keyword_map, self._universal_stops, self._domain_word_map = await self._load_keywords()
            self._personal_keywords = await self._load_personal_keywords()
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
            is_active_country = country_id is not None and country_id in self._active_countries
            is_watched = ch.get("is_watched", False)
            is_watched_with_geo = is_watched and country_id is not None

            if is_active_country:
                hot.append(ch)
            elif is_watched_with_geo:
                # Watched channel with geo — tier by country activity
                if participants and participants >= 1000:
                    warm.append(ch)
                else:
                    cold.append(ch)
            elif is_watched:
                # Legacy watched channel without geo — always monitor
                if participants and participants >= 1000:
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
        """Return all channels with country_id and participant count.

        Sources:
        - CatalogChannel: public channels from catalog (with geo from auto_matched)
        - WatchedChat: manually added channels/groups (with geo from country_id column)

        For WatchedChat entries without a username (private groups),
        chat_username stores the Telegram peer ID in format "-100XXXXXXX".
        """
        from app.db.models import CatalogChannel, WatchedChat
        try:
            async with async_session_factory() as session:
                cat_result = await session.execute(
                    select(
                        CatalogChannel.chat_username,
                        CatalogChannel.auto_matched_country_id,
                        CatalogChannel.participants,
                    ).where(CatalogChannel.is_ignored == False)
                )
                watched_result = await session.execute(
                    select(
                        WatchedChat.chat_username,
                        WatchedChat.country_id,
                    ).where(
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
                        "is_watched": False,
                    })
                    seen.add(row[0])
                for row in watched_result.all():
                    username = row[0]
                    if username not in seen:
                        channels.append({
                            "chat_username": username,
                            "country_id": row[1],
                            "participants": None,
                            "is_watched": True,
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
            await redis.aclose()
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
            await redis.aclose()
        except Exception:
            pass

    # ═══════════════ CHANNEL POLLING ═══════════════

    async def _resolve_entity(self, account, channel_username: str):
        """Return entity for channel_username — from cache or via ResolveUsername.

        Handles two formats:
        - @username (or raw username): public channels — resolved via get_input_entity
        - -100XXXXXXXXX: private groups without username — resolved by peer ID
          (entity must be in the session cache; the userbot account must be a member)

        Caches (channel_id, access_hash) per account since access_hash differs
        between accounts. On cache hit, constructs InputPeerChannel directly —
        no API call, no limiter.acquire().
        """
        per_account = self._entity_cache.setdefault(channel_username, {})
        cached = per_account.get(account.account_id)
        if cached is not None:
            return InputPeerChannel(*cached)

        await limiter.acquire(account.account_id)

        # ID-based resolution for private groups without usernames
        if channel_username.startswith("-"):
            # Formats: -100XXXXXXX (supergroup) or -XXXXXXXX (legacy)
            # Strip leading -100 or - to get the positive entity ID
            raw = channel_username
            if raw.startswith("-100"):
                entity_id = int(raw[4:])
            else:
                entity_id = int(raw[1:])
            from telethon.tl.types import PeerChannel
            entity = await account.client.get_input_entity(PeerChannel(entity_id))
        else:
            entity = await account.get_input_entity(channel_username)

        if hasattr(entity, 'channel_id'):
            per_account[account.account_id] = (entity.channel_id, entity.access_hash)
            return entity
        # Fallback: full entity (shouldn't normally happen with get_input_entity)
        per_account[account.account_id] = (entity.id, entity.access_hash)
        return entity

    async def _poll_channel(
        self, account, channel_username: str, tier_name: str,
    ) -> None:
        """Poll a single channel: get all new messages since cursor, classify, dispatch.

        First-acquaintance mode is derived from the Redis cursor, not from a
        restart flag: cursor == 0 (channel never polled) → fetch the last
        FETCH_LIMIT messages and set the cursor; cursor > 0 → incremental.
        A worker restart therefore never re-reads (and re-classifies) history.

        Args:
            account: UserbotAccount to use
            channel_username: @username of the channel
            tier_name: "Hot" | "Warm" | "Cold" — picks TIER_LIMITS[tier]
        """
        try:
            entity = await self._resolve_entity(account, channel_username)
        except FloodWaitError:
            raise
        except Exception as e:
            logger.warning("poll @%s: %s", channel_username, type(e).__name__)
            return

        # Skip broadcast-only channels (news feeds, announcement channels).
        # We want groups/supergroups where people actually post requests.
        if settings.exclude_broadcast_channels:
            is_broadcast = getattr(entity, "broadcast", False)
            is_megagroup = getattr(entity, "megagroup", False)
            if is_broadcast and not is_megagroup:
                logger.info("Skipping broadcast channel @%s (not a chat)", channel_username)
                return

        cursor = await self._get_cursor(channel_username)

        # Fetch ALL messages since cursor, paginating if needed
        all_messages = await self._fetch_all_since(
            account, entity, channel_username, cursor,
        )

        if not all_messages:
            return

        # ── 7-day freshness gate ──
        # server_max: max id from FULL server output (before any text/date filters).
        # This is the cursor target — prevents re-reading dead channels and
        # ensures the cursor advances past skipped (old/textless) messages.
        server_max = max((m.id for m in all_messages), default=None)
        # cutoff: messages older than this are intentionally skipped.
        cutoff = datetime.now(timezone.utc) - timedelta(days=settings.message_max_age_days)

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

            # ── 7-day freshness gate ──
            # Messages older than cutoff are intentionally skipped.
            # This is a pure gating decision — no cursor touching here.
            # Cursor advances via server_max (full server output), not by this filter.
            if msg.date and msg.date < cutoff:
                continue

            msg_id = msg.id
            if msg_id > max_msg_id:
                max_msg_id = msg_id

            result = classify_message(msg.message, self._keyword_map, self._universal_stops)

            # Channel pre-tagging boost — STRONG demand only (a bare «?» is
            # not enough: any question in a pre-tagged channel is not a lead)
            channel_segs = self._channel_segments.get(channel_username, [])
            if channel_segs and not result.matched_segments:
                if _has_strong_demand_signal(msg.message):
                    result = result._replace(matched_segments=channel_segs)
            elif channel_segs and result.matched_segments:
                extra = [s for s in channel_segs if s not in result.matched_segments]
                if extra:
                    result = result._replace(
                        matched_segments=result.matched_segments + extra
                    )

            if result.matched_segments:
                # ── Reality filter: require at least one domain-specific word ──
                # Prevents LLM calls for messages with no relation to the segment.
                # e.g. "продам гантели" matched moto-purchase → filtered out.
                verified = self._filter_by_domain(msg.message, result.matched_segments)
                if not verified:
                    logger.info(
                        "Reality filter: @%s msg %d blocked (%s) — no domain words",
                        channel_username, msg_id, ",".join(result.matched_segments),
                    )
                    await self._log_unmatched(channel_username, msg.message, msg_id)
                    continue

                # Queue for batch LLM validation (flushed after poll batch completes)
                self._pending_matches.append(PendingMatch(
                    chat_username=channel_username,
                    message_id=msg_id,
                    text=msg.message,
                    candidate_segments=verified,
                    account_id=account.account_id,
                    is_urgent=result.is_urgent,
                    sender=getattr(msg.sender, "username", None) if msg.sender else None,
                    skip_llm=is_high_confidence_demand(msg.message),
                ))
            elif self._matches_personal_keyword(msg.message):
                # Вариант Б: no segment match, but a personal user keyword hit.
                # Personal keywords work unconditionally (spec §5а) — bypass
                # the reality filter (it is segment-based) and the LLM.
                # _dispatch narrows delivery to users whose own keyword matched.
                self._pending_matches.append(PendingMatch(
                    chat_username=channel_username,
                    message_id=msg_id,
                    text=msg.message,
                    candidate_segments=[],
                    account_id=account.account_id,
                    is_urgent=result.is_urgent,
                    sender=getattr(msg.sender, "username", None) if msg.sender else None,
                    skip_llm=True,
                    keyword_only=True,
                ))
            else:
                await self._log_unmatched(channel_username, msg.message, msg_id)

        # Update cursor from FULL server output (server_max), unconditionally.
        # This prevents cursor lag from old/textless messages — the cursor always
        # moves to the highest message_id Telegram returned, regardless of filters.
        # server_max is computed before the text/date gates (see freshness gate above).
        new_cursor = max(cursor, server_max) if server_max is not None else cursor
        if server_max is not None and new_cursor != cursor:
            await self._set_cursor(channel_username, new_cursor)

    async def _fetch_all_since(
        self, account, entity, channel_username: str, cursor: int,
    ) -> list:
        """Fetch messages since cursor. Single API call, no pagination.

        One get_messages call per channel per poll cycle. Hot channels poll
        more frequently → naturally catch new messages without extra API cost.
        """
        await limiter.acquire(account.account_id)
        try:
            if cursor > 0:
                batch = await account.get_messages(entity, min_id=cursor, limit=FETCH_LIMIT)
            else:
                batch = await account.get_messages(entity, limit=FETCH_LIMIT)
            return list(batch) if batch else []
        except FloodWaitError:
            raise
        except ChannelInvalidError:
            self._entity_cache.get(channel_username, {}).pop(account.account_id, None)
            raise
        except Exception:
            return []

    # ═══════════════ BATCH & TIER LOOPS ═══════════════

    async def _poll_batch(
        self, account, channels: list[dict], tier_name: str,
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
                    tier_name=tier_name,
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
                return False
            except Exception as e:
                logger.warning("poll @%s: %s", ch.get('chat_username', '?'), type(e).__name__)
                return False

        # Shuffle channel order to break predictable patterns
        shuffled = list(channels)
        random.shuffle(shuffled)

        ok, errors = 0, 0
        for i, ch in enumerate(shuffled):
            try:
                result = await _poll_one(ch)
            except BudgetExceeded:
                logger.warning(
                    "Budget exceeded for account %d — stopping batch after %d channels",
                    account.account_id, i,
                )
                # Throttle: at most one budget notification per account per 15 min
                alert_key = f"alert:last:budget_exceed:{account.account_id}"
                redis = await get_redis()
                last_alert = await redis.get(alert_key)
                now = time.time()
                if not last_alert or (now - float(last_alert)) >= 900:
                    await redis.setex(alert_key, 900, str(now))
                    from app.worker.notify_admin import notify_admin
                    await notify_admin(
                        f"📊 Аккаунт #{account.account_id} исчерпал суточный бюджет "
                        f"API-запросов. Поллинг остановлен до следующих суток."
                    )
                await redis.aclose()
                break  # budget exhausted, no point polling remaining channels
            if result:
                ok += 1
            else:
                errors += 1
                if await limiter.is_circuit_open(account.account_id):
                    break
            if i < len(shuffled) - 1:
                delay = next_delay()
                await asyncio.sleep(delay)

            # Periodic flush: batch-validate & dispatch every N channels.
            # Keeps notification delay to ~40s while still batching LLM calls.
            if (i + 1) % FLUSH_EVERY_N_CHANNELS == 0:
                await self._flush_pending_matches(account.account_id)

        # Update last_poll_at for alert_loop liveness check (per-account)
        try:
            redis = await get_redis()
            await redis.set(f"stats:last_poll_at:{account.account_id}", str(time.time()))
            await redis.aclose()
        except Exception:
            pass

        # Flush pending LLM validations for this account only
        await self._flush_pending_matches(account.account_id)

        return ok, errors

    async def _flush_pending_matches(self, account_id: int) -> None:
        """Batch-validate queued matches for one account and dispatch those that pass."""
        # Pop only matches for this account (other tiers may be collecting concurrently)
        my_matches = [m for m in self._pending_matches if m.account_id == account_id]
        self._pending_matches = [m for m in self._pending_matches if m.account_id != account_id]

        if not my_matches:
            return

        matches = my_matches

        t0 = time.monotonic()
        results = await llm_validator.validate_batch(matches)
        elapsed = time.monotonic() - t0

        if len(results) != len(matches):
            logger.error(
                "LLM batch returned %d results for %d matches — filling DEMAND fallbacks",
                len(results), len(matches),
            )
            # Pad with fail-open results
            while len(results) < len(matches):
                results.append(LLMResult(
                    verdict="DEMAND", reason="Missing result — fail-open", error="pad",
                ))

        blocked = 0
        passed = 0
        skipped_llm = 0

        for match, llm_result in zip(matches, results):
            match.llm_result = llm_result

            # Log decision to DB
            await self._log_llm_decision(
                match.chat_username, match.message_id, match.text,
                match.candidate_segments, llm_result,
            )

            # Check if blocked
            if (
                settings.llm_mode == "blocking"
                and llm_validator.should_block(llm_result)
            ):
                urgency = "🔥 " if match.is_urgent else ""
                logger.info(
                    "%sBLOCKED by LLM in @%s (msg %d): %s",
                    urgency, match.chat_username, match.message_id,
                    llm_result.reason[:120],
                )
                blocked += 1
                continue

            # Dispatch
            if match.skip_llm or is_high_confidence_demand(match.text):
                skipped_llm += 1
            passed += 1

            urgency = "🔥 " if match.is_urgent else ""
            logger.info(
                "%sMatch in @%s (msg %d): segments=%s [LLM: %s]",
                urgency, match.chat_username, match.message_id,
                match.candidate_segments, llm_result.verdict,
            )
            await self._dispatch(
                chat_username=match.chat_username,
                message_text=match.text,
                message_id=match.message_id,
                matched_segments=match.candidate_segments,
                is_urgent=match.is_urgent,
                sender=match.sender,
            )

        if matches:
            logger.info(
                "LLM batch flush: %d msgs validated in %.1fs — "
                "%d passed, %d blocked, %d skipped (high-conf)",
                len(matches), elapsed, passed, blocked, skipped_llm,
            )

    # ── Reality filter (zero-cost LLM bypass) ──

    def _filter_by_domain(self, text: str, segments: list[str]) -> list[str]:
        """Return only segments that have at least one domain word in the text.
        
        Uses the synonym-based domain word map loaded from DB.
        Segments with no domain words defined pass through unchanged.
        """
        text_lower = text.lower()
        verified = []
        for slug in segments:
            words = self._domain_word_map.get(slug)
            if not words:
                # No domain words defined for this segment → pass through
                verified.append(slug)
                continue
            # Check if any domain word appears in the text
            for w in words:
                if w in text_lower:
                    verified.append(slug)
                    break
        return verified

    # ── Tier attribute mapping: each tier name maps to a self.* attribute ──
    # _run_tier_loop re-reads channels from self each cycle so that
    # _maintenance_loop's _rebuild_tiers() changes are picked up immediately.
    # This prevents the bug where a tier loop launched with 0 channels
    # would return and never recover (July 9, 2026 production outage).
    _TIER_ATTRS = {
        "Hot": "_hot_channels",
        "Warm": "_warm_channels",
        "Cold": "_cold_channels",
        "Dormant": "_dormant_channels",
    }

    async def _run_tier_loop(
        self, tier_name: str, channels: list[dict], interval: int,
        startup_delay: int = 0,
    ):
        """Continuous loop — thin wrapper around _run_tier_once + timing.

        Never crashes: a single-cycle failure is caught and logged;
        the loop continues with the next cycle after a short backoff.

        Re-reads channels from self each cycle via _TIER_ATTRS mapping —
        if _maintenance_loop rebuilds tiers, the loop picks up new channels
        without restart. Zero channels is handled with a sleep loop rather
        than an early return.
        """
        tier_attr = self._TIER_ATTRS.get(tier_name)

        if startup_delay > 0:
            logger.info(
                "Tier '%s': staggered start — waiting %ds before first cycle",
                tier_name, startup_delay,
            )
            await asyncio.sleep(startup_delay)

        cycle_num = 0
        logged_start = False
        _zero_logged = False
        _zero_cycle_count = 0

        while True:
            # ── Re-read channels from source attribute each cycle ──
            # _maintenance_loop calls _rebuild_tiers() which replaces
            # self._hot_channels etc. with a fresh list. Re-reading here
            # ensures we pick up changes without restarting the worker.
            # Fallback: if tier_name is not in _TIER_ATTRS (test tiers),
            # use the static channels parameter passed at call time.
            if tier_attr is not None:
                channels = getattr(self, tier_attr)
            total_channels = len(channels)

            if total_channels == 0:
                _zero_cycle_count += 1
                if not _zero_logged:
                    logger.info(
                        "Tier '%s': 0 channels — sleeping until channels appear "
                        "(maintenance rebuilds tiers every hour)",
                        tier_name,
                    )
                    _zero_logged = True
                elif _zero_cycle_count % 12 == 0:  # log every ~1h
                    logger.debug(
                        "Tier '%s': still 0 channels after %d cycles",
                        tier_name, _zero_cycle_count,
                    )
                await asyncio.sleep(300)  # Check every 5 minutes
                continue

            if not logged_start:
                _zero_logged = False
                logger.info(
                    "Tier '%s' loop started: %d channels, every %ds "
                    "(stagger=%ds, warmup=%d steps)",
                    tier_name, total_channels, interval, startup_delay,
                    len(WARMUP_STEPS),
                )
                logged_start = True

            cycle_num += 1
            cycle_start = time.time()

            try:
                # ── Warmup skip: if only 1 CB-free account, go full speed ──
                # The account has been polling for days — its pattern is
                # established. Warmup (7 cycles of ramping batch size) would
                # look like bot calibration to Telegram.
                cb_free = 0
                for acc in self.pool.accounts:
                    if not acc.is_healthy:
                        continue
                    if await limiter.is_circuit_open(acc.account_id):
                        continue
                    cb_free += 1

                skip_warmup = (cb_free >= 1)

                # Warmup: limit channels during first N cycles
                if not skip_warmup and cycle_num <= len(WARMUP_STEPS):
                    fraction = WARMUP_STEPS[cycle_num - 1]
                    limit = max(1, int(total_channels * fraction))
                    tier_channels = channels[:limit]
                    logger.info(
                        "Tier '%s' warmup %d/%d: %d/%d channels (%.0f%%)",
                        tier_name, cycle_num, len(WARMUP_STEPS),
                        len(tier_channels), total_channels, fraction * 100,
                    )
                elif skip_warmup and cycle_num == 1:
                    tier_channels = channels
                    logger.info(
                        "Tier '%s': warmup SKIPPED (only %d CB-free account) — "
                        "using all %d channels",
                        tier_name, cb_free, len(tier_channels),
                    )
                else:
                    tier_channels = channels
                    logger.debug(
                        "Tier '%s' cycle %d: %d channels",
                        tier_name, cycle_num, len(tier_channels),
                    )

                # Delegate to testable once()-method
                await self._run_tier_once(tier_name, tier_channels)

                # Dynamic interval + jitter
                # Post-ban multiplier is now inside _get_effective_interval —
                # it checks all accounts and uses max() across them.
                effective_interval = await self._get_effective_interval(tier_name, interval)
                jitter = effective_interval * INTERVAL_JITTER
                jittered = effective_interval + random.uniform(-jitter, jitter)
                elapsed = time.time() - cycle_start
                sleep_time = max(5.0, jittered - elapsed)

            except Exception:
                logger.exception(
                    "Tier '%s' cycle %d crashed — retrying in 60s",
                    tier_name, cycle_num,
                )
                sleep_time = 60.0

            await asyncio.sleep(sleep_time)

    async def _run_tier_once(
        self, tier_name: str, tier_channels: list[dict],
    ) -> None:
        """One polling cycle: distribute → guards → poll.

        Extracted for testability — real _run_tier_once is the integration
        test target for session skip, try-lock skip, and degradation.
        First-acquaintance vs incremental mode is per-channel (cursor == 0
        in _poll_channel), not a loop-level flag.
        """
        start = time.time()

        # Distribute channels across available accounts
        account_chunks = await self._distribute(tier_channels)

        # Guard: pause Warm/Cold/Dormant when only 1 CB-free account is available
        if not await self._should_poll_tier(tier_name):
            available = await self._get_available_account_count()
            logger.debug(
                "%s tier: paused (only %d CB-free account(s) — need 2+)",
                tier_name, available,
            )
            return  # skip this cycle

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
                ok, err = await self._poll_batch(account, chunk, tier_name=tier_name)
                elapsed = time.time() - start
                if ok + err > 0:
                    logger.info(
                        "%s tier: %d ok, %d errors in %.1fs",
                        tier_name, ok, err, elapsed,
                    )

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
            # Exclude account #3 during discovery night window (it's searching)
            if a.account_id == settings.discovery_account_id and is_discovery_window():
                logger.debug("Account %d excluded — discovery window active", a.account_id)
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

        Guard: if this account is the only one with a clear circuit breaker,
        it stays ACTIVE regardless of schedule — otherwise the service
        would have zero polling capacity.
        """
        while True:
            # Proactive guard: if this is the only CB-free account, force ACTIVE
            # regardless of what Redis says. Fixes stale PAUSED states that
            # were written before the guard existed.
            cb_free = 0
            for acc in self.pool.accounts:
                if not acc.is_healthy:
                    continue
                if await limiter.is_circuit_open(acc.account_id):
                    continue
                cb_free += 1

            is_only_healthy = (cb_free <= 1)

            redis = await get_redis()
            state = await redis.get(f"session:state:{account_id}")
            until_raw = await redis.get(f"session:until:{account_id}")
            await redis.aclose()

            now = time.time()

            # Override stale PAUSED/SLEEPING immediately
            if is_only_healthy and state in ("PAUSED", "SLEEPING"):
                logger.info(
                    "ONLY HEALTHY: account %d is %s but only %d CB-free — "
                    "forcing ACTIVE immediately",
                    account_id, state, cb_free,
                )
                state = "ACTIVE"
                until_raw = None  # force immediate transition

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

            # Guard: never pause/sleep the last healthy (non-CB) account
            if is_only_healthy and new_state in ("PAUSED", "SLEEPING"):
                logger.info(
                    "ONLY HEALTHY: overriding %s → ACTIVE for account %d "
                    "(only %d CB-free account(s))",
                    new_state, account_id, cb_free,
                )
                new_state = "ACTIVE"
                new_until = now + random.uniform(20 * 60, 60 * 60)

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
            until = now + random.uniform(40 * 60, 90 * 60)
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
            return ("ACTIVE", now + random.uniform(40 * 60, 90 * 60))

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

        Evenly spaces N accounts across 24h so sleep windows (6h each)
        never overlap. Uses position in pool.accounts list, not account_id,
        to handle potential gaps if accounts are removed.
        """
        total = max(1, len(self.pool.accounts))
        for idx, acc in enumerate(self.pool.accounts):
            if acc.account_id == account_id:
                return (idx * (24 // total)) % 24
        return 2  # fallback: account not found in pool

    # ═══════════════ ALERT LOOP ═══════════════

    async def _alert_loop(self):
        """Periodic system health checks → notify_admin with throttling."""
        CHECK_INTERVAL = 300  # 5 minutes

        while True:
            try:
                await self._run_alert_checks()
            except Exception:
                logger.exception("Alert loop iteration failed — continuing")
            await asyncio.sleep(CHECK_INTERVAL)

    async def _run_alert_checks(self):
        """Run all alert conditions independently — one failure doesn't stop others."""
        checks = [
            self._check_queue_backlog,
            self._check_dlq,
            self._check_flood_wait,
            self._check_budget_exceeded,
            self._check_poller_stuck,
        ]
        for check in checks:
            try:
                level, text = await check()
                if level and text:
                    await self._send_alert(level, text, check.__name__)
            except Exception:
                logger.exception("Alert check %s failed", check.__name__)

    async def _send_alert(self, level: str, text: str, alert_type: str):
        """Send alert with Redis-backed throttling (survives restart via AOF)."""
        key = f"alert:last:{alert_type}"
        redis = await get_redis()
        last_raw = await redis.get(key)
        await redis.aclose()

        now = time.time()
        cooldown = 15 * 60  # all levels: at most once per 15 min
        if last_raw and (now - float(last_raw)) < cooldown:
            return

        emoji = {"CRITICAL": "🚨", "WARNING": "⚠️", "INFO": "ℹ️"}.get(level, "")
        from app.worker.notify_admin import notify_admin
        await notify_admin(f"{emoji} {level}\n\n{text}")

        redis = await get_redis()
        await redis.setex(key, cooldown + 60, str(now))
        await redis.aclose()

    async def _check_queue_backlog(self) -> tuple[str | None, str | None]:
        redis = await get_redis()
        length = await redis.llen("queue:notifications")
        await redis.aclose()
        if length > 100:
            return ("WARNING", f"Очередь уведомлений: {length} шт (порог 100)")
        return (None, None)

    async def _check_dlq(self) -> tuple[str | None, str | None]:
        redis = await get_redis()
        length = await redis.llen("dlq:notifications")
        await redis.aclose()
        if length > 0:
            return ("WARNING", f"Dead-letter очередь: {length} неотправленных уведомлений")
        return (None, None)

    async def _check_flood_wait(self) -> tuple[str | None, str | None]:
        """Escalated FloodWait check: >30min CRITICAL, else any WARNING.

        Replaces two independent checks that caused duplicate alerts.
        """
        for acc in self.pool.accounts:
            if not acc.is_healthy:
                continue
            redis = await get_redis()
            expires_raw = await redis.get(f"circuit:expires:{acc.account_id}")
            await redis.aclose()
            if expires_raw:
                remaining = int(expires_raw) - int(time.time())
                if remaining > 0:
                    hours = remaining // 3600
                    mins = (remaining % 3600) // 60
                    if remaining > 30 * 60:
                        return (
                            "CRITICAL",
                            f"Аккаунт #{acc.account_id}: FloodWait > 30 мин "
                            f"(осталось {hours}ч {mins}м)",
                        )
                    else:
                        return (
                            "WARNING",
                            f"Аккаунт #{acc.account_id}: FloodWait "
                            f"(осталось {hours}ч {mins}м)",
                        )
        return (None, None)

    async def _check_budget_exceeded(self) -> tuple[str | None, str | None]:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        for acc in self.pool.accounts:
            if not acc.is_healthy:
                continue
            redis = await get_redis()
            used_raw = await redis.get(f"budget:used:{acc.account_id}:{today}")
            await redis.aclose()
            if used_raw and int(used_raw) >= settings.daily_request_budget:
                return (
                    "WARNING",
                    f"Аккаунт #{acc.account_id}: суточный бюджет исчерпан "
                    f"({used_raw}/{settings.daily_request_budget})",
                )
        return (None, None)

    async def _check_poller_stuck(self) -> tuple[str | None, str | None]:
        """Check poller liveness per-account.

        Only alerts when ALL accounts that CAN poll (healthy + ACTIVE + CB clear)
        have been silent > threshold. PAUSED/SLEEPING accounts are excluded.
        If at least one account is polling normally → no alert.
        """
        redis = await get_redis()

        # "All accounts stuck" ⟺ even the FRESHEST can-poll account is silent
        # longer than the threshold → take the MIN silence across accounts.
        # (max would fire when ANY single account is silent — false CRITICALs
        # while the other account polls normally.)
        min_silence = float("inf")
        can_poll_count = 0
        for acc in self.pool.accounts:
            if not acc.is_healthy:
                continue
            state = await self._get_session_state(acc.account_id)
            if state != "ACTIVE":
                continue
            if await limiter.is_circuit_open(acc.account_id):
                continue

            can_poll_count += 1
            last_raw = await redis.get(f"stats:last_poll_at:{acc.account_id}")
            if last_raw:
                silence = time.time() - float(last_raw)
            else:
                # No poll data for this account yet — silent "forever";
                # never the minimum unless ALL accounts lack data.
                silence = float("inf")
            if silence < min_silence:
                min_silence = silence

        await redis.aclose()

        if can_poll_count == 0:
            return (None, None)  # no accounts expected to poll

        if min_silence == float("inf"):
            return (None, None)  # freshly started, no poll data at all yet

        if min_silence > 60 * 60:
            return (
                "CRITICAL",
                f"Все {can_poll_count} активных аккаунта не завершали батчей "
                f">{min_silence/60:.0f} мин — возможная остановка поллера",
            )
        elif min_silence > 30 * 60:
            return (
                "WARNING",
                f"Все {can_poll_count} активных аккаунта без батчей "
                f"{min_silence/60:.0f} мин",
            )
        return (None, None)

    async def _get_available_account_count(self) -> int:
        """Count accounts that are healthy AND have a clear circuit breaker.

        Unlike the previous sync-only version, this checks CB state via Redis
        so degradation kicks in when an account gets banned. This was the root
        cause of the July 3-4 incident: after Acc1 was banned, this method
        still returned 2 → no degradation → Acc2 kept polling at full speed.
        """
        count = 0
        for a in self.pool.accounts:
            if not a.is_healthy:
                continue
            if await limiter.is_circuit_open(a.account_id):
                continue
            count += 1
        return count

    async def _should_poll_tier(self, tier_name: str) -> bool:
        """Check if this tier should be polled given current account availability.

        Hot tier always runs. Warm/Cold/Dormant require 2+ CB-free accounts —
        a single account must not bear the full load to avoid repeat bans.
        """
        if tier_name == "Hot":
            return True
        available = await self._get_available_account_count()
        return available >= 2

    async def _get_effective_interval(
        self, tier_name: str, base_interval: int,
    ) -> int:
        """Calculate effective interval with degradation and cap.

        Hot tier only — non-Hot tiers pass through unchanged.
        Multipliers: degradation (×2 at 1 CB-free acc) and post_ban
        (escalating 1.5→3.0→5.0 based on ban count per account).
        max() wins (they don't multiply — distinct risk factors).
        Hard cap prevents excessive sparseness regardless of conditions.
        """
        if tier_name != "Hot":
            return base_interval

        available = await self._get_available_account_count()

        if available == 0:
            logger.critical(
                "ZERO CB-free accounts! All api-call-capable accounts are blocked. "
                "Using cap interval (%.0fs) — service has no polling capacity.",
                settings.hot_interval_cap,
            )
            return settings.hot_interval_cap

        if available >= 3:
            base = settings.hot_interval_3plus
        else:
            base = base_interval  # settings.hot_interval_base for 1 or 2 accounts

        degraded = settings.hot_degraded_multiplier if available < 2 else 1.0

        # Escalating post-ban multiplier — take max across all accounts
        # so the whole tier slows down if ANY account is in severe post-ban.
        max_pb_mult = 1.0
        for acc in self.pool.accounts:
            if not acc.is_healthy:
                continue
            try:
                pb_mult = await limiter.get_post_ban_interval_multiplier(acc.account_id)
                if pb_mult > max_pb_mult:
                    max_pb_mult = pb_mult
            except Exception:
                pass

        multiplier = max(degraded, max_pb_mult)

        effective = base * multiplier
        return min(int(effective), settings.hot_interval_cap)

    # ═══════════════ MAIN LOOP ═══════════════

    async def run_forever(self):
        """Main entry point: start tiers, health checks, periodic rebuilds."""
        await self.start()

        # Start health check in background
        asyncio.create_task(self.pool.health_check_loop())

        # Launch session tickers — one per account (sole owner of state transitions)
        for acc in self.pool.accounts:
            asyncio.create_task(self._session_ticker(acc.account_id))

        # Launch alert loop — system health monitoring
        asyncio.create_task(self._alert_loop())

        KEYWORD_RELOAD = 300  # Reload keywords from DB every 5 minutes (live admin changes)
        TIER_REBUILD = 3600  # Rebuild tiers every hour
        _last_reload = time.time()
        _last_tier_rebuild = time.time()

        # Launch all tier loops with staggered startup
        await asyncio.gather(
            self._run_tier_loop("Hot", self._hot_channels, settings.hot_interval_base, startup_delay=HOT_STARTUP_DELAY),
            self._run_tier_loop("Warm", self._warm_channels, settings.warm_interval, startup_delay=WARM_STARTUP_DELAY),
            self._run_tier_loop("Cold", self._cold_channels, settings.cold_interval, startup_delay=COLD_STARTUP_DELAY),
            self._run_tier_loop("Dormant", self._dormant_channels, settings.dormant_interval, startup_delay=COLD_STARTUP_DELAY),
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
                    self._keyword_map, self._universal_stops, self._domain_word_map = await self._load_keywords()
                    self._personal_keywords = await self._load_personal_keywords()
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

        Matches both name_ru AND name_en against channel title (lowercase).
        No minimum length filter — short city names (Уфа, Пермь) are matched.
        Channels with existing channel_cities entries get additional cities
        if new matches are found (previously skipped).
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

            channels = (await session.execute(
                sa_select(CatalogChannel).where(
                    CatalogChannel.auto_matched_country_id.isnot(None),
                    CatalogChannel.auto_matched_city_id.is_(None),
                    CatalogChannel.title.isnot(None),
                    CatalogChannel.is_ignored == False,
                )
            )).scalars().all()

        # Build search index: (city_id, country_id) → [search_names]
        # Use BOTH name_ru AND name_en for each city
        country_cities: dict[int, list[tuple[int, str]]] = {}
        for c in cities:
            names = []
            if c.name_ru:
                names.append(c.name_ru.lower())
            if c.name_en and c.name_en.lower() != (c.name_ru or "").lower():
                names.append(c.name_en.lower())
            for name in names:
                # No minimum length — short names (Уфа, Пермь) are valid
                country_cities.setdefault(c.country_id, []).append((c.id, name))

        tagged = 0
        for ch in channels:
            if ch.auto_matched_country_id not in country_cities:
                continue

            # Search both username and title — many channels have city in @name
            search_text = f"{ch.chat_username.lower()} {ch.title.lower()}"
            city_hits: list[int] = []
            city_scores: dict[int, float] = {}
            seen_city_ids: set[int] = set()

            # Pass 1: exact substring match (name in username or title)
            for city_id, city_name in country_cities[ch.auto_matched_country_id]:
                if city_id in seen_city_ids:
                    continue
                if city_name in search_text:
                    city_hits.append(city_id)
                    city_scores[city_id] = 1.0
                    seen_city_ids.add(city_id)

            # Pass 2: fuzzy match (transliteration variants: Анталья/Анталия)
            if not city_hits:
                from difflib import SequenceMatcher
                import re
                search_words = re.split(r"[\s,./|()\[\]{}«»—–_-]+", search_text)
                search_words = [w for w in search_words if len(w) >= 3]

                for city_id, city_name in country_cities[ch.auto_matched_country_id]:
                    if city_id in seen_city_ids:
                        continue
                    threshold = 0.95 if len(city_name) < 5 else 0.85
                    for word in search_words:
                        score = SequenceMatcher(None, city_name, word).ratio()
                        if score >= threshold:
                            city_hits.append(city_id)
                            city_scores[city_id] = score
                            seen_city_ids.add(city_id)
                            logger.info(
                                "Fuzzy match: '%s' vs '%s' in @%s (score: %.2f)",
                                city_name, word, ch.chat_username, score,
                            )
                            break

            unique = list(dict.fromkeys(city_hits))
            if not unique:
                continue
            match_score = min(city_scores[c] for c in unique)
            needs_review = match_score < settings.review_score_threshold

            if len(unique) == 1:
                async with async_session_factory() as s:
                    await s.execute(
                        sa_update(CatalogChannel)
                        .where(CatalogChannel.id == ch.id)
                        .values(auto_matched_city_id=unique[0], match_score=match_score, needs_review=needs_review)
                    )
                    await s.commit()
                tagged += 1
            else:
                async with async_session_factory() as s:
                    # Clear old entries, insert all matched cities
                    await s.execute(
                        sa_delete(ChannelCity).where(ChannelCity.channel_id == ch.id)
                    )
                    for city_id in unique:
                        s.add(ChannelCity(channel_id=ch.id, city_id=city_id))
                    await s.execute(
                        sa_update(CatalogChannel)
                        .where(CatalogChannel.id == ch.id)
                        .values(auto_matched_city_id=unique[0], match_score=match_score, needs_review=needs_review)
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
            compute_content_hash, rebuild_subscription_cache,
        )
        from app.db.models import CatalogChannel, ChannelCity, Segment
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

            if ch is not None:
                channel_country_id = ch.auto_matched_country_id
                channel_city_id = ch.auto_matched_city_id
                effective_city_ids = {channel_city_id} if channel_city_id else set()
                cc_rows = (await session.execute(
                    sa_select(ChannelCity.city_id).where(ChannelCity.channel_id == ch.id)
                )).scalars().all()
                effective_city_ids.update(cc_rows)
            else:
                # Channel not in catalog (user-added via watched_chats) — no geo
                # metadata exists. Geo filters are skipped entirely below:
                # subscriptions match by segment alone.
                channel_country_id = None
                effective_city_ids = set()

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

        message_lower = message_text.lower()
        message_lemma = _lemmatize_text(message_lower)

        for user in users:
            subscriptions = user.get("subscriptions", [])
            personal_kws = user.get("keyword_texts", [])
            lang = user.get("lang", "ru")

            interested = False
            match_type = None  # "segment" or "keyword"

            # ── Segment branch (Вариант А) ──
            # Geo filters apply only to catalog channels (ch found); user-added
            # channels have no geo metadata → match by segment alone.
            # Skipped for keyword_only messages (matched_segment_ids empty).
            if matched_segment_ids:
                for sub in subscriptions:
                    if ch is not None:
                        if sub["country_id"] != channel_country_id:
                            continue
                        if sub.get("city_ids") and effective_city_ids:
                            if not (effective_city_ids & set(sub["city_ids"])):
                                continue
                    if sub["segment_id"] in matched_segment_ids:
                        interested = True
                        match_type = "segment"
                        break

            # ── Personal keyword branch (Вариант Б) ──
            # Works unconditionally (spec §5а): no subscription required,
            # no geo filtering. Word-boundary + lemma matching (A1.4).
            if not interested and personal_kws:
                if any(
                    _personal_keyword_hits(kw.lower(), message_lower, message_lemma)
                    for kw in personal_kws
                ):
                    interested = True
                    match_type = "keyword"

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
                "content_hash": compute_content_hash(chat_username, message_text),
                "is_urgent": is_urgent,
                "matched_segments": matched_names,
            })

    # ═══════════════ KEYWORD LOADING ═══════════════

    async def _load_keywords(self) -> tuple[dict, list, dict]:
        """Load all segment keywords from DB into memory.
        
        Returns (keyword_map, universal_stops, domain_word_map).
        domain_word_map: {slug: [specific words]} — used by reality filter
        to skip LLM when no domain-specific word appears in the text.
        """
        async with async_session_factory() as session:
            result = await session.execute(
                select(SegmentKeyword).where(SegmentKeyword.is_active == True)
            )
            keywords = result.scalars().all()

        async with async_session_factory() as session:
            seg_result = await session.execute(select(Segment))
            segments = {s.id: s.slug for s in seg_result.scalars().all()}

        keyword_map: dict[str, dict[str, list[str]]] = {}
        domain_word_map: dict[str, list[str]] = {}
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
            # Build domain word map from synonyms (specific domain words)
            if kw.keyword_type == "synonym":
                if slug not in domain_word_map:
                    domain_word_map[slug] = []
                domain_word_map[slug].append(kw.text.lower())

        logger.info(
            "Loaded %d keywords across %d segments, %d universal stops, %d domain words",
            len(keywords), len(keyword_map), len(universal_stops),
            sum(len(v) for v in domain_word_map.values()),
        )
        return keyword_map, universal_stops, domain_word_map

    async def _load_personal_keywords(self) -> list[str]:
        """Load all active personal user keywords (Вариант Б).

        A flat deduplicated list across all users — used by _poll_channel to
        decide whether a message with no segment match still needs dispatch.
        Per-user filtering happens later in _dispatch. Reloaded every
        KEYWORD_RELOAD by _maintenance_loop.
        """
        from app.db.models import Keyword

        async with async_session_factory() as session:
            rows = await session.execute(
                select(Keyword.text).where(Keyword.is_active == True).distinct()
            )
            keywords = [
                text.strip().lower()
                for (text,) in rows.all()
                if text and text.strip()
            ]

        logger.info("Loaded %d personal keywords", len(keywords))
        return keywords

    def _matches_personal_keyword(self, text: str) -> bool:
        """Check text against all active personal keywords (word-boundary + lemma)."""
        if not self._personal_keywords:
            return False
        text_lower = text.lower()
        text_lemma = _lemmatize_text(text_lower)
        return any(
            _personal_keyword_hits(kw, text_lower, text_lemma)
            for kw in self._personal_keywords
        )

    async def _load_channel_segments(self) -> None:
        """Pre-tag channels with segments based on their titles."""
        try:
            from app.db.models import CatalogChannel

            async with async_session_factory() as session:
                channels = (await session.execute(
                    select(CatalogChannel.chat_username, CatalogChannel.title)
                    .where(CatalogChannel.is_ignored == False)
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
                await redis.aclose()
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
            await redis.aclose()
        except Exception:
            pass

    @staticmethod
    async def _log_llm_decision(
        chat_username: str, message_id: int, message_text: str,
        rule_segments: list[str], llm_result,
    ) -> None:
        """Log LLM decision to DB for shadow monitoring and fine-tune dataset."""
        try:
            from app.db.session import async_session_factory

            masked = sanitize_text(message_text)
            async with async_session_factory() as sess:
                decision = LLMDecision(
                    chat_username=chat_username,
                    message_id=message_id,
                    message_text_masked=masked,
                    rule_segments=rule_segments,
                    llm_verdict=llm_result.verdict,
                    llm_segments=llm_result.relevant_segments or [],
                    llm_reason=llm_result.reason,
                    certainty=llm_result.certainty,
                    llm_mode=settings.llm_mode,
                    prompt_tokens=llm_result.prompt_tokens or None,
                    completion_tokens=llm_result.completion_tokens or None,
                    total_tokens=llm_result.total_tokens or None,
                )
                sess.add(decision)
                await sess.commit()
        except Exception as e:
            logger.warning("Failed to log LLM decision: %s", e)


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
