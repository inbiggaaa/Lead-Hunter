"""Phase 9: offline golden corpus for segment LLM profiles."""

from __future__ import annotations

from pathlib import Path

from app.userbot.segment_profile_cases import (
    adapter_roundtrip_ok,
    bypass_stays_off_for_requires_llm,
    load_cases,
    profile_examples_covered,
    profiles_as_runtime_map,
    score_offline_predictions,
    segments_below_precision,
    validate_corpus,
)
from seed.segment_llm_profiles_ru import load_profiles

FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "tests"
    / "fixtures"
    / "segment_llm_profiles_ru_cases.json"
)


def test_corpus_meets_coverage_minimums():
    cases = load_cases(FIXTURE)
    profiles = load_profiles()
    slugs = {p["segment_slug"] for p in profiles}
    issues = validate_corpus(cases, required_slugs=slugs)
    assert not issues, issues
    assert len(cases) >= 350


def test_profile_accept_reject_examples_are_in_corpus():
    cases = load_cases(FIXTURE)
    profiles = load_profiles()
    issues = profile_examples_covered(cases, profiles)
    assert not issues, issues


def test_adapter_roundtrip_for_every_case():
    cases = load_cases(FIXTURE)
    failed = [c["id"] for c in cases if not adapter_roundtrip_ok(c)]
    assert not failed, failed[:20]


def test_requires_llm_profiles_do_not_bypass_accept_cases():
    cases = load_cases(FIXTURE)
    profiles = profiles_as_runtime_map(load_profiles())
    failed = bypass_stays_off_for_requires_llm(cases, profiles)
    assert not failed, failed[:20]


def test_offline_marker_gates_precision_recall():
    """Synthetic marker baseline — not live LLM proof; still must clear gates."""
    scores = score_offline_predictions(load_cases(FIXTURE))
    assert scores.precision >= 0.75, scores.precision
    assert scores.recall >= 0.80, scores.recall
    assert scores.fail_open_rate < 0.05
    assert not segments_below_precision(scores, threshold=0.60)
