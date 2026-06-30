"""Telethon-based channel poller using userbot pool."""

import asyncio
import logging
import random

from telethon.errors import FloodWaitError
from telethon.tl.types import Message

from app.userbot.classifier import classify_message
from app.userbot.pool import UserbotPool
from app.userbot.rate_limiter import limiter
from app.db.session import async_session_factory
from app.db.models import SegmentKeyword, Segment
from sqlalchemy import select

logger = logging.getLogger(__name__)


class ChannelPoller:
    """Polls Telegram channels using a pool of userbot accounts."""

    def __init__(self):
        self.pool = UserbotPool()
        self._keyword_map: dict[str, dict[str, list[str]]] = {}

    async def start(self):
        """Initialize pool and load keywords. Idempotent — safe to call multiple times."""
        if not self.pool.accounts:
            await self.pool.initialize()
        if not self._keyword_map:
            self._keyword_map = await self._load_keywords()

    async def poll_channels(self, channels: list[str]):
        """Distribute and poll channels across pool accounts."""
        # Redistribute channels across pool
        await self.pool.redistribute_channels(channels)

        # Poll accounts sequentially to avoid concurrent API bursts
        for account in self.pool.accounts:
            if not account.is_healthy:
                continue
            acc_channels = [
                ch for ch, aid in self.pool._channel_assignments.items()
                if aid == account.account_id
            ]
            if acc_channels:
                await self._poll_account_channels(account, acc_channels)

    async def _poll_account_channels(self, account, channels: list[str]):
        """Poll channels assigned to a specific account."""
        # Aggressive rate limit: max 10 channels per cycle
        max_per_cycle = 10
        channels_to_poll = channels[:max_per_cycle]

        for channel in channels_to_poll:
            # Check circuit breaker before each channel
            await limiter.wait_if_circuit_open()

            try:
                await self._poll_channel(account, channel.strip().lstrip("@"))
            except FloodWaitError as e:
                logger.warning("FloodWait for account %d: %ds", account.account_id, e.seconds)
                await limiter.report_flood_wait(e.seconds, context=f"poller:@{channel}")
                await asyncio.sleep(e.seconds)
            except Exception:
                logger.exception("Error polling channel %s on account %d", channel, account.account_id)

    async def _poll_channel(self, account, channel_username: str):
        """Poll a single channel using a specific account."""
        try:
            await limiter.acquire()
            entity = await account.get_entity(channel_username)
        except FloodWaitError:
            raise  # Handled by _poll_account_channels
        except Exception as e:
            logger.warning("Account %d cannot access @%s: %s", account.account_id, channel_username, e)
            return

        await limiter.acquire()
        messages = await account.get_messages(entity, limit=3)
        if not messages:
            return

        for msg in messages:
            if not isinstance(msg, Message) or not msg.message:
                continue

            result = classify_message(msg.message, self._keyword_map)
            if result.matched_segments:
                urgency = "🔥 " if result.is_urgent else ""
                logger.info(
                    "%s[Acc %d] Match in @%s (msg %d): segments=%s",
                    urgency, account.account_id, channel_username, msg.id, result.matched_segments,
                )
                await self._dispatch(
                    chat_username=channel_username,
                    message_text=msg.message,
                    message_id=msg.id,
                    matched_segments=result.matched_segments,
                    is_urgent=result.is_urgent,
                    sender=getattr(msg.sender, "username", None) if msg.sender else None,
                )
            else:
                # Log unmatched messages for statistics analysis
                await self._log_unmatched(channel_username, msg.message, msg.id)

    async def _dispatch(self, chat_username, message_text, message_id, matched_segments, is_urgent, sender):
        """Find interested users matching BOTH segment AND geo, push to queue."""
        from app.cache.subscription_cache import (
            get_interested_users, push_notification, build_message_hash, rebuild_subscription_cache,
        )
        from app.db.models import CatalogChannel, Segment
        from sqlalchemy import select as sa_select

        message_hash = build_message_hash(chat_username, message_id)
        users = await get_interested_users(chat_username)

        if not users:
            await rebuild_subscription_cache(chat_username)
            users = await get_interested_users(chat_username)

        # Get channel's country/city
        async with async_session_factory() as session:
            ch = (await session.execute(
                sa_select(CatalogChannel).where(CatalogChannel.chat_username == chat_username)
            )).scalar_one_or_none()
        channel_country_id = ch.auto_matched_country_id if ch else None
        channel_city_id = ch.auto_matched_city_id if ch else None

        # Map matched segment slugs → IDs
        async with async_session_factory() as session:
            segs = (await session.execute(sa_select(Segment))).scalars().all()
        seg_by_slug = {s.slug: s.id for s in segs}
        matched_segment_ids = {seg_by_slug.get(s) for s in matched_segments}
        matched_segment_ids.discard(None)

        for user in users:
            subscriptions = user.get("subscriptions", [])
            personal_kws = user.get("keyword_texts", [])

            # Check geo + segment match
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

            # Personal keywords also respect geo filter
            if not interested:
                for sub in subscriptions:
                    if sub["country_id"] != channel_country_id:
                        continue
                    if sub.get("city_ids") and channel_city_id:
                        if channel_city_id not in sub["city_ids"]:
                            continue
                    if personal_kws and any(kw.lower() in message_text.lower() for kw in personal_kws):
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

    @staticmethod
    async def _log_unmatched(chat_username: str, text: str, msg_id: int) -> None:
        """Log unmatched messages to Redis for later statistics analysis.

        Stores last 10000 unmatched messages with chat source and timestamp.
        """
        try:
            import json
            from datetime import datetime, timezone
            from app.cache import get_redis

            redis = await get_redis()
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
            pass  # Never let stats collection break the main loop

    async def _load_keywords(self) -> dict[str, dict[str, list[str]]]:
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
        for kw in keywords:
            if kw.segment_id is None:
                continue
            slug = segments.get(kw.segment_id)
            if not slug:
                continue
            if slug not in keyword_map:
                keyword_map[slug] = {"demand": [], "stop": [], "synonym": []}
            keyword_map[slug][kw.keyword_type].append(kw.text)

        logger.info("Loaded %d keywords across %d segments", len(keywords), len(keyword_map))
        return keyword_map

    async def run_forever(self):
        """Main loop: periodically poll all watched channels via pool."""
        await self.start()

        # Start health check in background
        asyncio.create_task(self.pool.health_check_loop())

        while True:
            async with async_session_factory() as session:
                # User-specific watched channels
                from app.db.models import WatchedChat, CatalogChannel
                watched_result = await session.execute(
                    select(WatchedChat.chat_username).where(
                        WatchedChat.status == "approved"
                    ).distinct()
                )
                # Global catalog channels
                catalog_result = await session.execute(
                    select(CatalogChannel.chat_username)
                )
                channels = [row[0] for row in watched_result.all()]
                channels += [row[0] for row in catalog_result.all()]
                # Deduplicate
                channels = list(set(channels))

            if channels:
                await self.poll_channels(channels)

            await asyncio.sleep(600)  # Poll every 10 minutes
