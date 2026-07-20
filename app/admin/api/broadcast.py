"""Broadcast API — ported from dashboard.py broadcast endpoints."""

from fastapi import APIRouter, HTTPException

from app.admin.broadcast import (
    broadcast_send,
    create_broadcast_preview,
    get_broadcast_stats,
)

router = APIRouter(prefix="/api/broadcast", tags=["broadcast"])


@router.get("/stats")
async def broadcast_stats():
    return await get_broadcast_stats()


@router.post("/send")
async def broadcast_send_route(data: dict):
    result = await broadcast_send(
        plan_filter=data.get("plan"),
        source_filter=data.get("source"),
        text=data.get("text", ""),
        confirmation_token=data.get("confirmation_token", ""),
    )
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/preview")
async def broadcast_preview_route(data: dict):
    try:
        return await create_broadcast_preview(
            plan_filter=data.get("plan"),
            source_filter=data.get("source"),
            text=data.get("text", ""),
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
