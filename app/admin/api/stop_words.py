"""Stop-words API — dedicated CRUD for segment_keywords with keyword_type='stop'.

Includes segment title via JOIN and handles universal stops (segment_id=NULL).
"""

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select, func, delete as sa_delete
from sqlalchemy.orm import joinedload

from app.db.session import async_session_factory
from app.db.models import SegmentKeyword, Segment

router = APIRouter(prefix="/api/stop-words", tags=["stop-words"])


@router.get("")
async def list_stop_words(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    search: str | None = None,
):
    """List stop-words with segment title."""
    async with async_session_factory() as session:
        # Base query: stop-words with optional join to segments
        stmt = select(SegmentKeyword).where(
            SegmentKeyword.keyword_type == "stop"
        )

        if search:
            stmt = stmt.where(SegmentKeyword.text.ilike(f"%{search}%"))

        # Count
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await session.execute(count_stmt)).scalar() or 0

        # Paginate
        stmt = stmt.order_by(SegmentKeyword.id).offset(
            (page - 1) * per_page
        ).limit(per_page)
        result = await session.execute(stmt)
        keywords = result.scalars().all()

    # Resolve segment titles in a second query (avoids N+1)
    segment_ids = {kw.segment_id for kw in keywords if kw.segment_id is not None}
    segment_titles: dict[int, str] = {}
    if segment_ids:
        async with async_session_factory() as session:
            seg_result = await session.execute(
                select(Segment).where(Segment.id.in_(segment_ids))
            )
            for seg in seg_result.scalars().all():
                segment_titles[seg.id] = seg.title_ru

    items = []
    for kw in keywords:
        items.append({
            "id": kw.id,
            "segment_id": kw.segment_id,
            "segment_title": segment_titles.get(kw.segment_id) if kw.segment_id else "Все сегменты",
            "text": kw.text,
            "is_regex": kw.is_regex,
            "is_active": kw.is_active,
        })

    return {"items": items, "total": total, "page": page, "per_page": per_page}


@router.get("/{item_id}")
async def get_stop_word(item_id: int):
    """Get a single stop-word."""
    async with async_session_factory() as session:
        kw = await session.get(SegmentKeyword, item_id)
        if not kw or kw.keyword_type != "stop":
            raise HTTPException(status_code=404, detail="Not found")

        segment_title = None
        if kw.segment_id:
            seg = await session.get(Segment, kw.segment_id)
            segment_title = seg.title_ru if seg else None

        return {
            "id": kw.id,
            "segment_id": kw.segment_id,
            "segment_title": segment_title or "Все сегменты",
            "text": kw.text,
            "is_regex": kw.is_regex,
            "is_active": kw.is_active,
        }


@router.post("")
async def create_stop_word(data: dict):
    """Create a new stop-word (keyword_type forced to 'stop')."""
    async with async_session_factory() as session:
        kw = SegmentKeyword(
            segment_id=data.get("segment_id"),
            text=data["text"],
            keyword_type="stop",
            is_regex=data.get("is_regex", False),
            is_active=data.get("is_active", True),
        )
        session.add(kw)
        await session.commit()
        await session.refresh(kw)

        return {
            "id": kw.id,
            "segment_id": kw.segment_id,
            "segment_title": None,
            "text": kw.text,
            "is_regex": kw.is_regex,
            "is_active": kw.is_active,
        }


@router.put("/{item_id}")
async def update_stop_word(item_id: int, data: dict):
    """Update a stop-word."""
    async with async_session_factory() as session:
        kw = await session.get(SegmentKeyword, item_id)
        if not kw or kw.keyword_type != "stop":
            raise HTTPException(status_code=404, detail="Not found")

        updatable = {"text", "segment_id", "is_regex", "is_active"}
        for k, v in data.items():
            if k in updatable:
                setattr(kw, k, v)
        kw.keyword_type = "stop"  # force type

        await session.commit()
        await session.refresh(kw)

        return {
            "id": kw.id,
            "segment_id": kw.segment_id,
            "segment_title": None,
            "text": kw.text,
            "is_regex": kw.is_regex,
            "is_active": kw.is_active,
        }


@router.delete("/{item_id}")
async def delete_stop_word(item_id: int):
    """Delete a stop-word."""
    async with async_session_factory() as session:
        kw = await session.get(SegmentKeyword, item_id)
        if not kw or kw.keyword_type != "stop":
            raise HTTPException(status_code=404, detail="Not found")

        await session.delete(kw)
        await session.commit()
        return {"ok": True}
