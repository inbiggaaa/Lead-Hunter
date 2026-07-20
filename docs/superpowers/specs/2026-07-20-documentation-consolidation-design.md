# Documentation Consolidation Design

**Date:** 2026-07-20  
**Repository:** `inbiggaaa/Lead-Hunter`  
**Branch baseline:** `main` at `1ed4dc1`

## Goal

Replace the accumulated mixture of current documentation, completed development
plans, dated audits, session logs, handoffs, and template text with a compact
product-and-engineering documentation set that describes the behavior present in
the current codebase.

## Source of Truth

Documentation claims must be checked in this order:

1. Runtime code and configuration under `app/`, `docker-compose.yml`,
   `.env.example`, migrations, and deployment or backup scripts.
2. Automated tests and GitHub Actions, which define supported behavior and
   release gates.
3. Current operational documents and decision records, but only when they do not
   contradict code or configuration.
4. Historical plans, audits, and handoffs as context only. They cannot establish
   current behavior.

No documentation will claim that a planned, disabled, placeholder, or untested
capability is operational. Secrets, production values, and personal data will not
be copied into documentation.

## Target Documentation Set

The active documentation will have one clear entry point and focused supporting
documents:

- `README.md`: product summary, implemented capabilities, architecture overview,
  repository map, quick start, validation commands, and links to deeper guides.
- `docs/PRODUCT_OVERVIEW.md`: product audience, supported user journeys, plans,
  payments, localization, notifications, and explicit limitations.
- `docs/ARCHITECTURE.md`: bot, worker, userbot, classifier, persistence, cache,
  payment, lifecycle, admin API/UI, and data-flow boundaries.
- `SETUP.md`: local and server prerequisites, environment preparation,
  migrations, service startup, and first-run checks.
- `TESTING.md`: actual test suites, markers, CI jobs, frontend checks, and commands.
- `OPERATIONS.md`: normal operation, deployment, monitoring, queue handling,
  Telegram account safety, backup status, and incident response entry points.
- `RECOVERY.md`: evidence-backed recovery procedures and destructive-action
  warnings aligned with the current scripts and persistent Redis configuration.
- `USERFLOW.md`: concise current RU/EN bot flow and links to the executable text
  sources and snapshot tests; historical audit narrative is removed.
- `DECISIONS.md`: durable technical and product decisions only, normalized into a
  short decision-log format.
- `CODING_STYLE.md`: enforceable repository conventions that match current code
  and tooling.
- `CLAUDE.md`: concise agent orientation, safety constraints, source-of-truth map,
  and commands; it will not duplicate the full specification.
- `admin-panel/README.md`: real admin-panel setup, scripts, architecture, and API
  relationship instead of the Vite template.

`specification.md` will be retired after its still-current facts are incorporated
into the focused documents above. This avoids maintaining a second monolithic
source of truth.

## Historical Material Policy

Git history is the archive. Completed working artifacts will be removed from the
active branch after any still-valid decision or procedure is migrated:

- completed `fable_*` plans and audits;
- `codex_userflow.md` after the current flow is represented in `USERFLOW.md`;
- `docs/SESSION_LOG.md`;
- dated handoffs under `.pi/handoffs/` and `.rpiv/artifacts/handoffs/`;
- dated audits and implementation plans under `docs/archive/`;
- one-time cleanup lists, drafts, branch-switch runlists, and superseded deploy
  runbooks under `docs/`;
- obsolete eval diffs and reports when their reproducible checks are already in
  code or tests.

For classifier evaluation, retain only material that is still required to
reproduce the current baseline or review unmatched samples. All retained eval
documents must state what command or tool produces them and whether the data is
current or a dated snapshot.

Tool instructions under `.cursor/skills/`, `.pi/skills/`, and `.pi/agents/` are
not treated as ordinary project documentation. They remain in place when they
still reference existing files and commands. Broken or obsolete instructions are
updated or removed individually. Design prompts under `.rpiv/artifacts/designs/`
are removed when they describe completed work and have no runtime role.

## Consolidation Method

1. Build a feature and operations matrix from code, configuration, migrations,
   tests, CI, and scripts.
2. Extract valid decisions and unresolved operational constraints from historical
   files.
3. Rewrite the active documents around the target responsibilities above.
4. Remove completed and superseded artifacts only after extraction.
5. Check all internal links, referenced files, commands, environment variables,
   service names, routes, and test paths.
6. Run documentation consistency checks plus the repository's feasible automated
   validation. Existing unrelated failures will be reported, not hidden.

## Content Rules

- Use present tense only for implemented behavior.
- Label disabled-by-default, optional, manual, placeholder, and untested features.
- Separate product behavior from deployment assumptions.
- Avoid duplicating detailed facts across files; link to the owning document.
- Keep dated incident facts only when they explain an active operational rule.
- Preserve RU/EN parity for documented user-facing flows.
- Do not promise that every lead contains contact details or a usable chat link.
- Commands must be copyable and must target names that exist in the current tree.

## Verification

The documentation update is complete when:

- every active document has one defined responsibility;
- no active document describes an already completed phase as future work;
- Markdown links and repository paths resolve;
- documented Docker services match `docker-compose.yml`;
- documented environment variables match fields consumed by `app/config.py` or
  variables used by scripts, with unused compatibility keys clearly marked;
- documented bot flows and plan limits agree with handlers, locale files, and
  user-flow tests;
- setup, migration, test, build, deploy, backup, and restore commands correspond
  to current files;
- deleted artifacts are recoverable from Git history;
- the final diff contains documentation changes only unless a separate code defect
  must be fixed and is explicitly approved.

## Out of Scope

- Changing application behavior, pricing, infrastructure, or production state.
- Publishing, pushing, or opening a pull request without separate authorization.
- Rewriting third-party Markdown under dependency directories.
- Treating aspirational roadmap items as committed functionality.
