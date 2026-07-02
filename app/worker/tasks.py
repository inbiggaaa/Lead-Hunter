"""Worker entry point: runs userbot poller + notification sender + heartbeat."""

import asyncio
import logging

from app.worker.sender import NotificationSender
from app.worker.heartbeat import heartbeat_loop
from app.worker.reminders import reminders_loop
from app.worker.end_of_day import end_of_day_loop
from app.worker.payment_checker import payment_checker_loop
from app.userbot.discovery import discovery_loop
from app.userbot.discovery_v2 import discovery_v2_loop
from app.userbot.poller import ChannelPoller

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    logger.info("Worker starting (poller + sender + heartbeat)...")

    poller = ChannelPoller()
    sender = NotificationSender()

    # Initialize pool first so discovery can share the client
    await poller.start()
    discovery_client = poller.pool.get_healthy_client()

    # Run all loops concurrently
    await asyncio.gather(
        poller.run_forever(),
        sender.run(),
        heartbeat_loop(),
        reminders_loop(),
        end_of_day_loop(),
        payment_checker_loop(),
        # discovery_loop(client=discovery_client),  # DISABLED: shares acc1 client, risks FloodWait
        discovery_v2_loop(client=discovery_client),  # shares userbot1 with poller
    )


if __name__ == "__main__":
    asyncio.run(main())
