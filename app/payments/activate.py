"""Idempotent paid-subscription activation (Stars + CryptoBot)."""

from __future__ import annotations

import datetime
import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db.models import Subscription, User, WinbackOffer
from app.db.session import async_session_factory

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ActivateResult:
    status: str  # "created" | "already_applied"
    expires_at: datetime.datetime
    plan: str
    period_key: str
    user_id: int
    language: str


async def activate_paid_subscription(
    *,
    user_db_id: int,
    plan: str,
    period_key: str,
    method: str,
    provider_charge_id: str,
    invoice_id: str | None,
    amount: float,
    promo: str | None = None,
    months: int,
) -> ActivateResult | None:
    """Activate or no-op if provider_charge_id was already applied.

    Returns None if the user row is missing. Never extends expiry twice for
    the same charge id (UNIQUE + early SELECT + IntegrityError race path).
    """
    if not provider_charge_id:
        raise ValueError("provider_charge_id is required")

    async with async_session_factory() as session:
        existing = (await session.execute(
            select(Subscription).where(
                Subscription.provider_charge_id == provider_charge_id
            )
        )).scalar_one_or_none()
        if existing:
            user = (await session.execute(
                select(User).where(User.id == existing.user_id)
            )).scalar_one()
            return ActivateResult(
                status="already_applied",
                expires_at=existing.expires_at or user.plan_expires_at,
                plan=existing.plan,
                period_key=existing.period,
                user_id=user.id,
                language=user.language or "ru",
            )

        user = (await session.execute(
            select(User).where(User.id == user_db_id)
        )).scalar_one_or_none()
        if not user:
            return None

        now = datetime.datetime.now(datetime.timezone.utc)
        expires = now + datetime.timedelta(days=30 * months)
        session.add(Subscription(
            user_id=user.id,
            plan=plan,
            period=period_key,
            expires_at=expires,
            payment_method=method,
            payment_status="paid",
            invoice_id=invoice_id,
            provider_charge_id=provider_charge_id,
            amount=amount,
        ))
        user.plan = plan
        user.plan_activated_at = now
        user.plan_expires_at = expires
        user.free_lifecycle_at = None
        if promo == "wb25":
            offer = (await session.execute(
                select(WinbackOffer).where(WinbackOffer.user_id == user.id)
            )).scalar_one_or_none()
            if offer and offer.redeemed_at is None:
                offer.redeemed_at = now

        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            existing = (await session.execute(
                select(Subscription).where(
                    Subscription.provider_charge_id == provider_charge_id
                )
            )).scalar_one_or_none()
            if not existing:
                raise
            user = (await session.execute(
                select(User).where(User.id == existing.user_id)
            )).scalar_one()
            logger.info(
                "Payment race: charge %s already applied for user %d",
                provider_charge_id, user.id,
            )
            return ActivateResult(
                status="already_applied",
                expires_at=existing.expires_at or user.plan_expires_at,
                plan=existing.plan,
                period_key=existing.period,
                user_id=user.id,
                language=user.language or "ru",
            )

        return ActivateResult(
            status="created",
            expires_at=expires,
            plan=plan,
            period_key=period_key,
            user_id=user.id,
            language=user.language or "ru",
        )
