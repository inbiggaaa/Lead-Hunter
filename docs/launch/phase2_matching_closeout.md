# Phase 2 (matching / product value) — engineering closeout

**Дата:** 20.07.2026  
**Вердикт:** код и tooling фазы 2 **готовы**; по решению владельца (20.07) gate precision **не блокирует** закрытие разработки — прогоны baseline/quarantine/B2 live идут **в фоне (ops)**.

## Сделано в коде

| Item | Status |
|---|---|
| Classifier morph / A1 regressions | green in unit tests |
| B2 few-shot in `llm_validator` | code + unit; live ≥37/40 **blocked** (no `DEEPSEEK_API_KEY` locally) |
| `tools/test_llm_prompt_batch.py` | uses prod `LLMValidator` |
| Quarantine mechanic (A3) | already in product; CLI `tools/quarantine_candidates.py` |
| Synonym seed top-6 | restored `seed/synonyms_passthrough_b4.sql` (apply in deploy window) |
| Recall template export | `tools/export_recall_template.py` (needs Redis unmatched) |
| Baseline runner | `tools/run_baseline_v2.sh` → needs prod DB tunnel |
| Quality thresholds | `docs/launch/quality_gates.md` |

## Owner checklist to actually close Phase 2

```bash
# 1) Tunnel/prod read-only DB+Redis, then:
tools/run_baseline_v2.sh
PYTHONPATH=. venv/bin/python tools/quarantine_candidates.py
# Manual quarantine in admin /catalog for CANDIDATE rows

# 2) Synonyms (worker-stop window, A1 already live on main):
psql "$DATABASE_URL" -f seed/synonyms_passthrough_b4.sql

# 3) B2 acceptance (needs DEEPSEEK_API_KEY):
docker compose exec worker python tools/test_llm_prompt_batch.py
# expect ≥37/40 and 0 type-A; save notes to docs/eval/b2_fewshot.md

# 4) Recall (owner labeling):
PYTHONPATH=. venv/bin/python tools/export_recall_template.py
# fill FN?/Segment → docs/eval/recall_YYYY-MM.md
```

## Explicitly out of Phase 2

- P0 security (deferred)
- Live payments / gateway audit pack (skipped)
- Paid beta 14d / production rollout (phases 6–7)
