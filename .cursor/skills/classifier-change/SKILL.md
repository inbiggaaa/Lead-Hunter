---
name: classifier-change
description: Change LeadHunter message classifier, LLM validator, segment keywords, or matching rules safely with eval. Use when editing classifier.py, llm_validator.py, segment_keywords, reality filter, or matching quality.
---

# Classifier Change

## Before edits
1. Read `OPERATIONS.md` §2 if touching poller-adjacent code paths.
2. Read `CLAUDE.md` §5а (three-pass NLP + LLM + reality filter).
3. Do not hardcode segment directions — use DB `segments.lead_direction` (demand/buy/supply).

## Invariants
- Demand match: word-boundary + lemmas; multi-word uses `KEYWORD_MATCH_WINDOW`.
- Stop phrases override unless strong demand signal; bare `?` is weak.
- Reality filter: domain synonym word-boundary before LLM.
- Personal keywords bypass segments/LLM (Variant B) — do not break this.
- LLM fail-open: API error → lead passes; log to `llm_decisions`.

## Workflow

```
Task:
- [ ] Minimal rule/prompt change
- [ ] Unit tests for the scenario
- [ ] Eval: venv/bin/python tools/eval_matching.py
- [ ] Compare precision/noise vs previous docs/eval report
- [ ] Owner gate if precision worsens
- [ ] Deploy via safe-deploy (worker restart)
- [ ] Monitor FloodWait 2 min (if poller touched)
```

## After
- Note eval delta in SESSION_LOG.
- Do not quarantine/unquarantine segments without owner decision.
