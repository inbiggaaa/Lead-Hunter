"""Unmatched messages API — reads from Redis stats:unmatched list."""

from fastapi import APIRouter, Query
from app.cache import get_redis

router = APIRouter(prefix="/api/unmatched", tags=["unmatched"])


@router.get("")
async def list_unmatched(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    search: str | None = None,
    chat: str | None = None,
):
    """List unmatched messages from Redis with pagination and filters."""
    import json

    redis = await get_redis()
    try:
        # Get all entries (LRANGE is O(N) but limited to 10000)
        raw = await redis.lrange("stats:unmatched", 0, -1)
    finally:
        await redis.aclose()

    items: list[dict] = []
    for entry in raw:
        if isinstance(entry, bytes):
            entry = entry.decode("utf-8")
        try:
            obj = json.loads(entry)
            items.append(obj)
        except (json.JSONDecodeError, TypeError):
            continue

    # Filters
    if chat:
        items = [it for it in items if it.get("chat", "").lower() == chat.lower()]
    if search:
        s = search.lower()
        items = [
            it
            for it in items
            if s in it.get("text", "").lower() or s in it.get("chat", "").lower()
        ]

    total = len(items)

    # Paginate
    start = (page - 1) * per_page
    end = start + per_page
    page_items = items[start:end]

    return {
        "items": page_items,
        "total": total,
        "page": page,
        "per_page": per_page,
    }


@router.get("/chats")
async def list_unmatched_chats():
    """List distinct chat usernames that have unmatched messages."""
    import json

    redis = await get_redis()
    try:
        raw = await redis.lrange("stats:unmatched", 0, -1)
    finally:
        await redis.aclose()

    chats: set[str] = set()
    for entry in raw:
        if isinstance(entry, bytes):
            entry = entry.decode("utf-8")
        try:
            obj = json.loads(entry)
            chat_name = obj.get("chat", "")
            if chat_name:
                chats.add(chat_name)
        except (json.JSONDecodeError, TypeError):
            continue

    return {"chats": sorted(chats)}


@router.get("/count")
async def unmatched_count():
    """Return total count of unmatched messages."""
    redis = await get_redis()
    try:
        count = await redis.llen("stats:unmatched")
    finally:
        await redis.aclose()
    return {"count": count}
