"""Notification sender: reads from Redis queue, sends via Bot API with throttle."""

import asyncio
import html
import json
import logging
from datetime import datetime, timezone

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.config import settings
from app.locales import get_text, normalize_language
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


def _is_numeric_chat(chat: str) -> bool:
    """True for private-group peer ids stored as «-100…» (no public @username)."""
    return chat.lstrip("-").isdigit()


def _chat_label(chat: str, title: str | None) -> str:
    """Human-readable chat name: title preferred over the raw «-100…» id.

    Mirrors the «My channels» screen convention (channels.py:_channel_label):
    private groups added by internal id are shown by title; a bare «@-100…» is
    a last resort only when no title is known.
    """
    title = (title or "").strip()
    if title:
        return title
    return f"группа {chat}" if _is_numeric_chat(chat) else f"@{chat}"


def _chat_link(chat: str, msg_id: int) -> str | None:
    """t.me link to the message, or None when it cannot be linked.

    Private groups (numeric peer id) use the t.me/c/ form; a link like
    «t.me/-100…» is invalid and would render as broken text.
    """
    if _is_numeric_chat(chat):
        if chat.startswith("-100"):
            return f"https://t.me/c/{chat[4:]}/{msg_id}"
        return None
    return f"https://t.me/{chat}/{msg_id}"


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

        # A cached paid plan must not expose contacts after its exact expiry.
        expired_in_cache = False
        expires_raw = payload.get("plan_expires_at")
        if payload.get("plan") in ("trial", "start", "pro", "business") and expires_raw:
            try:
                expires_at = datetime.fromisoformat(expires_raw)
                if expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=timezone.utc)
                if expires_at <= datetime.now(timezone.utc):
                    payload["plan"] = "free"
                    expired_in_cache = True
            except (TypeError, ValueError):
                logger.warning("Invalid plan_expires_at for user %d", user_id)

        # Дневной лимит уведомлений отменён (#81): метрика ценности — широта
        # покрытия (направления × гео), а не объём доставок. Счётчик sent
        # сохраняется для статистики (T5.1) и end-of-day отчётов.
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        matched = payload.get("matched_segments", [])
        seg_label = ", ".join(m.get("title", "") for m in matched) if matched else None
        meta = {
            "chat_username": payload.get("chat_username"), "sender": payload.get("sender"),
            "segment": seg_label, "message_id": payload.get("message_id"),
        }

        # Free lifecycle: only two hidden lead teasers on days 0/3/7/14.
        # All matches are still counted by the poller for the end-of-day report.
        if payload.get("plan", "free") == "free":
            if expired_in_cache:
                from app.lifecycle import increment_lifecycle_matches
                await increment_lifecycle_matches(user_id)
            from app.lifecycle import claim_free_teaser
            allowed, lifecycle_day = await claim_free_teaser(user_id, message_hash)
            if not allowed:
                logger.info("Free lead suppressed for user %d on lifecycle day %d", user_id, lifecycle_day)
                return

        # T5.3: digest-режим — не-срочные откладываем в буфер (flush по расписанию),
        # срочные (🔥) всегда доставляем мгновенно. mark_sent сразу — для дедупа.
        if payload.get("plan", "free") != "free" and payload.get("digest_mode", "instant") != "instant" and not payload.get("is_urgent"):
            from app.cache.subscription_cache import buffer_digest
            await buffer_digest(user_id, payload)
            await mark_sent(user_id, message_hash, False, content_hash=content_hash, meta=meta)
            return

        if payload.get("plan", "free") == "free":
            token = message_hash[:12]
            payload["_lead_token"] = token
            from app.analytics import store_lead_paywall_context
            await store_lead_paywall_context(user_id, token, (payload.get("text") or "")[:160])

        # Build and send message
        text = self._format_notification(payload)
        kb = self._build_keyboard(payload)

        delivered = await self._deliver_with_retry(payload, text, kb)
        if not delivered:
            return

        await mark_sent(user_id, message_hash, payload.get("is_urgent", False),
                       content_hash=content_hash, meta=meta)
        await increment_daily_stats(user_id, today, "sent")
        from app.analytics import record_once_event
        await record_once_event("first_lead_delivered", user_id=user_id, language=payload.get("lang"), plan=payload.get("plan"), context={"lead_id": message_hash})

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
        lang = normalize_language(payload.get("lang"))
        chat = payload.get("chat_username", "unknown") or "unknown"
        msg_id = payload.get("message_id", 0)
        sender = payload.get("sender", None)
        sender = html.escape(sender) if sender else None
        text_preview = html.escape((payload.get("text", "") or "")[:500])
        is_free = payload.get("plan", "free") == "free"

        # Chat title preferred over the raw «-100…» peer id (private groups).
        label = html.escape(_chat_label(chat, payload.get("chat_title")))
        link = _chat_link(chat, msg_id)
        link = html.escape(link) if link else None

        msg = f"{urgency}{get_text(lang, 'lead_title')}\n\n"
        msg += f"{text_preview}\n\n"
        if is_free:
            # D1 (DECISIONS #79): Free — no links at all. Chat name as plain
            # text, sender hidden entirely; the paywall line below is honest.
            msg += get_text(lang, "lead_chat", chat=label)
            msg += "\n\n" + get_text(lang, "lead_hidden")
        else:
            msg += get_text(lang, "lead_chat", chat=(f"<a href='{link}'>{label}</a>" if link else label))
            if sender:
                msg += get_text(lang, "lead_sender", sender=sender)
            else:
                # No public @username → no direct DM path (Telegram privacy).
                # Show the author's name (if any) so the lead isn't anonymous,
                # then state honestly that contacts are hidden.
                sender_name = payload.get("sender_name")
                if sender_name:
                    msg += get_text(lang, "lead_sender_name", name=html.escape(sender_name))
                msg += get_text(lang, "lead_contact_hidden")

        # Add category label(s)
        matched = payload.get("matched_segments", [])
        if matched:
            labels = ", ".join(
                html.escape(f"{m['emoji']} {m['title']}" if m["emoji"] else m["title"])
                for m in matched
            )
            msg += "\n\n" + get_text(lang, "lead_tags", labels=labels)

        return msg

    def _build_keyboard(self, payload: dict) -> InlineKeyboardMarkup:
        """Build notification keyboard with feedback buttons."""
        is_free = payload.get("plan", "free") == "free"
        lang = normalize_language(payload.get("lang"))
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
                    text=get_text(lang, "lead_btn_unlock", price=settings.price_start_monthly_usd),
                    callback_data=f"lead:unlock:{payload.get('_lead_token', 'unknown')}"),
            ])
        else:
            buttons = []
            chat_link = _chat_link(chat, msg_id) if chat else None
            if chat_link:
                buttons.append(InlineKeyboardButton(text=get_text(lang, "lead_btn_chat"), url=chat_link))
            if sender:
                buttons.append(InlineKeyboardButton(text=get_text(lang, "lead_btn_sender"), url=f"https://t.me/{sender}"))
            if buttons:
                rows.append(buttons)

        return InlineKeyboardMarkup(inline_keyboard=rows)
