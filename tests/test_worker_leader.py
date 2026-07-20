"""Unit tests for worker leader lease and heartbeat helpers."""

from unittest.mock import AsyncMock, Mock

import pytest

from app.worker import leader, heartbeat


class _FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.incrs: dict[str, int] = {}

    async def set(self, key: str, value: str, nx: bool = False, ex: int | None = None):
        if nx and key in self.store:
            return False
        self.store[key] = value
        return True

    async def get(self, key: str):
        return self.store.get(key)

    async def incr(self, key: str) -> int:
        self.incrs[key] = self.incrs.get(key, 0) + 1
        return self.incrs[key]

    async def expire(self, key: str, ttl: int) -> None:
        return None

    async def delete(self, key: str) -> int:
        return 1 if self.store.pop(key, None) is not None else 0

    async def eval(self, script: str, numkeys: int, *args):
        key, token, *rest = args
        if "EXPIRE" in script:
            if self.store.get(key) == token:
                return 1
            return 0
        if self.store.get(key) == token:
            del self.store[key]
            return 1
        return 0


@pytest.mark.asyncio
async def test_second_worker_cannot_acquire_leader_lease(monkeypatch) -> None:
    redis = _FakeRedis()
    monkeypatch.setattr(leader, "get_redis", AsyncMock(return_value=redis))

    first = leader.LeaderLease(owner_token="owner-a")
    second = leader.LeaderLease(owner_token="owner-b")

    assert await first.try_acquire() is True
    assert await second.try_acquire() is False
    assert redis.incrs[leader.STATS_LEADER_REJECTED] == 1
    assert redis.store[leader.LEADER_KEY] == "owner-a"


@pytest.mark.asyncio
async def test_leader_renew_and_release_are_owner_scoped(monkeypatch) -> None:
    redis = _FakeRedis()
    monkeypatch.setattr(leader, "get_redis", AsyncMock(return_value=redis))

    lease = leader.LeaderLease(owner_token="owner-a")
    assert await lease.try_acquire() is True
    assert await lease.renew_once() is True

    redis.store[leader.LEADER_KEY] = "someone-else"
    assert await lease.renew_once() is False

    redis.store[leader.LEADER_KEY] = "owner-a"
    await lease.release()
    assert leader.LEADER_KEY not in redis.store


@pytest.mark.asyncio
async def test_heartbeat_writes_loop_and_per_account_keys(monkeypatch) -> None:
    redis = _FakeRedis()
    monkeypatch.setattr(heartbeat, "get_redis", AsyncMock(return_value=redis))

    await heartbeat.send_heartbeat([1, 2])

    assert heartbeat.HEARTBEAT_LOOP_KEY in redis.store
    assert heartbeat.HEARTBEAT_KEY in redis.store
    assert heartbeat.heartbeat_account_key(1) in redis.store
    assert heartbeat.heartbeat_account_key(2) in redis.store
    assert "heartbeat:wall:userbot:2" in redis.store
