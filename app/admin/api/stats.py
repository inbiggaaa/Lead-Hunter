"""Dashboard stats API."""

from fastapi import APIRouter
from sqlalchemy import select, func, desc

from app.db.models import (
    User, Subscription, SentLog, LLMDecision,
    UserSubscription, SubscriptionCity, Country, City, Segment,
)
from app.db.session import async_session_factory

router = APIRouter(prefix="/api/stats", tags=["stats"])

# DeepSeek pricing per 1M tokens (USD)
DEEPSEEK_INPUT_PRICE = 0.27   # $0.27 per 1M input
DEEPSEEK_OUTPUT_PRICE = 1.10  # $1.10 per 1M output
AVG_COST_PER_1M = 0.40        # blended estimate for display


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

    # B6: латентность доставки за сегодня (UTC) — счётчики пишет sender
    import time as _time

    from app.cache import get_redis
    redis = await get_redis()
    date = _time.strftime("%Y-%m-%d", _time.gmtime())
    latency = {
        bucket: int(await redis.get(f"stats:latency:{date}:{bucket}") or 0)
        for bucket in ("lt5m", "lt30m", "lt2h", "ge2h")
    }

    return {
        "total_users": total,
        "new_today": new_today,
        "active_subscriptions": active_subs,
        "plans": plans,
        "sent_today": sent_today,
        "latency_today": latency,
        "new_users_30d": [
            {"date": str(row.date), "count": row.count} for row in new_by_day
        ],
    }


@router.get("/llm")
async def llm_stats():
    """LLM token usage and verdict statistics."""
    async with async_session_factory() as session:
        # Total tokens all-time
        total_row = (await session.execute(
            select(
                func.coalesce(func.sum(LLMDecision.prompt_tokens), 0),
                func.coalesce(func.sum(LLMDecision.completion_tokens), 0),
                func.coalesce(func.sum(LLMDecision.total_tokens), 0),
                func.count(LLMDecision.id),
            )
        )).one()
        prompt_all, completion_all, tokens_all, total_decisions = total_row

        # Today's tokens
        today_row = (await session.execute(
            select(
                func.coalesce(func.sum(LLMDecision.prompt_tokens), 0),
                func.coalesce(func.sum(LLMDecision.completion_tokens), 0),
                func.coalesce(func.sum(LLMDecision.total_tokens), 0),
                func.count(LLMDecision.id),
            ).where(func.date(LLMDecision.created_at) == func.current_date())
        )).one()
        prompt_today, completion_today, tokens_today, decisions_today = today_row

        # This month's tokens
        month_row = (await session.execute(
            select(
                func.coalesce(func.sum(LLMDecision.prompt_tokens), 0),
                func.coalesce(func.sum(LLMDecision.completion_tokens), 0),
                func.coalesce(func.sum(LLMDecision.total_tokens), 0),
            ).where(
                func.date_trunc("month", LLMDecision.created_at)
                == func.date_trunc("month", func.now())
            )
        )).one()
        prompt_month, completion_month, tokens_month = month_row

        # Verdict breakdown (all-time)
        verdict_rows = (await session.execute(
            select(
                LLMDecision.llm_verdict,
                func.count(LLMDecision.id),
            ).group_by(LLMDecision.llm_verdict)
        )).all()
        verdicts = {row.llm_verdict: row.count for row in verdict_rows}

        # Daily tokens last 30 days (for chart)
        daily_rows = (await session.execute(
            select(
                func.date(LLMDecision.created_at).label("date"),
                func.coalesce(func.sum(LLMDecision.total_tokens), 0).label("tokens"),
                func.count(LLMDecision.id).label("decisions"),
            )
            .where(
                LLMDecision.created_at >= func.now() - func.make_interval(0, 0, 0, 30)
            )
            .group_by("date")
            .order_by("date")
        )).all()
        daily_tokens = [
            {"date": str(row.date), "tokens": row.tokens, "decisions": row.decisions}
            for row in daily_rows
        ]

        # Mode breakdown
        mode_rows = (await session.execute(
            select(
                LLMDecision.llm_mode,
                func.count(LLMDecision.id),
            ).group_by(LLMDecision.llm_mode)
        )).all()
        modes = {row.llm_mode: row.count for row in mode_rows}

        # Cost estimates
        def _cost(prompt: int, completion: int) -> float:
            return (prompt / 1_000_000) * DEEPSEEK_INPUT_PRICE + (completion / 1_000_000) * DEEPSEEK_OUTPUT_PRICE

        cost_all = _cost(prompt_all or 0, completion_all or 0)
        cost_today = _cost(prompt_today or 0, completion_today or 0)
        cost_month = _cost(prompt_month or 0, completion_month or 0)

    return {
        "total_decisions": total_decisions,
        "decisions_today": decisions_today,
        "tokens": {
            "all_time": tokens_all or 0,
            "today": tokens_today or 0,
            "this_month": tokens_month or 0,
            "prompt_all": prompt_all or 0,
            "prompt_today": prompt_today or 0,
            "completion_all": completion_all or 0,
            "completion_today": completion_today or 0,
        },
        "cost": {
            "all_time": round(cost_all, 4),
            "today": round(cost_today, 4),
            "this_month": round(cost_month, 4),
            "input_price_per_1m": DEEPSEEK_INPUT_PRICE,
            "output_price_per_1m": DEEPSEEK_OUTPUT_PRICE,
        },
        "verdicts": verdicts,
        "modes": modes,
        "daily_tokens": daily_tokens,
    }


