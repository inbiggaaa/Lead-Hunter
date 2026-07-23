# Закрытое тестирование матчинга — упрощённый дизайн

**Дата:** 24.07.2026
**Статус:** утверждён владельцем
**Первая волна:** один RU-тестер, тестирование категориями по 5–10 сегментов
**Принцип:** минимальная архитектура без потери данных, влияющих на качество

## 1. Цель

Собрать надёжную ручную разметку доставленных лидов, чтобы отдельно видеть:

- правильный коммерческий лид;
- false positive по намерению;
- правильный лид в неправильной подкатегории;
- ошибку географии;
- дубликат;
- неоднозначный пример.

Данные должны позволять оценить rule-based classifier, reality-фильтр, legacy LLM и segment-aware LLM, построить confusion matrix и подготовить gold export. Никакие keywords или LLM-профили не меняются автоматически.

## 2. UX разметки

### Первый уровень

Тестер видит:

- `✅ Верно` → `correct`;
- `⚠️ Ошибка` → открыть причины;
- `🤷 Не уверен` → `uncertain`.

`uncertain` хранится, но исключается из precision и gold-датасета.

Если доставлен один сегмент, `✅ Верно` сохраняется сразу. Если доставлено несколько сегментов, бот показывает selector «Какие категории верны?» и позволяет выбрать одну или несколько доставленных подкатегорий. Это не даёт ошибочно засчитать correct всем сегментам multi-match уведомления.

### Второй уровень

После `⚠️ Ошибка` уведомление не удаляется. Бот показывает:

- `📂 Не та категория` → `wrong_category`;
- `📢 Реклама / предложение` → `provider_offer`;
- `💼 Вакансия` → `job_vacancy`;
- `🙋 Поиск работы` → `job_search`;
- `👥 Некоммерческий запрос` → `social_request`;
- `📰 Обсуждение / новость` → `discussion_news`;
- `📍 Не та география` → `wrong_geography`;
- `🔁 Дубликат` → `duplicate`;
- `❓ Другое` → `other`;
- `◀️ Назад`.

Выбор причины сохраняет оценку. Для `wrong_category` бот затем предлагает:

1. До четырёх альтернативных candidate segments, кроме доставленных.
2. `📚 Выбрать из каталога` → категория → подкатегория.
3. `➕ Категории нет`.
4. `Пропустить`.

После сохранения клавиатура показывает выбранную оценку и кнопку `✏️ Изменить`. Повторный ответ обновляет текущую запись.

## 3. Закрытый доступ

Новый интерфейс включается только когда:

- `MATCHING_FEEDBACK_ENABLED=true`;
- Telegram ID входит в `MATCHING_FEEDBACK_TESTER_IDS`;
- задан непустой `MATCHING_FEEDBACK_BATCH`, например `ru_matching_v1`.

Пустой allowlist означает «не показывать никому». Обычные пользователи продолжают получать текущий интерфейс. Их legacy feedback не смешивается с закрытой выборкой.

Allowlist сохраняется даже при отсутствии реальных клиентов: это дешёвая защита от случайной регистрации во время теста.

## 4. Одна таблица `feedback`

Legacy feedback уже очищен. Существующая таблица расширяется и становится одновременно:

- feedback item со snapshot;
- текущей оценкой тестера.

Поля:

- `id`;
- `public_token` — случайный короткий URL-safe token, UNIQUE;
- `test_batch`;
- `user_id`;
- `chat_username`, `message_id`;
- `message_hash`, `content_hash`;
- `message_text_masked`;
- `delivered_segments`;
- `rule_segments`;
- `reality_segments`;
- `legacy_llm_verdict`, `legacy_llm_segments`;
- `v2_intent`, `v2_segment_verdicts`;
- `model_name`, `prompt_version`, `schema_version`;
- `profile_versions` JSONB;
- `verdict`: nullable `correct`, `error`, `uncertain`;
- `reason_code`;
- `confirmed_segments`;
- `expected_segment_id`;
- `expected_segment_slug`;
- `expected_segment_missing`;
- `created_at`, `rated_at`, `updated_at`.

Уникальность: `(test_batch, user_id, chat_username, message_id)`.

Ограничения:

- `correct` и `uncertain` не могут иметь `reason_code`;
- `error` обязан иметь `reason_code`;
- `correct` обязан иметь хотя бы один `confirmed_segment`, являющийся подмножеством `delivered_segments`;
- `error` и `uncertain` не могут иметь `confirmed_segments`;
- правильная категория допустима только для `wrong_category`;
- нельзя одновременно задать `expected_segment_id` и `expected_segment_missing=true`.

Raw-текст, телефон, username автора и ссылки в feedback не сохраняются. Используется маскированный текст.

## 5. Создание item и callback

Sender перед отправкой тестеру делает idempotent `get_or_create_feedback_item()` и получает `public_token`. Ошибка создания item не блокирует лид: уведомление отправляется без экспериментальных кнопок, а ошибка логируется.

Callback:

```text
mf:v1:<action>:<public_token>
```

Callback не содержит chat username, message ID или текст и обязан укладываться в лимит Telegram 64 bytes.

Обработчик проверяет:

- feature flag;
- tester allowlist;
- совпадение владельца item;
- текущий `test_batch`;
- существование segment при выборе правильной категории.

Двойной клик и повторная доставка не создают дубликаты. Последнее подтверждённое действие становится текущей оценкой.

