"""Redis client factory — one client (one connection pool) per process."""

from redis.asyncio import Redis

from app.config import settings

_client: Redis | None = None


async def get_redis() -> Redis:
    """Return the process-wide Redis client, creating it lazily.

    The client owns a connection pool and lives for the whole process —
    callers must NOT aclose() it. Before B3 every call opened a fresh TCP
    connection (hundreds per minute across poller/sender/limiter).
    Created lazily so the client is born inside the running event loop.
    """
    global _client
    if _client is None:
        _client = Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            db=settings.redis_db,
            decode_responses=True,
        )
    return _client
