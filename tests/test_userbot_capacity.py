"""Phase 1 — pure capacity governor model and configuration."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.userbot.capacity import (
    FloodSeverity,
    GovernorState,
    capacity_required,
    classify_flood,
    recovery_plan,
)


def test_classify_flood_boundaries() -> None:
    assert classify_flood(60) is FloodSeverity.SHORT
    assert classify_flood(61) is FloodSeverity.MEDIUM
    assert classify_flood(1800) is FloodSeverity.MEDIUM
    assert classify_flood(1801) is FloodSeverity.LONG


def test_long_recovery_is_gradual() -> None:
    stages = recovery_plan(FloodSeverity.LONG)
    assert [stage.power_percent for stage in stages] == [10, 25, 50, 75, 100]
    assert [stage.hold_seconds for stage in stages[:-1]] == [1800, 3600, 7200, 14400]


def test_capacity_keeps_thirty_percent_reserve() -> None:
    result = capacity_required(
        projected_daily_rpc=8000,
        account_count=2,
        safe_daily_budget=4000,
        reserve_ratio=0.30,
    )
    assert result.usable_per_account == 2800
    assert result.required_accounts == 3
    assert result.additional_accounts == 1
    assert result.has_deficit is True


def test_capacity_zero_accounts_reports_full_utilization() -> None:
    result = capacity_required(
        projected_daily_rpc=100,
        account_count=0,
        safe_daily_budget=4000,
        reserve_ratio=0.30,
    )
    assert result.utilization_percent == 100
    assert result.required_accounts == 1
    assert result.additional_accounts == 1
    assert result.has_deficit is True


def test_governor_config_defaults_and_ordering() -> None:
    from app.config import settings

    assert settings.userbot_safe_daily_budget == 4000
    assert settings.userbot_capacity_reserve_ratio == 0.30
    assert settings.userbot_poll_slice_size == 25
    assert settings.userbot_governor_soft_percent == 70
    assert settings.userbot_governor_hard_percent == 85
    assert settings.userbot_governor_stop_percent == 95
    assert settings.userbot_max_continuous_minutes == 45
    assert settings.userbot_recovery_stable_windows == 3
    assert settings.userbot_rpc_metrics_enabled is True
    assert settings.userbot_governor_enforcing is False
    assert settings.userbot_adaptive_polling_enabled is False
    assert (
        settings.userbot_governor_soft_percent
        < settings.userbot_governor_hard_percent
        < settings.userbot_governor_stop_percent
    )


def _minimal_settings_kwargs(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "bot_token": "1:test",
        "owner_telegram_id": 1,
        "userbot_api_id": 1,
        "userbot_api_hash": "hash",
        "postgres_password": "pw",
        "admin_password": "admin",
    }
    base.update(overrides)
    return base


def test_invalid_governor_percent_order_fails_startup() -> None:
    with pytest.raises(ValidationError):
        Settings(
            **_minimal_settings_kwargs(
                userbot_governor_soft_percent=90,
                userbot_governor_hard_percent=80,
                userbot_governor_stop_percent=95,
            )
        )


def test_invalid_reserve_ratio_fails_startup() -> None:
    with pytest.raises(ValidationError):
        Settings(**_minimal_settings_kwargs(userbot_capacity_reserve_ratio=0.95))


def test_governor_state_enum_values() -> None:
    assert set(GovernorState) == {
        GovernorState.NORMAL,
        GovernorState.THROTTLED,
        GovernorState.COOLDOWN,
        GovernorState.RECOVERY,
        GovernorState.QUARANTINED,
        GovernorState.OFFLINE,
    }
