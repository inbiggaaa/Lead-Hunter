"""Session-based auth for admin SPA — with Redis-based brute-force protection."""

import time

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.config import settings

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Rate limit config
MAX_ATTEMPTS = 5           # failed attempts before block
ATTEMPT_WINDOW = 60         # seconds — sliding window for attempts
BLOCK_DURATION = 300        # seconds — first block (5 min)
BLOCK_DURATION_LONG = 3600  # seconds — repeat offender (1 hour)
MAX_BLOCKS_BEFORE_LONG = 3  # blocks before longer cooldown


def _get_ip(request: Request) -> str:
    """Extract real client IP, respecting reverse proxies."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class LoginRequest(BaseModel):
    password: str


@router.post("/login")
async def login(request: Request, body: LoginRequest):
    client_ip = _get_ip(request)

    try:
        from app.cache import get_redis

        redis = await get_redis()
        attempt_key = f"login_attempts:{client_ip}"
        block_key = f"login_blocked:{client_ip}"
        block_count_key = f"login_block_count:{client_ip}"

        # ── Check if currently blocked ──
        block_ttl = await redis.ttl(block_key)
        if block_ttl > 0:
            raise HTTPException(
                status_code=429,
                detail=f"Too many attempts. Try again in {block_ttl} seconds.",
            )

        # ── Check password ──
        if body.password != settings.admin_password:
            # Record failed attempt
            pipe = redis.pipeline()
            pipe.incr(attempt_key)
            pipe.expire(attempt_key, ATTEMPT_WINDOW)
            attempts = (await pipe.execute())[0]

            remaining = MAX_ATTEMPTS - attempts
            if remaining > 0:
                raise HTTPException(
                    status_code=401,
                    detail=f"Invalid password. {remaining} attempts remaining.",
                )

            # Block the IP
            block_count = await redis.incr(block_count_key)
            await redis.expire(block_count_key, 86400)  # keep count for 24h
            duration = BLOCK_DURATION_LONG if block_count >= MAX_BLOCKS_BEFORE_LONG else BLOCK_DURATION
            await redis.setex(block_key, duration, int(time.time()))
            raise HTTPException(
                status_code=429,
                detail=f"Too many attempts. Blocked for {duration} seconds.",
            )

        # ── Success — clear attempt counters ──
        await redis.delete(attempt_key, block_count_key)
        request.session["authenticated"] = True
        return {"ok": True}

    except HTTPException:
        raise
    except Exception:
        # If Redis is down, fall back to password-only check
        if body.password != settings.admin_password:
            raise HTTPException(status_code=401, detail="Invalid password")
        request.session["authenticated"] = True
        return {"ok": True}


@router.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return {"ok": True}


@router.get("/check")
async def check(request: Request):
    if not request.session.get("authenticated"):
        return {"authenticated": False}
    return {"authenticated": True}
