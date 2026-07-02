import asyncio
import logging

import sentry_sdk

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
from app.bot.handlers.plan import router as plan_router
from app.bot.handlers.feedback import router as feedback_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def init_db():
    """Create all tables if they don't exist."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables created")


async def main():
    # Sentry
    if settings.sentry_dsn:
        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            traces_sample_rate=0.1,
            environment="production",
        )
        logger.info("Sentry initialized")

    # Init DB
    await init_db()

    # Bot
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    # Set persistent commands menu (RU + EN)
    from aiogram.types import BotCommand, BotCommandScopeAllPrivateChats
    ru_cmds = [
        BotCommand(command="start", description="🏠 Главное меню"),
        BotCommand(command="search", description="🔍 Поиск клиентов"),
        BotCommand(command="keywords", description="⚙️ Мои ключевые слова"),
        BotCommand(command="channels", description="📢 Мои каналы"),
        BotCommand(command="subscriptions", description="📋 Мои подписки"),
        BotCommand(command="plan", description="💰 Тариф и оплата"),
        BotCommand(command="settings", description="⚙️ Настройки"),
        BotCommand(command="cancel", description="❌ Отмена"),
    ]
    en_cmds = [
        BotCommand(command="start", description="🏠 Main menu"),
        BotCommand(command="search", description="🔍 Find clients"),
        BotCommand(command="keywords", description="⚙️ My keywords"),
        BotCommand(command="channels", description="📢 My channels"),
        BotCommand(command="subscriptions", description="📋 My subscriptions"),
        BotCommand(command="plan", description="💰 Plan & payment"),
        BotCommand(command="settings", description="⚙️ Settings"),
        BotCommand(command="cancel", description="❌ Cancel"),
    ]
    scope = BotCommandScopeAllPrivateChats()
    await bot.set_my_commands(ru_cmds, scope=scope, language_code="ru")
    await bot.set_my_commands(en_cmds, scope=scope, language_code="en")
    await bot.delete_my_commands(scope=scope)  # clear default (no language)
    logger.info("Commands menu set (RU + EN)")
    dp = Dispatcher()
    dp.include_router(catalog_router)
    dp.include_router(keywords_router)
    dp.include_router(channels_router)
    dp.include_router(discover_router)
    dp.include_router(plan_router)
    dp.include_router(feedback_router)
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
