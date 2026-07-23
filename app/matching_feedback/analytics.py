"""Canonical matching-feedback analytics and gold export helpers."""

from __future__ import annotations

import csv
import io
import json
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Feedback
from app.db.session import async_session_factory


@dataclass(frozen=True, slots=True)
class FeedbackFilters:
    verdict: str | None = None
    reason: str | None = None
    segment: str | None = None


def _row_as_dict(row: Feedback) -> dict[str, Any]:
    return {
        "id": row.id,
        "public_token": row.public_token,
        "test_batch": row.test_batch,
        "chat_username": row.chat_username,
        "message_id": row.message_id,
        "message_text_masked": row.message_text_masked,
        "delivered_segments": list(row.delivered_segments or []),
        "rule_segments": list(row.rule_segments or []),
        "reality_segments": list(row.reality_segments or []),
        "legacy_llm_verdict": row.legacy_llm_verdict,
        "legacy_llm_segments": list(row.legacy_llm_segments or []),
        "v2_intent": row.v2_intent,
        "v2_segment_verdicts": dict(row.v2_segment_verdicts or {}),
        "model_name": row.model_name,
        "prompt_version": row.prompt_version,
        "schema_version": row.schema_version,
        "profile_versions": dict(row.profile_versions or {}),
        "keyword_only": bool(row.keyword_only),
        "verdict": row.verdict,
        "reason_code": row.reason_code,
        "confirmed_segments": list(row.confirmed_segments or []),
        "expected_segment_id": row.expected_segment_id,
        "expected_segment_slug": row.expected_segment_slug,
        "expected_segment_missing": bool(row.expected_segment_missing),
        "rated_at": row.rated_at.isoformat() if row.rated_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def aggregate_feedback(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """One calculation path for API, eval and export."""
    delivered = len(rows)
    correct = sum(1 for r in rows if r.get("verdict") == "correct")
    error = sum(1 for r in rows if r.get("verdict") == "error")
    uncertain = sum(1 for r in rows if r.get("verdict") == "uncertain")
    unrated = sum(1 for r in rows if not r.get("verdict"))
    defined = correct + error
    rated = defined + uncertain
    precision = (correct / defined) if defined else None

    reasons = Counter(r.get("reason_code") for r in rows if r.get("verdict") == "error")
    reasons.pop(None, None)

    per_segment: dict[str, dict[str, int]] = defaultdict(
        lambda: {"correct": 0, "error": 0, "uncertain": 0}
    )
    confusion: Counter[tuple[str, str]] = Counter()

    for row in rows:
        delivered_segs = list(row.get("delivered_segments") or [])
        confirmed = set(row.get("confirmed_segments") or [])
        verdict = row.get("verdict")
        expected = row.get("expected_segment_slug")

        if verdict == "correct":
            for slug in confirmed:
                per_segment[slug]["correct"] += 1
            for slug in delivered_segs:
                if slug not in confirmed:
                    per_segment[slug]["error"] += 1
                    for good in confirmed:
                        confusion[(slug, good)] += 1
        elif verdict == "error":
            for slug in delivered_segs:
                per_segment[slug]["error"] += 1
                if expected:
                    confusion[(slug, expected)] += 1
        elif verdict == "uncertain":
            for slug in delivered_segs:
                per_segment[slug]["uncertain"] += 1

    per_segment_out = {}
    for slug, counts in per_segment.items():
        defined_seg = counts["correct"] + counts["error"]
        per_segment_out[slug] = {
            **counts,
            "precision": (counts["correct"] / defined_seg) if defined_seg else None,
        }

    missing_snapshot = sum(
        1
        for r in rows
        if not r.get("legacy_llm_verdict")
        and not r.get("v2_intent")
        and not r.get("rule_segments")
        and not r.get("keyword_only")
    )

    by_model = Counter(r.get("model_name") or "unknown" for r in rows)
    by_prompt = Counter(str(r.get("prompt_version")) for r in rows)
    by_schema = Counter(str(r.get("schema_version")) for r in rows)
    legacy_vs_v2 = {
        "legacy_only": sum(1 for r in rows if r.get("legacy_llm_verdict") and not r.get("v2_intent")),
        "with_v2": sum(1 for r in rows if r.get("v2_intent")),
        "neither": sum(
            1 for r in rows if not r.get("legacy_llm_verdict") and not r.get("v2_intent")
        ),
    }

    return {
        "delivered": delivered,
        "rated": rated,
        "defined": defined,
        "unrated": unrated,
        "correct": correct,
        "error": error,
        "uncertain": uncertain,
        "precision": precision,
        "uncertain_rate": (uncertain / rated) if rated else None,
        "rated_coverage": (rated / delivered) if delivered else None,
        "reasons": dict(reasons),
        "per_segment": per_segment_out,
        "confusion": [
            {"delivered": a, "expected": b, "count": n}
            for (a, b), n in confusion.most_common()
        ],
        "by_model": dict(by_model),
        "by_prompt_version": dict(by_prompt),
        "by_schema_version": dict(by_schema),
        "legacy_vs_v2": legacy_vs_v2,
        "missing_snapshot": missing_snapshot,
    }


def gold_export_rows(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Exclude uncertain/unrated; strip PII; mark intent-only wrong_category."""
    out: list[dict[str, Any]] = []
    for row in rows:
        verdict = row.get("verdict")
        if verdict not in {"correct", "error"}:
            continue
        intent_only = (
            verdict == "error"
            and row.get("reason_code") == "wrong_category"
            and not row.get("expected_segment_slug")
            and not row.get("expected_segment_missing")
        )
        out.append(
            {
                "test_batch": row.get("test_batch"),
                "chat_username": row.get("chat_username"),
                "message_id": row.get("message_id"),
                "message_text_masked": row.get("message_text_masked"),
                "delivered_segments": row.get("delivered_segments") or [],
                "confirmed_segments": row.get("confirmed_segments") or [],
                "verdict": verdict,
                "reason_code": row.get("reason_code"),
                "expected_segment_slug": row.get("expected_segment_slug"),
                "expected_segment_missing": bool(row.get("expected_segment_missing")),
                "intent_only": intent_only,
                "legacy_llm_verdict": row.get("legacy_llm_verdict"),
                "v2_intent": row.get("v2_intent"),
                "model_name": row.get("model_name"),
                "prompt_version": row.get("prompt_version"),
                "schema_version": row.get("schema_version"),
                "profile_versions": row.get("profile_versions") or {},
            }
        )
    out.sort(key=lambda r: (r.get("chat_username") or "", r.get("message_id") or 0))
    return out


def assert_no_pii(rows: Iterable[dict[str, Any]]) -> None:
    forbidden = ("telegram_id", "sender", "phone", "message_text")
    for row in rows:
        for key in forbidden:
            if key in row:
                raise AssertionError(f"PII field present in export: {key}")
        text = str(row.get("message_text_masked") or "")
        if "http://" in text or "https://" in text:
            raise AssertionError("raw link in masked text")


async def load_feedback_rows(
    batch: str,
    filters: FeedbackFilters | None = None,
    *,
    session: AsyncSession | None = None,
) -> list[dict[str, Any]]:
    filters = filters or FeedbackFilters()

    async def _load(sess: AsyncSession) -> list[dict[str, Any]]:
        stmt = select(Feedback).where(Feedback.test_batch == batch)
        if filters.verdict:
            stmt = stmt.where(Feedback.verdict == filters.verdict)
        if filters.reason:
            stmt = stmt.where(Feedback.reason_code == filters.reason)
        result = await sess.execute(stmt.order_by(Feedback.id))
        rows = [_row_as_dict(r) for r in result.scalars().all()]
        if filters.segment:
            rows = [
                r
                for r in rows
                if filters.segment in (r.get("delivered_segments") or [])
                or filters.segment in (r.get("confirmed_segments") or [])
                or filters.segment == r.get("expected_segment_slug")
            ]
        return rows

    if session is not None:
        return await _load(session)
    async with async_session_factory() as sess:
        return await _load(sess)


async def build_feedback_summary(batch: str) -> dict[str, Any]:
    rows = await load_feedback_rows(batch)
    summary = aggregate_feedback(rows)
    summary["batch"] = batch
    return summary


async def list_feedback_rows(batch: str, filters: FeedbackFilters) -> list[dict[str, Any]]:
    return await load_feedback_rows(batch, filters)


def export_feedback_csv_bytes(rows: Sequence[dict[str, Any]]) -> bytes:
    gold = gold_export_rows(rows)
    assert_no_pii(gold)
    buf = io.StringIO()
    if not gold:
        return b""
    writer = csv.DictWriter(buf, fieldnames=list(gold[0].keys()))
    writer.writeheader()
    for row in gold:
        flat = dict(row)
        for key in (
            "delivered_segments",
            "confirmed_segments",
            "profile_versions",
        ):
            flat[key] = json.dumps(flat[key], ensure_ascii=False)
        writer.writerow(flat)
    return buf.getvalue().encode("utf-8")


def export_feedback_jsonl_bytes(rows: Sequence[dict[str, Any]]) -> bytes:
    gold = gold_export_rows(rows)
    assert_no_pii(gold)
    lines = [json.dumps(row, ensure_ascii=False) for row in gold]
    return ("\n".join(lines) + ("\n" if lines else "")).encode("utf-8")
