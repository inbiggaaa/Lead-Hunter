"""Worker entry point: runs the userbot poller."""

import asyncio
import logging

from app.userbot.poller import ChannelPoller

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    logger.info("Worker starting...")
    poller = ChannelPoller()
    await poller.run_forever()


if __name__ == "__main__":
    asyncio.run(main())
