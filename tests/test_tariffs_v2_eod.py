"""T4.2 — End-of-day v2: только Free с заявками>0, «скрытые контакты», кнопка апгрейда."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import app.worker.end_of_day as eod


class _Result:
    def __init__(self, users=None, count=None):
        self._users, self._count = users, count

    def scalars(self):
        return SimpleNamespace(all=lambda: self._users)

    def scalar(self):
        return self._count


class _Session:
    def __init__(self, result):
        self._result = result

    async def execute(self, _q):
        return self._result

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


def _factory(users, counts):
    """Первый сеанс → список Free-юзеров; далее по сеансу на count каждого."""
    sessions = [_Session(_Result(users=users))] + [_Session(_Result(count=c)) for c in counts]
    it = iter(sessions)
    return lambda: next(it)


@pytest.fixture
def fake_bot(monkeypatch):
    bot = SimpleNamespace(send_message=AsyncMock(),
                          session=SimpleNamespace(close=AsyncMock()))
    monkeypatch.setattr(eod, "Bot", lambda *a, **k: bot)
    return bot


async def test_zero_leads_user_skipped(fake_bot, monkeypatch):
    users = [SimpleNamespace(id=1, telegram_id=111, language="ru", plan="free")]
    monkeypatch.setattr(eod, "async_session_factory", _factory(users, [0]))
    await eod.send_end_of_day_reports()
    fake_bot.send_message.assert_not_awaited()


async def test_free_user_with_leads_gets_report(fake_bot, monkeypatch):
    users = [SimpleNamespace(id=1, telegram_id=111, language="ru", plan="free")]
    monkeypatch.setattr(eod, "async_session_factory", _factory(users, [7]))
    await eod.send_end_of_day_reports()
    fake_bot.send_message.assert_awaited_once()
    kwargs = fake_bot.send_message.await_args.kwargs
    text = fake_bot.send_message.await_args.args[1]
    assert "7" in text and "лимит" not in text.lower()   # без старой лимитной риторики
    # есть кнопка апгрейда на экран тарифа
    kb = kwargs["reply_markup"]
    cbs = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert "menu:plan" in cbs
