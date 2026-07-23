"""Build offline golden cases for segment-aware LLM profiles (Phase 9).

Build-time only: parses the human-approved Markdown spec + seed profiles.
Does NOT run at worker/runtime and does NOT write to production DB.

Usage:
  venv/bin/python tools/build_segment_profile_cases.py
  venv/bin/python tools/build_segment_profile_cases.py --out tests/fixtures/segment_llm_profiles_ru_cases.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from seed.segment_llm_profiles_ru import load_profiles  # noqa: E402

SPEC_PATH = PROJECT_ROOT / "docs" / "semantic" / "keyword_profiles_ru_v1.md"
DEFAULT_OUT = PROJECT_ROOT / "tests" / "fixtures" / "segment_llm_profiles_ru_cases.json"

SUPPLY_SLUGS = frozenset({"moto-purchase", "car-purchase"})
BUY_SLUGS = frozenset({"moto-sale", "car-sale", "housing-buy", "housing-rent"})

# Segments where vacancy/job-search noise is common enough to require a case.
VACANCY_APPLICABLE = frozenset({
    "delivery", "courier", "cargo", "massage", "manicure", "cosmetology",
    "hairdresser", "hair-color", "tattoo", "lashes", "brows", "makeup",
    "barber", "epilation", "therapist", "dentist", "psychologist",
    "dermatologist", "gynecologist", "pediatrician", "surgeon",
    "orthopedist", "neurologist", "nutritionist", "translator",
    "language-courses", "driving-instructor", "moto-instructor", "tutor",
    "cleaning", "repair", "plumber", "electrician", "nanny", "pets",
    "guide", "excursions", "visa-support", "travel-agent", "taxi-transfer",
    "driver", "catering", "private-chef", "pastry-chef", "event-management",
    "music", "fitness", "yoga", "martial-arts", "pilates", "padel",
    "tennis", "basketball", "football", "photo", "video", "design",
    "graphics", "notary", "company-registration", "lawyer", "accountant",
    "currency-exchange",
})

_HEADER_RE = re.compile(
    r"^## .+?\(`([a-z0-9-]+)`(?:,\s*`lead_direction=(?:supply|buy|demand)`)?\)\s*$",
    re.M,
)


def _split_phrases(raw: str) -> list[str]:
    parts = re.split(r"[;\n]", raw)
    out: list[str] = []
    for part in parts:
        text = part.strip().strip("`").strip().rstrip(".")
        if text:
            out.append(text[0].upper() + text[1:] if text[0].islower() else text)
    return out


def _grab_field(block: str, label: str) -> list[str]:
    match = re.search(
        rf"\*\*{re.escape(label)}:\*\*\s*(.+?)(?:\n\n|\n\*\*[A-Za-zА-Яа-я])",
        block,
        re.S,
    )
    if not match:
        return []
    return _split_phrases(match.group(1))


def parse_spec_blocks(spec_text: str) -> dict[str, dict]:
    """Extract demand/stop/LLM examples per slug from the Markdown spec."""
    blocks = re.split(r"\n(?=## )", spec_text)
    by_slug: dict[str, dict] = {}
    for block in blocks:
        headers = _HEADER_RE.findall(block)
        if not headers:
            continue
        demand = _grab_field(block, "demand")
        stop = _grab_field(block, "stop")
        acc = re.search(r"\*\*LLM accept:\*\*\s*`([^`]+)`", block)
        rej = re.search(r"\*\*LLM reject:\*\*\s*`([^`]+)`", block)
        conflicts = _grab_field(block, "conflicts")
        for slug in headers:
            by_slug[slug] = {
                "demand": demand,
                "stop": stop,
                "llm_accept": acc.group(1).strip() if acc else "",
                "llm_reject": rej.group(1).strip() if rej else "",
                "conflicts": [c.strip("`") for c in conflicts],
            }
    return by_slug


def _lead_direction(slug: str) -> str:
    if slug in SUPPLY_SLUGS:
        return "supply"
    if slug in BUY_SLUGS:
        return "buy"
    return "demand"


def _case(
    *,
    slug: str,
    kind: str,
    seq: int,
    text: str,
    decision: str,
    intent: str,
    origin: str,
    notes: str,
) -> dict:
    return {
        "id": f"{slug}-{kind}-{seq:03d}",
        "segment": slug,
        "text": text,
        "expected_intent": intent,
        "expected_decision": decision,
        "origin": origin,
        "notes": notes,
        "case_kind": kind,
        "lead_direction": _lead_direction(slug),
    }


def build_cases_for_segment(profile: dict, spec: dict | None) -> list[dict]:
    slug = profile["segment_slug"]
    spec = spec or {}
    demand = list(spec.get("demand") or [])
    stop = list(spec.get("stop") or [])
    conflicts = list(profile.get("conflict_slugs") or spec.get("conflicts") or [])
    accept_examples = list(profile.get("accept_examples") or [])
    reject_examples = list(profile.get("reject_examples") or [])

    cases: list[dict] = []

    # Accept ≥2
    accept_texts: list[tuple[str, str, str]] = []
    if accept_examples:
        accept_texts.append((accept_examples[0], "synthetic", "profile accept_example"))
    elif spec.get("llm_accept"):
        accept_texts.append((spec["llm_accept"], "synthetic", "spec LLM accept"))
    for phrase in demand:
        if len(accept_texts) >= 2:
            break
        if all(phrase.lower() != t[0].lower() for t in accept_texts):
            accept_texts.append((phrase, "synthetic", "spec demand phrase"))
    while len(accept_texts) < 2:
        n = len(accept_texts) + 1
        accept_texts.append((
            f"Нужна услуга по направлению {slug}, подскажите контакты проверенного исполнителя ({n}).",
            "synthetic",
            "fallback accept template",
        ))
    for i, (text, origin, notes) in enumerate(accept_texts[:2], start=1):
        cases.append(_case(
            slug=slug, kind="accept", seq=i, text=text,
            decision="accept", intent="commercial_demand",
            origin=origin, notes=notes,
        ))

    # Reject ≥2 (provider / stop)
    reject_texts: list[tuple[str, str, str, str]] = []
    if reject_examples:
        reject_texts.append((
            reject_examples[0], "synthetic", "profile reject_example", "provider_offer",
        ))
    elif spec.get("llm_reject"):
        reject_texts.append((
            spec["llm_reject"], "synthetic", "spec LLM reject", "provider_offer",
        ))
    for phrase in stop:
        if len(reject_texts) >= 2:
            break
        if all(phrase.lower() != t[0].lower() for t in reject_texts):
            reject_texts.append((phrase, "synthetic", "spec stop phrase", "provider_offer"))
    while len(reject_texts) < 2:
        n = len(reject_texts) + 1
        reject_texts.append((
            f"Предлагаю услуги {slug}, открыта запись, прайс в личку ({n}).",
            "synthetic",
            "fallback provider template",
            "provider_offer",
        ))
    for i, (text, origin, notes, intent) in enumerate(reject_texts[:2], start=1):
        cases.append(_case(
            slug=slug, kind="reject", seq=i, text=text,
            decision="reject", intent=intent,
            origin=origin, notes=notes,
        ))

    # Collision ≥1
    conflict = conflicts[0] if conflicts else "other"
    cases.append(_case(
        slug=slug,
        kind="collision",
        seq=1,
        text=(
            f"Ищу помощь по соседней теме {conflict}, к {slug} это не относится — "
            f"нужен именно {conflict}."
        ),
        decision="reject",
        intent="irrelevant",
        origin="synthetic",
        notes=f"collision vs {conflict}",
    ))

    # Offer ≥1
    cases.append(_case(
        slug=slug,
        kind="offer",
        seq=1,
        text=f"Предлагаю услуги в нише {slug}, оказываю услуги, пишите в личку.",
        decision="reject",
        intent="provider_offer",
        origin="synthetic",
        notes="explicit provider offer",
    ))

    # Vacancy / job-search when applicable
    if slug in VACANCY_APPLICABLE:
        cases.append(_case(
            slug=slug,
            kind="vacancy",
            seq=1,
            text=(
                f"Вакансия: требуется сотрудник в направление {slug}, "
                f"зарплата оклад, график 5/2, в штат."
            ),
            decision="reject",
            intent="job_vacancy",
            origin="synthetic",
            notes="hiring noise",
        ))
        cases.append(_case(
            slug=slug,
            kind="job_search",
            seq=1,
            text=f"Ищу работу в сфере {slug}, возьму заказы, есть опыт.",
            decision="reject",
            intent="job_search",
            origin="synthetic",
            notes="job-seeker noise",
        ))

    return cases


def build_all_cases(spec_path: Path = SPEC_PATH) -> list[dict]:
    profiles = load_profiles()
    spec_map = parse_spec_blocks(spec_path.read_text(encoding="utf-8"))
    cases: list[dict] = []
    for profile in profiles:
        cases.extend(build_cases_for_segment(profile, spec_map.get(profile["segment_slug"])))
    cases.sort(key=lambda c: c["id"])
    return cases


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--spec", type=Path, default=SPEC_PATH)
    args = parser.parse_args()

    cases = build_all_cases(args.spec)
    payload = {
        "locale": "ru",
        "version": 1,
        "source_profiles": "seed/data/segment_llm_profiles_ru.json",
        "source_spec": str(args.spec.relative_to(PROJECT_ROOT)),
        "case_count": len(cases),
        "cases": cases,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(cases)} cases → {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
