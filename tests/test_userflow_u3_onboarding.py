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
    message.delete.assert_awaited_once_with()
    message.answer.assert_awaited_once_with("catalog", reply_markup=keyboard)


def test_catalog_screen_still_edits_text_messages() -> None:
    message = AsyncMock()
    message.text = "welcome"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])

    asyncio.run(_edit_text_or_replace_media(message, "catalog", keyboard))

    message.edit_text.assert_awaited_once_with("catalog", reply_markup=keyboard)
    message.delete.assert_not_awaited()
    message.answer.assert_not_awaited()


def test_fsm_is_persisted_in_redis() -> None:
    source = (ROOT / "app/main.py").read_text()
    assert "RedisStorage.from_url" in source
    assert "Dispatcher(storage=storage)" in source


def test_catalog_back_navigation_matches_previous_screen() -> None:
    source = (ROOT / "app/bot/handlers/catalog_nav.py").read_text()
    expected = (
        "CatStates.choosing_segments, F.data == \"cat:back:to_categories\"",
        "CatStates.choosing_geo, F.data == \"cat:back:to_country\"",
        "CatStates.choosing_cities, F.data == \"cat:back:to_country\"",
        "CatStates.confirm_subscription, F.data == \"cat:back:previous\"",
    )
    assert all(marker in source for marker in expected)


def test_stale_pre_redis_catalog_buttons_have_recovery_handlers() -> None:
    source = (ROOT / "app/bot/handlers/catalog_nav.py").read_text()
    assert "async def recover_stale_continue" in source
    assert "async def recover_stale_back" in source
    assert "_selected_segments_from_keyboard" in source


def test_confirmation_lists_selected_service_names() -> None:
    source = (ROOT / "app/bot/handlers/catalog_nav.py").read_text()
    confirmation = source[source.index("async def _show_confirmation"):source.index("async def on_subscribe")]
    assert "Segment as SegmentModel" in confirmation
    assert "segment_labels.append" in confirmation
    assert "search_scope_services" in confirmation
    assert r'text += get_text(lang, "search_scope_services") + "\n"' in confirmation
    assert "catalog_new_services" not in confirmation
    assert r'text += "\n".join(segment_labels)' in confirmation


def test_welcome_is_text_so_flow_stays_in_place() -> None:
    source = (ROOT / "app/bot/handlers/start.py").read_text()
    welcome = source[source.index("async def _show_welcome"):source.index("# ── Language selection")]
    assert "answer_photo" not in welcome
    assert "await message.answer(text, reply_markup=kb)" in welcome


def test_search_created_invites_plan_after_launch() -> None:
    source = (ROOT / "app/bot/handlers/catalog_nav.py").read_text()
    subscribe = source[source.index("async def on_subscribe"):source.index("# ═══════════════ SUBSCRIPTIONS LIST")]
    # Upsell is shown on the post-launch screen, not on the confirmation screen.
    assert "search_upsell_after" in subscribe
    assert 'callback_data="menu:plan"' in subscribe


def test_trial_can_only_be_started_once() -> None:
    source = (ROOT / "app/bot/handlers/catalog_nav.py").read_text()
    assert "first_search_completed = created > 0 and not user.onboarded" in source
    assert 'if first_search_completed and user.plan == "free":' in source
