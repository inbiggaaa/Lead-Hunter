"""Shared admin notifications — sends alerts to admin channel about service events."""

import logging

from app.config import settings

logger = logging.getLogger(__name__)

_admins: list[int] | None = None


def _get_admin_ids() -> list[int]:
    """Resolve admin target IDs: admin_channel_id first, owner as fallback."""
    global _admins
    if _admins is not None:
        return _admins
    _admins = []
    if settings.admin_channel_id:
        _admins.append(settings.admin_channel_id)
    elif settings.owner_telegram_id:
        _admins.append(settings.owner_telegram_id)
    return _admins


async def notify_admin(text: str) -> bool:
    """Send a message to all configured admin targets. Returns True if any succeeded."""
    targets = _get_admin_ids()
    if not targets:
        logger.warning("No admin targets configured (ADMIN_CHANNEL_ID or OWNER_TELEGRAM_ID)")
        return False

    from aiogram import Bot

    sent = False
    for chat_id in targets:
        try:
            bot = Bot(token=settings.bot_token)
            await bot.send_message(chat_id, text)
            await bot.session.close()
            sent = True
        except Exception:
            logger.exception("Failed to notify admin target %d", chat_id)

    return sent
