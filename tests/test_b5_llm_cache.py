"""B5 (fable_core_plan): кэш LLM-вердиктов по нормализованному тексту.

Репост одного объявления в N чатов — один вызов DeepSeek: вердикт кладётся
в Redis (llm:verdict:{sha256}, TTL 24ч) и переиспользуется. Ключ БЕЗ
chat_username (в отличие от компонент content_hash доставки). Fail-open
вердикты не кэшируются; ошибки Redis = промах (fail-open поведение не тронуто).
Кэш-хиты помечаются from_cache → llm_mode='cache' в llm_decisions
(датасет без дублей) и не попадают в знаменатель fail-open метрики A2.
"""

from unittest.mock import AsyncMock, patch

import pytest
from fakeredis.aioredis import FakeRedis

from app.userbot.llm_validator import (
    LLMResult,
    LLMValidator,
    PendingMatch,
    _llm_cache_key,
)

DEMAND_OK = LLMResult(verdict="DEMAND", reason="ok", certainty="high")
FAIL_OPEN = LLMResult(verdict="DEMAND", reason="fail-open", error="timeout")


def _pm(chat: str, msg_id: int, text: str) -> PendingMatch:
    return PendingMatch(chat, msg_id, text, ["seg"])


def _validator_ctx(validator, batch_return):
    return (
        patch.object(type(validator), "enabled", property(lambda self: True)),
        patch.object(
            validator, "_call_llm_batch", AsyncMock(return_value=batch_return)
        ),
        patch("app.userbot.llm_validator.is_high_confidence_demand", lambda t: False),
    )


async def _run(validator, matches, batch_return):
    p1, p2, p3 = _validator_ctx(validator, batch_return)
    with p1, p2 as call_mock, p3:
        results = await validator.validate_batch(matches)
    return results, call_mock


def test_cache_key_ignores_chat_case_and_whitespace():
    assert _llm_cache_key("Продам  Байк\n срочно") == _llm_cache_key("продам байк срочно")


@pytest.mark.asyncio
@patch("app.cache.get_redis")
async def test_repost_served_from_cache_without_llm_call(mock_get_redis):
    redis = FakeRedis()
    mock_get_redis.return_value = redis
    validator = LLMValidator()

    # Первый заход: вердикт от «LLM», кладётся в кэш
    _res, call1 = await _run(validator, [_pm("chat_a", 1, "Продам байк срочно")], {0: DEMAND_OK})
    assert call1.await_count == 1

    # Репост того же текста в другом чате: LLM НЕ вызывается
    res2, call2 = await _run(validator, [_pm("chat_b", 77, "продам  байк срочно")], {})
    assert call2.await_count == 0
    assert res2[0].verdict == "DEMAND"
    assert res2[0].from_cache is True
    assert await redis.get(_llm_cache_key("продам байк срочно")) is not None


@pytest.mark.asyncio
@patch("app.cache.get_redis")
async def test_fail_open_verdict_not_cached(mock_get_redis):
    redis = FakeRedis()
    mock_get_redis.return_value = redis
    validator = LLMValidator()

    _res, _ = await _run(validator, [_pm("chat_a", 1, "текст с таймаутом")], {0: FAIL_OPEN})
    assert await redis.get(_llm_cache_key("текст с таймаутом")) is None

    # Повтор → снова идёт к LLM (кэша нет)
    _res2, call2 = await _run(validator, [_pm("chat_b", 2, "текст с таймаутом")], {0: DEMAND_OK})
    assert call2.await_count == 1


@pytest.mark.asyncio
@patch("app.cache.get_redis")
async def test_redis_failure_is_a_miss_not_a_crash(mock_get_redis):
    mock_get_redis.side_effect = ConnectionError("redis down")
    validator = LLMValidator()
    results, call = await _run(validator, [_pm("c", 1, "любой текст")], {0: DEMAND_OK})
    assert call.await_count == 1
    assert results[0].verdict == "DEMAND"


@pytest.mark.asyncio
@patch("app.cache.get_redis")
async def test_cache_hit_counter_increments(mock_get_redis):
    redis = FakeRedis()
    mock_get_redis.return_value = redis
    validator = LLMValidator()

    await _run(validator, [_pm("a", 1, "объявление про аренду")], {0: DEMAND_OK})
    await _run(validator, [_pm("b", 2, "объявление про аренду")], {})

    import time
    date = time.strftime("%Y-%m-%d", time.gmtime())
    assert int(await redis.get(f"stats:llm:cache_hit:{date}")) == 1
