import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.config import settings
from app.db.session import engine
from app.db.models import Base
from app.bot.handlers.start import router as start_router
from app.bot.handlers.keywords import router as keywords_router
from app.bot.handlers.channels import router as channels_router
from app.bot.handlers.catalog_nav import router as catalog_router
from app.bot.handlers.discover import router as discover_router
from app.bot.handlers.support import router as support_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def init_db():
    """Create all tables if they don't exist."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables created")


async def main():
    # Init DB
    await init_db()

    # Bot
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    dp.include_router(catalog_router)
    dp.include_router(keywords_router)
    dp.include_router(channels_router)
    dp.include_router(discover_router)
    dp.include_router(support_router)
    dp.include_router(start_router)

    logger.info("Bot started")

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
