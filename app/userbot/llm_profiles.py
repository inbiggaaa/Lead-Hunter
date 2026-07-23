"""Runtime snapshot of segment LLM profiles (Phase 3).

Loaded with the keyword reload cycle — no per-message SQL.
Empty table is valid: callers fall back to the universal prompt.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SegmentLLMProfile:
    segment_slug: str
    locale: str
    target_lead: str
    accept_examples: tuple[str, ...]
    reject_examples: tuple[str, ...]
    conflict_slugs: tuple[str, ...]
    requires_llm: bool
    version: int


_profile_snapshot: Mapping[str, SegmentLLMProfile] = MappingProxyType({})
_missing_total: int = 0


def reset_profile_runtime_state() -> None:
    """Test helper: clear snapshot and missing counter."""
    global _profile_snapshot, _missing_total
    _profile_snapshot = MappingProxyType({})
    _missing_total = 0


def get_profile_snapshot() -> Mapping[str, SegmentLLMProfile]:
    return _profile_snapshot


def replace_profile_snapshot(profiles: Mapping[str, SegmentLLMProfile]) -> None:
    """Atomically replace the immutable in-memory snapshot."""
    global _profile_snapshot
    _profile_snapshot = MappingProxyType(dict(profiles))


def profile_missing_total() -> int:
    return _missing_total


def select_candidate_profiles(
    candidate_segments: list[str],
    profiles: Mapping[str, SegmentLLMProfile],
) -> tuple[SegmentLLMProfile, ...]:
    """Return profiles for candidates; unknown slugs increment missing metric."""
    global _missing_total
    selected: list[SegmentLLMProfile] = []
    seen: set[str] = set()
    for slug in candidate_segments:
        if slug in seen:
            continue
        seen.add(slug)
        profile = profiles.get(slug)
        if profile is None:
            _missing_total += 1
            continue
        selected.append(profile)
    return tuple(selected)


def _to_runtime(slug: str, row) -> SegmentLLMProfile:
    return SegmentLLMProfile(
        segment_slug=slug,
        locale=row.locale,
        target_lead=row.target_lead,
        accept_examples=tuple(row.accept_examples or ()),
        reject_examples=tuple(row.reject_examples or ()),
        conflict_slugs=tuple(row.conflict_slugs or ()),
        requires_llm=bool(row.requires_llm),
        version=int(row.version),
    )


async def load_segment_llm_profiles(
    locale: str = "ru",
    *,
    session: AsyncSession | None = None,
) -> dict[str, SegmentLLMProfile]:
    """Load profiles for active segments only. Empty dict if none."""
    from app.db.crud import list_active_segment_llm_profiles
    from app.db.session import async_session_factory

    if session is not None:
        rows = await list_active_segment_llm_profiles(session, locale=locale)
        return {slug: _to_runtime(slug, row) for slug, row in rows}

    async with async_session_factory() as own:
        rows = await list_active_segment_llm_profiles(own, locale=locale)
        return {slug: _to_runtime(slug, row) for slug, row in rows}


async def reload_profile_snapshot(locale: str = "ru") -> bool:
    """Reload snapshot from DB. On error keep previous snapshot and return False."""
    try:
        loaded = await load_segment_llm_profiles(locale=locale)
        replace_profile_snapshot(loaded)
        active_candidates = len(loaded)
        logger.info(
            "LLM profiles loaded: %d (locale=%s)",
            active_candidates,
            locale,
        )
        return True
    except Exception:
        logger.warning(
            "LLM profile reload failed, keeping previous snapshot (%d profiles)",
            len(_profile_snapshot),
            exc_info=True,
        )
        return False
