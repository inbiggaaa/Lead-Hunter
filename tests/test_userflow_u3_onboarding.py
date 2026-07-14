from pathlib import Path

from app.bot.handlers.catalog_nav import trial_days_for_source
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
