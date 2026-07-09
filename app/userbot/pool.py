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
        api_id, api_hash, _ = settings.get_userbot_creds(account_id)
        self.client = TelegramClient(
            str(SESSIONS_DIR / session_name),
            api_id,
            api_hash,
            flood_sleep_threshold=settings.flood_sleep_threshold,
        )
        self.is_healthy = True
        self.last_error: str | None = None

    async def start(self):
        """Start and authorize this account."""
        try:
            _, _, phone = settings.get_userbot_creds(self.account_id)
            await self.client.start(phone=phone or None)
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

    async def get_input_entity(self, username: str):
        """Get input entity (prefers session cache), with health check.

        Unlike get_entity, this returns InputPeer* directly without a full
        ResolveUsername API call when the entity is in the session cache.
        """
        if not self.is_healthy:
            raise ValueError(f"Account {self.account_id} is unhealthy")
        return await self.client.get_input_entity(username)

    async def get_messages(self, entity, limit: int = 10, **kwargs):
        """Get messages from a channel. Passes through all Telethon kwargs."""
        return await self.client.get_messages(entity, limit=limit, **kwargs)


class UserbotPool:
    """Manages multiple userbot accounts."""

    def __init__(self):
        self.accounts: list[UserbotAccount] = []
        self._lock = asyncio.Lock()

    @staticmethod
    async def discover_sessions() -> list[str]:
        """List session files on disk — diagnostics only, never assigns IDs."""
        if not SESSIONS_DIR.exists():
            return []
        sessions = []
        for f in SESSIONS_DIR.iterdir():
            if f.suffix == ".session" and f.stem != ".gitkeep":
                sessions.append(f.stem)
        return sorted(sessions)

    async def initialize(self):
        """Initialize pool from the explicit account_id → session map.

        IDs come from settings.userbot_session_map, NOT from directory
        listing: a new file on disk (e.g. discovery.session) must never
        renumber existing accounts — Redis keys (budgets, circuit breaker,
        ban counts, session windows) are bound to account IDs.
        """
        mapping = settings.userbot_sessions

        for account_id in sorted(mapping):
            name = mapping[account_id]
            if not (SESSIONS_DIR / f"{name}.session").exists():
                logger.warning(
                    "Account %d: session file %s.session not found — skipped",
                    account_id, name,
                )
                continue
            account = UserbotAccount(account_id=account_id, session_name=name)
            await account.start()
            if account.is_healthy:
                self.accounts.append(account)

        unknown = [
            s for s in await self.discover_sessions() if s not in mapping.values()
        ]
        if unknown:
            logger.warning(
                "Session files not in userbot_session_map (ignored): %s", unknown,
            )

        logger.info("Pool initialized: %d healthy accounts", len(self.accounts))

        if not self.accounts:
            raise RuntimeError("No healthy userbot accounts available. Run auth.py to create sessions.")

    async def handle_account_failure(self, failed_account: UserbotAccount):
        """Alert on account failure — NO channel redistribution.

        Redistribution caused incidents #2 and #3: the surviving account
        took over ALL channels and was banned too. _distribute() in poller.py
        handles account-level skipping correctly at the tier loop level.
        """
        logger.error(
            "Account %d failed — channels handled by _distribute(), no redistribution",
            failed_account.account_id,
        )

    async def health_check_loop(self):
        """Periodically check health of all accounts."""
        while True:
            for acc in self.accounts:
                was_healthy = acc.is_healthy
                is_ok = await acc.check_health()

                if was_healthy and not is_ok:
                    logger.warning("Account %d became unhealthy", acc.account_id)
                    await self.handle_account_failure(acc)
                    from app.worker.notify_admin import notify_admin
                    await notify_admin(
                        f"⚠️ Аккаунт #{acc.account_id} перестал отвечать.\n\n"
                        f"Поллинг остановлен для этого аккаунта. Каналы НЕ перераспределяются "
                        f"(защита от повторного бана)."
                    )
                elif not was_healthy and is_ok:
                    logger.info("Account %d recovered", acc.account_id)
                    from app.worker.notify_admin import notify_admin
                    await notify_admin(f"✅ Аккаунт #{acc.account_id} восстановил работу")

            await asyncio.sleep(300)  # Check every 5 minutes

    def get_healthy_client(self, prefer_account_id: int | None = None):
        """Return a healthy account's Telethon client. Optionally prefer a specific account_id."""
        if prefer_account_id:
            for a in self.accounts:
                if a.account_id == prefer_account_id and a.is_healthy:
                    return a.client
        for a in self.accounts:
            if a.is_healthy:
                return a.client
        raise RuntimeError("No healthy accounts available")

    @property
    def healthy_count(self) -> int:
        return sum(1 for a in self.accounts if a.is_healthy)
