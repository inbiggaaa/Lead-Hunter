"""Sender closed-matching feedback keyboard tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import settings
from app.matching_feedback.domain import decode_feedback_callback
from app.worker.sender import NotificationSender
from tests.test_sender import _make_sender, _payload, _run_send


def _button_texts(kb) -> list[str]:
    return [btn.text for row in kb.inline_keyboard for btn in row]


@pytest.mark.asyncio
async def test_tester_gets_three_feedback_buttons(monkeypatch):
    monkeypatch.setattr(settings, "matching_feedback_enabled", True)
    monkeypatch.setattr(settings, "matching_feedback_tester_ids", "100500")
    monkeypatch.setattr(settings, "matching_feedback_batch", "ru_matching_v1")

    sender = _make_sender()
    fake_item = MagicMock(public_token="AbCdEf123456")
    with patch(
        "app.matching_feedback.repository.get_or_create_feedback_item",
        new=AsyncMock(return_value=fake_item),
    ) as create_item:
        result = await _run_send(
            sender,
            _payload(
                matched_segment_slugs=["cleaning"],
                matching_feedback_snapshot={
                    "delivered_segments": ["cleaning"],
                    "rule_segments": ["cleaning"],
                    "reality_segments": ["cleaning"],
                    "legacy_llm_verdict": "DEMAND",
                },
            ),
        )
    assert result == "ok"
    create_item.assert_awaited()
    kb = sender.bot.send_message.call_args.kwargs["reply_markup"]
    texts = _button_texts(kb)
    assert texts[:3] == ["✅ Верно", "⚠️ Ошибка", "🤷 Не уверен"]
    decoded = decode_feedback_callback(kb.inline_keyboard[0][0].callback_data)
    assert decoded.token == "AbCdEf123456"
    assert decoded.action == "correct"


@pytest.mark.asyncio
async def test_non_tester_keeps_legacy_keyboard(monkeypatch):
    monkeypatch.setattr(settings, "matching_feedback_enabled", True)
    monkeypatch.setattr(settings, "matching_feedback_tester_ids", "999")
    monkeypatch.setattr(settings, "matching_feedback_batch", "ru_matching_v1")

    sender = _make_sender()
    with patch(
        "app.matching_feedback.repository.get_or_create_feedback_item",
        new=AsyncMock(),
    ) as create_item:
        await _run_send(sender, _payload())
    create_item.assert_not_awaited()
    kb = sender.bot.send_message.call_args.kwargs["reply_markup"]
    texts = _button_texts(kb)
    assert "👍" in texts and "👎" in texts


@pytest.mark.asyncio
async def test_feedback_db_failure_still_sends_lead(monkeypatch):
    monkeypatch.setattr(settings, "matching_feedback_enabled", True)
    monkeypatch.setattr(settings, "matching_feedback_tester_ids", "100500")
    monkeypatch.setattr(settings, "matching_feedback_batch", "ru_matching_v1")

    sender = _make_sender()
    with patch(
        "app.matching_feedback.repository.get_or_create_feedback_item",
        new=AsyncMock(side_effect=RuntimeError("db unavailable")),
    ):
        result = await _run_send(sender, _payload())
    assert result == "ok"
    sender.bot.send_message.assert_awaited_once()
    kb = sender.bot.send_message.call_args.kwargs["reply_markup"]
    assert "👍" in _button_texts(kb)


@pytest.mark.asyncio
async def test_retry_reuses_same_feedback_item(monkeypatch):
    monkeypatch.setattr(settings, "matching_feedback_enabled", True)
    monkeypatch.setattr(settings, "matching_feedback_tester_ids", "100500")
    monkeypatch.setattr(settings, "matching_feedback_batch", "ru_matching_v1")

    from aiogram.exceptions import TelegramRetryAfter

    sender = _make_sender()
    sender.bot.send_message = AsyncMock(
        side_effect=[
            TelegramRetryAfter(method=MagicMock(), message="slow", retry_after=0),
            MagicMock(),
        ]
    )
    fake_item = MagicMock(public_token="TokSame99")
    with (
        patch(
            "app.matching_feedback.repository.get_or_create_feedback_item",
            new=AsyncMock(return_value=fake_item),
        ) as create_item,
        patch("app.worker.sender.asyncio.sleep", new=AsyncMock()),
    ):
        result = await _run_send(sender, _payload())
    assert result == "ok"
    assert create_item.await_count == 1
    assert sender.bot.send_message.await_count == 2
    first_kb = sender.bot.send_message.call_args_list[0].kwargs["reply_markup"]
    second_kb = sender.bot.send_message.call_args_list[1].kwargs["reply_markup"]
    assert first_kb.inline_keyboard[0][0].callback_data == second_kb.inline_keyboard[0][0].callback_data
