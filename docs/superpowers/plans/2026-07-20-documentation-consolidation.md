# LeadHunter Documentation Consolidation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace stale phase-oriented Markdown with a compact product-and-engineering documentation set verified against the current `main` codebase.

**Architecture:** `README.md` becomes the entry point; each supporting document owns one subject and links instead of duplicating details. Runtime code, configuration, migrations, tests, CI, and operational scripts are the evidence for every current-state claim; Git history replaces checked-in session logs and completed plans.

**Tech Stack:** Python 3.11, aiogram 3, Telethon, SQLAlchemy/Alembic, PostgreSQL 16, Redis 7, FastAPI, React 19, TypeScript 6, Vite 8, Docker Compose, GitHub Actions, Markdown.

## Global Constraints

- Describe present behavior only when confirmed by runtime code, configuration, migrations, tests, CI, or scripts.
- Mark optional, disabled-by-default, manual, placeholder, and untested capabilities explicitly.
- Preserve RU/EN parity in user-flow descriptions.
- Do not claim that every lead contains contact details or a working chat link.
- Do not copy secrets, production values, or personal data into documentation.
- Do not change application behavior, infrastructure, pricing, or production state.
- Keep `.cursor/skills/`, `.pi/skills/`, and `.pi/agents/` only when their instructions still match current files and commands.
- Removed historical files remain recoverable through Git history.

---

### Task 1: Capture the Current Runtime Contract

**Files:**
- Read: `app/config.py`
- Read: `app/main.py`
- Read: `app/worker/tasks.py`
- Read: `app/db/models.py`
- Read: `app/bot/handlers/*.py`
- Read: `app/locales/ru.py`
- Read: `app/locales/en.py`
- Read: `app/userbot/*.py`
- Read: `app/worker/*.py`
- Read: `app/payments/*.py`
- Read: `app/admin/**/*.py`
- Read: `admin-panel/src/**/*.{ts,tsx}`
- Read: `docker-compose.yml`
- Read: `.env.example`
- Read: `.github/workflows/*.yml`
- Read: `scripts/*.sh`
- Read: `backup.sh`
- Read: `restore.sh`
- Read: `tests/*.py`

**Interfaces:**
- Consumes: current `main` source tree at or after commit `343ef7f`.
- Produces: a verified fact matrix used by Tasks 2–6; no repository file is created for this temporary working note.

- [ ] **Step 1: Record repository and document baseline**

Run:

```bash
git status --short --branch
git rev-parse HEAD
git ls-files '*.md' '*.mdx' | wc -l
```

Expected: clean branch apart from the plan commit workflow, a concrete HEAD SHA,
and the tracked Markdown count before consolidation.

- [ ] **Step 2: Record the deployable service contract**

Run:

```bash
docker compose config --services
rg -n '^class Settings|^[[:space:]]+[a-z][a-z0-9_]+:' app/config.py
rg -n '^  [a-z][a-z0-9_-]+:' docker-compose.yml
```

Expected services: `db`, `redis`, `bot`, `worker`, `admin`. Record settings that
are consumed by Python separately from script-only environment variables.

- [ ] **Step 3: Record product and user-flow behavior**

Inspect handlers, locale keys, plan-limit helpers, notification rendering,
lifecycle workers, payment providers, and the following contract tests:

```bash
pytest -q tests/test_tariffs_v2_matrix.py \
  tests/test_userflow_u10_snapshots.py \
  tests/test_userflow_lifecycle.py \
  tests/test_payment_idempotency.py \
  tests/test_reliable_queue.py
```

Expected: tests pass. If the environment lacks PostgreSQL or Redis, record the
exact infrastructure error and continue with static evidence plus CI definitions;
do not rewrite a failure as a passing result.

- [ ] **Step 4: Record admin and release gates**

Run:

```bash
rg -n '@router\.(get|post|put|patch|delete)' app/admin/api
rg -n 'path:|element:|createBrowserRouter|Routes|Route' admin-panel/src
sed -n '1,260p' .github/workflows/ci.yml
sed -n '1,220p' .github/workflows/deploy.yml
```

