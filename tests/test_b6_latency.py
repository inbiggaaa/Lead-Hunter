"""B6 (fable_core_plan): метрика латентности доставки.

sender после успешной доставки пишет разницу msg_ts → now в бакеты
stats:latency:{date}:{lt5m|lt30m|lt2h|ge2h} (TTL 14д). Данные — gate
для решения C1 (event-push). Отсутствие msg_ts (старые payload'ы в
очереди при деплое) — no-op, не ошибка.
"""

import time
from unittest.mock import patch

import pytest
from fakeredis.aioredis import FakeRedis

from app.worker.sender import record_latency

DATE = time.strftime("%Y-%m-%d", time.gmtime())


@pytest.mark.asyncio
@pytest.mark.parametrize("lag,bucket", [
    (30, "lt5m"),
    (600, "lt30m"),
    (3600, "lt2h"),
    (10 * 3600, "ge2h"),
])
@patch("app.cache.get_redis")
async def test_latency_bucketed(mock_get_redis, lag, bucket):
    redis = FakeRedis()
    mock_get_redis.return_value = redis
    await record_latency(time.time() - lag)
    assert int(await redis.get(f"stats:latency:{DATE}:{bucket}")) == 1
    assert await redis.ttl(f"stats:latency:{DATE}:{bucket}") > 0


@pytest.mark.asyncio
@patch("app.cache.get_redis")
async def test_missing_msg_ts_noop(mock_get_redis):
    redis = FakeRedis()
    mock_get_redis.return_value = redis
    await record_latency(None)
    assert await redis.keys("stats:latency:*") == []


@pytest.mark.asyncio
@patch("app.cache.get_redis")
async def test_redis_failure_does_not_raise(mock_get_redis):
    mock_get_redis.side_effect = ConnectionError("down")
    await record_latency(time.time() - 60)  # не должно бросить
