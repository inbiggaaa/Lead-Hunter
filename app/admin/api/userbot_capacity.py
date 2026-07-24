"""Read-only userbot capacity fleet stats for admin dashboard."""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from math import floor

from fastapi import APIRouter

from app.cache import get_redis
from app.config import settings
from app.userbot.capacity import capacity_required
from app.userbot.poll_schedule import SUMMARY_KEY
from app.userbot.rate_limiter import _governor_key, _rpc_bucket_keys

router = APIRouter(prefix="/api/stats", tags=["stats"])


def _int(raw: str | None, default: int = 0) -> int:
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@router.get("/userbots")
async def userbot_capacity_stats() -> dict:
    """Compact fleet + per-account governor metrics (no Telegram calls)."""
    redis = await get_redis()
    account_ids = sorted(settings.userbot_sessions.keys())
    now = int(time.time())
    utc = datetime.now(timezone.utc)

    summary = await redis.hgetall(SUMMARY_KEY) or {}
    eligible = _int(summary.get("eligible"))
    parked = _int(summary.get("parked"))

    # Projected daily RPC from class counts × polls/day (approx).
    class_intervals = {"A": 120, "B": 300, "C": 900, "D": 3600, "E": 21600}
    projected = 0
    for cls, interval in class_intervals.items():
        count = _int(summary.get(f"class:{cls}"))
        if count and interval:
            projected += count * int(86400 / interval)

    safe = settings.userbot_safe_daily_budget
    reserve = settings.userbot_capacity_reserve_ratio
    usable = floor(safe * (1.0 - reserve))
    available = 0
    accounts: list[dict] = []
    rpc_minutes: list[dict] = []

    for account_id in account_ids:
        gov = await redis.hgetall(_governor_key(account_id)) or {}
        state = gov.get("state") or "OFFLINE"
        power = _int(gov.get("power_percent"), 0 if not gov else 100)
        if state not in {"COOLDOWN", "QUARANTINED", "OFFLINE"} and power > 0:
            available += 1

        minute_key, hour_key, day_key = _rpc_bucket_keys(account_id, utc)
        day_total = _int(await redis.hget(day_key, "total"))
        hour_total = _int(await redis.hget(hour_key, "total"))
        _ = minute_key

        # Last 60 minute buckets without SCAN: build keys by clock.
        rpc_5m = 0
        for minutes_ago in range(60):
            stamp = (utc - timedelta(minutes=minutes_ago)).strftime("%Y%m%d%H%M")
            key = f"stats:tg_rpc:{account_id}:minute:{stamp}"
            count = _int(await redis.hget(key, "total"))
            if minutes_ago < 5:
                rpc_5m += count
            iso = (utc - timedelta(minutes=minutes_ago)).strftime("%Y-%m-%dT%H:%M:00Z")
            rpc_minutes.append(
                {"minute": iso, "account_id": account_id, "count": count}
            )

        assigned = _int(summary.get(f"assigned:{account_id}"))
        continuous_started = _int(gov.get("continuous_started_at"), 0) or None
        continuous_minutes = 0
        if continuous_started:
            continuous_minutes = max(0, (now - continuous_started) // 60)

        accounts.append(
            {
                "account_id": account_id,
                "state": state,
                "power_percent": power,
                "recommended_state": gov.get("recommended_state") or state,
                "recommended_power_percent": _int(
                    gov.get("recommended_power_percent"), power
                ),
                "rpc_5m": rpc_5m,
                "rpc_1h": hour_total,
                "rpc_6h": hour_total,  # compact v1: reuse hour until 6h bucket exists
                "rpc_24h": day_total,
                "safe_daily_budget": safe,
                "utilization_percent": min(100, int(day_total / max(safe, 1) * 100)),
                "continuous_minutes": continuous_minutes,
                "assigned_chats": assigned,
                "cooldown_until": _int(gov.get("cooldown_until")) or None,
                "stage_until": _int(gov.get("stage_until")) or None,
                "last_flood_seconds": _int(gov.get("last_flood_seconds")),
                "last_rpc_at": _int(gov.get("last_rpc_at")) or None,
            }
        )

    capacity = capacity_required(
        projected_daily_rpc=projected or eligible * 96,
        account_count=max(available, 0),
        safe_daily_budget=safe,
        reserve_ratio=reserve,
    )

    return {
        "fleet": {
            "configured_accounts": len(account_ids),
            "available_accounts": available,
            "required_accounts": capacity.required_accounts,
            "additional_accounts": capacity.additional_accounts,
            "utilization_percent": capacity.utilization_percent,
            "projected_daily_rpc": capacity.projected_daily_rpc,
            "safe_daily_capacity": usable,
            "eligible_chats": eligible,
            "parked_chats": parked,
            "has_deficit": capacity.has_deficit,
            "server_now": now,
        },
        "accounts": accounts,
        "rpc_minutes": rpc_minutes,
    }
