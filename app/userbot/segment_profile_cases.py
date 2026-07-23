"""Offline golden corpus helpers for segment-aware LLM profiles (Phase 9).

Corpus is synthetic / bounded evidence for gates — not production proof alone.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.userbot.llm_response import (
    CommercialIntent,
    LLMDecision,
    SegmentVerdict,
    to_legacy_llm_result,
)
from app.userbot.llm_validator import LLMValidator, may_bypass_llm
from app.userbot.llm_profiles import SegmentLLMProfile

ALLOWED_ORIGINS = frozenset({
    "synthetic",
    "bounded_real",
    "feedback",
    "llm_decision",
    "unmatched",
})
ALLOWED_DECISIONS = frozenset({"accept", "reject"})
ALLOWED_INTENTS = frozenset(i.value for i in CommercialIntent)

_VACANCY_MARKERS = re.compile(
    r"(?iu)(?<!\w)(вакансия|зарплата|график|смена|в\s+штат)(?!\w)",
)
_JOB_SEARCH_MARKERS = re.compile(
    r"(?iu)(?<!\w)("
    r"ищу\s+работу|ищет\s+(?:постоянную\s+)?работу|возьму\s+заказы"
    r")(?!\w)",
)
_SOCIAL_MARKERS = re.compile(
    r"(?iu)(ищу\s+партн[её]ра|кто\s+хочет\s+поиграть|поиграть)",
)
_PROVIDER_MARKERS = re.compile(
    r"(?iu)(?<!\w)("
    r"предлагаю|предлагаем|предлагает|оказываю\s+услуги|оказывает|"
    r"открыта\s+запись|открыл[аи]?\s+запись|запись\s+открыта|"
    r"набираю\s+клиентов|набирает|набираю\s+(?:новую|учеников)|"
    r"откры(?:ла|вает|т)\s+набор|набор\s+в\s+новую|набираем\s+групп|"
    r"в\s+наличии|пишите\s+(в\s+)?(личк\w*|лс|директ|менеджер\w*)|"
    r"бронируйте|свободн(?:ые|ая|ое|ый)\b|наш[ае]?\s+(прокат|служба)|автопарк|прайс|"
    r"сдаю|сдаём|сдам|услуги\s+\w+|делаю\s+\w+|оформляем|"
    r"беру\s+(компани|проект|новые)|выезд\s+бесплатно|"
    r"приглашает|приглашаем|вед[её]т\s+при[её]м|веду\s+при[её]м|"
    r"регистрируем|организуем|наращиваю|провожу|прода[её]тся|"
    r"портфолио|акция\s+на|запись\s+через|принимаю\s+заказ|"
    r"принимает\s+(?:взрослых|заказ)|возьму\s+собак"
    r")(?!\w)",
)
_DEMAND_LEAD = re.compile(
    r"(?iu)^(ищу|ищем|нужен|нужна|нужно|нужны|требуется|требуются|"
    r"сниму|снимем|куплю|приобрету|закажу|подскажите|посоветуйте)\b",
)
_TEAM_SOCIAL = re.compile(
    r"(?iu)(собираем\s+.{0,20}команд|бесплатн\w+\s+игр|секция\s+набира|"
    r"ищем\s+игроков|любительск\w+\s+команд)",
)
_SELL_MARKERS = re.compile(r"(?iu)(?<!\w)(продам|продаю)(?!\w)")
_BUY_MARKERS = re.compile(
    r"(?iu)(?<!\w)(куплю|покупаю|для\s+покупки)(?!\w)",
)
_COLLISION_MARKERS = re.compile(
    r"(?iu)(не\s+относится|соседн|к\s+\S+\s+это\s+не)",
)

DEFAULT_CASES_PATH = (
    Path(__file__).resolve().parents[2]
    / "tests"
    / "fixtures"
    / "segment_llm_profiles_ru_cases.json"
)


@dataclass(frozen=True)
class CorpusIssue:
    code: str
    detail: str


def load_cases(path: Path | None = None) -> list[dict[str, Any]]:
    target = path or DEFAULT_CASES_PATH
    payload = json.loads(target.read_text(encoding="utf-8"))
    cases = payload.get("cases")
    if not isinstance(cases, list):
        raise ValueError(f"cases list missing in {target}")
    return cases


def validate_corpus(
    cases: list[dict[str, Any]],
    *,
    required_slugs: set[str],
    min_total: int = 350,
    min_accept: int = 2,
    min_reject: int = 2,
    min_collision: int = 1,
    min_offer: int = 1,
) -> list[CorpusIssue]:
    """Structural gates for the golden corpus."""
    issues: list[CorpusIssue] = []
    if len(cases) < min_total:
        issues.append(CorpusIssue("too_few_cases", f"{len(cases)} < {min_total}"))

    ids = [c.get("id") for c in cases]
    if len(ids) != len(set(ids)):
        issues.append(CorpusIssue("duplicate_ids", "case id must be unique"))

    by_seg: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for case in cases:
        for key in (
            "id", "segment", "text", "expected_intent",
            "expected_decision", "origin",
        ):
            if not str(case.get(key) or "").strip():
                issues.append(CorpusIssue("missing_field", f"{case.get('id')}:{key}"))
        if case.get("origin") not in ALLOWED_ORIGINS:
            issues.append(CorpusIssue(
                "bad_origin", f"{case.get('id')}:{case.get('origin')}",
            ))
        if case.get("expected_decision") not in ALLOWED_DECISIONS:
            issues.append(CorpusIssue(
                "bad_decision", f"{case.get('id')}:{case.get('expected_decision')}",
            ))
        if case.get("expected_intent") not in ALLOWED_INTENTS:
            issues.append(CorpusIssue(
                "bad_intent", f"{case.get('id')}:{case.get('expected_intent')}",
            ))
        by_seg[str(case.get("segment"))].append(case)

    missing = sorted(required_slugs - set(by_seg))
    if missing:
        issues.append(CorpusIssue("missing_segments", ",".join(missing[:20])))

    for slug in sorted(required_slugs & set(by_seg)):
        rows = by_seg[slug]
        kinds = [str(r.get("case_kind") or "") for r in rows]
        accepts = sum(1 for r in rows if r.get("expected_decision") == "accept")
        rejects = sum(1 for r in rows if r.get("expected_decision") == "reject")
        collisions = sum(1 for k in kinds if k == "collision")
        offers = sum(1 for k in kinds if k == "offer")
        if accepts < min_accept:
            issues.append(CorpusIssue("accept_shortfall", f"{slug}:{accepts}"))
        if rejects < min_reject:
            issues.append(CorpusIssue("reject_shortfall", f"{slug}:{rejects}"))
        if collisions < min_collision:
            issues.append(CorpusIssue("collision_shortfall", f"{slug}:{collisions}"))
        if offers < min_offer:
            issues.append(CorpusIssue("offer_shortfall", f"{slug}:{offers}"))
    return issues


def profile_examples_covered(
    cases: list[dict[str, Any]],
    profiles: list[dict[str, Any]],
) -> list[CorpusIssue]:
    """Every profile accept/reject example must appear as a labeled case."""
    by_seg_text: dict[str, set[tuple[str, str]]] = defaultdict(set)
    for case in cases:
        by_seg_text[str(case["segment"])].add((
            case["text"].strip().lower(),
            str(case["expected_decision"]),
        ))
    issues: list[CorpusIssue] = []
    for profile in profiles:
        slug = profile["segment_slug"]
        for text in profile.get("accept_examples") or []:
            key = (text.strip().lower(), "accept")
            if key not in by_seg_text.get(slug, set()):
                issues.append(CorpusIssue("missing_accept_example", f"{slug}:{text[:60]}"))
        for text in profile.get("reject_examples") or []:
            key = (text.strip().lower(), "reject")
            if key not in by_seg_text.get(slug, set()):
                issues.append(CorpusIssue("missing_reject_example", f"{slug}:{text[:60]}"))
    return issues


def offline_predict(
    text: str,
    *,
    segment: str,
    lead_direction: str = "demand",
) -> tuple[str, str]:
    """Deterministic marker-based predictor for synthetic offline gates.

    Not a substitute for live LLM eval — only checks that golden labels align
    with the same safety markers used by may_bypass_llm / Phase 7.
    """
    body = (text or "").strip()
    if _VACANCY_MARKERS.search(body):
        return "reject", "job_vacancy"
    if _JOB_SEARCH_MARKERS.search(body):
        return "reject", "job_search"
    if _SOCIAL_MARKERS.search(body) or _TEAM_SOCIAL.search(body):
        return "reject", "social_request"
    if _COLLISION_MARKERS.search(body):
        return "reject", "irrelevant"

    direction = (lead_direction or "demand").lower()
    has_sell = bool(_SELL_MARKERS.search(body))
    has_buy = bool(_BUY_MARKERS.search(body))
    if has_sell and direction != "supply":
        return "reject", "provider_offer"
    if has_buy and direction == "supply":
        return "reject", "irrelevant"
    if has_sell and direction == "supply":
        return "accept", "commercial_demand"

    # Clear client asks win over secondary provider-ish tokens («под ключ»).
    if _DEMAND_LEAD.match(body) and not _PROVIDER_MARKERS.search(body[:40]):
        return "accept", "commercial_demand"

    if _PROVIDER_MARKERS.search(body):
        return "reject", "provider_offer"
    if len(body.split()) <= 4 and re.search(r"(?iu)\b(услуг\w+|секци\w+)\b", body):
        return "reject", "provider_offer"
    return "accept", "commercial_demand"


def adapter_roundtrip_ok(case: dict[str, Any]) -> bool:
    """IF LLM returns expected per-segment verdict, delivery mapping is correct."""
    decision = LLMDecision(case["expected_decision"])
    intent = CommercialIntent(case["expected_intent"])
    verdict = SegmentVerdict(
        segment_slug=case["segment"],
        decision=decision,
        intent=intent,
        certainty="high",
        reason_code=str(case.get("case_kind") or "case"),
        reason=str(case.get("notes") or "")[:80],
    )
    legacy = to_legacy_llm_result(
        candidate_segments=[case["segment"]],
        verdicts=[verdict],
        fail_open_segments=[],
        malformed=False,
    )
    validator = LLMValidator()
    if decision is LLMDecision.ACCEPT:
        return (
            legacy.verdict in ("DEMAND", "MIXED")
            and case["segment"] in (legacy.relevant_segments or [])
            and not validator.should_block(legacy)
        )
    return (
        legacy.verdict in ("OFFER", "OTHER")
        and not (legacy.relevant_segments or [])
        and validator.should_block(legacy)
    )


@dataclass
class EvalScores:
    total: int
    tp: int
    fp: int
    fn: int
    tn: int
    precision: float
    recall: float
    per_segment: dict[str, dict[str, float | int]]
    confusion_pairs: list[tuple[str, str, int]]
    fail_open_rate: float


def score_offline_predictions(cases: list[dict[str, Any]]) -> EvalScores:
    tp = fp = fn = tn = 0
    per: dict[str, dict[str, int]] = defaultdict(
        lambda: {"tp": 0, "fp": 0, "fn": 0, "tn": 0, "n": 0}
    )
    confusion: dict[tuple[str, str], int] = defaultdict(int)

    for case in cases:
        gold_d = case["expected_decision"]
        pred_d, pred_i = offline_predict(
            case["text"],
            segment=case["segment"],
            lead_direction=str(case.get("lead_direction") or "demand"),
        )
        gold_i = case["expected_intent"]
        slug = case["segment"]
        per[slug]["n"] += 1
        if pred_d != gold_d or (pred_d == "reject" and pred_i != gold_i and gold_d == "reject"):
            # Intent mismatch on rejects counts as soft confusion, not FN/FP for decision.
            if pred_d != gold_d:
                confusion[(gold_d, pred_d)] += 1
            elif pred_i != gold_i:
                confusion[(f"intent:{gold_i}", f"intent:{pred_i}")] += 1

        if gold_d == "accept" and pred_d == "accept":
            tp += 1
            per[slug]["tp"] += 1
        elif gold_d == "reject" and pred_d == "accept":
            fp += 1
            per[slug]["fp"] += 1
        elif gold_d == "accept" and pred_d == "reject":
            fn += 1
            per[slug]["fn"] += 1
        else:
            tn += 1
            per[slug]["tn"] += 1

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    per_out: dict[str, dict[str, float | int]] = {}
    for slug, s in per.items():
        p = s["tp"] / (s["tp"] + s["fp"]) if (s["tp"] + s["fp"]) else 0.0
        r = s["tp"] / (s["tp"] + s["fn"]) if (s["tp"] + s["fn"]) else 0.0
        per_out[slug] = {**s, "precision": round(p, 4), "recall": round(r, 4)}

    pairs = sorted(
        ((a, b, n) for (a, b), n in confusion.items()),
        key=lambda x: -x[2],
    )[:30]
    return EvalScores(
        total=len(cases),
        tp=tp,
        fp=fp,
        fn=fn,
        tn=tn,
        precision=precision,
        recall=recall,
        per_segment=per_out,
        confusion_pairs=pairs,
        fail_open_rate=0.0,  # offline predictor never fail-opens
    )


def segments_below_precision(
    scores: EvalScores,
    *,
    threshold: float = 0.60,
) -> list[str]:
    bad: list[str] = []
    for slug, stats in scores.per_segment.items():
        # Only enforce when the segment has predicted accepts (precision defined)
        if (stats["tp"] + stats["fp"]) == 0:
            continue
        if float(stats["precision"]) < threshold:
            bad.append(slug)
    return sorted(bad)


def profiles_as_runtime_map(profiles: list[dict[str, Any]]) -> dict[str, SegmentLLMProfile]:
    return {
        p["segment_slug"]: SegmentLLMProfile(
            segment_slug=p["segment_slug"],
            locale=p.get("locale") or "ru",
            target_lead=p.get("target_lead") or "",
            accept_examples=tuple(p.get("accept_examples") or ()),
            reject_examples=tuple(p.get("reject_examples") or ()),
            conflict_slugs=tuple(p.get("conflict_slugs") or ()),
            requires_llm=bool(p.get("requires_llm", True)),
            version=int(p.get("version") or 1),
        )
        for p in profiles
    }


def bypass_stays_off_for_requires_llm(
    cases: list[dict[str, Any]],
    profiles: dict[str, SegmentLLMProfile],
) -> list[str]:
    """With requires_llm=true, no accept case may be bypassed."""
    failures: list[str] = []
    for case in cases:
        if case["expected_decision"] != "accept":
            continue
        slug = case["segment"]
        ok = may_bypass_llm(
            text=case["text"],
            candidate_segments=(slug,),
            profiles=profiles,
            lead_directions={slug: str(case.get("lead_direction") or "demand")},
        )
        if ok:
            failures.append(case["id"])
    return failures
