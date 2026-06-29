"""Userbot pool manager — multiple Telegram accounts with load balancing."""

import asyncio
import logging
import os
from pathlib import Path

from telethon import TelegramClient
from telethon.errors import RPCError

from app.config import settings

logger = logging.getLogger(__name__)

SESSIONS_DIR = Path("/app/sessions")


class UserbotAccount:
    """A single userbot account with its own TelegramClient."""

    def __init__(self, account_id: int, session_name: str):
        self.account_id = account_id
        self.session_name = session_name
        self.client = TelegramClient(
            str(SESSIONS_DIR / session_name),
            settings.userbot_api_id,
            settings.userbot_api_hash,
        )
        self.channel_count = 0
        self.is_healthy = True
        self.last_error: str | None = None

    async def start(self):
        """Start and authorize this account."""
        try:
            await self.client.start(phone=settings.userbot_phone or None)
            me = await self.client.get_me()
            logger.info("Account %d authorized as @%s", self.account_id, me.username)
            self.is_healthy = True
        except Exception as e:
            logger.error("Account %d failed to start: %s", self.account_id, e)
            self.is_healthy = False
            self.last_error = str(e)

    async def check_health(self) -> bool:
        """Check if account is still healthy."""
        if not self.is_healthy:
            return False
        try:
            await self.client.get_me()
            return True
        except Exception:
            self.is_healthy = False
            return False

    async def get_entity(self, username: str):
        """Get channel entity, with health check."""
        if not self.is_healthy:
            raise ValueError(f"Account {self.account_id} is unhealthy")
        return await self.client.get_entity(username)

    async def get_messages(self, entity, limit: int = 10):
        """Get messages from a channel."""
        return await self.client.get_messages(entity, limit=limit)


class UserbotPool:
    """Manages multiple userbot accounts with automatic failover."""

    def __init__(self):
        self.accounts: list[UserbotAccount] = []
        self._channel_assignments: dict[str, int] = {}  # channel_username -> account_id
        self._lock = asyncio.Lock()

    @staticmethod
    async def discover_sessions() -> list[str]:
        """Discover available session files in sessions directory."""
        if not SESSIONS_DIR.exists():
            return []
        sessions = []
        for f in SESSIONS_DIR.iterdir():
            if f.suffix == ".session" and f.stem != ".gitkeep":
                sessions.append(f.stem)
        return sorted(sessions)

    async def initialize(self):
        """Initialize pool from available session files."""
        session_names = await self.discover_sessions()

        if not session_names:
            # Fall back to default single session
            session_names = ["userbot"]

        for i, name in enumerate(session_names):
            account = UserbotAccount(account_id=i + 1, session_name=name)
            await account.start()
            if account.is_healthy:
                self.accounts.append(account)

        logger.info("Pool initialized: %d healthy accounts", len(self.accounts))

        if not self.accounts:
            raise RuntimeError("No healthy userbot accounts available. Run auth.py to create sessions.")

    async def redistribute_channels(self, channels: list[str]):
        """Distribute channels across accounts evenly."""
        async with self._lock:
            # Reset counts
            for acc in self.accounts:
                acc.channel_count = 0
            self._channel_assignments.clear()

            healthy = [a for a in self.accounts if a.is_healthy]
            if not healthy:
                logger.error("No healthy accounts to distribute channels")
                return

            # Round-robin distribution across healthy accounts
            for i, channel in enumerate(channels):
                acc = healthy[i % len(healthy)]
                self._channel_assignments[channel] = acc.account_id
                acc.channel_count += 1

            logger.info(
                "Distributed %d channels across %d accounts: %s",
                len(channels),
                len(healthy),
                {a.account_id: a.channel_count for a in healthy},
            )

    def get_account_for_channel(self, channel_username: str) -> UserbotAccount | None:
        """Get the assigned account for a channel."""
        acc_id = self._channel_assignments.get(channel_username)
        if acc_id is None:
            return None
        for acc in self.accounts:
            if acc.account_id == acc_id and acc.is_healthy:
                return acc
        return None

    async def handle_account_failure(self, failed_account: UserbotAccount):
        """Redistribute channels from a failed account to healthy ones."""
        async with self._lock:
            failed_channels = [
                ch for ch, aid in self._channel_assignments.items()
                if aid == failed_account.account_id
            ]

            healthy = [a for a in self.accounts if a.is_healthy and a.account_id != failed_account.account_id]

            if not healthy:
                logger.error("No healthy accounts to take over channels from account %d", failed_account.account_id)
                return

            for channel in failed_channels:
                # Assign to least loaded healthy account
                target = min(healthy, key=lambda a: a.channel_count)
                self._channel_assignments[channel] = target.account_id
                target.channel_count += 1

            logger.info(
                "Redistributed %d channels from failed account %d to %d healthy accounts",
                len(failed_channels), failed_account.account_id, len(healthy),
            )

    async def health_check_loop(self):
        """Periodically check health of all accounts."""
        while True:
            for acc in self.accounts:
                was_healthy = acc.is_healthy
                is_ok = await acc.check_health()

                if was_healthy and not is_ok:
                    logger.warning("Account %d became unhealthy — redistributing channels", acc.account_id)
                    await self.handle_account_failure(acc)

            await asyncio.sleep(300)  # Check every 5 minutes

    @property
    def healthy_count(self) -> int:
        return sum(1 for a in self.accounts if a.is_healthy)

    @property
    def total_channels(self) -> int:
        return len(self._channel_assignments)
