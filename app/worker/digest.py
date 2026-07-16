"""Digest flush (T5.3): доставка отложенных уведомлений по расписанию.

digest_mode=hourly → каждый час; daily2 → в DIGEST_DAILY_HOURS (10:00 и 19:00 UTC).
Срочные (🔥) в буфер не попадают (sender шлёт их мгновенно). Мягкая митигация шума
при безлимите уведомлений (#81) — фича комфорта, доступна всем.
"""

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select

from app.db.models import User
from app.db.session import async_session_factory
from app.cache.subscription_cache import (
    claim_digest,
    ack_digest_head,
    finish_digest_claim,
    restore_digest,
    reclaim_stale_digests,
    mark_sent,
    increment_daily_stats,
)
from app.locales import get_text

logger = logging.getLogger(__name__)

DIGEST_DAILY_HOURS = (10, 19)


async def flush_digests():
    """Разослать накопленные буферы digest-пользователям, для которых сейчас время."""
    from app.worker.sender import NotificationSender

    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")
    hour = now.hour

    async with async_session_factory() as session:
        users = (await session.execute(
            select(User).where(User.digest_mode != "instant")
        )).scalars().all()

    try:
        await reclaim_stale_digests([u.id for u in users])
    except Exception:
        logger.exception("Digest reclaim failed")

    sender = NotificationSender()
    delivered = 0
    try:
        for user in users:
            if user.digest_mode == "daily2" and hour not in DIGEST_DAILY_HOURS:
                continue
            items = await claim_digest(user.id)
            if not items:
                continue

            lang = user.language or "ru"
            remaining = list(items)
            try:
                await sender.bot.send_message(
                    user.telegram_id, get_text(lang, "digest_header", count=len(items)))
                while remaining:
                    payload = remaining[0]
                    text = sender._format_notification(payload)
                    kb = sender._build_keyboard(payload)
                    await sender.bot.send_message(user.telegram_id, text, reply_markup=kb)
                    content_hash = payload.get("content_hash")
                    matched = payload.get("matched_segments", [])
                    seg_label = ", ".join(m.get("title", "") for m in matched) if matched else None
                    meta = {
                        "chat_username": payload.get("chat_username"),
                        "sender": payload.get("sender"),
                        "segment": seg_label,
                        "message_id": payload.get("message_id"),
                    }
                    await mark_sent(
                        user.id,
                        payload["message_hash"],
                        payload.get("is_urgent", False),
                        content_hash=content_hash,
                        meta=meta,
                    )
                    await ack_digest_head(user.id, payload.get("message_hash"))
                    await increment_daily_stats(user.id, today, "sent")
                    remaining.pop(0)
                    delivered += 1
                    await asyncio.sleep(sender.throttle_interval)
                await finish_digest_claim(user.id)
            except Exception:
                logger.exception("Digest flush failed for user %d", user.id)
                if remaining:
                    await restore_digest(user.id, remaining)
    finally:
        await sender.bot.session.close()

    if delivered:
        logger.info("Digest flush: delivered %d buffered notifications", delivered)


async def digest_flush_loop():
    """Каждый час на границе часа — flush_digests()."""
    from datetime import timedelta
    while True:
        now = datetime.now(timezone.utc)
        next_hour = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        await asyncio.sleep(max(1, (next_hour - now).total_seconds()))
        try:
            await flush_digests()
        except Exception:
            logger.exception("Digest flush loop error")