Expected: an exact list of admin surfaces and the five CI jobs: pytest, Alembic,
admin panel, Docker build, and secret scan; deploy runs after successful CI on
`main` or manual dispatch and uses the protected `production` environment.

### Task 2: Create the Documentation Entry Point and System Overview

**Files:**
- Create: `README.md`
- Modify: `docs/PRODUCT_OVERVIEW.md`
- Create: `docs/ARCHITECTURE.md`

**Interfaces:**
- Consumes: verified fact matrix from Task 1.
- Produces: canonical product summary and architecture links used by all later documents.

- [ ] **Step 1: Write `README.md`**

Include these exact sections: product summary; implemented capabilities;
architecture diagram in compact text form; repository map; prerequisites; local
Docker quick start; migration and seed note; validation commands; documentation
index; security warning. State that the product monitors configured Telegram
sources, classifies potential demand, and delivers matching notifications; do not
promise lead volume or universal contact availability.

- [ ] **Step 2: Rewrite `docs/PRODUCT_OVERVIEW.md`**

Cover the current audience, search setup, catalog and personal-keyword paths,
plans `free/start/pro/business/trial`, geography and plan limits from current
helpers, RU/EN localization, instant/digest delivery, statistics/CSV access,
referrals, Telegram Stars, optional CryptoBot, lifecycle reminders, and explicit
limitations. Link implementation detail to `ARCHITECTURE.md` instead of duplicating it.

- [ ] **Step 3: Write `docs/ARCHITECTURE.md`**

Document the five Compose services, bot router order, worker tasks, Telethon
account pool and rate limiting, classifier plus optional DeepSeek validation,
PostgreSQL/Alembic ownership, Redis FSM/cache/queue roles, reliable notification
delivery, payments, lifecycle, admin API/SPA, backup boundaries, and the CI/deploy
flow. Mark legacy `app/userbot/discovery.py` and `seed/import_channels.py` paths as
non-runtime utilities when mentioned; do not present them as active worker paths.

- [ ] **Step 4: Verify entry-point facts and links**

Run:

```bash
rg -n 'future|будущ|Фаза|TODO|TBD|кажд.*контакт|every lead' README.md docs/PRODUCT_OVERVIEW.md docs/ARCHITECTURE.md
git diff --check -- README.md docs/PRODUCT_OVERVIEW.md docs/ARCHITECTURE.md
```

Expected: no phase-status or placeholder language; any occurrence found by the
first command is either removed or explicitly labeled as non-current context.

- [ ] **Step 5: Commit the overview set**

```bash
git add README.md docs/PRODUCT_OVERVIEW.md docs/ARCHITECTURE.md
git commit -m "docs: document current product and architecture"
```

### Task 3: Rewrite Development and Validation Guides

**Files:**
- Modify: `SETUP.md`
- Modify: `TESTING.md`
- Modify: `CODING_STYLE.md`
- Modify: `admin-panel/README.md`

**Interfaces:**
- Consumes: `requirements.txt`, `.env.example`, Compose, pytest config, CI, and admin package scripts.
- Produces: copyable development and validation instructions.

- [ ] **Step 1: Rewrite `SETUP.md`**

Document Python 3.11, Docker with Compose v2, Node 22 for the admin UI, `.env`
creation, required versus optional settings, Docker startup, Alembic migration,
current seed utilities, Telethon session authorization, health checks, and local
non-Docker commands where supported. Remove pi/Claude installation, phase setup,
obsolete file lists, and claims that existing dependencies are future work.

- [ ] **Step 2: Rewrite `TESTING.md`**

Document `pytest tests/ -v --tb=short`, focused test examples using existing test
files, infrastructure requirements, Alembic head/reversibility checks, admin
`npm ci && npm run lint && npm run build`, Docker build, secret scan scope, and
matching-quality tools. State that `tools/export_baseline.py` and
`tools/eval_matching.py` create dated artifacts under `docs/eval/`; those outputs
are evidence snapshots, not canonical documentation.

- [ ] **Step 3: Rewrite `CODING_STYLE.md`**

