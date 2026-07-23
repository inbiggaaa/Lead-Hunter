# Closed matching feedback — runbook (RU)

Дата: 24.07.2026  
Код: ветка `feature/closed-matching-feedback-v2`  
Миграция: `matching_feedback_v2` (после `segment_profile_audit01`)

## Что это

Закрытый двухуровневый контур разметки доставленных лидов для владельца/тестеров.
Обычные пользователи сохраняют legacy 👍/👎. Segment-aware LLM blocking **не** включается этим runbook.

## Env (без реальных Telegram ID в git)

```env
MATCHING_FEEDBACK_ENABLED=false
MATCHING_FEEDBACK_TESTER_IDS=
MATCHING_FEEDBACK_BATCH=
```

Правила fail-closed:

- flag OFF → нового UI нет;
- пустой allowlist → нового UI нет ни у кого;
- пустой batch → item не создаётся.

В staging/prod `.env` задайте tester ID вручную (не коммитьте).

## Волны подписок

1. Через обычный бот подпишитесь на 5–10 сегментов одной категории.
2. Собирайте оценки до quality gates.
3. Экспортируйте batch (admin Matching QA / CSV+JSONL).
4. Снимите подписки волны и подключите следующую.
5. Не поднимайте лимит Business ради теста.

## Recall-выборка (precision ≠ recall)

Для каждого batch:

```bash
PYTHONPATH=. venv/bin/python tools/export_recall_template.py --batch ru_matching_v1
```

Артефакт: `docs/eval/recall_<batch>_<date>.md`  
Колонки: `missed_lead`, `expected_segment`, `missed_at_layer`.

## Staging rollout

1. Backup: `pg_dump` перед миграцией.
2. Worker: остановить **только если** миграция применяется на shared DB (см. OPERATIONS §2/§5 и prod safety).
3. `alembic upgrade head` на staging/test DB.
4. Deploy кода с defaults OFF.
5. В staging `.env`:

```env
MATCHING_FEEDBACK_ENABLED=true
MATCHING_FEEDBACK_TESTER_IDS=<owner_tg_id>
MATCHING_FEEDBACK_BATCH=ru_matching_v1
```

6. Restart **bot** (и admin при необходимости). Worker только если менялся poller payload path и нужен новый snapshot — по явной команде.
7. Smoke:
   - tester видит ✅/⚠️/🤷;
   - non-tester видит 👍/👎;
   - wrong_category → кандидаты/каталог;
   - multi-segment correct → selector;
   - admin `/matching-feedback` summary/export;
   - DB failure feedback → лид всё равно доходит.

## Rollback

1. `MATCHING_FEEDBACK_ENABLED=false` (+ пустой allowlist) → мгновенно скрывает новый UI.
2. При необходимости schema rollback **только на test/staging** после backup:

```bash
alembic downgrade -1
```

Downgrade **удаляет unrated** experimental rows (`verdict IS NULL`), затем возвращает legacy `relevant`/`not_relevant`.

## Quality gates (blocking candidate)

Не делать вывод по сегменту без:

- ≥30 определённых оценок (`correct + error`);
- разбора missing snapshot;
- ручной проверки wrong-category;
- recall-выборки без систематических FN.

Кандидат на blocking (отдельно от этого feature):

- precision ≥85%;
- wrong category ≤5%;
- intent-noise (provider_offer+job_*+social+discussion) ≤10%;
- v2 fail-open ≤5%;
- нет критичных ошибок дедупа/гео.

Недостаточная выборка = «решение не принято».

## Явные запреты

- Не включать `LLM_SEGMENT_PROFILES_BLOCKING` этим runbook.
- Не менять first-wave allowlist.
- Не править keywords/profiles автоматически из feedback.
- Не деплоить production без отдельной команды владельца.
