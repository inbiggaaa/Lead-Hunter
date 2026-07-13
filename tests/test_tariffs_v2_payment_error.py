"""T2.2 — экран ошибки оплаты: клавиатура повтора/другого способа + локали."""

import pytest

from app.locales import get_text
from app.bot.handlers.plan import payment_error_kb


def _callbacks(kb):
    return [btn.callback_data for row in kb.inline_keyboard for btn in row if btn.callback_data]


def test_error_kb_has_retry_other_back():
    kb = payment_error_kb("start", "1m", "stars", "ru")
    cbs = _callbacks(kb)
    assert "pay_exec:stars:start:1m" in cbs   # 🔄 повтор именно этого метода
    assert "pay_period:start:1m" in cbs       # 💱 другой способ
    assert "pay_plan:start" in cbs            # ◀️ назад


def test_error_kb_retry_keeps_method():
    kb = payment_error_kb("pro", "1y", "crypto", "ru")
    assert "pay_exec:crypto:pro:1y" in _callbacks(kb)


@pytest.mark.parametrize("lang", ["ru", "en"])
def test_error_texts_localized(lang):
    body = get_text(lang, "pay_error_body")
    expired = get_text(lang, "pay_error_expired")
    # ключи не «протекают» как plain slug
    assert body != "pay_error_body" and expired != "pay_error_expired"
    assert get_text(lang, "pay_err_retry") not in ("pay_err_retry",)
