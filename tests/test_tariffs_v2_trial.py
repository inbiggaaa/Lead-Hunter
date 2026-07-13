"""T4.3 — trial-воронка: trial_ending/trial_expired форматируют цену + кнопка апгрейда."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import app.worker.reminders as rem


class _NoExisting:
    def scalar_one_or_none(self):
        return None


class _Session:
    def __init__(self):
        self.execute = AsyncMock(return_value=_NoExisting())
        self.add = lambda obj: None
        self.commit = AsyncMock()


@pytest.fixture
def capture_bot(monkeypatch):
    bot = SimpleNamespace(send_message=AsyncMock(),
                          session=SimpleNamespace(close=AsyncMock()))
    monkeypatch.setattr(rem, "Bot", lambda *a, **k: bot)
    return bot


async def _send(capture_bot, rtype, day):
    user = SimpleNamespace(id=1, telegram_id=111, language="ru")
    await rem._maybe_send(_Session(), user, rtype, day)
    return capture_bot.send_message.await_args


async def test_trial_ending_has_price_and_button(capture_bot):
    call = await _send(capture_bot, "trial_ending", 2)
    text = call.args[1]
    assert "$" in text and "{start}" not in text          # цена подставлена
    kb = call.kwargs["reply_markup"]
    cbs = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert "menu:plan" in cbs


async def test_trial_expired_has_button_and_no_dead_tariffs(capture_bot):
    call = await _send(capture_bot, "trial_expired", 1)
    text = call.args[1]
    assert "Pro или Business" not in text and "150" not in text
    assert call.kwargs["reply_markup"] is not None


async def test_non_upgrade_type_no_keyboard(capture_bot):
    # subscription_expired пока без клавиатуры (кнопка добавится в T4.6)
    call = await _send(capture_bot, "subscription_expired", 1)
    assert call.kwargs["reply_markup"] is None


async def test_inactive_winback_has_search_button(capture_bot):
    # T4.4: winback неактивности → re-engage кнопка «Поиск клиентов»
    call = await _send(capture_bot, "inactive", 14)
    kb = call.kwargs["reply_markup"]
    cbs = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert "menu:search" in cbs


async def _send_plan(capture_bot, rtype, day, plan):
    user = SimpleNamespace(id=1, telegram_id=111, language="ru", plan=plan)
    await rem._maybe_send(_Session(), user, rtype, day)
    return capture_bot.send_message.await_args


async def test_subscription_ending_renew_current_plan(capture_bot):
    # T4.6: за 5 дней до истечения — кнопка продления ТЕКУЩЕГО плана + другие тарифы
    call = await _send_plan(capture_bot, "subscription_ending", 5, "pro")
    kb = call.kwargs["reply_markup"]
    cbs = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert "pay_plan:pro" in cbs      # продлить текущий
    assert "menu:plan" in cbs         # другие тарифы


async def test_subscription_expired_start_gets_renew(capture_bot):
    # T4.6-фикс: start — тоже платный, получает кнопку продления
    call = await _send_plan(capture_bot, "subscription_expired", 1, "start")
    cbs = [b.callback_data for row in call.kwargs["reply_markup"].inline_keyboard for b in row]
    assert "pay_plan:start" in cbs
