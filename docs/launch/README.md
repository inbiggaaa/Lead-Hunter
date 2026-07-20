# Launch docs index

**Development closed 20.07.2026** — see [development_closeout.md](development_closeout.md).  
Prod: `main` @ `2c6a29a`, alembic `u94_lifecycle_optout`. Matching quality = **background ops**.

| Doc | Purpose | Status |
|---|---|---|
| [development_closeout.md](development_closeout.md) | Engineering freeze / handoff | **Done** |
| [quality_gates.md](quality_gates.md) | Matching thresholds + measure commands | Ops / background |
| [phase2_matching_closeout.md](phase2_matching_closeout.md) | Baseline / quarantine / B2 live | Ops / background |
| [paid_beta_checklist.md](paid_beta_checklist.md) | 14-day beta entry/exit | Owner when ready |
| [payment_e2e_checklist.md](payment_e2e_checklist.md) | Stars/CryptoBot live E2E | **Skipped** |
| [production_launch_checklist.md](production_launch_checklist.md) | Public rollout | After beta |
| [github_deploy_setup.md](github_deploy_setup.md) | `DEPLOY_*` + Environment | Owner |
| [restore_drill.md](restore_drill.md) | Backup restore rehearsal | Owner |
| [dlq_replay.md](dlq_replay.md) | Dead-letter replay | Ops |

## Deferred (not engineering blockers)

- P0 admin bind / WS auth / ban-filter / hardened deploy
- Live payment E2E and payment-gateway audit pack
