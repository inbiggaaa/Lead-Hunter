"""Broadcast API — ported from dashboard.py broadcast endpoints."""

from fastapi import APIRouter

from app.admin.broadcast import broadcast_send, get_broadcast_stats

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
    )
    return result
