"""Notification sender: reads from Redis queue, sends via Bot API with throttle."""

import asyncio
import html
import json
import logging

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.config import settings
from app.cache.subscription_cache import (
    pop_notification,
    mark_sent,
    is_duplicate,
    is_content_duplicate,
    increment_daily_stats,
    QUEUE_DEAD_LETTER,
)

logger = logging.getLogger(__name__)

# Backoff delays between delivery attempts (DECISIONS #26): 1 try + 3 retries.
RETRY_SCHEDULE = (None, 1, 4, 9)


LATENCY_BUCKETS = (
    (300, "lt5m"), (1800, "lt30m"), (7200, "lt2h"), (float("inf"), "ge2h"),
)


async def record_latency(msg_ts: float | None) -> None:
    """B6: дистрибуция «время сообщения → доставка» — данные для решения по
    event-push (fable_core_plan C1). Ключи stats:latency:{date}:{bucket},
    TTL 14д. Ошибки Redis не мешают доставке."""
    if not msg_ts:
        return
    import time

    lag = time.time() - msg_ts
    bucket = next(name for limit, name in LATENCY_BUCKETS if lag < limit)
    date = time.strftime("%Y-%m-%d", time.gmtime())
    try:
        from app.cache import get_redis
        redis = await get_redis()
        key = f"stats:latency:{date}:{bucket}"
        pipe = redis.pipeline()
        pipe.incrby(key, 1)
        pipe.expire(key, 14 * 86400)
        await pipe.execute()
    except Exception:
        logger.warning("Latency stat write failed", exc_info=True)


async def push_dead_letter(payload: dict) -> None:
    """Store an undeliverable notification in the dead-letter queue."""
    from app.cache import get_redis

    redis = await get_redis()
    await redis.lpush(QUEUE_DEAD_LETTER, json.dumps(payload, default=str))


async def mark_user_blocked(user_id: int) -> None:
    """403 from Bot API — the user blocked the bot. Stop sending to them."""
    from datetime import datetime, timezone
    from sqlalchemy import update
    from app.db.session import async_session_factory
    from app.db.models import User

    async with async_session_factory() as session:
        await session.execute(
            update(User)
            .where(User.id == user_id)
            .values(is_blocked_bot=True, blocked_bot_at=datetime.now(timezone.utc))
        )
        await session.commit()

    from app.cache.subscription_cache import invalidate_all_subscription_caches
    await invalidate_all_subscription_caches()


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
        message_hash = payload["message_hash"]

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

        # Дневной лимит уведомлений отменён (#81): метрика ценности — широта
        # покрытия (направления × гео), а не объём доставок. Счётчик sent
        # сохраняется для статистики (T5.1) и end-of-day отчётов.
        from datetime import datetime, timezone
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # Build and send message
        text = self._format_notification(payload)
        kb = self._build_keyboard(payload)

        delivered = await self._deliver_with_retry(payload, text, kb)
        if not delivered:
            return

        matched = payload.get("matched_segments", [])
        seg_label = ", ".join(m.get("title", "") for m in matched) if matched else None
        await mark_sent(user_id, message_hash, payload.get("is_urgent", False),
                       content_hash=content_hash, meta={
                           "chat_username": payload.get("chat_username"),
                           "sender": payload.get("sender"),
                           "segment": seg_label,
                           "message_id": payload.get("message_id"),
                       })
        await increment_daily_stats(user_id, today, "sent")
        await record_latency(payload.get("msg_ts"))

    async def _deliver_with_retry(self, payload: dict, text: str, kb) -> bool:
        """Deliver with the DECISIONS #26 policy.

        403 → mark user blocked, stop. 429 → sleep(retry_after), retry.
        Anything else → backoff retries (1s/4s/9s), then dead-letter queue.
        Returns True only on actual delivery.
        """
        telegram_id = payload["telegram_id"]
        user_id = payload["user_id"]

        for delay in RETRY_SCHEDULE:
            if delay is not None:
                await asyncio.sleep(delay)
            try:
                await self.bot.send_message(telegram_id, text, reply_markup=kb)
                return True
            except TelegramForbiddenError:
                logger.info(
                    "User %d blocked the bot — marking is_blocked_bot", user_id,
                )
                await mark_user_blocked(user_id)
                return False
            except TelegramRetryAfter as e:
                logger.warning(
                    "429 for user %d — sleeping %ds before retry",
                    user_id, e.retry_after,
                )
                await asyncio.sleep(e.retry_after)
            except Exception as e:
                logger.warning(
                    "Send attempt failed for user %d: %s: %s",
                    user_id, type(e).__name__, e,
                )

        logger.error(
            "Notification for user %d undeliverable after %d attempts — dead-letter",
            user_id, len(RETRY_SCHEDULE),
        )
        await push_dead_letter(payload)
        return False

    def _format_notification(self, payload: dict) -> str:
        """Format notification text.

        All user-originated values (lead text, usernames, segment titles) are
        HTML-escaped — the message is sent with ParseMode.HTML, and raw «<»,
        «>», «&» would make Telegram reject the whole request (lost lead).
        """
        urgency = "🔥 " if payload.get("is_urgent") else ""
        chat = html.escape(payload.get("chat_username", "unknown") or "unknown")
        msg_id = payload.get("message_id", 0)
        sender = payload.get("sender", None)
        sender = html.escape(sender) if sender else None
        text_preview = html.escape((payload.get("text", "") or "")[:500])
        is_free = payload.get("plan", "free") == "free"

        msg = f"{urgency}🎯 <b>Я нашел нового клиента! | Lead Hunter AI</b>\n\n"
        msg += f"{text_preview}\n\n"
        if is_free:
            # D1 (DECISIONS #79): Free — no links at all. Chat name as plain
            # text, sender hidden entirely; the paywall line below is honest.
            msg += f"💬 @{chat}"
            msg += "\n\n🔒 Контакты скрыты. Этому клиенту сейчас ответит кто-то другой."
        else:
            msg += f"💬 <a href='https://t.me/{chat}/{msg_id}'>@{chat}</a>"
            if sender:
                msg += f" от <a href='https://t.me/{sender}'>@{sender}</a>"

        # Add category label(s)
        matched = payload.get("matched_segments", [])
        if matched:
            labels = ", ".join(
                html.escape(f"{m['emoji']} {m['title']}" if m["emoji"] else m["title"])
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
            # D1 (DECISIONS #79): no «💬 Чат» button on Free — the link led
            # straight to the lead's message, making the paywall nominal.
            rows.append([
                InlineKeyboardButton(
                    text=f"🎯 Открыть контакты — от ${settings.price_start_monthly_usd}/мес",
                    callback_data="menu:plan"),
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
