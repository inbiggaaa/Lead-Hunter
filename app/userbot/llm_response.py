"""LLM response schema v2 — per-segment verdicts + legacy adapter (Phase 5).

Parsing is fail-open: malformed/unknown values never silently drop a lead.
Delivery still uses LLMResult until Phase 8 switches blocking to v2.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import StrEnum

logger = logging.getLogger(__name__)

_REASON_CODE_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_MAX_REASON_LEN = 160
_ALLOWED_CERTAINTY = frozenset({"high", "medium", "low"})
_ACCEPT_INTENTS = frozenset({"commercial_demand", "mixed"})
_REJECT_INTENTS = frozenset({
    "provider_offer",
    "job_vacancy",
    "job_search",
    "social_request",
    "discussion",
    "irrelevant",
})


class LLMDecision(StrEnum):
    ACCEPT = "accept"
    REJECT = "reject"


class CommercialIntent(StrEnum):
    COMMERCIAL_DEMAND = "commercial_demand"
    PROVIDER_OFFER = "provider_offer"
    JOB_VACANCY = "job_vacancy"
    JOB_SEARCH = "job_search"
    SOCIAL_REQUEST = "social_request"
    DISCUSSION = "discussion"
    IRRELEVANT = "irrelevant"
    MIXED = "mixed"


@dataclass(frozen=True, slots=True)
class SegmentVerdict:
    segment_slug: str
    decision: LLMDecision
    intent: CommercialIntent
    certainty: str
    reason_code: str
    reason: str


@dataclass
class ParsedSegmentMessage:
    verdicts: list[SegmentVerdict] = field(default_factory=list)
    fail_open_segments: list[str] = field(default_factory=list)
    malformed: bool = False
    issues: list[str] = field(default_factory=list)


def _safe_reason_code(value: object) -> str:
    text = str(value or "").strip().lower()
    if _REASON_CODE_RE.fullmatch(text):
        return text
    return "invalid_reason_code"


def _safe_reason(value: object) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= _MAX_REASON_LEN:
        return text
    return text[: _MAX_REASON_LEN - 1] + "…"


def _safe_certainty(value: object) -> str:
    text = str(value or "low").strip().lower()
    return text if text in _ALLOWED_CERTAINTY else "low"


def parse_segment_aware_message(
    raw: object,
    *,
    expected_index: int,
    candidate_segments: list[str],
) -> ParsedSegmentMessage:
    """Parse one message object from a v2 LLM batch response."""
    candidates = list(dict.fromkeys(candidate_segments))
    result = ParsedSegmentMessage()

    if not isinstance(raw, dict):
        result.malformed = True
        result.fail_open_segments = candidates
        result.issues.append("message_not_object")
        return result

    if raw.get("index") != expected_index:
        result.malformed = True
        result.fail_open_segments = candidates
        result.issues.append("index_mismatch")
        return result

    segments_raw = raw.get("segments")
    if not isinstance(segments_raw, list):
        result.malformed = True
        result.fail_open_segments = candidates
        result.issues.append("segments_not_list")
        return result

    seen: set[str] = set()
    candidate_set = set(candidates)

    for item in segments_raw:
        if not isinstance(item, dict):
            result.issues.append("segment_not_object")
            continue
        slug = str(item.get("slug") or "").strip()
        if not slug:
            result.issues.append("empty_slug")
            continue
        if slug not in candidate_set:
            logger.info("LLM v2 unknown slug ignored: %s", slug)
            result.issues.append(f"unknown_slug:{slug}")
            continue
        if slug in seen:
            result.malformed = True
            result.issues.append(f"duplicate_slug:{slug}")
            result.verdicts = []
            result.fail_open_segments = candidates
            return result
        seen.add(slug)

        intent_raw = str(item.get("intent") or "").strip().lower()
        decision_raw = str(item.get("decision") or "").strip().lower()
        try:
            intent = CommercialIntent(intent_raw)
            decision = LLMDecision(decision_raw)
        except ValueError:
            result.fail_open_segments.append(slug)
            result.issues.append(f"unknown_enum:{slug}")
            continue

        if decision is LLMDecision.ACCEPT and intent_raw not in _ACCEPT_INTENTS:
            result.fail_open_segments.append(slug)
            result.issues.append(f"accept_intent_mismatch:{slug}")
            continue
        if decision is LLMDecision.REJECT and intent_raw not in _REJECT_INTENTS:
            # reject + commercial_demand/mixed is inconsistent → fail-open
            result.fail_open_segments.append(slug)
            result.issues.append(f"reject_intent_mismatch:{slug}")
            continue

        result.verdicts.append(
            SegmentVerdict(
                segment_slug=slug,
                decision=decision,
                intent=intent,
                certainty=_safe_certainty(item.get("certainty")),
                reason_code=_safe_reason_code(item.get("reason_code")),
                reason=_safe_reason(item.get("reason")),
            )
        )

    covered = {v.segment_slug for v in result.verdicts} | set(result.fail_open_segments)
    for slug in candidates:
        if slug not in covered:
            result.fail_open_segments.append(slug)
            result.issues.append(f"missing_candidate:{slug}")

    return result


def to_legacy_llm_result(
    *,
    candidate_segments: list[str],
    verdicts: list[SegmentVerdict],
    fail_open_segments: list[str] | None = None,
    malformed: bool = False,
) -> "LLMResult":
    """Map per-segment v2 verdicts to legacy message-level LLMResult."""
    from app.userbot.llm_validator import LLMResult

    fail_open = list(dict.fromkeys(fail_open_segments or []))
    if malformed:
        return LLMResult(
            verdict="DEMAND",
            relevant_segments=list(candidate_segments),
            reason="malformed v2 response — fail-open",
            certainty="low",
            error="malformed_v2",
        )

    accepted = [v.segment_slug for v in verdicts if v.decision is LLMDecision.ACCEPT]
    rejected = [v for v in verdicts if v.decision is LLMDecision.REJECT]
    relevant = list(dict.fromkeys([*accepted, *fail_open]))

    if relevant:
        has_mixed = any(
            v.intent is CommercialIntent.MIXED
            for v in verdicts
            if v.segment_slug in accepted
        )
        certainty = "low" if fail_open else _max_certainty(
            [v.certainty for v in verdicts if v.segment_slug in accepted]
        )
        return LLMResult(
            verdict="MIXED" if has_mixed else "DEMAND",
            relevant_segments=relevant,
            reason=_join_reasons(verdicts, fail_open),
            certainty=certainty or "low",
            error="missing_segment_v2" if fail_open else None,
        )

    # All candidates rejected with valid intents.
    if any(v.intent is CommercialIntent.PROVIDER_OFFER for v in rejected):
        verdict = "OFFER"
    else:
        verdict = "OTHER"
    return LLMResult(
        verdict=verdict,
        relevant_segments=[],
        reason=_join_reasons(verdicts, []),
        certainty=_max_certainty([v.certainty for v in rejected]) or "high",
    )


def _max_certainty(values: list[str]) -> str:
    order = {"high": 3, "medium": 2, "low": 1}
    if not values:
        return "low"
    return max(values, key=lambda c: order.get(c, 0))


def _join_reasons(verdicts: list[SegmentVerdict], fail_open: list[str]) -> str:
    parts = [f"{v.segment_slug}:{v.reason_code}" for v in verdicts]
    parts.extend(f"{slug}:fail_open" for slug in fail_open)
    return "; ".join(parts)[:300]
