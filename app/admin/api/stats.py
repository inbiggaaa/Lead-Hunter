"""Dashboard stats API."""

from fastapi import APIRouter
from sqlalchemy import select, func

from app.db.models import User, Subscription, SentLog
from app.db.session import async_session_factory

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("/dashboard")
async def dashboard_stats():
    async with async_session_factory() as session:
        # Total users
        total = (await session.execute(select(func.count(User.id)))).scalar() or 0

        # New today (UTC)
        new_today = (
            await session.execute(
                select(func.count(User.id)).where(
                    func.date(User.created_at) == func.current_date()
                )
            )
        ).scalar() or 0

        # Active paid subscriptions
        active_subs = (
            await session.execute(
                select(func.count(Subscription.id)).where(
                    Subscription.payment_status == "paid",
                    Subscription.expires_at > func.now(),
                )
            )
        ).scalar() or 0

        # Plans breakdown
        plan_result = await session.execute(
            select(User.plan, func.count(User.id)).group_by(User.plan)
        )
        plans = {plan: count for plan, count in plan_result.all()}

        # Sent today
        sent_today = (
            await session.execute(
                select(func.count(SentLog.id)).where(
                    func.date(SentLog.sent_at) == func.current_date()
                )
            )
        ).scalar() or 0

        # New users last 30 days (for chart)
        new_by_day = (
            await session.execute(
                select(
                    func.date(User.created_at).label("date"),
                    func.count(User.id).label("count"),
                )
                .where(
                    User.created_at >= func.now() - func.make_interval(0, 0, 0, 30)
                )
                .group_by("date")
                .order_by("date")
            )
        ).all()

    return {
        "total_users": total,
        "new_today": new_today,
        "active_subscriptions": active_subs,
        "plans": plans,
        "sent_today": sent_today,
        "new_users_30d": [
            {"date": str(row.date), "count": row.count} for row in new_by_day
        ],
    }
