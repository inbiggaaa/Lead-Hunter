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
            results = await client.search_public_chats(query)
            for chat in results:
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


async def discovery_loop():
    """Background loop: search for new channels periodically."""
    # Wait 5 minutes on startup before first run
    await asyncio.sleep(300)

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
        try:
            await search_channels(client, queries)
        except Exception:
            logger.exception("Discovery failed")

        # Run once per day
        await asyncio.sleep(86400)
