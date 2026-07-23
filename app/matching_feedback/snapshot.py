"""Build JSON-safe matching layer snapshots for closed feedback."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.userbot.llm_validator import LLMResult, PendingMatch


def build_matching_feedback_snapshot(
    *,
    match: PendingMatch,
    llm_result: LLMResult,
    delivered_segments: list[str],
) -> dict[str, object]:
    """Immutable delivery-time snapshot — never includes raw text or raw LLM JSON."""
    layer = dict(getattr(llm_result, "layer_snapshot", None) or {})
    reality = list(match.candidate_segments or [])
    rules = list(getattr(match, "rule_segments", None) or reality)

    snapshot: dict[str, object] = {
        "delivered_segments": list(delivered_segments),
        "rule_segments": rules,
        "reality_segments": reality,
        "legacy_llm_verdict": layer.get("legacy_llm_verdict", llm_result.verdict),
        "legacy_llm_segments": list(
            layer.get("legacy_llm_segments")
            or llm_result.relevant_segments
            or []
        ),
        "v2_intent": layer.get("v2_intent"),
        "v2_segment_verdicts": dict(layer.get("v2_segment_verdicts") or {}),
        "model_name": layer.get("model_name"),
        "prompt_version": layer.get("prompt_version"),
        "schema_version": layer.get("schema_version"),
        "profile_versions": dict(layer.get("profile_versions") or {}),
        "keyword_only": bool(match.keyword_only),
        "from_v2": bool(getattr(llm_result, "from_v2", False)),
        "snapshot_missing": False,
    }
    if not layer and not match.keyword_only:
        # Legacy path without v2 overlay — still usable, flag missing v2 only.
        snapshot["snapshot_missing"] = snapshot["v2_intent"] is None and not snapshot[
            "profile_versions"
        ]
    return snapshot


def layer_snapshot_from_v2(
    *,
    legacy: LLMResult,
    verdicts: list,
    profiles: dict,
    candidate_segments: list[str],
    model_name: str,
    prompt_version: int,
    schema_version: int,
) -> dict[str, object]:
    """Capture dual legacy+v2 layer data while both objects are in memory."""
    intents = [getattr(v, "intent", None) for v in verdicts]
    primary_intent = None
    for intent in intents:
        if intent is not None:
            primary_intent = getattr(intent, "value", str(intent))
            break

    segment_verdicts: dict[str, str] = {}
    for verdict in verdicts:
        slug = getattr(verdict, "segment_slug", None)
        decision = getattr(verdict, "decision", None)
        if slug and decision is not None:
            segment_verdicts[str(slug)] = getattr(decision, "value", str(decision))

    profile_versions: dict[str, int] = {}
    for slug in candidate_segments:
        profile = profiles.get(slug)
        if profile is not None:
            profile_versions[slug] = int(getattr(profile, "version", 0) or 0)

    return {
        "legacy_llm_verdict": legacy.verdict,
        "legacy_llm_segments": list(legacy.relevant_segments or []),
        "v2_intent": primary_intent,
        "v2_segment_verdicts": segment_verdicts,
        "model_name": model_name,
        "prompt_version": prompt_version,
        "schema_version": schema_version,
        "profile_versions": profile_versions,
    }
