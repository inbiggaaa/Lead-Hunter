"""A2 (fable_core_plan): метрика и алерт fail-open LLM-валидатора.

Blocking-LLM — единственный precision-барьер; при отказе DeepSeek все
fail-open пути ставят LLMResult.error, но до A2 деградация была невидима.
_record_llm_stats пишет почасовые счётчики stats:llm:{total,fail_open}:{час},
_check_llm_fail_open алертит: >20% за час → WARNING, >50% → CRITICAL,
при < 20 валидаций за час — молчит (нет статистики).
"""

from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from fakeredis.aioredis import FakeRedis

from app.userbot.llm_validator import LLMResult
from app.userbot.poller import ChannelPoller

HOUR = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H")


def _results(total: int, fails: int) -> list[LLMResult]:
    ok = [LLMResult(verdict="DEMAND") for _ in range(total - fails)]
    bad = [
        LLMResult(verdict="DEMAND", reason="fail-open", error="timeout")
        for _ in range(fails)
    ]
    return ok + bad


@pytest.mark.asyncio
@patch("app.userbot.poller.get_redis")
async def test_record_llm_stats_counts(mock_get_redis):
    redis = FakeRedis()
    mock_get_redis.return_value = redis

    await ChannelPoller._record_llm_stats(_results(total=5, fails=2))
    await ChannelPoller._record_llm_stats(_results(total=3, fails=0))

    assert int(await redis.get(f"stats:llm:total:{HOUR}")) == 8
    assert int(await redis.get(f"stats:llm:fail_open:{HOUR}")) == 2
    assert await redis.ttl(f"stats:llm:total:{HOUR}") > 0


@pytest.mark.asyncio
@patch("app.userbot.poller.get_redis")
async def test_record_llm_stats_empty_noop(mock_get_redis):
    redis = FakeRedis()
    mock_get_redis.return_value = redis
    await ChannelPoller._record_llm_stats([])
    assert await redis.get(f"stats:llm:total:{HOUR}") is None


async def _run_check(redis, total: int | None, fails: int | None) -> tuple:
    if total is not None:
        await redis.set(f"stats:llm:total:{HOUR}", total)
    if fails is not None:
        await redis.set(f"stats:llm:fail_open:{HOUR}", fails)
    poller = ChannelPoller()
    with patch("app.userbot.poller.get_redis", return_value=redis), \
         patch("app.userbot.poller.llm_validator") as mock_validator:
        mock_validator.enabled = True
        return await poller._check_llm_fail_open()


@pytest.mark.asyncio
async def test_check_silent_below_min_volume():
    level, _ = await _run_check(FakeRedis(), total=19, fails=19)
    assert level is None


@pytest.mark.asyncio
async def test_check_silent_at_low_rate():
    level, _ = await _run_check(FakeRedis(), total=100, fails=10)
    assert level is None


@pytest.mark.asyncio
async def test_check_warning_above_20_percent():
    level, text = await _run_check(FakeRedis(), total=100, fails=30)
    assert level == "WARNING"
    assert "30/100" in text


@pytest.mark.asyncio
async def test_check_critical_above_50_percent():
    level, text = await _run_check(FakeRedis(), total=100, fails=60)
    assert level == "CRITICAL"
    assert "60/100" in text


@pytest.mark.asyncio
async def test_check_silent_when_llm_disabled():
    redis = FakeRedis()
    await redis.set(f"stats:llm:total:{HOUR}", 100)
    await redis.set(f"stats:llm:fail_open:{HOUR}", 90)
    poller = ChannelPoller()
    with patch("app.userbot.poller.get_redis", return_value=redis), \
         patch("app.userbot.poller.llm_validator") as mock_validator:
        mock_validator.enabled = False
        level, _ = await poller._check_llm_fail_open()
    assert level is None
