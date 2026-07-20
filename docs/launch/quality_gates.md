# Quality gates — matching (MVP → production)

## Thresholds

| Metric | Closed paid beta (MVP) | Public production |
|---|---|---|
| Precision (current catalog feedback) | ≥ 35% | ≥ 50% |
| Fail-open LLM share / hour | < 5% steady; alert >20% | same |
| Deliveries older than 30 min (hot niches) | ≤ 10% | ≤ 10% |
| Recall (100 unmatched sample) | measured + no regression | measured on fresh sample |
| Rule/prompt change | `liked_lost = 0` on eval corpus | same |

## How to measure

```bash
# Precision / segment report (read-only prod DB via tunnel or local dump)
venv/bin/python tools/eval_matching.py > docs/eval/report_$(date +%F).md

# Fail-open (Redis)
docker compose exec redis redis-cli --scan --pattern 'stats:llm:*'

# Latency buckets (Redis)
docker compose exec redis redis-cli --scan --pattern 'stats:latency:*'
```

## Closed-loop actions before beta

1. Quarantine segments with ≥5 votes and precision <20% in admin `/catalog`.
2. Apply synonym seed for pass-through segments (`seed/synonyms_passthrough_b4.sql`) only in a deploy window with A1 already live.
3. Owner labels `docs/eval/recall_template_*.md` (100 unmatched) → write `docs/eval/recall_YYYY-MM.md`.
4. Optional B2 few-shot: code in `llm_validator.FEW_SHOT_EXAMPLES`; close with
   `tools/test_llm_prompt_batch.py` ≥37/40 and eval-diff (`docs/eval/b2_fewshot.md`).

## Security P0 (postponed)

Admin localhost bind, unauthenticated WS reject, ban/suspend delivery filter,
and hardened `deploy.sh` worker guards — deferred by owner (20.07.2026).
Do not treat them as closed for public launch.

## CI notes

- `pip-audit` and `npm audit` are informational (`|| true` / continue-on-error).
- Soft coverage floor target: raise gradually toward 50% (track locally with
  `coverage run -m pytest` when changing hot paths).

## Stop-the-line

- Precision below MVP threshold for 48h after launch → pause paid acquisition, quarantine noisy segments.
- Fail-open >50%/hour → treat as CRITICAL; consider temporary shadow mode only with owner approval.
- Any classifier/prompt change without eval-diff → revert.
