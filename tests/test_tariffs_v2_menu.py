"""T3.2 — главное меню: живой счётчик заявок + пометка Free (без «X/50»)."""

from unittest.mock import AsyncMock

import pytest

from app.bot.handlers.start import _show_menu
from app.locales import get_text


async def _render(lang, matched, is_free):
    message = AsyncMock()
    await _show_menu(message, lang, "Старт", matched=matched, is_free=is_free)
    return message.answer.call_args.args[0]


async def test_menu_shows_live_matched_not_limit():
    text = await _render("ru", 7, is_free=False)
    assert "Заявок сегодня: 7" in text
    assert "/50" not in text            # старого лимитного счётчика больше нет
    assert "0/50" not in text


async def test_free_menu_has_hidden_contacts_note():
    text = await _render("ru", 3, is_free=True)
    assert get_text("ru", "menu_free_hidden") in text


async def test_paid_menu_no_hidden_note():
    text = await _render("ru", 3, is_free=False)
    assert get_text("ru", "menu_free_hidden") not in text


async def test_en_menu_counter():
    text = await _render("en", 5, is_free=True)
    assert "Leads today: 5" in text