Keep enforceable conventions visible in current Python and TypeScript code:
typing at public boundaries, async I/O, structured logging, explicit config,
SQLAlchemy session discipline, migrations with downgrade paths, RU/EN locale
parity, stable callback data, tests for behavioral changes, and secret hygiene.
Remove arbitrary universal limits such as “every function must be at most 30
lines” when the repository does not enforce them.

- [ ] **Step 4: Replace the Vite template in `admin-panel/README.md`**

Document the React/Vite stack from `admin-panel/package.json`, scripts, local
startup, API dependency on the FastAPI admin service, authentication behavior,
route/page map from `admin-panel/src`, production build location, and CI checks.

- [ ] **Step 5: Verify commands and commit**

Run:

```bash
test -f requirements.txt
test -f admin-panel/package-lock.json
test -f migrations/env.py
docker compose config --quiet
npm --prefix admin-panel run lint
npm --prefix admin-panel run build
git diff --check -- SETUP.md TESTING.md CODING_STYLE.md admin-panel/README.md
```

Expected: Compose configuration is valid, admin lint/build pass, and Markdown has
no whitespace errors.

```bash
git add SETUP.md TESTING.md CODING_STYLE.md admin-panel/README.md
git commit -m "docs: refresh development and testing guides"
```

### Task 4: Rewrite Operations, Recovery, Decisions, and Agent Context

**Files:**
- Modify: `OPERATIONS.md`
- Modify: `RECOVERY.md`
- Modify: `DECISIONS.md`
- Modify: `CLAUDE.md`

**Interfaces:**
- Consumes: Compose health checks and limits, `scripts/deploy.sh`, backup/restore scripts, worker queue code, migrations, and GitHub Actions.
- Produces: current operational source of truth and concise agent orientation.

- [ ] **Step 1: Rewrite `OPERATIONS.md`**

Document normal health checks, service ownership, safe worker handling, Telegram
rate limiter/circuit breaker rules, deployment through GitHub Actions and
`scripts/deploy.sh`, migration safety, queue/DLQ observation, payment monitoring,
backup limitations, and incident recording. Preserve dated incidents only as
short rationale for still-active safety rules.

- [ ] **Step 2: Rewrite `RECOVERY.md`**

Provide symptom-first procedures for bot, worker, notifications, DB, Redis,
admin, payment, FloodWait, and storage failures. Correct the Redis statement:
Compose enables AOF with `appendfsync everysec`, while application-level recovery
still depends on the reliable queue/DLQ design. Put an explicit approval gate
before `restore.sh`, database recreation, session reset, or volume deletion.

- [ ] **Step 3: Normalize `DECISIONS.md`**

Retain only durable decisions that are still reflected in code: service split,
PostgreSQL/Redis, Telegram account identity, rate limiting, classifier/LLM mode,
plan model, RU/EN, queue/payment idempotency, admin access posture, migration and
deploy safety. Each entry must state decision, rationale, and current evidence.

- [ ] **Step 4: Reduce `CLAUDE.md` to an agent index**

Keep project summary, hard safety rules, source-of-truth order, repository map,
common commands, documentation links, and “do not mutate production without
approval.” Remove session status, future phase plans, duplicated schema tables,
and copied user-flow text.

- [ ] **Step 5: Verify operations references and commit**

Run:

```bash
rg -n 'queue:|dead|retry|appendonly|appendfsync' app/worker app/cache docker-compose.yml
rg -n 'alembic|docker compose|pg_dump|restore.sh|backup.sh' scripts/deploy.sh backup.sh restore.sh
git diff --check -- OPERATIONS.md RECOVERY.md DECISIONS.md CLAUDE.md
```

Expected: every documented queue key, service, and command has a matching source
reference; destructive recovery steps are clearly gated.

```bash
git add OPERATIONS.md RECOVERY.md DECISIONS.md CLAUDE.md
git commit -m "docs: align operations and recovery with runtime"
```

### Task 5: Consolidate User Flow and Tool Instructions

