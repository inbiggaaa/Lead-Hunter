"""Pre-expiry reminders and winback offer presentation."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
import app.worker.reminders as rem


class _NoExisting:
    def scalar_one_or_none(self): return None


class _Session:
    def __init__(self):
        self.execute = AsyncMock(return_value=_NoExisting())
        self.add = lambda obj: None
        self.commit = AsyncMock()


@pytest.fixture
def capture_bot(monkeypatch):
    bot = SimpleNamespace(send_message=AsyncMock(), session=SimpleNamespace(close=AsyncMock()))
    monkeypatch.setattr(rem, "Bot", lambda *a, **k: bot)
    return bot


async def test_trial_ending_has_price_and_plan_button(capture_bot):
    user = SimpleNamespace(id=1, telegram_id=111, language="ru", plan="trial")
    await rem._maybe_send(_Session(), user, "trial_ending", 2)
    call = capture_bot.send_message.await_args
    assert "$" in call.args[1] and "{start}" not in call.args[1]
    assert call.kwargs["reply_markup"].inline_keyboard[0][0].callback_data == "menu:plan"


async def test_subscription_ending_renews_current_plan(capture_bot):
    user = SimpleNamespace(id=1, telegram_id=111, language="en", plan="pro")
    await rem._maybe_send(_Session(), user, "subscription_ending", 5)
    cbs = [b.callback_data for row in capture_bot.send_message.await_args.kwargs["reply_markup"].inline_keyboard for b in row]
    assert cbs == ["pay_plan:pro", "menu:plan"]


def test_winback_keyboard_has_direct_three_month_plan_choices():
    kb = rem._offer_keyboard("ru")
    assert [row[0].callback_data for row in kb.inline_keyboard] == ["winback:buy:start", "winback:buy:pro", "winback:buy:business"]
    assert all("$" in row[0].text for row in kb.inline_keyboard)
