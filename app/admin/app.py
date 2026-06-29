import asyncio
import logging

logger = logging.getLogger(__name__)


async def main():
    logger.info("Admin panel (skeleton) — waiting for Phase 6a")
    while True:
        await asyncio.sleep(60)


if __name__ == "__main__":
    asyncio.run(main())
