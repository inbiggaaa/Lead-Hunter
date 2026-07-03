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

    # Discovery loops REMOVED — they shared acc1 client, causing FloodWait bans.
    # DO NOT re-enable without a dedicated discovery account (separate SIM).
    # See: fix/disable-discovery-fix-throttle, commits 61522a6 + 2fe673a.
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
