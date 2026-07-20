"""Redis leader lease — at most one worker may run Telethon polling."""

from __future__ import annotations

import asyncio
import logging
import secrets
import uuid

from app.cache import get_redis

logger = logging.getLogger(__name__)

LEADER_KEY = "worker:leader"
LEADER_TTL_SEC = 30
LEADER_RENEW_EVERY_SEC = 10
STATS_LEADER_REJECTED = "stats:worker:leader_rejected"
STATS_LEADER_LOST = "stats:worker:leader_lost"


class LeaderLease:
    """Exclusive lease: SET NX EX + ownership-checked renew/release."""

    def __init__(self, owner_token: str | None = None) -> None:
        self.owner_token = owner_token or f"{uuid.uuid4().hex}:{secrets.token_hex(8)}"
        self._stop = asyncio.Event()
        self._renew_task: asyncio.Task | None = None

    async def try_acquire(self) -> bool:
        redis = await get_redis()
        acquired = await redis.set(
            LEADER_KEY, self.owner_token, nx=True, ex=LEADER_TTL_SEC,
        )
        if acquired:
            logger.info("Worker leader lease acquired (%s)", self.owner_token[:12])
            return True
        await redis.incr(STATS_LEADER_REJECTED)
        current = await redis.get(LEADER_KEY)
        logger.error(
            "Worker leader lease held by another instance (%s) — refusing to start Telethon",
            current,
        )
        return False

    async def renew_once(self) -> bool:
        redis = await get_redis()
        # Renew only if we still own the key.
        script = """
        if redis.call('GET', KEYS[1]) == ARGV[1] then
            return redis.call('EXPIRE', KEYS[1], ARGV[2])
        end
        return 0
        """
        ok = await redis.eval(script, 1, LEADER_KEY, self.owner_token, LEADER_TTL_SEC)
        return bool(ok)

    async def release(self) -> None:
        self._stop.set()
        if self._renew_task and not self._renew_task.done():
            self._renew_task.cancel()
            try:
                await self._renew_task
            except asyncio.CancelledError:
                pass
        redis = await get_redis()
        script = """
        if redis.call('GET', KEYS[1]) == ARGV[1] then
            return redis.call('DEL', KEYS[1])
        end
        return 0
        """
        await redis.eval(script, 1, LEADER_KEY, self.owner_token)

    async def renew_loop(self) -> None:
        """Background renew; exits process path by raising if lease is lost."""
        while not self._stop.is_set():
            await asyncio.sleep(LEADER_RENEW_EVERY_SEC)
            if self._stop.is_set():
                return
            if await self.renew_once():
                continue
            redis = await get_redis()
            await redis.incr(STATS_LEADER_LOST)
            logger.critical("Worker leader lease lost — shutting down to avoid double poll")
            raise RuntimeError("worker leader lease lost")

    def start_renew_task(self) -> asyncio.Task:
        self._renew_task = asyncio.create_task(self.renew_loop(), name="leader-renew")
        return self._renew_task
