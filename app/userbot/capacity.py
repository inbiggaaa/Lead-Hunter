"""Pure capacity governor types and calculations (no I/O)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from math import ceil, floor


class GovernorState(StrEnum):
    NORMAL = "NORMAL"
    THROTTLED = "THROTTLED"
    COOLDOWN = "COOLDOWN"
    RECOVERY = "RECOVERY"
    QUARANTINED = "QUARANTINED"
    OFFLINE = "OFFLINE"


class FloodSeverity(StrEnum):
    SHORT = "short"
    MEDIUM = "medium"
    LONG = "long"


@dataclass(frozen=True)
class RecoveryStage:
    power_percent: int
    hold_seconds: int


@dataclass(frozen=True)
class CapacityResult:
    projected_daily_rpc: int
    usable_per_account: int
    required_accounts: int
    additional_accounts: int
    utilization_percent: int
    has_deficit: bool


@dataclass(frozen=True)
class GovernorSnapshot:
    account_id: int
    state: GovernorState
    power_percent: int
    recommended_state: GovernorState
    recommended_power_percent: int
    severity: FloodSeverity | None
    cooldown_until: int | None
    stage_index: int | None
    stage_until: int | None
    stable_windows: int
    last_flood_at: int | None
    last_flood_seconds: int
    last_rpc_at: int | None
    continuous_started_at: int | None


_RECOVERY_PLANS: dict[FloodSeverity, tuple[tuple[int, int], ...]] = {
    FloodSeverity.SHORT: ((25, 600), (50, 900), (75, 1800), (100, 0)),
    FloodSeverity.MEDIUM: ((10, 900), (25, 1800), (50, 3600), (75, 7200), (100, 0)),
    FloodSeverity.LONG: ((10, 1800), (25, 3600), (50, 7200), (75, 14400), (100, 0)),
}


def classify_flood(seconds: int) -> FloodSeverity:
    if seconds <= 60:
        return FloodSeverity.SHORT
    if seconds <= 1800:
        return FloodSeverity.MEDIUM
    return FloodSeverity.LONG


def recovery_plan(severity: FloodSeverity) -> tuple[RecoveryStage, ...]:
    stages = _RECOVERY_PLANS[severity]
    return tuple(
        RecoveryStage(power_percent=power, hold_seconds=hold)
        for power, hold in stages
    )


def capacity_required(
    projected_daily_rpc: int,
    account_count: int,
    safe_daily_budget: int,
    reserve_ratio: float,
) -> CapacityResult:
    usable = floor(safe_daily_budget * (1.0 - reserve_ratio))
    if usable < 1:
        usable = 1
    required = ceil(projected_daily_rpc / usable) if projected_daily_rpc > 0 else 0
    if projected_daily_rpc > 0 and required < 1:
        required = 1
    additional = max(0, required - account_count)
    if account_count == 0:
        utilization = 100
    else:
        fleet_usable = usable * account_count
        utilization = min(
            100,
            ceil((projected_daily_rpc / fleet_usable) * 100) if fleet_usable else 100,
        )
    return CapacityResult(
        projected_daily_rpc=projected_daily_rpc,
        usable_per_account=usable,
        required_accounts=required,
        additional_accounts=additional,
        utilization_percent=utilization,
        has_deficit=additional > 0,
    )
