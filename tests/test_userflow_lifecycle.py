"""U8/U9 lifecycle and one-time winback pricing contract."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import app.lifecycle as lc
from app.bot.handlers.plan import PLANS, _calc, _calc_winback
from app.locales import get_text, validate_locale_schema


class _Redis:
    def __init__(self):
        self.values = {}
        self.counts = {}
    async def set(self, key, value, nx=False, ex=None):
        if nx and key in self.values: return None
        self.values[key] = value
        return True
    async def incr(self, key):
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]
    async def expire(self, *args): return True


@pytest.mark.parametrize("day, expected", [(0, True), (1, False), (3, True), (7, True), (14, True), (30, False)])
def test_sparse_teaser_days(day, expected):
    assert (day in lc.TEASER_DAYS) is expected


def test_lifecycle_day_is_calendar_based():
    anchor = datetime(2026, 7, 1, 23, tzinfo=timezone.utc)
    assert lc.lifecycle_day(anchor, datetime(2026, 7, 4, 1, tzinfo=timezone.utc)) == 3


async def test_only_two_unique_teasers_and_duplicates_never_resurface(monkeypatch):
    redis = _Redis()
    anchor = datetime.now(timezone.utc)
    monkeypatch.setattr(lc, "ensure_free_lifecycle", AsyncMock(return_value=anchor))
    monkeypatch.setattr(lc, "get_redis", AsyncMock(return_value=redis))
    assert await lc.claim_free_teaser(1, "a", anchor) == (True, 0)
    assert await lc.claim_free_teaser(1, "b", anchor) == (True, 0)
    assert await lc.claim_free_teaser(1, "c", anchor) == (False, 0)
    assert await lc.claim_free_teaser(1, "a", anchor) == (False, 0)


def test_winback_is_25_percent_not_regular_three_month_discount():
    for plan in PLANS:
        regular = _calc(plan, "3m")["total"]
        promo = _calc_winback(plan)["total"]
        assert promo == PLANS[plan]["usd_monthly"] * 3 * 0.75
        assert promo < regular


def test_ru_en_winback_contract_and_callback_budget():
    validate_locale_schema()
    for lang in ("ru", "en"):
        text = get_text(lang, "winback_offer", missed=42, expires="01.08.2026 10:00 UTC")
        assert "42" in text and "25%" in text and "12" in text
    for plan in PLANS:
        assert len(f"winback:pay:crypto:{plan}".encode()) <= 64
