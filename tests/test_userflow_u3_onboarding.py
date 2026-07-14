import asyncio
from pathlib import Path
from unittest.mock import AsyncMock

from aiogram.types import InlineKeyboardMarkup

from app.bot.handlers.catalog_nav import _edit_text_or_replace_media, trial_days_for_source
from app.config import settings

ROOT = Path(__file__).parents[1]


def test_trial_duration_contract_is_three_and_seven_days() -> None:
    assert settings.trial_days == 3
    assert settings.referral_trial_bonus == 4
    assert settings.referral_bonus_days == 10
    assert trial_days_for_source("referral") == 7


def test_trial_duration_by_acquisition_source():
    assert trial_days_for_source("direct") == settings.trial_days
    assert trial_days_for_source("referral") == settings.trial_days + settings.referral_trial_bonus


def test_start_has_no_trial_activation_bypass():
    source = (ROOT / "app/bot/handlers/start.py").read_text()
    assert "user.plan = \"trial\"" not in source
    assert "on_show_categories(callback, state)" in source
    assert "onb:cat:" not in source


def test_trial_and_onboarded_follow_first_search_commit_path():
    source = (ROOT / "app/bot/handlers/catalog_nav.py").read_text()
    create_pos = source.index("await create_subscription(")
    onboard_pos = source.index("await set_onboarded(")
    trial_pos = source.index("user.plan = \"trial\"")
    commit_pos = source.index("await session.commit()", trial_pos)
    assert create_pos < onboard_pos < trial_pos < commit_pos


def test_first_catalog_screen_replaces_media_welcome() -> None:
    message = AsyncMock()
    message.text = None
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])

    asyncio.run(_edit_text_or_replace_media(message, "catalog", keyboard))

    message.edit_text.assert_not_awaited()
    message.edit_reply_markup.assert_awaited_once_with(reply_markup=None)
    message.answer.assert_awaited_once_with("catalog", reply_markup=keyboard)


def test_catalog_screen_still_edits_text_messages() -> None:
    message = AsyncMock()
    message.text = "welcome"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])

    asyncio.run(_edit_text_or_replace_media(message, "catalog", keyboard))

    message.edit_text.assert_awaited_once_with("catalog", reply_markup=keyboard)
    message.edit_reply_markup.assert_not_awaited()
    message.answer.assert_not_awaited()
