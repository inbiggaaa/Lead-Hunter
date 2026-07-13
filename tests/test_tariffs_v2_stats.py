"""T5.1 — статистика: пейволл для free/start, суммирование по-сегментных счётчиков."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.bot.handlers.discover import build_stats_screen


def _cbs(kb):
    return [b.callback_data for row in kb.inline_keyboard for b in row if b.callback_data]


async def test_free_sees_stats_paywall():
    user = SimpleNamespace(id=1, plan="free")
    text, kb = await build_stats_screen(user, "ru")
    assert "pay_plan:pro" in _cbs(kb)      # статистика — с Профи


async def test_start_sees_stats_paywall():
    user = SimpleNamespace(id=2, plan="start")
    _, kb = await build_stats_screen(user, "ru")
    assert "pay_plan:pro" in _cbs(kb)


async def test_segment_stats_sums_over_days(monkeypatch):
    import app.cache.subscription_cache as sc
    # fake redis: mget возвращает по 2 значения на каждый вызов (2 дня)
    redis = SimpleNamespace(mget=AsyncMock(return_value=[b"3", b"4"]))
    monkeypatch.setattr(sc, "get_redis", AsyncMock(return_value=redis))
    totals = await sc.get_segment_stats(user_id=1, segment_ids=[10], days=2)
    assert totals == {10: 7}


async def test_segment_stats_empty_ids():
    import app.cache.subscription_cache as sc
    assert await sc.get_segment_stats(1, [], 30) == {}
