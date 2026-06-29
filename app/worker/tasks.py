import asyncio
import logging

logger = logging.getLogger(__name__)


async def main():
    logger.info("Worker started (skeleton)")

    # Keep alive — will be replaced with real listener in Phase 4
    while True:
        await asyncio.sleep(60)


if __name__ == "__main__":
    asyncio.run(main())
