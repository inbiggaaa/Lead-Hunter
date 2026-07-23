# Промпт для Cursor Grok 4.5 — закрытая разметка качества матчинга

Скопируй весь текст ниже в новый Cursor Agent chat.

---

Ты работаешь в репозитории Lead-Hunter. Нужно реализовать закрытый двухуровневый feedback-контур для ручной оценки матчинга лидов.

## Главная цель

Владелец сервиса подписывается через обычный Telegram-бот на группы категорий и размечает доставленные уведомления:

- `✅ Верно`;
- `⚠️ Ошибка` → точная причина;
- `🤷 Не уверен`;
- при `Не та категория` выбирает правильную подкатегорию.

Результат должен позволять надёжно определить, какой слой ошибся: keywords/classifier, reality filter, legacy LLM, segment-aware LLM или распределение категории.

## Обязательные документы

Перед любыми изменениями полностью прочитай:

1. `AGENTS.md`
2. `CODING_STYLE.md`
3. `TESTING.md`
4. `OPERATIONS.md`, особенно §2 и §5
5. `docs/superpowers/specs/2026-07-24-closed-matching-feedback-design.md`
6. `docs/superpowers/plans/2026-07-24-closed-matching-feedback.md`
7. `docs/ops/segment_profiles_enablement_ru.md`

Implementation plan является исполнимой спецификацией. Не заменяй его собственной архитектурой без остановки и согласования с владельцем.

## Перед началом

1. Покажи:
   - текущую ветку;
   - `git status --short`;
   - последний commit;
   - Alembic heads;
   - список существующих worktree.
2. Не работай напрямую в `main`.
3. Создай изолированную ветку `feature/closed-matching-feedback-v2`.
4. Если рабочее дерево не чистое, не stash, не reset и не удаляй чужие изменения. Создай отдельный worktree.
5. Запусти baseline:
   - `pytest -q tests/test_sender.py`;
   - существующие segment LLM shadow/blocking tests;
   - `npm run lint` и `npm run build` в `admin-panel`.
6. Если baseline падает, остановись, зафиксируй точную ошибку и не начинай реализацию без решения владельца.

## Жёсткие архитектурные ограничения

### Использовать одну таблицу

Расширь существующую пустую таблицу `feedback`.

Не создавай:

- `feedback_rounds`;
- `feedback_items`;
- `feedback_labels`;
- `feedback_events`;
- универсальную платформу экспериментов.

Одна строка `feedback` — item snapshot плюс текущая оценка.

Уникальность:

```text
(test_batch, user_id, chat_username, message_id)
```

Повторный ответ обновляет текущую оценку. История версий в этой итерации не нужна.

### Не экономить на данных качества

Обязательно сохраняй:

- masked message text;
- delivered segment slugs;
- confirmed segment slugs для multi-match;
- rule candidates;
- segments после reality filter;
- legacy LLM verdict/segments;
- v2 commercial intent;
- v2 per-segment verdicts;
- model name;
- prompt/schema versions;
- profile versions;
- verdict, reason и expected segment.

Raw message text, телефоны, username автора, ссылки и контакты в feedback/logs/export запрещены.

Не восстанавливай snapshots позднее JOIN-ом к «последнему» `llm_decisions`: snapshot должен фиксироваться во время доставки.

### Closed-test gate

Добавь:

```env
MATCHING_FEEDBACK_ENABLED=false
MATCHING_FEEDBACK_TESTER_IDS=
MATCHING_FEEDBACK_BATCH=
```

Правила:

- flag OFF → нового UI нет;
- пустой allowlist → нового UI нет ни у кого;
- пустой batch → item не создаётся;
- только tester ID получает новый интерфейс;
- обычные пользователи сохраняют текущий интерфейс;
- никаких реальных Telegram ID в git.

### Feedback не блокирует лиды

Если создание item или чтение feedback БД упало:

- залогируй безопасную ошибку;
- отправь лид без экспериментальных кнопок;
- не меняй retry/DLQ/dedup/throttle;
- не помещай raw text или полный token в лог.

### Callback protocol

Формат:

```text
mf:v1:<short_action>:<public_token>
```

Callback data обязана быть ≤64 bytes. Не кодируй в callback chat username, message ID или текст.

## UX

Первый уровень:

- `✅ Верно`
- `⚠️ Ошибка`
- `🤷 Не уверен`

Причины ошибки:

- `wrong_category`
- `provider_offer`
- `job_vacancy`
- `job_search`
- `social_request`
- `discussion_news`
- `wrong_geography`
- `duplicate`
- `other`

После отрицательной оценки не удаляй уведомление.

`wrong_category`:

1. Сохрани ошибку сразу.
2. Покажи до четырёх альтернативных candidate segments.
3. Дай выбрать из каталога `категория → подкатегория`.
4. Добавь `Категории нет` и `Пропустить`.

После оценки показывай summary и `✏️ Изменить`.

`uncertain` хранится, но не входит в precision или gold export.

