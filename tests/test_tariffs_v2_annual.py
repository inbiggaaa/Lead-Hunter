"""T4.5 — годовой апселл: 2-й подряд месячный платёж одного плана → предложение (−20%), однократно."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import app.bot.handlers.plan as plan_mod
from app.bot.handlers.plan import maybe_offer_annual


class _CountResult:
    def __init__(self, n):
        self._n = n

    def scalar(self):
        return self._n


def _session_with_count(n):
    session = SimpleNamespace(execute=AsyncMock(return_value=_CountResult(n)))

    async def gen():
        yield session
    return gen


@pytest.fixture
def fake_bot(monkeypatch):
    bot = SimpleNamespace(send_message=AsyncMock(),
                          session=SimpleNamespace(close=AsyncMock()))
    import aiogram
    monkeypatch.setattr(aiogram, "Bot", lambda *a, **k: bot)
    return bot


@pytest.fixture
def fake_redis(monkeypatch):
    redis = SimpleNamespace(get=AsyncMock(return_value=None), set=AsyncMock())
    import app.cache
    monkeypatch.setattr(app.cache, "get_redis", AsyncMock(return_value=redis))
    return redis


async def test_annual_period_is_noop(fake_bot):
    # Годовой платёж не триггерит апселл (возврат до любого I/O).
    await maybe_offer_annual(1, 111, "pro", "1y")
    fake_bot.send_message.assert_not_awaited()


async def test_second_monthly_offers_annual(monkeypatch, fake_bot, fake_redis):
    monkeypatch.setattr(plan_mod, "get_session", _session_with_count(2))
    await maybe_offer_annual(1, 111, "pro", "1m")
    fake_bot.send_message.assert_awaited_once()
    kb = fake_bot.send_message.await_args.kwargs["reply_markup"]
    cbs = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert "pay_period:pro:1y" in cbs
    fake_redis.set.assert_awaited_once()   # флаг «уже предлагали» выставлен


async def test_first_monthly_no_offer(monkeypatch, fake_bot, fake_redis):
    monkeypatch.setattr(plan_mod, "get_session", _session_with_count(1))
    await maybe_offer_annual(1, 111, "pro", "1m")
    fake_bot.send_message.assert_not_awaited()


async def test_already_offered_skipped(monkeypatch, fake_bot, fake_redis):
    fake_redis.get = AsyncMock(return_value="1")  # флаг уже стоит
    monkeypatch.setattr(plan_mod, "get_session", _session_with_count(2))
    await maybe_offer_annual(1, 111, "pro", "1m")
    fake_bot.send_message.assert_not_awaited()
