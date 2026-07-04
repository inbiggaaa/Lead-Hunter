"""Admin REST API — root router assembling all sub-routers."""

from fastapi import APIRouter, Depends, HTTPException, Request

from app.admin.api.auth import router as auth_router
from app.admin.api.users import router as users_router
from app.admin.api.stats import router as stats_router
from app.admin.api.broadcast import router as broadcast_router
from app.admin.api.chat import router as chat_router
from app.admin.api.crud import create_crud_router
from app.admin.api.stop_words import router as stop_words_router
from app.admin.api.unmatched import router as unmatched_router
from app.admin.api.segments import router as segments_detail_router
from app.db.models import Country, City, Segment, SegmentKeyword

# ── Auth dependency (duplicated here to avoid circular import) ──

async def require_auth(request: Request):
    if not request.session.get("authenticated"):
        raise HTTPException(status_code=401, detail="Not authenticated")


api_router = APIRouter()

# Auth (public — no dependency)
api_router.include_router(auth_router)

# Protected routes
_protected = [Depends(require_auth)]
api_router.include_router(users_router, dependencies=_protected)
api_router.include_router(stats_router, dependencies=_protected)
api_router.include_router(broadcast_router, dependencies=_protected)
api_router.include_router(chat_router, dependencies=_protected)
api_router.include_router(create_crud_router(Country, "countries", "countries"), dependencies=_protected)
api_router.include_router(create_crud_router(City, "cities", "cities"), dependencies=_protected)
api_router.include_router(create_crud_router(Segment, "segments", "segments"), dependencies=_protected)
api_router.include_router(
    create_crud_router(SegmentKeyword, "segment_keywords", "segment-keywords"),
    dependencies=_protected,
)
api_router.include_router(stop_words_router, dependencies=_protected)
api_router.include_router(unmatched_router, dependencies=_protected)
api_router.include_router(segments_detail_router, dependencies=_protected)


# ── Channels (custom — needs M:N joins) ──

from sqlalchemy import select, func
from app.db.models import (
    CatalogChannel,
    ChannelSegment,
    ChannelCity,
)
from app.db.session import async_session_factory

channels_router = APIRouter(prefix="/api/channels", tags=["channels"])


@channels_router.get("")
async def list_channels(
    page: int = 1,
    per_page: int = 20,
    search: str | None = None,
    is_verified: bool | None = None,
    has_city: bool | None = None,
    country_id: int | None = None,
    city_id: int | None = None,
    is_ignored: bool | None = None,
):
    async with async_session_factory() as session:
        stmt = select(CatalogChannel)

        if search:
            stmt = stmt.where(
                (CatalogChannel.chat_username.ilike(f"%{search}%"))
                | (CatalogChannel.title.ilike(f"%{search}%"))
            )
        if is_verified is not None:
            stmt = stmt.where(CatalogChannel.is_verified == is_verified)
        if is_ignored is not None:
            stmt = stmt.where(CatalogChannel.is_ignored == is_ignored)
        if country_id is not None:
            stmt = stmt.where(CatalogChannel.auto_matched_country_id == country_id)
        if city_id is not None:
            stmt = stmt.where(
                (CatalogChannel.auto_matched_city_id == city_id)
                | CatalogChannel.id.in_(
                    select(ChannelCity.channel_id).where(
                        ChannelCity.city_id == city_id
                    )
                )
            )
        if has_city is not None:
            if has_city:
                stmt = stmt.where(
                    (CatalogChannel.auto_matched_city_id.isnot(None))
                    | CatalogChannel.id.in_(
                        select(ChannelCity.channel_id)
                    )
                )
            else:
                stmt = stmt.where(
                    CatalogChannel.auto_matched_city_id.is_(None)
                ).where(
                    ~CatalogChannel.id.in_(
                        select(ChannelCity.channel_id)
                    )
                )

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await session.execute(count_stmt)).scalar() or 0

        stmt = stmt.offset((page - 1) * per_page).limit(per_page)
        result = await session.execute(stmt)
        channels = result.scalars().all()

    items = []
    for ch in channels:
        items.append(
            {
                "id": ch.id,
                "chat_username": ch.chat_username,
                "title": ch.title,
                "participants": ch.participants,
                "is_verified": ch.is_verified,
                "is_ignored": ch.is_ignored,
                "auto_matched_country_id": ch.auto_matched_country_id,
                "auto_matched_city_id": ch.auto_matched_city_id,
                "discovered_at": ch.discovered_at.isoformat()
                if ch.discovered_at
                else None,
            }
        )

    return {"items": items, "total": total, "page": page, "per_page": per_page}


@channels_router.get("/{channel_id}")
async def get_channel(channel_id: int):
    async with async_session_factory() as session:
        ch = await session.get(CatalogChannel, channel_id)
        if not ch:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Not found")

        # Get segments
        seg_result = await session.execute(
            select(ChannelSegment).where(ChannelSegment.channel_id == channel_id)
        )
        segments = [s.segment_id for s in seg_result.scalars().all()]

        # Get cities
        city_result = await session.execute(
            select(ChannelCity).where(ChannelCity.channel_id == channel_id)
        )
        cities = [c.city_id for c in city_result.scalars().all()]

        return {
            "id": ch.id,
            "chat_username": ch.chat_username,
            "title": ch.title,
            "participants": ch.participants,
            "is_verified": ch.is_verified,
            "auto_matched_country_id": ch.auto_matched_country_id,
            "auto_matched_city_id": ch.auto_matched_city_id,
            "discovered_at": ch.discovered_at.isoformat()
            if ch.discovered_at
            else None,
            "segments": segments,
            "cities": cities,
        }


@channels_router.put("/{channel_id}")
async def update_channel(channel_id: int, data: dict):
    from fastapi import HTTPException

    async with async_session_factory() as session:
        ch = await session.get(CatalogChannel, channel_id)
        if not ch:
            raise HTTPException(status_code=404, detail="Not found")

        updatable = {"title", "participants", "is_verified",
                      "auto_matched_country_id", "auto_matched_city_id",
                      "is_ignored"}
        for k, v in data.items():
            if k in updatable:
                setattr(ch, k, v)

        # Auto-set country from city if missing — city without country is invalid
        if "country_id" in data and not ch.auto_matched_country_id:
            ch.auto_matched_country_id = data["country_id"]

        # Update segments
        if "segments" in data:
            await session.execute(
                __import__("sqlalchemy").sql.delete(ChannelSegment).where(
                    ChannelSegment.channel_id == channel_id
                )
            )
            for sid in data["segments"]:
                session.add(
                    ChannelSegment(channel_id=channel_id, segment_id=sid)
                )

        # Update cities
        if "cities" in data:
            await session.execute(
                __import__("sqlalchemy").sql.delete(ChannelCity).where(
                    ChannelCity.channel_id == channel_id
                )
            )
            for cid in data["cities"]:
                session.add(ChannelCity(channel_id=channel_id, city_id=cid))

        await session.commit()
        return {"ok": True}


api_router.include_router(channels_router, dependencies=_protected)
