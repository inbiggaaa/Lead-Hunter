"""Worker entry point: runs userbot poller + notification sender + heartbeat."""

import asyncio
import logging

from app.worker.sender import NotificationSender
from app.worker.heartbeat import heartbeat_loop
from app.worker.reminders import reminders_loop
from app.userbot.poller import ChannelPoller

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    logger.info("Worker starting (poller + sender + heartbeat)...")

    poller = ChannelPoller()
    sender = NotificationSender()

    # Run all four loops concurrently
    await asyncio.gather(
        poller.run_forever(),
        sender.run(),
        heartbeat_loop(),
        reminders_loop(),
    )


if __name__ == "__main__":
    asyncio.run(main())
