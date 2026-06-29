"""Telethon-based channel poller. Reads messages from watched channels without joining."""

import asyncio
import logging
from datetime import datetime, timezone

from telethon import TelegramClient
from telethon.errors import FloodWaitError
from telethon.tl.types import Message

from app.config import settings
from app.userbot.classifier import classify_message
from app.db.session import async_session_factory
from app.db.models import SegmentKeyword
from sqlalchemy import select

logger = logging.getLogger(__name__)


class ChannelPoller:
    """Polls Telegram channels for new messages using Telethon userbot."""

    def __init__(self):
        self.client = TelegramClient(
            "/app/sessions/userbot",
            settings.userbot_api_id,
            settings.userbot_api_hash,
        )

    async def start(self):
        """Connect and authorize the userbot."""
        await self.client.start(phone=settings.userbot_phone or None)
        logger.info("Userbot authorized as %s", await self.client.get_me())

    async def poll_channels(self, channels: list[str]):
        """
        Poll a list of channel usernames for recent messages.

        Args:
            channels: List of channel usernames (with or without @).
        """
        # Load segment keywords from DB into memory
        keyword_map = await self._load_keywords()

        for channel in channels:
            try:
                await self._poll_channel(channel.strip().lstrip("@"), keyword_map)
            except FloodWaitError as e:
                logger.warning("FloodWait for %s: %ds", channel, e.seconds)
                await asyncio.sleep(e.seconds)
            except Exception:
                logger.exception("Error polling channel %s", channel)

    async def _poll_channel(self, channel_username: str, keyword_map: dict[str, dict[str, list[str]]]):
        """Poll a single channel for recent messages."""
        try:
            entity = await self.client.get_entity(channel_username)
        except Exception:
            logger.warning("Cannot access channel: %s", channel_username)
            return

        # Get last 10 messages (in production: tier-based polling, see ROADMAP.md)
        messages = await self.client.get_messages(entity, limit=10)
        if not messages:
            return

        for msg in messages:
            if not isinstance(msg, Message) or not msg.message:
                continue

            result = classify_message(msg.message, keyword_map)
            if result.matched_segments:
                urgency = "🔥 " if result.is_urgent else ""
                logger.info(
                    "%sMatch in @%s (msg %d): segments=%s",
                    urgency, channel_username, msg.id, result.matched_segments,
                )
                await self._dispatch(
                    chat_username=channel_username,
                    message_text=msg.message,
                    message_id=msg.id,
                    matched_segments=result.matched_segments,
                    is_urgent=result.is_urgent,
                    sender=getattr(msg.sender, "username", None) if msg.sender else None,
                )

    async def _dispatch(
        self,
        chat_username: str,
        message_text: str,
        message_id: int,
        matched_segments: list[str],
        is_urgent: bool,
        sender: str | None,
    ):
        """Find interested users and push notifications to queue."""
        from app.cache.subscription_cache import (
            get_interested_users,
            push_notification,
            build_message_hash,
        )

        message_hash = build_message_hash(chat_username, message_id)
        users = await get_interested_users(chat_username)

        # If cache is empty for this chat, rebuild it
        if not users:
            from app.cache.subscription_cache import rebuild_subscription_cache
            await rebuild_subscription_cache(chat_username)
            users = await get_interested_users(chat_username)

        for user in users:
            # Check if user is interested in any matched segment
            user_segment_ids = set(user.get("segment_ids", []))
            # Also check personal keywords
            personal_kws = user.get("keyword_texts", [])

            interested = bool(
                user_segment_ids  # if user has segment subs, all segments match
                or any(kw.lower() in message_text.lower() for kw in personal_kws)
            )

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

    async def _load_keywords(self) -> dict[str, dict[str, list[str]]]:
        """Load all segment keywords from DB into memory."""
        async with async_session_factory() as session:
            result = await session.execute(
                select(SegmentKeyword).where(SegmentKeyword.is_active == True)
            )
            keywords = result.scalars().all()

        # Also fetch segment slugs
        from app.db.models import Segment
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
        """Main loop: periodically poll all watched channels."""
        await self.start()

        while True:
            async with async_session_factory() as session:
                from app.db.models import WatchedChat
                result = await session.execute(
                    select(WatchedChat.chat_username).where(
                        WatchedChat.status == "approved"
                    ).distinct()
                )
                channels = [row[0] for row in result.all()]

            if channels:
                await self.poll_channels(channels)

            # Sleep between polling rounds (smart polling in Phase 9)
            await asyncio.sleep(60)
