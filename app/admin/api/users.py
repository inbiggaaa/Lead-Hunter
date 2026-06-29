"""Users API endpoints with filtering."""

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.db.session import async_session_factory

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("")
async def list_users(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    plan: str | None = None,
    source: str | None = None,
    search: str | None = None,
    sort: str = "created_at",
    order: str = "desc",
):
    async with async_session_factory() as session:
        stmt = select(User)

        if plan and plan != "all":
            stmt = stmt.where(User.plan == plan)
        if source and source != "all":
            stmt = stmt.where(User.source == source)
        if search:
            stmt = stmt.where(
                (User.username.ilike(f"%{search}%"))
                | (User.telegram_id.cast(str).ilike(f"%{search}%"))
            )

        # Count
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await session.execute(count_stmt)).scalar() or 0

        # Sort
        col = getattr(User, sort, User.created_at)
        if order == "asc":
            stmt = stmt.order_by(col.asc())
        else:
            stmt = stmt.order_by(col.desc())

        stmt = stmt.offset((page - 1) * per_page).limit(per_page)
        result = await session.execute(stmt)
        users = result.scalars().all()

    items = []
    for u in users:
        items.append({
            "id": u.id,
            "telegram_id": u.telegram_id,
            "username": u.username,
            "language": u.language,
            "plan": u.plan,
            "plan_activated_at": u.plan_activated_at.isoformat() if u.plan_activated_at else None,
            "plan_expires_at": u.plan_expires_at.isoformat() if u.plan_expires_at else None,
            "is_banned": u.is_banned,
            "is_suspended": u.is_suspended,
            "suspended_until": u.suspended_until.isoformat() if u.suspended_until else None,
            "is_blocked_bot": u.is_blocked_bot,
            "blocked_bot_at": u.blocked_bot_at.isoformat() if u.blocked_bot_at else None,
            "source": u.source,
            "admin_note": u.admin_note,
            "created_at": u.created_at.isoformat() if u.created_at else None,
        })

    return {"items": items, "total": total, "page": page, "per_page": per_page}


@router.get("/{user_id}")
async def get_user(user_id: int):
    async with async_session_factory() as session:
        u = await session.get(User, user_id)
        if not u:
            raise HTTPException(status_code=404, detail="User not found")

        return {
            "id": u.id,
            "telegram_id": u.telegram_id,
            "username": u.username,
            "language": u.language,
            "plan": u.plan,
            "plan_activated_at": u.plan_activated_at.isoformat() if u.plan_activated_at else None,
            "plan_expires_at": u.plan_expires_at.isoformat() if u.plan_expires_at else None,
            "is_banned": u.is_banned,
            "is_suspended": u.is_suspended,
            "suspended_until": u.suspended_until.isoformat() if u.suspended_until else None,
            "is_blocked_bot": u.is_blocked_bot,
            "blocked_bot_at": u.blocked_bot_at.isoformat() if u.blocked_bot_at else None,
            "source": u.source,
            "admin_note": u.admin_note,
            "created_at": u.created_at.isoformat() if u.created_at else None,
        }


@router.put("/{user_id}")
async def update_user(user_id: int, data: dict):
    async with async_session_factory() as session:
        u = await session.get(User, user_id)
        if not u:
            raise HTTPException(status_code=404, detail="User not found")

        allowed_fields = {"plan", "is_banned", "is_suspended", "admin_note"}
        for k, v in data.items():
            if k in allowed_fields:
                setattr(u, k, v)

        await session.commit()
        return {"ok": True}
