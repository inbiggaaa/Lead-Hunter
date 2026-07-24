"""API contract tests for GET /api/stats/userbots."""

from __future__ import annotations

import pytest
import fakeredis.aioredis

from app.admin.api import userbot_capacity as capacity_mod


@pytest.fixture
async def fake_redis():
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield redis
    await redis.aclose()


@pytest.mark.asyncio
async def test_userbots_endpoint_returns_fleet_shape(fake_redis, monkeypatch):
    await fake_redis.hset(
        "poll:summary:v1",
        mapping={
            "eligible": "753",
            "parked": "1074",
            "class:C": "753",
            "assigned:1": "25",
        },
    )
    await fake_redis.hset(
        "userbot:governor:1",
        mapping={
            "state": "THROTTLED",
            "power_percent": "50",
            "recommended_state": "THROTTLED",
            "recommended_power_percent": "50",
        },
    )

    async def _get_redis():
        return fake_redis

    monkeypatch.setattr(capacity_mod, "get_redis", _get_redis)

    class _Sessions:
        def keys(self):
            return [1, 2]

    monkeypatch.setattr(
        capacity_mod.settings,
        "userbot_session_map",
        "1:userbot,2:userbot2",
    )

    data = await capacity_mod.userbot_capacity_stats()
    assert "fleet" in data
    assert "accounts" in data
    assert data["fleet"]["eligible_chats"] == 753
    assert data["fleet"]["parked_chats"] == 1074
    assert any(
        a["account_id"] == 1 and a["state"] == "THROTTLED" for a in data["accounts"]
    )
    assert data["fleet"]["configured_accounts"] == 2
