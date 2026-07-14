"""Sparse lifecycle EOD reports: total demand, shown teasers, and missed leads."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import app.worker.end_of_day as eod


class _Result:
    def __init__(self, users): self._users = users
    def scalars(self): return SimpleNamespace(all=lambda: self._users)


class _Session:
    def __init__(self, users): self.users = users
    async def execute(self, _q): return _Result(self.users)
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return False


def _factory(users): return lambda: _Session(users)


@pytest.fixture
def fake_bot(monkeypatch):
    bot = SimpleNamespace(send_message=AsyncMock(), session=SimpleNamespace(close=AsyncMock()))
    monkeypatch.setattr(eod, "Bot", lambda *a, **k: bot)
    return bot


async def test_zero_leads_gets_one_diagnostic(fake_bot, monkeypatch):
    now = datetime.now(timezone.utc)
    users = [SimpleNamespace(id=1, telegram_id=111, language="ru", plan="free", free_lifecycle_at=now)]
    monkeypatch.setattr(eod, "async_session_factory", _factory(users))
    monkeypatch.setattr(eod, "daily_counts", AsyncMock(return_value=(0, 0)))
    await eod.send_end_of_day_reports(now)
    fake_bot.send_message.assert_awaited_once()
    assert fake_bot.send_message.await_args.kwargs["reply_markup"].inline_keyboard[0][0].callback_data == "menu:subs"


async def test_report_shows_total_delivered_and_missed_with_direct_plan_buttons(fake_bot, monkeypatch):
    now = datetime.now(timezone.utc)
    users = [SimpleNamespace(id=1, telegram_id=111, language="ru", plan="free", source="direct", free_lifecycle_at=now)]
    monkeypatch.setattr(eod, "async_session_factory", _factory(users))
    monkeypatch.setattr(eod, "daily_counts", AsyncMock(return_value=(7, 2)))
    monkeypatch.setattr("app.analytics.record_event", AsyncMock())
    await eod.send_end_of_day_reports(now)
    text = fake_bot.send_message.await_args.args[1]
    assert "7" in text and "2" in text and "5" in text
    kb = fake_bot.send_message.await_args.kwargs["reply_markup"]
    assert [row[0].callback_data for row in kb.inline_keyboard] == ["pay_plan:start", "pay_plan:pro", "pay_plan:business"]


async def test_report_is_silent_between_sparse_days(fake_bot, monkeypatch):
    now = datetime.now(timezone.utc)
    users = [SimpleNamespace(id=1, telegram_id=111, language="en", plan="free", free_lifecycle_at=now - timedelta(days=2))]
    monkeypatch.setattr(eod, "async_session_factory", _factory(users))
    monkeypatch.setattr(eod, "daily_counts", AsyncMock(return_value=(9, 0)))
    await eod.send_end_of_day_reports(now)
    fake_bot.send_message.assert_not_awaited()
