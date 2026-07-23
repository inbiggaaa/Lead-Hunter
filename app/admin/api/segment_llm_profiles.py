"""Admin API — segment LLM profiles (draft / publish / rollback / preview)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.db import crud
from app.db.models import Segment
from app.db.session import async_session_factory
from app.userbot.llm_profiles import SegmentLLMProfile as RuntimeProfile
from app.userbot.llm_validator import may_bypass_llm
from app.userbot.segment_profile_cases import offline_predict

router = APIRouter(prefix="/api/segments", tags=["segment-llm-profiles"])


def _admin_user(request: Request) -> str:
    return str(request.session.get("admin_user") or "admin")


def _serialize_profile(profile) -> dict:
    published = crud.profile_to_payload(profile)
    draft = profile.draft_payload
    return {
        "id": profile.id,
        "segment_id": profile.segment_id,
        "locale": profile.locale,
        "published": published,
        "draft": draft,
        "has_draft": bool(draft),
        "version": profile.version,
        "requires_llm": profile.requires_llm,
        "target_lead": profile.target_lead,
        "accept_examples": list(profile.accept_examples or []),
        "reject_examples": list(profile.reject_examples or []),
        "conflict_slugs": list(profile.conflict_slugs or []),
        "diff": crud.profile_diff(published, draft) if draft else {},
    }


@router.get("/{segment_id}/llm-profile")
async def get_llm_profile(segment_id: int, locale: str = "ru"):
    async with async_session_factory() as session:
        seg = await session.get(Segment, segment_id)
        if not seg:
            raise HTTPException(status_code=404, detail="Segment not found")
        profile = await crud.get_segment_llm_profile(
            session, segment_id=segment_id, locale=locale,
        )
        if not profile:
            return {
                "segment": {"id": seg.id, "slug": seg.slug, "title_ru": seg.title_ru},
                "profile": None,
            }
        return {
            "segment": {"id": seg.id, "slug": seg.slug, "title_ru": seg.title_ru},
            "profile": _serialize_profile(profile),
        }


@router.post("/{segment_id}/llm-profile")
async def create_llm_profile(segment_id: int, data: dict, request: Request):
    async with async_session_factory() as session:
        seg = await session.get(Segment, segment_id)
        if not seg:
            raise HTTPException(status_code=404, detail="Segment not found")
        existing = await crud.get_segment_llm_profile(
            session, segment_id=segment_id, locale=data.get("locale") or "ru",
        )
        if existing:
            raise HTTPException(status_code=409, detail="Profile already exists")
        try:
            profile = await crud.create_segment_llm_profile(
                session,
                segment_id=segment_id,
                target_lead=data.get("target_lead") or "",
                accept_examples=data.get("accept_examples") or [],
                reject_examples=data.get("reject_examples") or [],
                conflict_slugs=data.get("conflict_slugs") or [],
                locale=data.get("locale") or "ru",
                requires_llm=bool(data.get("requires_llm", True)),
            )
            await crud.record_profile_create_audit(
                session,
                profile=profile,
                segment_slug=seg.slug,
                admin_user=_admin_user(request),
                reason=str(data.get("reason") or "create"),
            )
            await session.commit()
            await session.refresh(profile)
        except crud.SegmentLLMProfileValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _serialize_profile(profile)


@router.put("/{segment_id}/llm-profile/draft")
async def save_llm_profile_draft(segment_id: int, data: dict, request: Request):
    async with async_session_factory() as session:
        seg = await session.get(Segment, segment_id)
        if not seg:
            raise HTTPException(status_code=404, detail="Segment not found")
        profile = await crud.get_segment_llm_profile(
            session, segment_id=segment_id, locale=data.get("locale") or "ru",
        )
        if not profile:
            raise HTTPException(status_code=404, detail="Profile not found")
        try:
            await crud.save_segment_llm_profile_draft(
                session,
                profile=profile,
                payload=data,
                admin_user=_admin_user(request),
                segment_slug=seg.slug,
                reason=str(data.get("reason") or "draft"),
            )
            await session.commit()
            await session.refresh(profile)
        except crud.SegmentLLMProfileValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _serialize_profile(profile)


@router.post("/{segment_id}/llm-profile/publish")
async def publish_llm_profile(segment_id: int, data: dict, request: Request):
    if not data.get("confirm"):
        raise HTTPException(
            status_code=400,
            detail="publish requires confirm=true",
        )
    reason = str(data.get("reason") or "").strip()
    if not reason:
        raise HTTPException(status_code=400, detail="publish requires reason")

    async with async_session_factory() as session:
        seg = await session.get(Segment, segment_id)
        if not seg:
            raise HTTPException(status_code=404, detail="Segment not found")
        profile = await crud.get_segment_llm_profile(
            session, segment_id=segment_id, locale=data.get("locale") or "ru",
        )
        if not profile:
            raise HTTPException(status_code=404, detail="Profile not found")
        try:
            await crud.publish_segment_llm_profile(
                session,
                profile=profile,
                admin_user=_admin_user(request),
                segment_slug=seg.slug,
                reason=reason,
                payload=data.get("payload"),
            )
            await session.commit()
            await session.refresh(profile)
        except crud.SegmentLLMProfileValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _serialize_profile(profile)


@router.post("/{segment_id}/llm-profile/rollback")
async def rollback_llm_profile(segment_id: int, data: dict, request: Request):
    if not data.get("confirm"):
        raise HTTPException(
            status_code=400,
            detail="rollback requires confirm=true",
        )
    reason = str(data.get("reason") or "").strip()
    if not reason:
        raise HTTPException(status_code=400, detail="rollback requires reason")

    async with async_session_factory() as session:
        seg = await session.get(Segment, segment_id)
        if not seg:
            raise HTTPException(status_code=404, detail="Segment not found")
        profile = await crud.get_segment_llm_profile(
            session, segment_id=segment_id, locale=data.get("locale") or "ru",
        )
        if not profile:
            raise HTTPException(status_code=404, detail="Profile not found")
        try:
            await crud.rollback_segment_llm_profile(
                session,
                profile=profile,
                admin_user=_admin_user(request),
                segment_slug=seg.slug,
                reason=reason,
                audit_id=data.get("audit_id"),
            )
            await session.commit()
            await session.refresh(profile)
        except crud.SegmentLLMProfileValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _serialize_profile(profile)


@router.get("/{segment_id}/llm-profile/audits")
async def list_llm_profile_audits(segment_id: int, locale: str = "ru", limit: int = 20):
    async with async_session_factory() as session:
        seg = await session.get(Segment, segment_id)
        if not seg:
            raise HTTPException(status_code=404, detail="Segment not found")
        profile = await crud.get_segment_llm_profile(
            session, segment_id=segment_id, locale=locale,
        )
        if not profile:
            return {"items": []}
        rows = await crud.list_segment_llm_profile_audits(
            session, profile_id=profile.id, limit=limit,
        )
        return {
            "items": [
                {
                    "id": row.id,
                    "admin_user": row.admin_user,
                    "action": row.action,
                    "reason": row.reason,
                    "version_after": row.version_after,
                    "before": row.before_json,
                    "after": row.after_json,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                    "segment_slug": row.segment_slug,
                }
                for row in rows
            ]
        }


@router.get("/{segment_id}/llm-profile/diff")
async def llm_profile_diff(segment_id: int, locale: str = "ru"):
    async with async_session_factory() as session:
        profile = await crud.get_segment_llm_profile(
            session, segment_id=segment_id, locale=locale,
        )
        if not profile:
            raise HTTPException(status_code=404, detail="Profile not found")
        published = crud.profile_to_payload(profile)
        draft = profile.draft_payload or {}
        return {
            "version": profile.version,
            "has_draft": bool(profile.draft_payload),
            "diff": crud.profile_diff(published, draft) if draft else {},
            "published": published,
            "draft": draft or None,
        }


@router.post("/{segment_id}/llm-profile/preview")
async def preview_llm_profile(segment_id: int, data: dict):
    """Offline preview for one message (no live DeepSeek call)."""
    text = str(data.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is required")
    if len(text) > 1000:
        raise HTTPException(status_code=400, detail="text too long (max 1000)")

    async with async_session_factory() as session:
        seg = await session.get(Segment, segment_id)
        if not seg:
            raise HTTPException(status_code=404, detail="Segment not found")
        profile = await crud.get_segment_llm_profile(
            session, segment_id=segment_id, locale=data.get("locale") or "ru",
        )
        if not profile:
            raise HTTPException(status_code=404, detail="Profile not found")

        source = profile.draft_payload or crud.profile_to_payload(profile)
        runtime = RuntimeProfile(
            segment_slug=seg.slug,
            locale=profile.locale,
            target_lead=str(source.get("target_lead") or profile.target_lead),
            accept_examples=tuple(source.get("accept_examples") or []),
            reject_examples=tuple(source.get("reject_examples") or []),
            conflict_slugs=tuple(source.get("conflict_slugs") or []),
            requires_llm=bool(source.get("requires_llm", profile.requires_llm)),
            version=int(profile.version),
        )
        decision, intent = offline_predict(
            text,
            segment=seg.slug,
            lead_direction=getattr(seg, "lead_direction", None) or "demand",
        )
        bypass = may_bypass_llm(
            text=text,
            candidate_segments=(seg.slug,),
            profiles={seg.slug: runtime},
            lead_directions={
                seg.slug: getattr(seg, "lead_direction", None) or "demand",
            },
        )
        return {
            "segment": seg.slug,
            "using_draft": bool(profile.draft_payload),
            "offline_decision": decision,
            "offline_intent": intent,
            "may_bypass_llm": bypass,
            "requires_llm": runtime.requires_llm,
            "note": "Offline marker preview — not a live DeepSeek verdict.",
        }
