"""Notification sender: reads from Redis queue, sends via Bot API with throttle."""

import asyncio
import logging

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.config import settings
from app.cache.subscription_cache import (
    pop_notification,
    mark_sent,
    is_duplicate,
    is_content_duplicate,
    check_daily_limit,
    increment_daily_stats,
)

logger = logging.getLogger(__name__)


class NotificationSender:
    """Consumes notification queue and sends via Bot API."""

    def __init__(self):
        self.bot = Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        self.throttle_interval = 1 / settings.sender_throttle_per_second  # 0.04s per msg

    async def run(self):
        """Main loop: pop from queue and send."""
        logger.info("Sender started (throttle: %d/sec)", settings.sender_throttle_per_second)

        while True:
            payload = await pop_notification(timeout=5)
            if payload is None:
                await asyncio.sleep(0.5)
                continue

            await self._send_notification(payload)
            await asyncio.sleep(self.throttle_interval)

    async def _send_notification(self, payload: dict):
        """Send a single notification to a user."""
        user_id = payload["user_id"]
        telegram_id = payload["telegram_id"]
        message_hash = payload["message_hash"]
        plan = payload.get("plan", "free")

        # Deduplication by message identity
        if await is_duplicate(user_id, message_hash):
            return

        # Content dedup: suppress identical text within 24h
        content_hash = payload.get("content_hash")
        if content_hash and await is_content_duplicate(user_id, content_hash):
            logger.info(
                "Duplicate content suppressed for user %d in @%s",
                user_id, payload.get("chat_username", "?"),
            )
            return

        # Daily limit
        from datetime import datetime, timezone
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        max_per_day = (
            settings.notifications_per_day_free
            if plan == "free"
            else settings.notifications_per_day_pro
        )
        if plan == "business" or plan == "trial":
            max_per_day = 999999

        if await check_daily_limit(user_id, today, max_per_day):
            # Limit reached → send limit warning once
            from app.cache.subscription_cache import LIMIT_REACHED_KEY
            from app.cache import get_redis
            redis = await get_redis()
            limit_key = LIMIT_REACHED_KEY.format(user_id=user_id, date=today)
            already_warned = await redis.get(limit_key)
            await redis.aclose()

            if not already_warned:
                redis = await get_redis()
                await redis.set(limit_key, "1")
                await redis.aclose()
                await self._send_limit_warning(telegram_id, payload.get("lang", "ru"))
            return

        # Build and send message
        text = self._format_notification(payload)
        kb = self._build_keyboard(payload)

        try:
            await self.bot.send_message(telegram_id, text, reply_markup=kb)
            await mark_sent(user_id, message_hash, payload.get("is_urgent", False),
                           content_hash=content_hash)
            await increment_daily_stats(user_id, today, "sent")
        except Exception:
            logger.exception("Failed to send notification to user %d", user_id)

    def _format_notification(self, payload: dict) -> str:
        """Format notification text."""
        urgency = "🔥 " if payload.get("is_urgent") else ""
        chat = payload.get("chat_username", "unknown")
        msg_id = payload.get("message_id", 0)
        sender = payload.get("sender", None)
        text_preview = (payload.get("text", "") or "")[:500]
        is_free = payload.get("plan", "free") == "free"

        msg = f"{urgency}🎯 <b>Я нашел нового клиента! | Lead Hunter AI</b>\n\n"
        msg += f"{text_preview}\n\n"
        msg += f"💬 <a href='https://t.me/{chat}/{msg_id}'>@{chat}</a>"
        if sender:
            msg += f" от <a href='https://t.me/{sender}'>@{sender}</a>"

        if is_free:
            msg += "\n\n🔒 Контакты скрыты на Free-тарифе.\n💰 Активируй подписку чтобы видеть отправителя."

        # Add category label(s)
        matched = payload.get("matched_segments", [])
        if matched:
            labels = ", ".join(
                f"{m['emoji']} {m['title']}" if m["emoji"] else m["title"]
                for m in matched
            )
            msg += f"\n\n🏷 {labels}"

        return msg

    def _build_keyboard(self, payload: dict) -> InlineKeyboardMarkup:
        """Build notification keyboard with feedback buttons."""
        is_free = payload.get("plan", "free") == "free"
        chat = payload.get("chat_username", "")
        msg_id = payload.get("message_id", 0)
        sender = payload.get("sender", None)

        rows = []

        # Feedback row — always present
        fb_data = f"fb:{chat}:{msg_id}"
        rows.append([
            InlineKeyboardButton(text="👍", callback_data=f"{fb_data}:relevant"),
            InlineKeyboardButton(text="👎", callback_data=f"{fb_data}:not_relevant"),
        ])

        if is_free:
            rows.append([
                InlineKeyboardButton(text="💰 Активировать подписку", callback_data="menu:plan"),
            ])
            if chat:
                rows.append([
                    InlineKeyboardButton(text="💬 Чат", url=f"https://t.me/{chat}/{msg_id}"),
                ])
        else:
            buttons = []
            if chat:
                buttons.append(InlineKeyboardButton(text="💬 Чат", url=f"https://t.me/{chat}/{msg_id}"))
            if sender:
                buttons.append(InlineKeyboardButton(text="💬 Написать", url=f"https://t.me/{sender}"))
            if buttons:
                rows.append(buttons)

        return InlineKeyboardMarkup(inline_keyboard=rows)

    async def _send_limit_warning(self, telegram_id: int, lang: str):
        """Send daily limit reached warning."""
        text = (
            "⚠️ Лимит уведомлений на сегодня исчерпан.\n\n"
            "На Free-тарифе — 50 уведомлений в день.\n"
            "💰 Перейди на Pro или Business чтобы снять лимит."
            if lang == "ru"
            else
            "⚠️ Daily notification limit reached.\n\n"
            "Free plan: 50 notifications/day.\n"
            "💰 Upgrade to Pro or Business for unlimited."
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="💰 Тариф и оплата" if lang == "ru" else "💰 Plan & payment",
                callback_data="menu:plan",
            )],
        ])
        try:
            await self.bot.send_message(telegram_id, text, reply_markup=kb)
        except Exception:
            pass
