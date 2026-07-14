"""Tests for task A3 (fable_audit.md) — sender: HTML escaping + retry/DLQ.

Bug C3: _format_notification inserted raw lead text into a ParseMode.HTML
message — any «<», «>», «&» made Telegram reject the request, the exception
was swallowed and the lead was lost forever (no retry, no dead-letter).
DECISIONS #26 retry policy (403 → block user, 429 → sleep+retry,
other → 3 retries then DLQ) was never implemented in the sender.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter

from app.worker.sender import NotificationSender


def _payload(**overrides) -> dict:
    payload = {
        "user_id": 42,
        "telegram_id": 100500,
        "lang": "ru",
        "plan": "business",
        "chat_username": "test_chat",
        "text": "Ищу байк, цена <3000$ & срочно <b>сегодня</b>",
        "sender": "lead_author",
        "message_id": 77,
        "message_hash": "hash77",
        "content_hash": "chash77",
        "is_urgent": False,
        "matched_segments": [{"emoji": "🛵", "title": "Аренда скутеров"}],
    }
    payload.update(overrides)
    return payload


def _make_sender() -> NotificationSender:
    with patch("app.worker.sender.Bot"):
        sender = NotificationSender()
    sender.bot = MagicMock()
    sender.bot.send_message = AsyncMock()
    return sender


def _quiet_patches():
    """Silence dedup/limits/stats — focus tests on delivery logic."""
    return [
        patch("app.worker.sender.is_duplicate", new=AsyncMock(return_value=False)),
        patch("app.worker.sender.is_content_duplicate", new=AsyncMock(return_value=False)),
        patch("app.worker.sender.mark_sent", new=AsyncMock()),
        patch("app.worker.sender.increment_daily_stats", new=AsyncMock()),
    ]


async def _run_send(sender, payload):
    patches = _quiet_patches()
    for p in patches:
        p.start()
    try:
        await sender._send_notification(payload)
    finally:
        for p in patches:
            p.stop()


# ═══ A3.1: HTML escaping ═══


def test_format_escapes_user_content():
    """«<», «>», «&» из текста лида экранируются; собственные теги шаблона целы."""
    sender = _make_sender()
    text = sender._format_notification(_payload())

    assert "&lt;3000$" in text
    assert "&lt;b&gt;сегодня&lt;/b&gt;" in text
    assert "&amp; срочно" in text
    # Шаблонная разметка не тронута
    assert "<b>" in text  # заголовок уведомления
    assert "<a href='https://t.me/test_chat/77'>" in text


def test_format_escapes_sender_and_chat():
    """Username отправителя/чата с спецсимволами не ломают разметку."""
    sender = _make_sender()
    text = sender._format_notification(
        _payload(sender="evil<i>name", chat_username="chat&co")
    )
    assert "evil<i>name" not in text
    assert "evil&lt;i&gt;name" in text


async def test_send_with_html_chars_delivers():
    """Уведомление с HTML-символами доходит до bot.send_message без исключений."""
    sender = _make_sender()
    await _run_send(sender, _payload())
    sender.bot.send_message.assert_awaited_once()
    sent_text = sender.bot.send_message.call_args.args[1]
    assert "&lt;3000$" in sent_text


# ═══ A3.2: retry / DLQ (DECISIONS #26) ═══


async def test_forbidden_marks_user_blocked():
    """403 → is_blocked_bot=true, без ретраев и без DLQ."""
    sender = _make_sender()
    sender.bot.send_message = AsyncMock(
        side_effect=TelegramForbiddenError(method=MagicMock(), message="bot was blocked")
    )
    with patch("app.worker.sender.mark_user_blocked", new=AsyncMock()) as blocked, \
         patch("app.worker.sender.push_dead_letter", new=AsyncMock()) as dlq:
        await _run_send(sender, _payload())

    blocked.assert_awaited_once_with(42)
    dlq.assert_not_awaited()
    assert sender.bot.send_message.await_count == 1


async def test_retry_after_sleeps_and_retries():
    """429 → sleep(retry_after) → повтор → успех."""
    sender = _make_sender()
    sender.bot.send_message = AsyncMock(
        side_effect=[
            TelegramRetryAfter(method=MagicMock(), message="flood", retry_after=7),
            MagicMock(),
        ]
    )
    with patch("app.worker.sender.asyncio.sleep", new=AsyncMock()) as sleep, \
         patch("app.worker.sender.push_dead_letter", new=AsyncMock()) as dlq:
        await _run_send(sender, _payload())

    assert sender.bot.send_message.await_count == 2
    sleep.assert_any_await(7)
    dlq.assert_not_awaited()


async def test_generic_error_retries_then_dlq():
    """Прочие ошибки → 3 ретрая (1с/4с/9с) → payload в dead-letter."""
    sender = _make_sender()
    sender.bot.send_message = AsyncMock(side_effect=RuntimeError("network down"))

    with patch("app.worker.sender.asyncio.sleep", new=AsyncMock()) as sleep, \
         patch("app.worker.sender.push_dead_letter", new=AsyncMock()) as dlq:
        await _run_send(sender, _payload())

    assert sender.bot.send_message.await_count == 4  # 1 + 3 ретрая
    sleep.assert_any_await(1)
    sleep.assert_any_await(4)
    sleep.assert_any_await(9)
    dlq.assert_awaited_once()
    dead_payload = dlq.call_args.args[0]
    assert json.dumps(dead_payload)  # сериализуемый
    assert dead_payload["user_id"] == 42


# ═══════════════════════════════════════════════════════════════════
# D1: Free-пейволл — ни одной ссылки на чат/отправителя (DECISIONS #79)
# ═══════════════════════════════════════════════════════════════════


def _keyboard_urls(kb) -> list[str]:
    return [
        btn.url
        for row in kb.inline_keyboard
        for btn in row
        if btn.url
    ]


def test_free_format_no_links():
    """Free: полный текст лида, но без <a href> — чат plain-текстом, отправителя нет."""
    sender = _make_sender()
    text = sender._format_notification(_payload(plan="free"))
    assert "<a href" not in text
    assert "t.me" not in text
    assert "@test_chat" in text          # название чата — просто текстом
    assert "lead_author" not in text     # отправитель скрыт полностью
    assert "Контакты скрыты" in text


def test_free_keyboard_no_chat_button():
    """Free: кнопки «💬 Чат» нет, CTA «Открыть контакты» и 👍👎 на месте (T3.5)."""
    sender = _make_sender()
    kb = sender._build_keyboard(_payload(plan="free"))
    assert _keyboard_urls(kb) == []
    all_texts = [btn.text for row in kb.inline_keyboard for btn in row]
    assert any("Открыть контакты" in t for t in all_texts)
    assert "👍" in all_texts and "👎" in all_texts


@pytest.mark.parametrize("plan", ["start", "pro", "business", "trial"])
def test_paid_format_keeps_links(plan):
    """Paid/Trial: ссылки на сообщение и отправителя не тронуты."""
    sender = _make_sender()
    text = sender._format_notification(_payload(plan=plan))
    assert "https://t.me/test_chat/77" in text
    assert "https://t.me/lead_author" in text
    assert "Контакты скрыты" not in text


@pytest.mark.parametrize("plan", ["start", "pro", "business", "trial"])
def test_paid_keyboard_keeps_buttons(plan):
    """Paid/Trial: кнопки «💬 Чат» и «💬 Написать» на месте."""
    sender = _make_sender()
    kb = sender._build_keyboard(_payload(plan=plan))
    urls = _keyboard_urls(kb)
    assert "https://t.me/test_chat/77" in urls
    assert "https://t.me/lead_author" in urls


# ═══ Название чата вместо «-100…»-ID ═══

def test_title_preferred_over_username():
    """Есть chat_title → в тексте название, а не «@username» и не голый id."""
    sender = _make_sender()
    text = sender._format_notification(
        _payload(plan="business", chat_username="test_chat", chat_title="Аренда Бали")
    )
    assert "Аренда Бали" in text
    assert "@test_chat" not in text
    # ссылка на сообщение всё равно ведёт по username
    assert "https://t.me/test_chat/77" in text


def test_private_group_shows_title_not_numeric_id():
    """Приватная группа (-100…) без @username: название вместо голого id."""
    sender = _make_sender()
    text = sender._format_notification(_payload(
        plan="business", chat_username="-1002046178126",
        chat_title="TravelAsk — Пхукет", message_id=124035,
    ))
    assert "TravelAsk — Пхукет" in text
    assert "-1002046178126" not in text
    # «-100…» линк невалиден как t.me/<id> → используется t.me/c/<internal>
    assert "https://t.me/c/2046178126/124035" in text
    assert "https://t.me/-100" not in text


def test_private_group_free_plain_title():
    """Free + приватная группа: название plain-текстом, ни одной ссылки."""
    sender = _make_sender()
    text = sender._format_notification(_payload(
        plan="free", chat_username="-1002046178126", chat_title="TravelAsk — Пхукет",
    ))
    assert "TravelAsk — Пхукет" in text
    assert "t.me" not in text
    assert "-1002046178126" not in text


def test_private_group_no_title_falls_back():
    """Нет ни title, ни @username: показываем «группа -100…», а не голый id-как-username."""
    sender = _make_sender()
    text = sender._format_notification(_payload(
        plan="business", chat_username="-1002046178126", chat_title=None,
    ))
    assert "группа -1002046178126" in text


def test_private_group_keyboard_uses_c_link():
    """Кнопка «💬 Чат» приватной группы ведёт по t.me/c/, не по битому t.me/-100."""
    sender = _make_sender()
    kb = sender._build_keyboard(_payload(
        plan="business", chat_username="-1002046178126", message_id=124035,
    ))
    urls = _keyboard_urls(kb)
    assert "https://t.me/c/2046178126/124035" in urls
    assert not any(u.startswith("https://t.me/-100") for u in urls)


# ═══ T1.2: дневной лимит уведомлений отменён (#81) ═══


async def test_free_plan_gets_claimed_teaser(monkeypatch):
    """A Free notification is delivered only after claiming a lifecycle slot."""
    monkeypatch.setattr("app.lifecycle.claim_free_teaser", AsyncMock(return_value=(True, 0)))
    sender = _make_sender()
    await _run_send(sender, _payload(plan="free"))
    assert sender.bot.send_message.await_count == 1


def test_no_daily_limit_symbols_left():
    """В sender не осталось ссылок на снятый механизм лимита."""
    import app.worker.sender as s
    assert not hasattr(s.NotificationSender, "_send_limit_warning")
    assert "check_daily_limit" not in dir(s)
