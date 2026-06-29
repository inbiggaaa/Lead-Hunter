"""Redis client factory."""

from redis.asyncio import Redis

from app.config import settings


async def get_redis() -> Redis:
    return Redis(
        host=settings.redis_host,
        port=settings.redis_port,
        db=settings.redis_db,
        decode_responses=True,
    )
