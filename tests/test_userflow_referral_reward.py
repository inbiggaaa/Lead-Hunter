"""Referral reward contract after the invited user's first payment."""

import datetime
from pathlib import Path

from app.bot.handlers.plan import referral_reward_expiry, referral_reward_plan

ROOT = Path(__file__).parents[1]


def test_referral_reward_keeps_active_plan() -> None:
    assert referral_reward_plan("pro", "business") == "pro"
    assert referral_reward_plan("trial", None) == "trial"


def test_referral_reward_restores_last_paid_plan() -> None:
    assert referral_reward_plan("free", "business") == "business"


def test_referral_reward_falls_back_to_start() -> None:
    assert referral_reward_plan("free", None) == "start"


def test_referral_reward_extends_future_expiry() -> None:
    now = datetime.datetime(2026, 7, 14, tzinfo=datetime.timezone.utc)
    current_expiry = now + datetime.timedelta(days=5)

    assert referral_reward_expiry(current_expiry, now, 10) == now + datetime.timedelta(days=15)


def test_referral_reward_reactivates_from_now() -> None:
    now = datetime.datetime(2026, 7, 14, tzinfo=datetime.timezone.utc)
    expired = now - datetime.timedelta(days=2)

    assert referral_reward_expiry(expired, now, 10) == now + datetime.timedelta(days=10)


def test_stars_uses_internal_user_id_for_referral_reward() -> None:
    source = (ROOT / "app/bot/handlers/plan.py").read_text()
    assert "await _apply_referral_bonus(user_db_id)" in source
    assert "await _apply_referral_bonus(message.from_user.id)" not in source
