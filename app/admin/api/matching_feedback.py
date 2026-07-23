"""Admin API for closed matching feedback analytics."""

from __future__ import annotations

from fastapi import APIRouter, Query
from fastapi.responses import Response

from app.matching_feedback.analytics import (
    FeedbackFilters,
    build_feedback_summary,
    export_feedback_csv_bytes,
    export_feedback_jsonl_bytes,
    list_feedback_rows,
)

router = APIRouter(prefix="/api/matching-feedback", tags=["matching-feedback"])


@router.get("/summary")
async def matching_feedback_summary(batch: str = Query(...)):
    return await build_feedback_summary(batch)


@router.get("/items")
async def matching_feedback_items(
    batch: str = Query(...),
    verdict: str | None = None,
    reason: str | None = None,
    segment: str | None = None,
):
    rows = await list_feedback_rows(
        batch,
        FeedbackFilters(verdict=verdict, reason=reason, segment=segment),
    )
    # Never expose tokens fully in list UI — truncate
    safe = []
    for row in rows:
        item = dict(row)
        token = item.get("public_token") or ""
        item["public_token"] = f"{token[:4]}…" if token else None
        safe.append(item)
    return {"items": safe, "count": len(safe)}


@router.get("/export.csv")
async def matching_feedback_export_csv(batch: str = Query(...)):
    rows = await list_feedback_rows(batch, FeedbackFilters())
    body = export_feedback_csv_bytes(rows)
    return Response(
        content=body,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="matching_feedback_{batch}.csv"'
        },
    )


@router.get("/export.jsonl")
async def matching_feedback_export_jsonl(batch: str = Query(...)):
    rows = await list_feedback_rows(batch, FeedbackFilters())
    body = export_feedback_jsonl_bytes(rows)
    return Response(
        content=body,
        media_type="application/x-ndjson; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="matching_feedback_{batch}.jsonl"'
        },
    )
