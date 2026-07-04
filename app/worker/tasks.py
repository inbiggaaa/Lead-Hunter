"""Worker entry point: runs userbot poller + notification sender + heartbeat."""

import asyncio
import logging

from app.worker.sender import NotificationSender
from app.worker.heartbeat import heartbeat_loop
from app.worker.reminders import reminders_loop
from app.worker.end_of_day import end_of_day_loop
from app.worker.payment_checker import payment_checker_loop
from app.userbot.poller import ChannelPoller

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    logger.info("Worker starting (poller + sender + heartbeat)...")

    poller = ChannelPoller()
    sender = NotificationSender()

    # Discovery v3 — dedicated account, fully isolated from poller.
    # Enable with DISCOVERY_ENABLED=true in .env.
    # Requires DISCOVERY_ACCOUNT_ID=3 (separate SIM) for production mode.
    # Without account #3: runs in manual/test mode (only when poller inactive).
    if settings.discovery_enabled:
        from app.userbot.discovery_v2 import DiscoveryWorker
        discovery = DiscoveryWorker()
        asyncio.create_task(discovery.run())
        logger.info("Discovery worker started (account #%d)", settings.discovery_account_id)

    await poller.start()

    await asyncio.gather(
        poller.run_forever(),
        sender.run(),
        heartbeat_loop(),
        reminders_loop(),
        end_of_day_loop(),
        payment_checker_loop(),
    )


if __name__ == "__main__":
    asyncio.run(main())
