---
name: session-close
description: Close a LeadHunter work session by writing SESSION_LOG and updating CLAUDE.md status. Use when finishing a task, ending a coding session, or before handing off to another agent.
---

# Session Close

Task incomplete until both steps are done.

## 1. Append `docs/SESSION_LOG.md`

Format (end of file):

```markdown
**DD.MM.YYYY HH:MM — Short title.** What changed. Result/verification. Errors/lessons. Deploy status if relevant.
```

Include: files/areas touched, test commands + outcome, whether prod was touched, FloodWait if worker restarted.

## 2. Update `CLAUDE.md` §8

- Set **Дата** to today.
- Rewrite **Статус** in 2–4 sentences: branch, what shipped, what's blocked, next step.
- Keep historical bullets below if they remain accurate; mark obsolete worker-stop notes clearly.

## Do not
- Skip log because change was "small".
- Commit unless the user asked.
