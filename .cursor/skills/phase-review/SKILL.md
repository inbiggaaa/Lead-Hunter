---
name: phase-review
description: Run LeadHunter phase review — pytest then code review against CODING_STYLE. Use after completing a development phase, before tagging phase-N-done, or when the user asks for phase-review.
---

# Phase Review

## Step 1 — Tests

```bash
pytest tests/ -v
```

Fail → stop, show failures, propose fixes. Pass → Step 2.

## Step 2 — Code review (diff)

Review `git diff` / commits since last `phase-*-done` tag (or agreed base) against `CODING_STYLE.md`:

- Functions ≤ 30 lines
- Early return
- Explicit names
- Comments = why
- No bare `except Exception` / no `Any`
- Public functions typed

Label findings: **blocker** / **concern** / **suggestion**.

## Step 3 — Fixes
- suggestion → auto-fix if safe
- concern → fix if trivial, else ask owner
- blocker → stop for owner decision

## Step 4 — Re-test

```bash
pytest tests/ -v
```

## Step 5 — Finish
Only when green and no blockers. Commit/tag **only if user asked**:

```bash
git tag phase-N-done
```

Then run skill `session-close`.

## Rules
- Do not change business logic without confirmation.
- `CODING_STYLE.md` is the style source of truth.
