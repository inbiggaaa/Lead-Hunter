"""Segment detail API — keywords grouped by segment."""

from fastapi import APIRouter, HTTPException
from sqlalchemy import select, delete as sa_delete

from app.db.session import async_session_factory
from app.db.models import Segment, SegmentKeyword

router = APIRouter(prefix="/api/segments", tags=["segments"])


@router.get("/{segment_id}/keywords")
async def get_segment_keywords(segment_id: int):
    """Get all keywords for a segment, grouped by keyword_type."""
    async with async_session_factory() as session:
        seg = await session.get(Segment, segment_id)
        if not seg:
            raise HTTPException(status_code=404, detail="Segment not found")

        result = await session.execute(
            select(SegmentKeyword)
            .where(SegmentKeyword.segment_id == segment_id)
            .order_by(SegmentKeyword.keyword_type, SegmentKeyword.text)
        )
        keywords = result.scalars().all()

    demand = []
    stop = []
    synonym = []

    for kw in keywords:
        item = {
            "id": kw.id,
            "text": kw.text,
            "is_regex": kw.is_regex,
            "is_active": kw.is_active,
        }
        if kw.keyword_type == "stop":
            stop.append(item)
        elif kw.keyword_type == "synonym":
            synonym.append(item)
        else:
            demand.append(item)

    return {
        "segment": {
            "id": seg.id,
            "slug": seg.slug,
            "title_ru": seg.title_ru,
            "title_en": seg.title_en,
            "emoji": seg.emoji,
        },
        "demand": demand,
        "stop": stop,
        "synonym": synonym,
    }


@router.post("/{segment_id}/keywords")
async def create_segment_keyword(segment_id: int, data: dict):
    """Add a keyword to a segment."""
    async with async_session_factory() as session:
        seg = await session.get(Segment, segment_id)
        if not seg:
            raise HTTPException(status_code=404, detail="Segment not found")

        kw = SegmentKeyword(
            segment_id=segment_id,
            text=data["text"],
            keyword_type=data.get("keyword_type", "demand"),
            is_regex=data.get("is_regex", False),
            is_active=data.get("is_active", True),
        )
        session.add(kw)
        await session.commit()
        await session.refresh(kw)

        return {
            "id": kw.id,
            "text": kw.text,
            "keyword_type": kw.keyword_type,
            "is_regex": kw.is_regex,
            "is_active": kw.is_active,
        }


@router.put("/{segment_id}/keywords/{kw_id}")
async def update_segment_keyword(segment_id: int, kw_id: int, data: dict):
    """Update a keyword within a segment."""
    async with async_session_factory() as session:
        kw = await session.get(SegmentKeyword, kw_id)
        if not kw or kw.segment_id != segment_id:
            raise HTTPException(status_code=404, detail="Keyword not found")

        updatable = {"text", "keyword_type", "is_regex", "is_active"}
        for k, v in data.items():
            if k in updatable:
                setattr(kw, k, v)

        await session.commit()
        await session.refresh(kw)

        return {
            "id": kw.id,
            "text": kw.text,
            "keyword_type": kw.keyword_type,
            "is_regex": kw.is_regex,
            "is_active": kw.is_active,
        }


@router.delete("/{segment_id}/keywords/{kw_id}")
async def delete_segment_keyword(segment_id: int, kw_id: int):
    """Delete a keyword from a segment."""
    async with async_session_factory() as session:
        kw = await session.get(SegmentKeyword, kw_id)
        if not kw or kw.segment_id != segment_id:
            raise HTTPException(status_code=404, detail="Keyword not found")

        await session.delete(kw)
        await session.commit()
        return {"ok": True}