Если доставлен один сегмент, `✅ Верно` сохраняется сразу. Если сегментов несколько, обязательно покажи selector и сохрани `confirmed_segments`: какие доставленные подкатегории действительно верны. Не засчитывай correct автоматически всем сегментам multi-match.

Добавляй RU и EN locale keys одновременно. Тон нейтральный и корпоративный.

## Что нельзя менять

- Не меняй тарифы и лимит Business.
- Не подписывай пользователя автоматически.
- Не меняй keywords.
- Не публикуй и не редактируй segment LLM profiles.
- Не включай segment-aware blocking.
- Не меняй first-wave blocking allowlist.
- Не меняй polling intervals, Telegram API call count, account pool или rate limiter.
- Не добавляй сторонние зависимости без доказанной необходимости.
- Не запускай production deploy, migration, seed, worker restart или env flip.

## Порядок выполнения

Работай строго по задачам в:

```text
docs/superpowers/plans/2026-07-24-closed-matching-feedback.md
```

Перед каждой фазой:

1. Покажи цель.
2. Перечисли точные файлы.
3. Покажи тесты, которые сначала должны упасть.
4. Дождись подтверждения владельца.

В каждой фазе используй TDD:

1. Напиши тест.
2. Запусти и покажи ожидаемый RED.
3. Реализуй минимальное изменение.
4. Запусти GREEN.
5. Запусти релевантные regression tests.
6. Выполни `git diff --check`.
7. Сделай отдельный commit.
8. Поставь tag `phase-N-done`.
9. Запусти `/skill:phase-review`.

Не объединяй несколько фаз в один большой commit.

## Особые требования к snapshot

Сейчас `_dispatch()` получает только финальные сегменты и теряет часть информации о слоях. Исправь это типизированно:

- не парси downstream `raw_response`;
- сформируй JSON-safe snapshot в момент, когда доступны legacy и parsed v2 decisions;
- передай snapshot через poller notification payload;
- отдели slugs от локализованных display titles;
- добавь в `PendingMatch` отдельные `rule_segments` до reality-фильтра и сохрани существующие `candidate_segments` как reality-confirmed;
- keyword-only delivery пометь явно;
- отсутствие v2/profile не должно ломать legacy path.

Не добавляй Telegram API requests.

## Миграция

Новая миграция идёт после `segment_profile_audit01`.

Требования:

- один Alembic head;
- upgrade и downgrade;
- CHECK constraints для verdict/reason;
- FK expected segment с `ON DELETE SET NULL`;
- UNIQUE token;
- UNIQUE batch/user/chat/message;
- существующие legacy строки не должны ломать upgrade;
- downgrade-поведение для unrated rows явно описано и протестировано.

Перед любой shared/staging миграцией нужен `pg_dump`. В этой задаче выполняй миграцию только на отдельной тестовой БД.

## Аналитика

Один канонический агрегатор должен использоваться API, eval и export.

Обязательные показатели:

- delivered;
- rated coverage;
- correct/error/uncertain;
- precision без uncertain;
- reasons distribution;
- per-segment precision;
- confusion matrix delivered → expected;
- breakdown по model/prompt/schema/profile;
- legacy против v2;
- missing snapshot.

Gold export:

- исключает uncertain и unrated;
- не содержит PII;
- wrong_category без expected segment помечает как intent-only;
- не применяет никаких изменений автоматически.

Оценка доставленных лидов измеряет только precision. Расширь существующий `tools/export_recall_template.py`, чтобы каждый batch имел отдельную masked выборку: 50 unmatched + 50 LLM-rejected с ручными колонками `missed_lead`, `expected_segment`, `missed_at_layer`. Не создавай для recall новую runtime-таблицу.

Сделай минимальную страницу существующей admin-панели. Не создавай отдельный экспериментальный продукт.

## Quality gates

Не делай вывод по сегменту, пока нет:

- минимум 30 определённых оценок;
- разбора missing snapshot;
- ручной проверки wrong-category.

Кандидат на blocking:

- precision ≥85%;
- wrong category ≤5%;
- суммарный intent-noise ≤10%;
- v2 fail-open ≤5%;
- нет критических ошибок дедупликации или географии.
- recall-выборка не показывает систематические false negatives.

Недостаточная выборка означает «решение не принято».

## Финальная проверка

В конце обязательно выполни:

```bash
pytest tests/ -v --tb=short
cd admin-panel && npm run lint && npm run build
alembic heads
git diff --check
git status --short
```

Отдельно покажи:

- результаты focused feedback tests;
- upgrade → downgrade → upgrade миграции на test DB;
- callback length tests;
- fail-open delivery test при ошибке feedback DB;
- PII exclusion export tests;
- RU/EN locale validation;
- отсутствие изменений в LLM blocking/env production.

## Финальный отчёт

Верни владельцу:

1. Список фаз и commits.
2. Список изменённых/созданных файлов.
3. Результаты тестов и сборки.
4. Alembic head и результат reversibility smoke.
5. Известные ограничения.
6. Точный staging rollout.
7. Точный rollback.
8. Подтверждение, что production, worker, Telegram sessions и blocking flags не затрагивались.

Не мержи и не деплой без отдельной команды владельца.
