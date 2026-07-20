"""Worker entry point: runs userbot poller + notification sender + heartbeat."""

import asyncio
import logging
import sys

from app.worker.sender import NotificationSender
from app.worker.heartbeat import heartbeat_loop
from app.worker.reminders import reminders_loop
from app.worker.end_of_day import end_of_day_loop
from app.worker.payment_checker import payment_checker_loop
from app.worker.digest import digest_flush_loop
from app.worker.leader import LeaderLease
from app.config import settings
from app.userbot.poller import ChannelPoller
from app.sentry_setup import init_sentry

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    init_sentry("worker")
    logger.info("Worker starting (poller + sender + heartbeat)...")

    lease = LeaderLease()
    if not await lease.try_acquire():
        logger.error("Another worker already holds the leader lease — exiting")
        sys.exit(1)

    renew_task = lease.start_renew_task()
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

    try:
        await poller.start()
        account_ids = [acc.account_id for acc in poller.pool.accounts]

        await asyncio.gather(
            poller.run_forever(),
            sender.run(),
            heartbeat_loop(account_ids),
            reminders_loop(),
            end_of_day_loop(),
            payment_checker_loop(),
            digest_flush_loop(),
            renew_task,
        )
    except Exception:
        logger.exception("Worker stopped due to error")
        raise
    finally:
        await lease.release()


if __name__ == "__main__":
    asyncio.run(main())