## 6. Snapshot качества

Snapshot нельзя убирать ради упрощения: без него невозможно понять, какой слой ошибся после изменения профилей или ключей.

До sender payload должны доходить:

- доставленные сегменты;
- rule candidates;
- сегменты после reality;
- legacy LLM verdict/segments;
- v2 intent и per-segment verdicts;
- model, prompt/schema versions;
- версии профилей.

Если часть данных отсутствует, item всё равно сохраняется, но получает `snapshot_missing` в диагностике и не используется для решений о blocking без ручной проверки.

## 7. Аналитика без отдельной экспериментальной платформы

Нужны:

- API summary по `test_batch`;
- per-segment precision и причины ошибок;
- confusion matrix `delivered → expected`;
- фильтры verdict/reason/segment;
- простой экран в существующей админке;
- CSV и JSONL export.

Метрики:

- delivered items;
- rated coverage;
- `correct`, `error`, `uncertain`;
- precision = `correct / (correct + error)`;
- uncertain rate;
- reasons distribution;
- precision по сегментам;
- confusion matrix;
- breakdown по model/prompt/schema/profile version;
- legacy LLM против v2;
- missing snapshot.

При multi-segment уведомлении выбранные `confirmed_segments` получают correct. Остальные доставленные сегменты получают ошибку распределения и создают confusion edges к подтверждённым правильным сегментам. Message-level причины относятся ко всем доставленным сегментам.

## 8. Gold export

В gold входят:

- `correct`;
- `error` с причиной;
- `wrong_category` с expected segment — для category-training;
- `wrong_category` без expected segment — только для intent/filter evaluation.

Не входят:

- `uncertain`;
- неоценённые items;
- legacy feedback другого batch;
- raw PII;
- snapshot с неизвестной версией без ручной проверки.

Export не применяет изменения автоматически. Любые правки keywords/LLM-профилей проходят review, offline eval и staged rollout.

## 9. Recall-контроль

Feedback доставленных уведомлений измеряет precision, но не показывает пропущенные лиды. Каждый batch поэтому включает отдельную ручную recall-выборку:

- 50 случайных сообщений из `stats:unmatched`;
- 50 сообщений, отклонённых legacy или v2 LLM;
- дедупликация и только masked text;
- ручные поля `missed_lead`, `expected_segment`, `missed_at_layer`.

Recall-аудит использует существующий eval/tooling, не создаёт runtime-таблицу и сохраняется как версионируемый артефакт в `docs/eval/`.

## 10. Quality gates

Перед выводом по сегменту:

- минимум 30 оценок `correct + error`;
- `uncertain` не входит в знаменатель;
- missing snapshot разобран вручную;
- wrong-category примеры по возможности имеют expected segment.

Для первой blocking-волны:

- observed precision ≥85%;
- wrong category ≤5%;
- сумма `provider_offer`, `job_vacancy`, `job_search`, `social_request`, `discussion_news` ≤10%;
- v2 fail-open ≤5%;
- нет критической ошибки дедупликации или географии.
- recall-выборка не выявила систематического пропуска целевых запросов.

Недостаточная выборка означает «решение не принято».

## 11. Тестирование категориями

У Business доступно до 12 подкатегорий одновременно. Для понятного анализа тестер подключает 5–10 сегментов одной волной:

1. Подписаться через обычный flow бота.
2. Собирать разметку до достаточной выборки.
3. Экспортировать и проанализировать batch.
4. Удалить подписки первой волны.
5. Подключить следующую волну.

Повышать лимит Business до 71 для теста не требуется: одновременная подписка на весь каталог ухудшит диагностируемость.

## 12. Надёжность

- Feedback DB failure не блокирует доставку.
- Telegram edit failure не откатывает сохранённую оценку.
- Удалённое уведомление не удаляет feedback.
- Устаревший или чужой token возвращает локализованное нейтральное сообщение.
- Logs и Sentry не содержат raw text, PII и полный token.
- RU/EN locale schema сохраняется, хотя первая волна русская.
- Миграция имеет рабочий downgrade.
- Legacy users, Free paywall и paid contact buttons не меняются.

## 13. Rollout

1. Реализовать схему и UI с feature flag OFF.
2. Проверить upgrade/downgrade на отдельной БД.
3. В staging включить только Telegram ID владельца.
4. Smoke: `correct`, `provider_offer`, `wrong_category`, изменение ответа.
5. В production включать feedback только после backup и контролируемого deploy-окна с остановленным worker по `OPERATIONS.md`.
6. Начать `ru_matching_v1`.
7. Откат интерфейса: `MATCHING_FEEDBACK_ENABLED=false`; данные сохраняются.

Эта задача не включает включение segment-aware LLM blocking.

## 14. Критерии готовности

- Все verdict/reason сценарии сохраняются и изменяются.
- Wrong category позволяет указать правильную подкатегорию.
- Multi-match позволяет выбрать фактически правильные доставленные сегменты.
- Callback data ≤64 bytes.
- Одна запись на message/user/batch.
- Snapshot достаточен для layer attribution.
- Uncertain исключён из precision/gold.
- Analytics и export воспроизводимы.
- Для batch существуют precision-разметка и отдельная recall-выборка.
- Новый UI видит только tester allowlist.
- Feedback failure не влияет на доставку.
- Privacy, RU/EN, migration, tests и CI проходят.
- Production blocking не включён.
