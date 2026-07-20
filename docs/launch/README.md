# Launch docs index

Engineering readiness for controlled MVP. **Prod deploy is owner-gated.**

| Doc | Purpose | Status |
|---|---|---|
| [quality_gates.md](quality_gates.md) | Matching thresholds + measure commands | Active |
| [paid_beta_checklist.md](paid_beta_checklist.md) | 14-day beta entry/exit | Payments skipped |
| [payment_e2e_checklist.md](payment_e2e_checklist.md) | Stars/CryptoBot live E2E | **Skipped** (owner) |
| [production_launch_checklist.md](production_launch_checklist.md) | Public rollout | After beta |
| [github_deploy_setup.md](github_deploy_setup.md) | `DEPLOY_*` + Environment | Owner |
| [restore_drill.md](restore_drill.md) | Backup restore rehearsal | Owner |
| [dlq_replay.md](dlq_replay.md) | Dead-letter replay | Ops |

## Explicitly deferred (20.07.2026)

- P0 admin bind / WS auth / ban-filter / hardened deploy
- Live payment E2E and payment-gateway audit document pack
- Prod baseline eval / B3 recall labeling / B2 live LLM batch ≥37/40

## Ready in code (not necessarily deployed)

- Classifier morph + B2 few-shot prompt
- U9.4 lifecycle marketing opt-out (`u94_lifecycle_optout` — apply in worker-stop window)
- Sentry on bot/worker/admin + lead scrubber
- Immutable prod compose + `docker-compose.dev.yml`
- Smoke harness, referral monthly cap, tariff copy without regex promise
- Phase 2 tooling: `quarantine_candidates.py`, `export_recall_template.py`, `seed/synonyms_passthrough_b4.sql`
- See [phase2_matching_closeout.md](phase2_matching_closeout.md)
