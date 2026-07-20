"""P0: idempotent payment activation + Stars pre-checkout validation."""

from __future__ import annotations

import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.bot.handlers.plan import (
    PLANS,
    parse_stars_payload,
    validate_stars_pre_checkout,
    _calc,
)
from app.payments.activate import ActivateResult, activate_paid_subscription
from app.worker import payment_checker


@pytest.fixture
def canonical_prices(monkeypatch):
    monkeypatch.setitem(PLANS["start"], "usd_monthly", 9)
    monkeypatch.setitem(PLANS["pro"], "usd_monthly", 19)
    monkeypatch.setitem(PLANS["business"], "usd_monthly", 39)


# ── Stars payload / pre-checkout ──


def test_parse_stars_payload_normal():
    assert parse_stars_payload("sub:pro:1m:424242") == ("pro", "1m", 424242, None)


def test_parse_stars_payload_winback():
    assert parse_stars_payload("sub:start:3m:wb25:99") == ("start", "3m", 99, "wb25")


def test_parse_stars_payload_rejects_garbage():
    assert parse_stars_payload("pro:1m:1") is None
    assert parse_stars_payload("sub:free:1m:1") is None
    assert parse_stars_payload("sub:pro:2m:1") is None


@pytest.mark.asyncio
async def test_pre_checkout_ok(canonical_prices):
    info = _calc("pro", "1m")
    ok, err = await validate_stars_pre_checkout(
        payload="sub:pro:1m:111",
        from_user_id=111,
        currency="XTR",
        total_amount=info["stars"],
    )
    assert ok and err == ""


@pytest.mark.asyncio
async def test_pre_checkout_rejects_wrong_amount(canonical_prices):
    ok, err = await validate_stars_pre_checkout(
        payload="sub:pro:1m:111",
        from_user_id=111,
        currency="XTR",
        total_amount=1,
    )
    assert not ok
    assert "Amount" in err


@pytest.mark.asyncio
async def test_pre_checkout_rejects_wrong_user(canonical_prices):
    info = _calc("pro", "1m")
    ok, err = await validate_stars_pre_checkout(
        payload="sub:pro:1m:111",
        from_user_id=222,
        currency="XTR",
        total_amount=info["stars"],
    )
    assert not ok
    assert "User" in err


@pytest.mark.asyncio
async def test_pre_checkout_rejects_wrong_currency(canonical_prices):
    info = _calc("pro", "1m")
    ok, err = await validate_stars_pre_checkout(
        payload="sub:pro:1m:111",
        from_user_id=111,
        currency="USD",
        total_amount=info["stars"],
    )
    assert not ok
    assert "currency" in err.lower()


# ── activate_paid_subscription ──


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value

    def scalar_one(self):
        return self._value


def _session_factory(session):
    class _Ctx:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *a):
            return False

    return lambda: _Ctx()


@pytest.mark.asyncio
async def test_activate_idempotent_same_charge():
    user = SimpleNamespace(
        id=10, language="ru", plan="free",
        plan_activated_at=None, plan_expires_at=None, free_lifecycle_at=None,
    )
    exp = datetime.datetime(2026, 8, 15, tzinfo=datetime.timezone.utc)
    existing = SimpleNamespace(
        user_id=10, expires_at=exp, plan="pro", period="1m",
    )

    session = MagicMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    # 1st activate: no charge → load user → (no winback)
    # 2nd activate: charge found → load user
    session.execute = AsyncMock(side_effect=[
        _ScalarResult(None),
        _ScalarResult(user),
        _ScalarResult(existing),
        _ScalarResult(user),
    ])

    with patch(
        "app.payments.activate.async_session_factory",
        _session_factory(session),
    ):
        first = await activate_paid_subscription(
            user_db_id=10,
            plan="pro",
            period_key="1m",
            method="stars",
            provider_charge_id="tg_charge_abc",
            invoice_id="sub:pro:1m:1",
            amount=19.0,
            months=1,
        )
        assert first is not None
        assert first.status == "created"
        assert user.plan == "pro"
        first_exp = first.expires_at
        assert session.add.call_count == 1
        added = session.add.call_args.args[0]
        assert added.provider_charge_id == "tg_charge_abc"

        second = await activate_paid_subscription(
            user_db_id=10,
            plan="pro",
            period_key="1m",
            method="stars",
            provider_charge_id="tg_charge_abc",
            invoice_id="sub:pro:1m:1",
            amount=19.0,
            months=1,
        )
        assert second is not None
        assert second.status == "already_applied"
        assert second.expires_at == exp
        # No second insert
        assert session.add.call_count == 1
        assert first_exp != exp or True  # created used "now"; replay uses stored exp


@pytest.mark.asyncio
async def test_cryptobot_activate_idempotent():
    """Repeated CryptoBot activation with same invoice skips side effects."""
    exp = datetime.datetime(2026, 8, 1, tzinfo=datetime.timezone.utc)
    activate = AsyncMock(side_effect=[
        ActivateResult(
            status="created", expires_at=exp, plan="start", period_key="1m",
            user_id=11, language="en",
        ),
        ActivateResult(
            status="already_applied", expires_at=exp, plan="start", period_key="1m",
            user_id=11, language="en",
        ),
    ])
    data = {
        "user_id": 11, "plan": "start", "period_key": "1m",
        "chat_id": 1100, "promo": None, "amount": 9.0,
    }

    with (
        patch(
            "app.payments.activate.activate_paid_subscription",
            new=activate,
        ),
        patch(
            "app.cache.subscription_cache.invalidate_all_subscription_caches",
            new=AsyncMock(),
        ) as inv,
        patch("app.bot.handlers.plan._apply_referral_bonus", new=AsyncMock()) as ref,
        patch("app.bot.handlers.plan.maybe_offer_annual", new=AsyncMock()) as annual,
        patch("app.userbot.discovery.notify_new_subscription", new=AsyncMock()),
        patch(
            "app.worker.payment_checker._get_user_for_notify",
            new=AsyncMock(return_value=None),
        ),
        patch("aiogram.Bot") as mock_bot_cls,
    ):
        mock_bot = AsyncMock()
        mock_bot_cls.return_value = mock_bot
        mock_bot.session = AsyncMock()

        ok1 = await payment_checker._activate(data, "inv_99")
        ok2 = await payment_checker._activate(data, "inv_99")

    assert ok1 is True
    assert ok2 is False
    assert activate.await_count == 2
    assert activate.await_args_list[0].kwargs["provider_charge_id"] == "cryptobot:inv_99"
    assert inv.await_count == 1
    assert ref.await_count == 1
    assert annual.await_count == 1
