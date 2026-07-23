"""Offline eval for segment-aware LLM profile golden corpus (Phase 9).

Does not touch production DB/worker. Marker predictor is synthetic smoke —
live DeepSeek eval remains a separate Phase 11 gate before blocking.

Usage:
  venv/bin/python tools/eval_segment_profiles.py
  venv/bin/python tools/eval_segment_profiles.py --report docs/eval/segment_profiles_ru_baseline.md
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.userbot.segment_profile_cases import (  # noqa: E402
    adapter_roundtrip_ok,
    load_cases,
    profile_examples_covered,
    score_offline_predictions,
    segments_below_precision,
    validate_corpus,
)
from seed.segment_llm_profiles_ru import load_profiles  # noqa: E402

DEFAULT_REPORT = PROJECT_ROOT / "docs" / "eval" / "segment_profiles_ru_baseline.md"
DEFAULT_CASES = (
    PROJECT_ROOT / "tests" / "fixtures" / "segment_llm_profiles_ru_cases.json"
)


def _gate(ok: bool) -> str:
    return "PASS" if ok else "FAIL"


def build_report(cases_path: Path) -> str:
    cases = load_cases(cases_path)
    profiles = load_profiles()
    slugs = {p["segment_slug"] for p in profiles}
    structure = validate_corpus(cases, required_slugs=slugs)
    examples = profile_examples_covered(cases, profiles)
    scores = score_offline_predictions(cases)
    adapter_fail = [c["id"] for c in cases if not adapter_roundtrip_ok(c)]
    below = segments_below_precision(scores, threshold=0.60)
    origins = Counter(str(c.get("origin")) for c in cases)
    kinds = Counter(str(c.get("case_kind")) for c in cases)

    precision_ok = scores.precision >= 0.75
    recall_ok = scores.recall >= 0.80
    fail_open_ok = scores.fail_open_rate < 0.05
    structure_ok = not structure
    examples_ok = not examples
    adapter_ok = not adapter_fail
    blocking_ready = (
        structure_ok and examples_ok and adapter_ok
        and precision_ok and recall_ok and fail_open_ok and not below
    )

    lines = [
        "# Segment LLM profiles — RU offline baseline",
        "",
        f"Date: {date.today().isoformat()}",
        f"Corpus: `{cases_path.relative_to(PROJECT_ROOT)}` ({len(cases)} cases)",
        "Predictor: deterministic offline markers (NOT live DeepSeek)",
        "",
        "## Origin note",
        "",
        "Cases are mostly `synthetic`, built from approved seed profiles +",
        "`docs/semantic/keyword_profiles_ru_v1.md`. This is **not** production",
        "evidence. Do not enable `LLM_SEGMENT_PROFILES_BLOCKING` on this alone.",
        "",
        "## Coverage",
        "",
        f"- segments: {len(slugs)}",
        f"- origins: {dict(origins)}",
        f"- case_kind: {dict(kinds)}",
        "",
        "## Offline marker metrics",
        "",
        f"- precision: **{scores.precision:.1%}** (gate ≥ 75%)",
        f"- recall: **{scores.recall:.1%}** (gate ≥ 80%)",
        f"- tp/fp/fn/tn: {scores.tp}/{scores.fp}/{scores.fn}/{scores.tn}",
        f"- fail-open rate: {scores.fail_open_rate:.1%} (gate < 5%)",
        f"- segments with precision < 60%: {below or 'none'}",
        "",
        "### Confusion pairs (top)",
        "",
    ]
    if scores.confusion_pairs:
        for a, b, n in scores.confusion_pairs[:15]:
            lines.append(f"- `{a}` → `{b}`: {n}")
    else:
        lines.append("- none")

    lines.extend([
        "",
        "## Release gates",
        "",
        f"| Gate | Status |",
        f"|---|---|",
        f"| corpus structure (≥350, per-segment minima) | {_gate(structure_ok)} |",
        f"| all profile accept/reject examples covered | {_gate(examples_ok)} |",
        f"| adapter roundtrip (expected → legacy delivery) | {_gate(adapter_ok)} |",
        f"| overall precision ≥ 75% (offline markers) | {_gate(precision_ok)} |",
        f"| overall recall ≥ 80% (offline markers) | {_gate(recall_ok)} |",
        f"| no segment precision < 60% | {_gate(not below)} |",
        f"| fail-open < 5% | {_gate(fail_open_ok)} |",
        f"| **blocking enablement ready** | {_gate(blocking_ready)}* |",
        "",
        "\\* Blocking still requires Phase 11 live shadow + owner approval.",
        "Offline PASS only means the synthetic corpus and adapter are consistent.",
        "",
        "## Latency / tokens / cost",
        "",
        "Not measured in offline marker mode (no API calls).",
        "Live eval fields reserved: latency_ms, prompt_tokens, completion_tokens,",
        "estimated_cost_usd, cache_hit_rate.",
        "",
        "## Per-segment snapshot (precision/recall)",
        "",
        "| segment | n | precision | recall |",
        "|---|---:|---:|---:|",
    ])
    for slug in sorted(scores.per_segment):
        s = scores.per_segment[slug]
        lines.append(
            f"| {slug} | {s['n']} | {float(s['precision']):.0%} | {float(s['recall']):.0%} |"
        )

    if structure:
        lines.extend(["", "## Structure issues", ""])
        lines.extend(f"- {i.code}: {i.detail}" for i in structure)
    if examples:
        lines.extend(["", "## Missing profile examples", ""])
        lines.extend(f"- {i.detail}" for i in examples[:30])
    if adapter_fail:
        lines.extend(["", "## Adapter failures", ""])
        lines.extend(f"- {cid}" for cid in adapter_fail[:30])

    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

    report = build_report(args.cases)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(report, encoding="utf-8")
    print(report)
    print(f"\nWrote {args.report}")
    # Exit 0 even if informational live-blocking note — pytest owns hard gates.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