@router.get("/popular")
async def popular_stats():
    """Most popular countries, cities, and business segments by subscriptions."""
    async with async_session_factory() as session:
        # Top countries by subscription count
        top_countries_rows = (await session.execute(
            select(
                Country.name_ru,
                Country.slug,
                func.count(func.distinct(UserSubscription.user_id)).label("users"),
                func.count(UserSubscription.id).label("subscriptions"),
            )
            .join(UserSubscription, UserSubscription.country_id == Country.id)
            .where(Country.is_active == True)
            .group_by(Country.id, Country.name_ru, Country.slug)
            .order_by(desc("subscriptions"))
            .limit(10)
        )).all()
        top_countries = [
            {"name": row.name_ru, "slug": row.slug, "users": row.users, "subscriptions": row.subscriptions}
            for row in top_countries_rows
        ]

        # Top cities by subscription_cities count
        top_cities_rows = (await session.execute(
            select(
                City.name_ru,
                City.slug,
                Country.name_ru.label("country_name"),
                func.count(func.distinct(SubscriptionCity.subscription_id)).label("subscriptions"),
            )
            .join(SubscriptionCity, SubscriptionCity.city_id == City.id)
            .join(Country, Country.id == City.country_id)
            .where(City.is_active == True)
            .group_by(City.id, City.name_ru, City.slug, Country.name_ru)
            .order_by(desc("subscriptions"))
            .limit(10)
        )).all()
        top_cities = [
            {
                "name": row.name_ru,
                "slug": row.slug,
                "country": row.country_name,
                "subscriptions": row.subscriptions,
            }
            for row in top_cities_rows
        ]

        # Top segments (business categories) by subscription count
        top_segments_rows = (await session.execute(
            select(
                Segment.title_ru,
                Segment.slug,
                Segment.emoji,
                func.count(func.distinct(UserSubscription.user_id)).label("users"),
                func.count(UserSubscription.id).label("subscriptions"),
            )
            .join(UserSubscription, UserSubscription.segment_id == Segment.id)
            .where(Segment.is_active == True)
            .group_by(Segment.id, Segment.title_ru, Segment.slug, Segment.emoji)
            .order_by(desc("subscriptions"))
            .limit(10)
        )).all()
        top_segments = [
            {
                "name": row.title_ru or row.slug,
                "slug": row.slug,
                "emoji": row.emoji or "",
                "users": row.users,
                "subscriptions": row.subscriptions,
            }
            for row in top_segments_rows
        ]

        # Also: top segments by actual sent notifications (leads delivered)
        top_by_leads_rows = (await session.execute(
            select(
                Segment.title_ru,
                Segment.slug,
                Segment.emoji,
                func.count(SentLog.id).label("leads"),
            )
            .select_from(SentLog)
            .join(UserSubscription, UserSubscription.user_id == SentLog.user_id)
            .join(Segment, Segment.id == UserSubscription.segment_id)
            .where(Segment.is_active == True)
            .group_by(Segment.id, Segment.title_ru, Segment.slug, Segment.emoji)
            .order_by(desc("leads"))
            .limit(10)
        )).all()
        top_by_leads = [
            {
                "name": row.title_ru or row.slug,
                "slug": row.slug,
                "emoji": row.emoji or "",
                "leads": row.leads,
            }
            for row in top_by_leads_rows
        ]

    return {
        "top_countries": top_countries,
        "top_cities": top_cities,
        "top_segments": top_segments,
        "top_segments_by_leads": top_by_leads,
    }


@router.get("/segment-feedback")
async def segment_feedback_stats(days: int = 30):
    """A3: 👍/👎 по сегментам за N дней — источник решений о карантине.

    Сегменты оценённого уведомления берутся из последнего llm_decision по тому
    же сообщению (llm_segments, иначе rule_segments); legacy-slug'и, которых
    нет в текущем каталоге, отсекаются JOIN'ом на segments.
    """
    from sqlalchemy import text

    sql = text(
        """
        SELECT x.slug,
               count(*) FILTER (WHERE x.verdict = 'relevant')      AS relevant,
               count(*) FILTER (WHERE x.verdict = 'not_relevant')  AS not_relevant
        FROM (
            SELECT f.verdict,
                   unnest(coalesce(nullif(d.llm_segments, '{}'), d.rule_segments)) AS slug
            FROM feedback f
            JOIN LATERAL (
                SELECT llm_segments, rule_segments
                FROM llm_decisions d
                WHERE d.chat_username = f.chat_username
                  AND d.message_id = f.message_id
                ORDER BY d.id DESC LIMIT 1
            ) d ON true
            WHERE f.created_at > now() - make_interval(days => :days)
        ) x
        JOIN segments s ON s.slug = x.slug
        GROUP BY x.slug
        """
    )
    async with async_session_factory() as session:
        rows = (await session.execute(sql, {"days": days})).all()
    return {
        r.slug: {"relevant": r.relevant, "not_relevant": r.not_relevant}
        for r in rows
    }
