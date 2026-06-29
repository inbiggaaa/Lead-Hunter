import asyncio
import logging

from aiogram import Bot, Dispatcher

from app.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    bot = Bot(token=settings.bot_token)
    dp = Dispatcher()

    logger.info("Bot started (skeleton)")

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
