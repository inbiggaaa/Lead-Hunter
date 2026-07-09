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
        patch("app.worker.sender.check_daily_limit", new=AsyncMock(return_value=False)),
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
