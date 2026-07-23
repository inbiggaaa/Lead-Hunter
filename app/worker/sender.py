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
    claim_notification,
    ack_notification,
    fail_notification,
    reclaim_stale_notifications,
    mark_sent,
    is_duplicate,
    is_content_duplicate,
    increment_daily_stats,
    QUEUE_DEAD_LETTER,
)

logger = logging.getLogger(__name__)

# Backoff delays between delivery attempts (DECISIONS #26): 1 try + 3 retries.
RETRY_SCHEDULE = (None, 1, 4, 9)


async def _user_may_receive(user_id: int) -> bool:
    """Defense-in-depth: ban/suspend/blocked users must not receive leads."""
    from app.db.session import async_session_factory
    from app.db.models import User
    from app.cache.subscription_cache import user_is_deliverable

    async with async_session_factory() as session:
        user = await session.get(User, user_id)
        if user is None:
            return True
        return user_is_deliverable(user)


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
        """Main loop: claim → send → ack/fail; periodically reclaim stale claims."""
        logger.info("Sender started (throttle: %d/sec)", settings.sender_throttle_per_second)
        iterations = 0

        while True:
            iterations += 1
            if iterations % 20 == 0:
                try:
                    await reclaim_stale_notifications()
                except Exception:
                    logger.exception("Notification reclaim failed")

            envelope = await claim_notification(timeout=5)
            if envelope is None:
                await asyncio.sleep(0.5)
                continue

            try:
                result = await self._send_notification(envelope)
                if result == "permanent_fail":
                    await fail_notification(envelope, to_dlq=True)
                else:
                    await ack_notification(envelope)
            except Exception:
                logger.exception(
                    "Unexpected sender error for user %s — requeue",
                    (envelope.get("body") or {}).get("user_id"),
                )
                await fail_notification(envelope, to_dlq=False)

            await asyncio.sleep(self.throttle_interval)

    async def _send_notification(self, envelope_or_payload: dict) -> str:
        """Send a single notification. Returns ok | skipped | permanent_fail.

        Accepts either a claimed envelope `{body, ...}` or a bare payload
        (tests / digest helpers).
        """
        if "body" in envelope_or_payload and "attempts" in envelope_or_payload:
            envelope = envelope_or_payload
            payload = envelope["body"]
        else:
            payload = envelope_or_payload
            envelope = {"id": None, "body": payload, "attempts": 0, "claimed_at": None}

        user_id = payload["user_id"]
        message_hash = payload["message_hash"]

        if not await _user_may_receive(user_id):
            logger.info("Skip delivery for undeliverable user %d", user_id)
            return "skipped"

        # Deduplication by message identity
        if await is_duplicate(user_id, message_hash):
            return "skipped"

        from app.cache.subscription_cache import is_digest_inflight
        if await is_digest_inflight(user_id, message_hash):
            logger.info("Digest-inflight skip for user %d hash %s", user_id, message_hash[:12])
            return "skipped"

        # Content dedup: suppress identical text within 24h
        content_hash = payload.get("content_hash")
        if content_hash and await is_content_duplicate(user_id, content_hash):
            logger.info(
                "Duplicate content suppressed for user %d in @%s",
                user_id, payload.get("chat_username", "?"),
            )
            return "skipped"

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
                return "skipped"

        # T5.3: digest — buffer without mark_sent (flush marks after real delivery).
        if payload.get("plan", "free") != "free" and payload.get("digest_mode", "instant") != "instant" and not payload.get("is_urgent"):
            from app.cache.subscription_cache import buffer_digest
            await buffer_digest(user_id, payload)
            return "ok"

        if payload.get("plan", "free") == "free":
            token = message_hash[:12]
            payload["_lead_token"] = token
            from app.analytics import store_lead_paywall_context
            await store_lead_paywall_context(user_id, token, (payload.get("text") or "")[:160])

        # Build and send message
        text = self._format_notification(payload)
        feedback_token = await self._maybe_create_feedback_token(payload)
        kb = self._build_keyboard(payload, feedback_token=feedback_token)

        delivered = await self._deliver_with_retry(envelope, payload, text, kb)
        if not delivered:
            return "permanent_fail"

        await mark_sent(user_id, message_hash, payload.get("is_urgent", False),
                       content_hash=content_hash, meta=meta)
        await increment_daily_stats(user_id, today, "sent")
        from app.analytics import record_once_event
        await record_once_event("first_lead_delivered", user_id=user_id, language=payload.get("lang"), plan=payload.get("plan"), context={"lead_id": message_hash})
        return "ok"

    async def _deliver_with_retry(
        self, envelope: dict, payload: dict, text: str, kb,
    ) -> bool:
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
                if envelope.get("id"):
                    from app.cache.subscription_cache import touch_claim
                    envelope.update(await touch_claim(envelope))
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
        # DLQ is written by fail_notification(to_dlq=True) in the run loop.
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

    async def _maybe_create_feedback_token(self, payload: dict) -> str | None:
        """Create closed-feedback item for testers; fail-open on any error."""
        from app.matching_feedback.domain import (
            FeedbackSnapshot,
            is_matching_feedback_enabled_for,
            mask_message_text,
        )
        from app.matching_feedback.repository import get_or_create_feedback_item

        telegram_id = int(payload.get("telegram_id") or 0)
        if not is_matching_feedback_enabled_for(telegram_id):
            return None
        batch = (settings.matching_feedback_batch or "").strip()
        if not batch:
            return None

        snap = payload.get("matching_feedback_snapshot") or {}
        try:
            delivered = tuple(
                payload.get("matched_segment_slugs")
                or snap.get("delivered_segments")
                or ()
            )
            snapshot = FeedbackSnapshot(
                test_batch=batch,
                user_id=int(payload["user_id"]),
                telegram_id=telegram_id,
                chat_username=str(payload.get("chat_username") or ""),
                message_id=int(payload.get("message_id") or 0),
                message_hash=str(payload.get("message_hash") or ""),
                content_hash=payload.get("content_hash"),
                message_text_masked=mask_message_text(str(payload.get("text") or "")),
                delivered_segments=tuple(str(s) for s in delivered),
                rule_segments=tuple(str(s) for s in (snap.get("rule_segments") or ())),
                reality_segments=tuple(
                    str(s) for s in (snap.get("reality_segments") or delivered)
                ),
                llm_snapshot={
                    "legacy_llm_verdict": snap.get("legacy_llm_verdict"),
                    "legacy_llm_segments": snap.get("legacy_llm_segments") or [],
                    "v2_intent": snap.get("v2_intent"),
                    "v2_segment_verdicts": snap.get("v2_segment_verdicts") or {},
                    "model_name": snap.get("model_name"),
                    "prompt_version": snap.get("prompt_version"),
                    "schema_version": snap.get("schema_version"),
                    "profile_versions": snap.get("profile_versions") or {},
                },
            )
            item = await get_or_create_feedback_item(snapshot)
            return item.public_token
        except Exception as exc:
            logger.warning(
                "matching feedback item create failed (fail-open): %s",
                type(exc).__name__,
            )
            return None

    def _build_keyboard(
        self,
        payload: dict,
        feedback_token: str | None = None,
    ) -> InlineKeyboardMarkup:
        """Build notification keyboard with feedback buttons."""
        is_free = payload.get("plan", "free") == "free"
        lang = normalize_language(payload.get("lang"))
        chat = payload.get("chat_username", "")
        msg_id = payload.get("message_id", 0)
        sender = payload.get("sender", None)

        rows = []

        if feedback_token:
            from app.matching_feedback.domain import encode_feedback_callback

            rows.append([
                InlineKeyboardButton(
                    text=get_text(lang, "mf_btn_correct"),
                    callback_data=encode_feedback_callback("correct", feedback_token),
                ),
                InlineKeyboardButton(
                    text=get_text(lang, "mf_btn_error"),
                    callback_data=encode_feedback_callback("error", feedback_token),
                ),
                InlineKeyboardButton(
                    text=get_text(lang, "mf_btn_uncertain"),
                    callback_data=encode_feedback_callback("uncertain", feedback_token),
                ),
            ])
        else:
            # Legacy feedback row — always present for non-testers
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
