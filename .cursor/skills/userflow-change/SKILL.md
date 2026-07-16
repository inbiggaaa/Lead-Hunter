---
name: userflow-change
description: Change LeadHunter bot screens, FSM funnel, menus, buttons, or user-facing copy with RU/EN parity. Use when editing handlers, locales, USERFLOW, payments screens, or menu navigation.
---

# Userflow Change

## Sources
- Screen map + copy: `USERFLOW.md`
- Strings: `app/locales/ru.py`, `en.py`
- Handlers: `app/bot/handlers/`
- Locked product decisions: `DECISIONS.md`, tariffs in `CLAUDE.md` §1

## Rules
1. Main menu = **4 buttons** (search / plan / referral / settings) — do not revive 9-button menu.
2. Inline keyboards only (except `/start`); every screen needs Back where applicable.
3. FSM: `CatStates` + `/cancel`. Respect plan limits via `_plan_limits()`.
4. RU+EN parity for every key and placeholder.
5. Free vs paid notification formats — do not weaken Free paywall (no contact links).
6. No new marketing promises without owner approval (post-userflow marketing is a separate stage).

## Workflow

```
- [ ] Identify screen IDs in USERFLOW.md
- [ ] Edit locales (both languages)
- [ ] Wire handlers/callbacks; keep callback_data stable or update all refs
- [ ] validate_locale_schema / i18n tests
- [ ] Update userflow snapshots if present
- [ ] Deploy bot only unless worker texts changed
```

## After
Skill `session-close`. Note deploy: usually `docker restart leadhunter-bot-1`.
