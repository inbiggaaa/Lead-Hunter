"""Auto-discovery: search for new channels using Telethon search_public_chats."""

import asyncio
import logging
import re
from pathlib import Path

from telethon import TelegramClient
from telethon.errors import FloodWaitError

from app.config import settings
from app.db.session import async_session_factory
from app.db.models import DiscoveredChat, CatalogChannel
from sqlalchemy import select

logger = logging.getLogger(__name__)

DISCOVERY_PATH = Path("/app/DISCOVERY.md")


async def parse_search_queries() -> list[str]:
    """Parse DISCOVERY.md and extract all search queries."""
    if not DISCOVERY_PATH.exists():
        logger.warning("DISCOVERY.md not found")
        return []

    text = DISCOVERY_PATH.read_text(encoding="utf-8")

    # Extract all backtick-quoted search queries
    queries = re.findall(r"`([^`]+)`", text)

    # Filter: only chat/channel search queries (not table headers)
    queries = [q.strip() for q in queries if "chat" in q.lower() or "rus" in q.lower() or "expats" in q.lower()]

    # Deduplicate
    queries = list(set(queries))
    logger.info("Parsed %d unique search queries from DISCOVERY.md", len(queries))
    return queries


async def search_channels(client: TelegramClient, queries: list[str], limit: int = 10):
    """Search for public channels matching queries."""
    found = 0
    skipped = 0

    for query in queries:
        try:
            from telethon.tl.functions.contacts import SearchRequest
            result = await client(SearchRequest(q=query, limit=limit))
            chats = result.chats

            for chat in chats:
                username = getattr(chat, "username", None)
                if not username:
                    continue

                # Check if already in catalog or discovered
                async with async_session_factory() as session:
                    existing_catalog = (await session.execute(
                        select(CatalogChannel).where(CatalogChannel.chat_username == username)
                    )).scalar_one_or_none()
                    existing_discovered = (await session.execute(
                        select(DiscoveredChat).where(DiscoveredChat.chat_username == username)
                    )).scalar_one_or_none()

                    if existing_catalog or existing_discovered:
                        skipped += 1
                        continue

                    title = getattr(chat, "title", username)
                    participants = getattr(chat, "participants_count", None)

                    # Auto-add to catalog
                    session.add(CatalogChannel(
                        chat_username=username,
                        title=title,
                        participants=participants,
                        is_verified=False,
                    ))
                    await session.commit()
                    found += 1
                    logger.info("Discovered: @%s (%s)", username, title)

            # Rate limit between queries
            await asyncio.sleep(1)

        except FloodWaitError as e:
            logger.warning("FloodWait during discovery: %ds", e.seconds)
            await asyncio.sleep(e.seconds)
        except Exception as e:
            logger.warning("Search failed for '%s': %s", query, e)

    logger.info("Discovery complete: %d new, %d skipped", found, skipped)
    return found


async def report_discovery_stats(new_found: int):
    """Send discovery stats to admin."""
    from aiogram import Bot
    from app.db.session import async_session_factory
    from app.db.models import CatalogChannel, DiscoveredChat
    from sqlalchemy import func, select as sa_sel

    async with async_session_factory() as s:
        total = (await s.execute(sa_sel(func.count(CatalogChannel.id)))).scalar() or 0
        discovered = (await s.execute(sa_sel(func.count(DiscoveredChat.id)))).scalar() or 0

    text = (
        f"📊 Отчёт поиска каналов\n\n"
        f"Найдено новых: {new_found}\n"
        f"Всего в каталоге: {total}\n"
        f"Ожидают проверки: {discovered}"
    )

    await _notify_admin(text)


async def _notify_admin(text: str):
    """Send notification to admin channel or owner."""
    from aiogram import Bot
    bot = Bot(token=settings.bot_token)
    chat_id = settings.admin_channel_id or settings.owner_telegram_id
    try:
        await bot.send_message(chat_id, text)
    except Exception:
        pass
    finally:
        await bot.session.close()


async def notify_new_trial(username: str, telegram_id: int, source: str):
    """Notify admin about new trial activation."""
    name = f"@{username}" if username else f"ID:{telegram_id}"
    text = (
        f"🆕 Новый пользователь!\n\n"
        f"👤 {name}\n"
        f"🎁 Активирован триал (5 дней Business)\n"
        f"📡 Источник: {source}"
    )
    await _notify_admin(text)


async def notify_new_subscription(username: str, telegram_id: int, plan: str, period: str, source: str):
    """Notify admin about new paid subscription."""
    name = f"@{username}" if username else f"ID:{telegram_id}"
    period_labels = {"1m": "1 месяц", "3m": "3 месяца", "1y": "1 год"}
    period_text = period_labels.get(period, period)
    text = (
        f"💰 Новая оплата!\n\n"
        f"👤 {name}\n"
        f"📋 Тариф: {plan.title()}\n"
        f"📅 Срок: {period_text}\n"
        f"📡 Источник: {source}"
    )
    await _notify_admin(text)


async def discovery_loop():
    """Background loop: search for new channels twice per day."""
    # Wait 2 minutes on startup
    await asyncio.sleep(120)

    queries = await parse_search_queries()
    if not queries:
        return

    client = TelegramClient(
        str(Path("/app/sessions/userbot")),
        settings.userbot_api_id,
        settings.userbot_api_hash,
    )
    await client.start()

    while True:
        logger.info("Starting channel discovery...")
        found = 0
        try:
            found = await search_channels(client, queries)
        except Exception:
            logger.exception("Discovery failed")

        # Report to admin
        await report_discovery_stats(found)

        # Run every 12 hours
        await asyncio.sleep(43200)
