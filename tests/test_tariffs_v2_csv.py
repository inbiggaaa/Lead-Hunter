"""T5.2 — CSV-экспорт: сборка CSV из метаданных + пейволл-гейт (Бизнес)."""

import datetime
from types import SimpleNamespace

import pytest

from app.bot.handlers.discover import _build_csv
from app.bot.handlers.plan import next_plan_for, build_paywall


def _row(**kw):
    base = dict(sent_at=datetime.datetime(2026, 7, 13, 12, 34), chat_username="danang_chat",
               segment="🍜 Кейтеринг", sender="anna", message_id=77, is_urgent=False)
    base.update(kw)
    return SimpleNamespace(**base)


def test_csv_header_and_row():
    csv = _build_csv([_row()])
    lines = csv.strip().splitlines()
    assert lines[0] == "date,chat,segment,sender,link,urgent"
    assert "danang_chat" in lines[1]
    assert "https://t.me/danang_chat/77" in lines[1]
    assert "@anna" in lines[1]


def test_csv_handles_missing_link():
    csv = _build_csv([_row(chat_username=None, message_id=None)])
    fields = csv.strip().splitlines()[1].split(",")
    # date, chat(пусто), segment, sender, link(пусто), urgent — без падения
    assert fields[1] == "" and "t.me" not in csv


def test_csv_no_lead_text_column():
    # приватность: полного текста заявки в экспорте нет
    csv = _build_csv([_row()])
    assert "text" not in csv.splitlines()[0]


def test_csv_gated_to_business():
    assert next_plan_for("csv", "free") == "business"
    assert next_plan_for("csv", "pro") == "business"
    _, kb = build_paywall("csv", "pro", "ru")
    cbs = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert "pay_plan:business" in cbs