**Files:**
- Modify: `USERFLOW.md`
- Modify: `.cursor/skills/classifier-change/SKILL.md`
- Modify: `.cursor/skills/migration-checklist/SKILL.md`
- Modify: `.cursor/skills/phase-review/SKILL.md`
- Modify: `.cursor/skills/recovery/SKILL.md`
- Modify: `.cursor/skills/safe-deploy/SKILL.md`
- Modify: `.cursor/skills/session-close/SKILL.md`
- Modify: `.cursor/skills/userflow-change/SKILL.md`
- Modify: `.pi/agents/userflow-validator.md`
- Modify: `.pi/agents/ux-tester.md`
- Delete: `.pi/agents/country-city-auditor.md`
- Delete: `.pi/skills/phase-review/SKILL.md`

**Interfaces:**
- Consumes: bot handlers, locale dictionaries, callback data, FSM states, user-flow tests, and the new canonical documents.
- Produces: one current user-flow guide plus valid tool instructions.

- [ ] **Step 1: Rewrite `USERFLOW.md` around runtime routes**

Document language selection, `/start`, the four-button main menu, search wizard,
subscriptions, keywords/channels, plan and payment screens, referrals, settings,
stats, digest, CSV, lifecycle messages, paywalls, error/empty states, and support.
For exact copy, point to `app/locales/{ru,en}.py`; for executable coverage, point
to `tests/test_userflow_*.py` and tariff tests. Remove historical problem lists,
superseded screen drafts, and duplicated full locale catalogs.

- [ ] **Step 2: Repair Cursor skill references**

Replace `SESSION_LOG` writes with a concise verification handoff; replace old
`CLAUDE.md` section anchors with `docs/ARCHITECTURE.md`, `USERFLOW.md`,
`OPERATIONS.md`, or `TESTING.md`; remove phase-tag assumptions; keep safety gates
for migrations, worker deploys, FloodWait, RU/EN parity, and classifier eval.

- [ ] **Step 3: Repair or remove pi instructions**

Update `userflow-validator.md` and `ux-tester.md` to treat handlers/locales/tests
as the exact source and `USERFLOW.md` as the map. Remove the obsolete 21-screen
and nine-button claims. Delete the country/city auditor because it requires a
root `SEED.md` that is absent, and delete the duplicate phase-review skill that
auto-pushes tags contrary to the repository's approval rules. Keep the shadcn
skill unchanged.

- [ ] **Step 4: Run user-flow contract tests and validate references**

```bash
pytest -q tests/test_userflow_u1_i18n.py \
  tests/test_userflow_u3_onboarding.py \
  tests/test_userflow_u10_snapshots.py \
  tests/test_userflow_lifecycle.py \
  tests/test_userflow_referral_reward.py
rg -n 'SESSION_LOG|CLAUDE\.md §|21 экран|9 кноп|SEED\.md|phase-N' \
  USERFLOW.md .cursor/skills .pi/agents .pi/skills
git diff --check -- USERFLOW.md .cursor/skills .pi/agents .pi/skills
```

Expected: user-flow tests pass; no obsolete references remain except a clearly
explained historical warning.

- [ ] **Step 5: Commit the user-flow and instruction set**

```bash
git add USERFLOW.md .cursor/skills .pi/agents .pi/skills
git commit -m "docs: consolidate user flow and agent instructions"
```

### Task 6: Remove Superseded Historical Artifacts

**Files:**
- Delete: `ONBOARDING.md`
- Delete: `specification.md`
- Delete: `codex_userflow.md`
- Delete: `fable_audit.md`
- Delete: `fable_core_plan.md`
- Delete: `fable_tariff_plan.md`
- Delete: `docs/SESSION_LOG.md`
- Delete: `docs/archive/2026-07/*.md`
- Delete: `docs/broken_channels_2026-07-14.md`
- Delete: `docs/eval/*.md`
- Delete: `docs/geo_markup_draft_2026-07-13.md`
- Delete: `docs/runbook_tariffs_v2_deploy.md`
- Delete: `docs/runlist_switch_2026-07-12.md`
- Delete: `docs/userflow_screen_registry.md`
- Delete: `docs/userflow_text_edit.md`
- Delete: `docs/userflow_text_map.md`
- Delete: `docs/userflow_u0_contract.md`
- Delete: `docs/userflow_u10_editorial_review.md`
- Delete: `docs/userflow_u10_scenario_matrix.md`
- Delete: `.pi/handoffs/*.md`
- Delete: `.rpiv/artifacts/handoffs/*.md`
- Delete: `.rpiv/artifacts/designs/landing-prompt.md`

