"""Generic CRUD router for simple models.

Usage:
    from app.admin.api.crud import create_crud_router
    router = create_crud_router(User, "users", "users")
    main_router.include_router(router)
"""

from typing import Any, Type

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import Table, inspect, select, func, delete as sa_delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import async_session_factory
from app.db.models import Base

# Whitelist of allowed models – prevents arbitrary table access
ALLOWED_MODELS: dict[str, Type[Base]] = {
    "users": None,          # custom handler
    "subscriptions": None,  # custom handler
    "keywords": None,       # via users
    "watched_chats": None,  # via users
    "sent_log": None,       # read-only
    "countries": None,      # set below
    "cities": None,         # set below
    "segments": None,       # set below
    "segment_keywords": None,
    "catalog_channels": None,
    "channel_segments": None,
    "channel_cities": None,
    "user_subscriptions": None,
    "subscription_cities": None,
    "discovered_chats": None,
    "referrals": None,
    "support_messages": None,
    "user_ignores": None,
    "reminders": None,
    "periodic_prefs": None,
}

# Import models and register
from app.db.models import Country, City, Segment, SegmentKeyword

ALLOWED_MODELS["countries"] = Country
ALLOWED_MODELS["cities"] = City
ALLOWED_MODELS["segments"] = Segment
ALLOWED_MODELS["segment_keywords"] = SegmentKeyword


async def _get_session() -> AsyncSession:
    return async_session_factory()


def _row_to_dict(row: Any, model: Type[Base]) -> dict[str, Any]:
    """Convert a SQLAlchemy row to a plain dict, handling datetime."""
    result = {}
    for col in inspect(model).columns:
        val = getattr(row, col.key, None)
        if hasattr(val, "isoformat"):
            val = val.isoformat()
        result[col.key] = val
    return result


def create_crud_router(model: Type[Base], model_name: str, prefix: str) -> APIRouter:
    """Create CRUD routes for a given model."""
    router = APIRouter(prefix=f"/api/{prefix}", tags=[model_name])
    table: Table = model.__table__
    pks = [c.key for c in table.primary_key.columns]

    if not pks:
        raise ValueError(f"Model {model_name} has no primary key")

    pk_col = table.c[pks[0]]

    # ── List ──

    @router.get("")
    async def list_items(
        page: int = Query(1, ge=1),
        per_page: int = Query(20, ge=1, le=500),
    ):
        async with async_session_factory() as session:
            count_q = select(func.count()).select_from(table)
            total = (await session.execute(count_q)).scalar() or 0

            q = select(table).offset((page - 1) * per_page).limit(per_page)
            rows = (await session.execute(q)).all()

        cols = [c.key for c in table.columns]
        items = []
        for row in rows:
            item = {}
            for i, col in enumerate(cols):
                val = row[i]
                if hasattr(val, "isoformat"):
                    val = val.isoformat()
                item[col] = val
            items.append(item)

        return {"items": items, "total": total, "page": page, "per_page": per_page}

    # ── Get one ──

    @router.get("/{item_id}")
    async def get_item(item_id: int):
        async with async_session_factory() as session:
            q = select(table).where(pk_col == item_id)
            row = (await session.execute(q)).first()
            if not row:
                raise HTTPException(status_code=404, detail="Not found")

            cols = [c.key for c in table.columns]
            item = {}
            for i, col in enumerate(cols):
                val = row[i]
                if hasattr(val, "isoformat"):
                    val = val.isoformat()
                item[col] = val
            return item

    # ── Create ──

    @router.post("")
    async def create_item(data: dict):
        async with async_session_factory() as session:
            # Remove pk so DB auto-generates it
            clean = {k: v for k, v in data.items() if k not in pks}
            try:
                stmt = table.insert().values(**clean)
                result = await session.execute(stmt)
                await session.commit()
            except IntegrityError:
                await session.rollback()
                raise HTTPException(
                    status_code=409,
                    detail=f"{model_name} already exists — unique constraint violated",
                )

            new_id = result.inserted_primary_key[0]
            q = select(table).where(pk_col == new_id)
            row = (await session.execute(q)).first()
            cols = [c.key for c in table.columns]
            item = {}
            for i, col in enumerate(cols):
                val = row[i]
                if hasattr(val, "isoformat"):
                    val = val.isoformat()
                item[col] = val
            return item

    # ── Update ──

    @router.put("/{item_id}")
    async def update_item(item_id: int, data: dict):
        async with async_session_factory() as session:
            clean = {k: v for k, v in data.items() if k not in pks}
            if not clean:
                raise HTTPException(status_code=400, detail="No data to update")
            stmt = table.update().where(pk_col == item_id).values(**clean)
            result = await session.execute(stmt)
            if result.rowcount == 0:
                raise HTTPException(status_code=404, detail="Not found")
            await session.commit()

            q = select(table).where(pk_col == item_id)
            row = (await session.execute(q)).first()
            cols = [c.key for c in table.columns]
            item = {}
            for i, col in enumerate(cols):
                val = row[i]
                if hasattr(val, "isoformat"):
                    val = val.isoformat()
                item[col] = val
            return item

    # ── Delete ──

    @router.delete("/{item_id}")
    async def delete_item(item_id: int):
        async with async_session_factory() as session:
            stmt = sa_delete(table).where(pk_col == item_id)
            result = await session.execute(stmt)
            if result.rowcount == 0:
                raise HTTPException(status_code=404, detail="Not found")
            await session.commit()
            return {"ok": True}

    return router
