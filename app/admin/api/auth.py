"""Session-based auth for admin SPA."""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.config import settings

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    password: str


@router.post("/login")
async def login(request: Request, body: LoginRequest):
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