**Interfaces:**
- Consumes: completed extraction in Tasks 2–5.
- Produces: a clean active tree whose historical detail remains in Git.

- [ ] **Step 1: Confirm no active document depends on a deletion target**

Run:

```bash
rg -n 'ONBOARDING|specification\.md|codex_userflow|fable_|SESSION_LOG|docs/archive|docs/eval/[a-z0-9_-]+\.md|userflow_(screen_registry|text_edit|text_map|u0_contract|u10_)' \
  README.md CLAUDE.md CODING_STYLE.md DECISIONS.md OPERATIONS.md RECOVERY.md SETUP.md TESTING.md USERFLOW.md docs/PRODUCT_OVERVIEW.md docs/ARCHITECTURE.md admin-panel/README.md .cursor .pi
```

Expected: no dependency on a deleted file. A generic statement that eval tools
generate reports under `docs/eval/` is allowed.

- [ ] **Step 2: Delete the listed artifacts with a reviewable patch**

Use `apply_patch` deletions, not filesystem-wide recursive removal. Confirm the
deletion list with `git status --short` before staging.

- [ ] **Step 3: Confirm retained Markdown inventory**

```bash
git ls-files '*.md' '*.mdx' | sort
```

Expected retained groups: canonical project docs, current tool skills/agents,
the two approved specs, and this implementation plan.

- [ ] **Step 4: Commit cleanup**

```bash
git add -A
git commit -m "docs: remove superseded plans and handoffs"
```

### Task 7: Validate the Consolidated Documentation

**Files:**
- Verify: all retained `*.md` and `*.mdx`
- Verify: repository code and tests without modification

**Interfaces:**
- Consumes: Tasks 2–6.
- Produces: evidence that documentation is internally consistent and the repository remains healthy.

- [ ] **Step 1: Check Markdown links and repository paths**

Run a read-only script that parses relative Markdown links from tracked files,
ignores HTTP(S), anchors, and example placeholders, and fails for missing local
targets. Then manually check plain backtick paths listed in the documentation.

Expected: zero broken links to local files.

- [ ] **Step 2: Scan for stale phase and placeholder language**

```bash
rg -n 'Фаза [0-9]|Этап [0-9]|в разработке|на будущее|когда появится|TODO|TBD|SESSION_LOG|phase-N' \
  README.md CLAUDE.md CODING_STYLE.md DECISIONS.md OPERATIONS.md RECOVERY.md SETUP.md TESTING.md USERFLOW.md docs/PRODUCT_OVERVIEW.md docs/ARCHITECTURE.md admin-panel/README.md .cursor/skills .pi/agents
```

Expected: no stale status language. Legitimate future limitations must be labeled
as optional or out of scope rather than scheduled phases.

- [ ] **Step 3: Run repository release-gate equivalents**

```bash
pytest tests/ -v --tb=short
alembic heads
npm --prefix admin-panel run lint
npm --prefix admin-panel run build
docker build -t leadhunter-docs-check .
```

Expected: pytest passes, `alembic heads` prints exactly one head, admin lint/build
pass, and Docker image builds. If infrastructure prevents a local test, report
the exact limitation and rely only on checks that actually ran.

- [ ] **Step 4: Review the final diff**

```bash
git diff --check HEAD~1..HEAD
git status --short --branch
git log --oneline --decorate -8
```

Expected: documentation-only changes, no secret files, no application code edits,
and a clean working tree after commits.

- [ ] **Step 5: Prepare completion summary**

Report retained document structure, removed artifact groups, verification commands
and exact outcomes, known runtime/documentation limitations discovered but not
changed, local commit SHAs, and whether anything was pushed or deployed.
