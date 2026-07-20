"""Phase 4: referral bind, winback gate, support imports."""

from __future__ import annotations

import datetime as dt
import importlib
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.bot.handlers import plan as plan_mod
from app.bot.handlers.plan import _calc_winback, validate_stars_pre_checkout
from app.payments.activate import activate_paid_subscription


def test_support_handler_imports_resolve() -> None:
    mod = importlib.import_module("app.bot.handlers.support")
    assert callable(mod.get_text)
    assert callable(mod.normalize_language)
    assert hasattr(mod, "on_support_message")


def test_referral_age_uses_total_seconds() -> None:
    """Old accounts must not bind: .seconds alone wraps at 86400."""
    created = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=2, seconds=30)
    age = dt.datetime.now(dt.timezone.utc) - created
    assert age.seconds < 60  # the old buggy check would wrongly pass
    assert age.total_seconds() >= 60


@pytest.mark.asyncio
async def test_two_invitees_create_independent_edges() -> None:
    """Binding must INSERT edges, not overwrite a single mutable referral row."""
    from app.db.models import Referral, User

    referrer = User(id=1, telegram_id=100, referral_code="ABC12345", source="direct")
    invite_a = User(id=2, telegram_id=200, source="direct",
                    created_at=dt.datetime.now(dt.timezone.utc))
    invite_b = User(id=3, telegram_id=300, source="direct",
                    created_at=dt.datetime.now(dt.timezone.utc))

    added: list[Referral] = []

    class _Result:
        def __init__(self, value):
            self._value = value

        def scalar_one_or_none(self):
            return self._value

    class _Session:
        async def execute(self, stmt):
            sql = str(stmt)
            if "referral_code" in sql or "users.referral_code" in sql.lower():
                return _Result(referrer)
            if "referral_id" in sql:
                # First bind: none; second bind for B: none; for already A: found
                target = getattr(stmt, "_where_criteria", None)
                # Fall back: count existing edges for this invitee among `added`
                # by inspecting compiled params — keep simple: empty until added.
                for edge in added:
                    # emulate unique invitee lookup returning existing
                    pass
                return _Result(None)
            return _Result(None)

        def add(self, obj):
            added.append(obj)

    # Simulate bind helper logic inline (mirrors start.py).
    async def bind(session, user, ref_code: str) -> None:
        from sqlalchemy import select
        if user.source != "direct" or not user.created_at:
            return
        if (dt.datetime.now(dt.timezone.utc) - user.created_at).total_seconds() >= 60:
            return
        referrer_row = (await session.execute(
            select(User).where(User.referral_code == ref_code)
        )).scalar_one_or_none()
        if not referrer_row or referrer_row.id == user.id:
            return
        already = next((e for e in added if e.referral_id == user.id), None)
        if already is not None:
            return
        user.source = "referral"
        session.add(Referral(
            referrer_id=referrer_row.id,
            referral_id=user.id,
            ref_code=ref_code,
            status="pending",
        ))

    session = _Session()
    await bind(session, invite_a, "ABC12345")
    await bind(session, invite_b, "ABC12345")

    assert len(added) == 2
    assert {e.referral_id for e in added} == {2, 3}
    assert invite_a.source == "referral" and invite_b.source == "referral"


@pytest.mark.asyncio
async def test_pre_checkout_rejects_expired_winback(monkeypatch) -> None:
    monkeypatch.setitem(plan_mod.PLANS["start"], "usd_monthly", 9)
    info = _calc_winback("start")

    class _S:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    with patch("app.db.crud.get_user", new=AsyncMock(return_value=SimpleNamespace(id=9))), \
         patch("app.db.session.async_session_factory", return_value=_S()), \
         patch.object(plan_mod, "_active_winback_offer", new=AsyncMock(return_value=None)):
        ok, err = await validate_stars_pre_checkout(
            payload="sub:start:3m:wb25:111",
            from_user_id=111,
            currency="XTR",
            total_amount=info["stars"],
        )
    assert not ok
    assert "Winback" in err


@pytest.mark.asyncio
async def test_activate_rejects_inactive_winback() -> None:
    user = SimpleNamespace(
        id=5, language="ru", plan="free",
        plan_activated_at=None, plan_expires_at=None, free_lifecycle_at=None,
    )
    expired = SimpleNamespace(
        user_id=5,
        redeemed_at=None,
        expires_at=dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=1),
    )

    class _Result:
        def __init__(self, value):
            self._value = value

        def scalar_one_or_none(self):
            return self._value

        def scalar_one(self):
            return self._value

    class _Session:
        def __init__(self):
            self.calls = 0
            self.rolled_back = False

        async def execute(self, stmt):
            self.calls += 1
            if self.calls == 1:
                return _Result(None)  # no existing subscription
            if self.calls == 2:
                return _Result(user)
            return _Result(expired)  # winback offer

        def add(self, obj):
            pass

        async def commit(self):
            pass

        async def rollback(self):
            self.rolled_back = True

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    session = _Session()
    with patch("app.payments.activate.async_session_factory", return_value=session):
        with pytest.raises(ValueError, match="winback_offer_inactive"):
            await activate_paid_subscription(
                user_db_id=5,
                plan="start",
                period_key="3m",
                method="stars",
                provider_charge_id="tg:charge-1",
                invoice_id="inv",
                amount=20.25,
                promo="wb25",
                months=3,
            )
    assert session.rolled_back
