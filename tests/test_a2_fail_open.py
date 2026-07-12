"""A2 (fable_core_plan): метрика и алерт fail-open LLM-валидатора.

Blocking-LLM — единственный precision-барьер; при отказе DeepSeek все
fail-open пути ставят LLMResult.error, но до A2 деградация была невидима.
Счётчики пишутся в validate_batch ТОЛЬКО по сообщениям, реально ходившим
к LLM (skip_llm/high-confidence не разбавляют знаменатель — фикс phase-review).
_check_llm_fail_open алертит только в llm_mode=blocking: >20% за час WARNING,
>50% CRITICAL; при <20 валидаций падает на предыдущий час, потом молчит.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fakeredis.aioredis import FakeRedis

from app.userbot.llm_validator import (
    LLMResult,
    LLMValidator,
    PendingMatch,
    _record_llm_stats,
)
from app.userbot.poller import ChannelPoller

HOUR = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H")
PREV_HOUR = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime("%Y-%m-%dT%H")


def _results(total: int, fails: int) -> list[LLMResult]:
    ok = [LLMResult(verdict="DEMAND") for _ in range(total - fails)]
    bad = [
        LLMResult(verdict="DEMAND", reason="fail-open", error="timeout")
        for _ in range(fails)
    ]
    return ok + bad


# ── Запись счётчиков (llm_validator._record_llm_stats) ──

@pytest.mark.asyncio
@patch("app.cache.get_redis")
async def test_record_llm_stats_counts(mock_get_redis):
    redis = FakeRedis()
    mock_get_redis.return_value = redis

    await _record_llm_stats(_results(total=5, fails=2))
    await _record_llm_stats(_results(total=3, fails=0))

    assert int(await redis.get(f"stats:llm:total:{HOUR}")) == 8
    assert int(await redis.get(f"stats:llm:fail_open:{HOUR}")) == 2
    assert await redis.ttl(f"stats:llm:total:{HOUR}") > 0


@pytest.mark.asyncio
@patch("app.cache.get_redis")
async def test_record_llm_stats_empty_noop(mock_get_redis):
    redis = FakeRedis()
    mock_get_redis.return_value = redis
    await _record_llm_stats([])
    assert await redis.get(f"stats:llm:total:{HOUR}") is None


@pytest.mark.asyncio
@patch("app.cache.get_redis")
async def test_validate_batch_denominator_excludes_skipped(mock_get_redis):
    # 1 skip_llm + 2 реальных (оба fail-open) → total=2, fails=2 (не 3/2):
    # 100% отказ реальных валидаций не должен разбавляться скипами
    redis = FakeRedis()
    mock_get_redis.return_value = redis

    matches = [
        PendingMatch("c", 1, "точно спрос", ["seg"], skip_llm=True),
        PendingMatch("c", 2, "текст один", ["seg"]),
        PendingMatch("c", 3, "текст два", ["seg"]),
    ]
    validator = LLMValidator()
    fail = {
        1: LLMResult(verdict="DEMAND", reason="fail-open", error="timeout"),
        2: LLMResult(verdict="DEMAND", reason="fail-open", error="timeout"),
    }
    with patch.object(type(validator), "enabled", property(lambda self: True)), \
         patch.object(validator, "_call_llm_batch", AsyncMock(return_value=fail)), \
         patch("app.userbot.llm_validator.is_high_confidence_demand", lambda t: False):
        results = await validator.validate_batch(matches)

    assert len(results) == 3
    assert int(await redis.get(f"stats:llm:total:{HOUR}")) == 2
    assert int(await redis.get(f"stats:llm:fail_open:{HOUR}")) == 2


# ── Алерт (_check_llm_fail_open) ──

async def _run_check(redis, mode: str = "blocking") -> tuple:
    poller = ChannelPoller()
    with patch("app.userbot.poller.get_redis", return_value=redis), \
         patch("app.userbot.poller.llm_validator") as mock_validator, \
         patch("app.userbot.poller.settings") as mock_settings:
        mock_validator.enabled = True
        mock_settings.llm_mode = mode
        return await poller._check_llm_fail_open()


async def _seed(redis, hour: str, total: int, fails: int) -> None:
    await redis.set(f"stats:llm:total:{hour}", total)
    await redis.set(f"stats:llm:fail_open:{hour}", fails)


@pytest.mark.asyncio
async def test_check_silent_below_min_volume_both_hours():
    redis = FakeRedis()
    await _seed(redis, HOUR, total=19, fails=19)
    level, _ = await _run_check(redis)
    assert level is None


@pytest.mark.asyncio
async def test_check_falls_back_to_previous_hour():
    # Граница часа: в текущем ведре мало данных, отказ виден по прошлому часу
    redis = FakeRedis()
    await _seed(redis, HOUR, total=3, fails=3)
    await _seed(redis, PREV_HOUR, total=100, fails=90)
    level, _ = await _run_check(redis)
    assert level == "CRITICAL"


@pytest.mark.asyncio
async def test_check_silent_at_low_rate():
    redis = FakeRedis()
    await _seed(redis, HOUR, total=100, fails=10)
    level, _ = await _run_check(redis)
    assert level is None


@pytest.mark.asyncio
async def test_check_warning_above_20_percent():
    redis = FakeRedis()
    await _seed(redis, HOUR, total=100, fails=30)
    level, text = await _run_check(redis)
    assert level == "WARNING"
    assert "30/100" in text


@pytest.mark.asyncio
async def test_check_critical_above_50_percent():
    redis = FakeRedis()
    await _seed(redis, HOUR, total=100, fails=60)
    level, text = await _run_check(redis)
    assert level == "CRITICAL"
    assert "60/100" in text


@pytest.mark.asyncio
async def test_check_silent_in_shadow_mode():
    # В shadow валидатор ничего не фильтрует — CRITICAL был бы ложной паникой
    redis = FakeRedis()
    await _seed(redis, HOUR, total=100, fails=90)
    level, _ = await _run_check(redis, mode="shadow")
    assert level is None


@pytest.mark.asyncio
async def test_check_silent_when_llm_disabled():
    redis = FakeRedis()
    await _seed(redis, HOUR, total=100, fails=90)
    poller = ChannelPoller()
    with patch("app.userbot.poller.get_redis", return_value=redis), \
         patch("app.userbot.poller.llm_validator") as mock_validator, \
         patch("app.userbot.poller.settings") as mock_settings:
        mock_validator.enabled = False
        mock_settings.llm_mode = "blocking"
        level, _ = await poller._check_llm_fail_open()
    assert level is None
