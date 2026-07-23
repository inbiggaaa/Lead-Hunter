# Segment LLM profiles — RU offline baseline

Date: 2026-07-24
Corpus: `tests/fixtures/segment_llm_profiles_ru_cases.json` (552 cases)
Predictor: deterministic offline markers (NOT live DeepSeek)

## Origin note

Cases are mostly `synthetic`, built from approved seed profiles +
`docs/semantic/keyword_profiles_ru_v1.md`. This is **not** production
evidence. Do not enable `LLM_SEGMENT_PROFILES_BLOCKING` on this alone.

## Coverage

- segments: 71
- origins: {'synthetic': 552}
- case_kind: {'accept': 142, 'collision': 71, 'job_search': 63, 'offer': 71, 'reject': 142, 'vacancy': 63}

## Offline marker metrics

- precision: **92.2%** (gate ≥ 75%)
- recall: **100.0%** (gate ≥ 80%)
- tp/fp/fn/tn: 142/12/0/398
- fail-open rate: 0.0% (gate < 5%)
- segments with precision < 60%: none

### Confusion pairs (top)

- `reject` → `accept`: 12
- `intent:provider_offer` → `intent:social_request`: 5
- `intent:provider_offer` → `intent:irrelevant`: 4
- `intent:provider_offer` → `intent:job_search`: 3
- `intent:provider_offer` → `intent:job_vacancy`: 1

## Release gates

| Gate | Status |
|---|---|
| corpus structure (≥350, per-segment minima) | PASS |
| all profile accept/reject examples covered | PASS |
| adapter roundtrip (expected → legacy delivery) | PASS |
| overall precision ≥ 75% (offline markers) | PASS |
| overall recall ≥ 80% (offline markers) | PASS |
| no segment precision < 60% | PASS |
| fail-open < 5% | PASS |
| **blocking enablement ready** | PASS* |

\* Blocking still requires Phase 11 live shadow + owner approval.
Offline PASS only means the synthetic corpus and adapter are consistent.

## Latency / tokens / cost

Not measured in offline marker mode (no API calls).
Live eval fields reserved: latency_ms, prompt_tokens, completion_tokens,
estimated_cost_usd, cache_hit_rate.

## Per-segment snapshot (precision/recall)

| segment | n | precision | recall |
|---|---:|---:|---:|
| accountant | 8 | 67% | 100% |
| barber | 8 | 100% | 100% |
| basketball | 8 | 100% | 100% |
| brows | 8 | 100% | 100% |
| car-purchase | 6 | 100% | 100% |
| car-rental | 6 | 100% | 100% |
| car-sale | 6 | 100% | 100% |
| cargo | 8 | 100% | 100% |
| catering | 8 | 100% | 100% |
| cleaning | 8 | 100% | 100% |
| company-registration | 8 | 67% | 100% |
| cosmetology | 8 | 100% | 100% |
| courier | 8 | 100% | 100% |
| currency-exchange | 8 | 100% | 100% |
| delivery | 8 | 100% | 100% |
| dentist | 8 | 100% | 100% |
| dermatologist | 8 | 100% | 100% |
| design | 8 | 100% | 100% |
| driver | 8 | 100% | 100% |
| driving-instructor | 8 | 100% | 100% |
| electrician | 8 | 67% | 100% |
| epilation | 8 | 100% | 100% |
| event-management | 8 | 100% | 100% |
| excursions | 8 | 67% | 100% |
| fitness | 8 | 100% | 100% |
| football | 8 | 100% | 100% |
| graphics | 8 | 100% | 100% |
| guide | 8 | 100% | 100% |
| gynecologist | 8 | 100% | 100% |
| hair-color | 8 | 100% | 100% |
| hairdresser | 8 | 67% | 100% |
| housing-buy | 6 | 100% | 100% |
| housing-rent | 6 | 100% | 100% |
| language-courses | 8 | 100% | 100% |
| lashes | 8 | 100% | 100% |
| lawyer | 8 | 100% | 100% |
| makeup | 8 | 100% | 100% |
| manicure | 8 | 100% | 100% |
| martial-arts | 8 | 100% | 100% |
| massage | 8 | 100% | 100% |
| moto-instructor | 8 | 100% | 100% |
| moto-purchase | 6 | 100% | 100% |
| moto-sale | 6 | 100% | 100% |
| music | 8 | 100% | 100% |
| nanny | 8 | 67% | 100% |
| neurologist | 8 | 100% | 100% |
| notary | 8 | 100% | 100% |
| nutritionist | 8 | 100% | 100% |
| orthopedist | 8 | 100% | 100% |
| padel | 8 | 100% | 100% |
| pastry-chef | 8 | 100% | 100% |
| pediatrician | 8 | 100% | 100% |
| pets | 8 | 100% | 100% |
| photo | 8 | 67% | 100% |
| pilates | 8 | 100% | 100% |
| plumber | 8 | 67% | 100% |
| private-chef | 8 | 67% | 100% |
| psychologist | 8 | 100% | 100% |
| repair | 8 | 100% | 100% |
| scooter-rental | 6 | 100% | 100% |
| surgeon | 8 | 100% | 100% |
| tattoo | 8 | 67% | 100% |
| taxi-transfer | 8 | 100% | 100% |
| tennis | 8 | 100% | 100% |
| therapist | 8 | 100% | 100% |
| translator | 8 | 100% | 100% |
| travel-agent | 8 | 100% | 100% |
| tutor | 8 | 100% | 100% |
| video | 8 | 67% | 100% |
| visa-support | 8 | 67% | 100% |
| yoga | 8 | 100% | 100% |
