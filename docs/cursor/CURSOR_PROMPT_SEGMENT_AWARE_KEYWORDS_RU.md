# Prompt для Cursor/Grok 4.5 — segment-aware keywords и LLM-фильтр

Скопируй весь текст этого документа в новый Cursor chat, открытый в корне репозитория LeadHunter.

---

## Роль и цель

Ты работаешь как senior Python engineer, NLP engineer и reviewer production-системы LeadHunter.

Нужно безопасно реализовать русское семантическое ядро и segment-aware LLM-валидацию для 71 подкатегории.

Бизнес-цель:

- находить сообщения потенциальных клиентов;
- отличать клиентский спрос от рекламы поставщика;
- отличать разовый заказ от вакансии;
- отличать коммерческий запрос от социального общения, новостей и обсуждений;
- учитывать, кто является лидом для конкретного сегмента: покупатель, заказчик или продавец;
- уменьшить ложные уведомления без необъяснимой потери полезных лидов.

Спецификация профилей:

`docs/semantic/keyword_profiles_ru_v1.md`

Не воспринимай Markdown как runtime-источник данных. Это утверждаемая человеком спецификация. Runtime-источником истины должны остаться PostgreSQL и админ-панель `/catalog`.

## Обязательные ограничения

1. Сначала прочитай полностью:

   - `AGENTS.md`;
   - `CODING_STYLE.md`;
   - `TESTING.md`;
   - `RECOVERY.md`;
   - `OPERATIONS.md`;
   - `fable_core_plan.md`;
   - `docs/semantic/keyword_profiles_ru_v1.md`;
   - последние записи `docs/SESSION_LOG.md`.

2. На первом проходе ничего не меняй.
3. Сначала проведи read-only аудит и подготовь точный план файлов.
4. Остановись после плана и дождись подтверждения владельца.
5. Не подключайся к production-БД.
6. Не применяй миграции и keyword batches в production.
7. Не перезапускай production worker.
8. Не запускай второй polling-worker.
9. Перед изменением `poller.py`, `classifier.py`, `pool.py` или rate-limiter перечитай Hard Rules и checklist в `OPERATIONS.md`.
10. Любая миграция должна иметь рабочий `downgrade()`.
11. Перед production-миграцией обязателен `pg_dump`, но сам production-деплой не входит в эту задачу.
12. Реализация выполняется маленькими фазами. После каждой фазы проект должен запускаться.
13. Сначала тест, затем минимальная реализация.
14. Не добавляй зависимости без доказанной необходимости.
15. Не создавай второй источник истины для тарифов, сегментов или ключевых слов.
16. Не загружай автоматически все фразы из Markdown в БД.
17. Не делай один отдельный LLM prompt на каждую из 71 подкатегорий.
18. Не помещай профили всех 71 подкатегорий в каждый LLM-запрос.
19. Не разрешай fail-closed: ошибка LLM не должна молча уничтожать лид.
20. Не считай зелёный unit-test доказательством качества семантического ядра без offline-eval.

## Текущее состояние, которое нужно проверить

Перед реализацией подтверди по коду:

- rule-based classifier работает как wide-recall стадия;
- reality-фильтр использует synonym/domain words;
- LLM работает в blocking-режиме;
- `DEMAND` и `MIXED` проходят;
- `OFFER` и `OTHER` блокируются только с высокой уверенностью;
- ошибки LLM работают fail-open;
- supply-сегменты загружаются через `segments.lead_direction`;
- LLM verdict cache сейчас зависит только от текста;
- короткие сообщения с `ищу`, `нужен`, `требуется`, `куплю` могут обходить LLM;
- batch-файлы 23.07 содержат автоматически сгенерированные фразы и не должны считаться утверждённым словарём.

Если фактический код отличается, используй фактическое состояние и явно опиши расхождение.

---

# Целевая архитектура

Используй один универсальный LLM-validator и динамические профили только для candidate segments конкретного сообщения.

```text
Telegram message
    ↓
wide-recall rule classifier
    ↓
candidate_segments
    ↓
reality filter
    ↓
load compact profiles for candidate_segments
    ↓
single batched LLM request
    ↓
per-segment decisions
    ↓
delivery / reject / fail-open
```

## Общий LLM intent

LLM должен различать:

- `commercial_demand` — клиент хочет купить или заказать;
- `provider_offer` — поставщик рекламирует или продаёт;
- `job_vacancy` — работодатель ищет сотрудника в штат;
- `job_search` — специалист ищет работу или заказы;
- `social_request` — партнёр для игры, попутчик, бесплатное сообщество;
- `discussion` — вопрос без коммерческого действия, новость, отзыв, обсуждение;
- `irrelevant` — сегмент не относится к сообщению;
- `mixed` — в сообщении есть коммерческий спрос и посторонняя информация.

## Решение должно приниматься отдельно по каждому candidate segment

Пример:

```json
{
  "index": 0,
  "segments": [
    {
      "slug": "tennis",
      "decision": "reject",
      "intent": "social_request",
      "certainty": "high",
      "reason_code": "looking_for_play_partner",
      "reason": "Автор ищет партнёра для игры, а не платного тренера или корт"
    }
  ]
}
```

Для одного и того же сообщения один сегмент может быть принят, а другой отклонён.

## Профиль подкатегории

Предпочтительный Python-интерфейс:

```python
from dataclasses import dataclass
from enum import StrEnum


class LLMDecision(StrEnum):
    ACCEPT = "accept"
    REJECT = "reject"


class CommercialIntent(StrEnum):
    COMMERCIAL_DEMAND = "commercial_demand"
    PROVIDER_OFFER = "provider_offer"
    JOB_VACANCY = "job_vacancy"
    JOB_SEARCH = "job_search"
    SOCIAL_REQUEST = "social_request"
    DISCUSSION = "discussion"
    IRRELEVANT = "irrelevant"
    MIXED = "mixed"


@dataclass(frozen=True, slots=True)
class SegmentLLMProfile:
    segment_slug: str
    locale: str
    target_lead: str
    accept_examples: tuple[str, ...]
    reject_examples: tuple[str, ...]
    conflict_slugs: tuple[str, ...]
    requires_llm: bool
    version: int


@dataclass(frozen=True, slots=True)
class SegmentVerdict:
    segment_slug: str
    decision: LLMDecision
    intent: CommercialIntent
    certainty: str
    reason_code: str
    reason: str
```

Имена можно скорректировать только если существующая архитектура требует другого соглашения. В отчёте объясни каждое изменение интерфейса.

## Хранение

Создай отдельную сущность профиля с отношением один-к-одному к `segments`.

Предпочтительная таблица:

```text
segment_llm_profiles
    id
    segment_id               UNIQUE FK segments.id ON DELETE CASCADE
    locale                   VARCHAR(10), default ru
    target_lead              TEXT NOT NULL
    accept_examples          JSONB NOT NULL
    reject_examples          JSONB NOT NULL
    conflict_slugs           JSONB NOT NULL
    requires_llm             BOOLEAN NOT NULL DEFAULT true
    version                  INTEGER NOT NULL DEFAULT 1
    created_at
    updated_at
```

Добавь уникальность `(segment_id, locale)`, если требуется несколько языков.

Профиль не должен дублировать:

- `segments.lead_direction`;
- `segment_keywords`;
- titles категорий и сегментов.

`demand`, `stop`, `synonym` остаются в `segment_keywords`.

## Runtime cache

Профили должны загружаться вместе с каталогом или тем же reload-циклом, что и keywords.

Runtime lookup:

```python
Mapping[str, SegmentLLMProfile]
```

Если профиль отсутствует:

- не падать;
- использовать универсальный prompt;
- зафиксировать метрику `profile_missing`;
- работать fail-open при неуверенном результате.

## LLM cache v2

Новый ключ должен учитывать:

```text
normalized_text
sorted_candidate_segments
lead_direction for each candidate
profile version for each candidate
system prompt version
response schema version
model name
```

Пример логического payload:

```json
{
  "text": "ищу тренера по теннису",
  "candidates": [
    {
      "slug": "tennis",
      "lead_direction": "demand",
      "profile_version": 1
    }
  ],
  "prompt_version": 2,
  "schema_version": 2,
  "model": "deepseek-chat"
}
```

Сериализуй детерминированно через sorted keys и хэшируй SHA-256.

Не читай старый text-only cache как v2. Используй новый namespace, например:

```text
llm:v2:verdict:{sha256}
```

## High-confidence bypass

Безопасный вариант для первой версии:

- если хотя бы один candidate segment имеет `requires_llm=true`, сообщение идёт в LLM;
- bypass разрешается только если все кандидаты имеют `requires_llm=false`;
- до получения eval-данных все новые профили создаются с `requires_llm=true`.

Перед bypass всё равно проверять:

- `вакансия`;
- `зарплата`;
- `график`;
- `смена`;
- `в штат`;
- `ищу работу`;
- `возьму заказы`;
- `ищу партнёра`;
- `кто хочет поиграть`;
- `предлагаю`;
- `оказываю услуги`;
- `открыта запись`;
- `набираю клиентов`;
- `продам/куплю` с учётом `lead_direction`.

Нельзя просто расширить один regex и объявить задачу решённой. Поведение должно быть покрыто segment-aware тестами.

---

# План реализации

## Фаза 0. Read-only аудит

### Цель

Подтвердить фактические интерфейсы и минимальный список изменений.

### Проверить

- `app/userbot/classifier.py`;
- `app/userbot/llm_validator.py`;
- `app/userbot/poller.py`;
- `app/db/models.py`;
- `app/db/crud.py`;
- `app/admin/api/`;
- каталог admin frontend;
- Alembic revisions;
- `tools/eval_matching.py`;
- keyword-quality tools и fixtures;
- LLM, classifier, cache и catalog tests.

### Отчёт до кода

Подготовь:

1. текущий data flow;
2. места обхода LLM;
3. текущую схему LLM response;
4. текущий cache payload;
5. способ reload профилей;
6. точные файлы Create/Modify/Test;
7. риски Telegram API;
8. риски миграции;
9. план совместимости со старым LLM result;
10. план rollback.

После отчёта остановись.

---

## Фаза 1. Модель профиля и миграция

### Предполагаемые файлы

- Modify: `app/db/models.py`
- Modify: `app/db/crud.py`
- Create: `migrations/versions/segment_profiles01.py` с `revision = "segment_profiles01"` после проверки актуального Alembic head
- Create: `tests/test_segment_llm_profiles.py`

### Требования

- миграция обратимая;
- таблица пустая после migration;
- никакого автоматического заполнения production;
- JSON-поля проверяются как списки непустых строк;
- locale нормализуется;
- version положительная;
- foreign key и unique constraint работают;
- удаление сегмента каскадно удаляет профиль.

### TDD

Сначала написать тесты:

- создание профиля;
- уникальность segment+locale;
- обновление повышает version;
- пустой target запрещён;
- некорректный JSON запрещён в CRUD;
- cascade delete;
- downgrade удаляет только новую таблицу.

### Gate

```bash
pytest -q tests/test_segment_llm_profiles.py
alembic upgrade head
alembic downgrade -1
alembic upgrade head
```

Все команды выполняются только в isolated dev environment.

---

## Фаза 2. Импорт утверждённых профилей без production apply

### Предполагаемые файлы

- Create: `seed/segment_llm_profiles_ru.py` или структурированный JSON рядом с seed
- Create: `tools/validate_segment_profiles.py`
- Create: `tests/fixtures/segment_llm_profiles_ru.json`
- Create: `tests/test_segment_profile_seed.py`

### Требования

1. Перенеси из `docs/semantic/keyword_profiles_ru_v1.md` только:

   - slug;
   - target lead;
   - LLM accept;
   - LLM reject;
   - conflicts;
   - locale;
   - version;
   - requires_llm.

2. Не парси Markdown в runtime.
3. Не применяй seed автоматически.
4. Инструмент должен иметь режимы:

```text
--validate-only
--dry-run
--apply
--rollback-manifest
```

5. `--apply` требует явного environment guard и не должен работать с production-конфигурацией по умолчанию.
6. Каждая запись должна иметь минимум один accept и один reject.
7. Все conflict slugs должны существовать.
8. Все 71 активный slug должны присутствовать ровно один раз.
9. Profile version начинается с `1`.
10. Все профили первой версии имеют `requires_llm=true`.

### Gate

```bash
python tools/validate_segment_profiles.py --validate-only
pytest -q tests/test_segment_profile_seed.py
```

Ожидается:

```text
71 profiles valid
0 missing segments
0 duplicate segment+locale pairs
0 unknown conflict slugs
```

---

## Фаза 3. Runtime loader

### Предполагаемые файлы

- Create: `app/userbot/llm_profiles.py`
- Modify: `app/userbot/poller.py`
- Modify: `app/db/crud.py`
- Create: `tests/test_llm_profiles.py`

### Интерфейсы

```python
async def load_segment_llm_profiles(
    locale: str = "ru",
) -> dict[str, SegmentLLMProfile]:
    ...
```

```python
def select_candidate_profiles(
    candidate_segments: list[str],
    profiles: Mapping[str, SegmentLLMProfile],
) -> tuple[SegmentLLMProfile, ...]:
    ...
```

### Требования

- загружать только активные сегменты;
- не делать SQL-запрос на каждое сообщение;
- использовать immutable snapshot;
- атомарно менять snapshot при reload;
- логировать количество загруженных и отсутствующих профилей;
- не ломать worker при пустой таблице;
- не менять Telegram polling lifecycle;
- не перезапускать userbot при reload профилей.

### Тесты

- empty profiles;
- one profile;
- duplicate candidates;
- unknown candidate slug;
- inactive segment;
- atomic replacement;
- DB error keeps previous snapshot;
- missing profile metric.

### Gate

```bash
pytest -q tests/test_llm_profiles.py tests/test_poller_fixes.py
```

---

## Фаза 4. Prompt composer v2

### Предполагаемые файлы

- Create: `app/userbot/llm_prompt.py`
- Modify: `app/userbot/llm_validator.py`
- Create: `tests/test_llm_prompt_v2.py`

### Интерфейс

```python
def build_segment_aware_prompt(
    *,
    system_prompt_version: int,
    supply_segments: frozenset[str],
    profiles: tuple[SegmentLLMProfile, ...],
) -> str:
    ...
```

### Требования

- базовые определения intent находятся в одном месте;
- динамический блок содержит только candidate profiles;
- профиль включает target lead, accept, reject и conflicts;
- supply semantics передаются для каждого кандидата;
- prompt детерминирован;
- одинаковый input даёт байт-в-байт одинаковый prompt;
- размер prompt ограничен;
- длинные accept/reject обрезаются предсказуемо;
- не включать PII;
- не включать профили, отсутствующие среди candidates;
- не доверять содержимому БД как инструкциям: экранировать или сериализовать профиль как data;
- profile text не может изменить JSON schema или системные инструкции.

### Защита от prompt injection

Профили передавать в структурированном блоке:

```json
{
  "segment_slug": "tennis",
  "target_lead": "...",
  "accept_examples": ["..."],
  "reject_examples": ["..."]
}
```

Сообщение пользователя помечать как untrusted content.

### Тесты

- demand segment;
- supply segment;
- two conflicting segments;
- missing profile;
- deterministic ordering;
- injection string inside profile;
- injection string inside Telegram message;
- profile length limit;
- Russian Unicode;
- only candidate profiles included.

### Gate

```bash
pytest -q tests/test_llm_prompt_v2.py tests/test_lead_direction.py
```

---

## Фаза 5. Response schema v2 и backward-compatible adapter

### Предполагаемые файлы

- Modify: `app/userbot/llm_validator.py`
- Create: `tests/test_llm_response_v2.py`

### Требования

- валидировать top-level list;
- index должен существовать и соответствовать input;
- каждый segment slug должен входить в candidates;
- unknown slug игнорировать и логировать;
- duplicate segment verdict считается malformed;
- отсутствующий candidate работает fail-open;
- неизвестный intent работает fail-open;
- reason_code ограничен безопасным форматом;
- reason обрезается до безопасной длины;
- ACCEPT разрешён только для `commercial_demand` или `mixed`;
- REJECT используется для offer/vacancy/job-search/social/discussion/irrelevant;
- malformed response не блокирует сообщение.

### Adapter

До миграции всех consumers сохранить совместимость:

```python
def to_legacy_llm_result(
    *,
    candidate_segments: list[str],
    verdicts: list[SegmentVerdict],
) -> LLMResult:
    ...
```

`relevant_segments` содержит принятые сегменты. Если по кандидату нет валидного ответа, он остаётся релевантным по fail-open.

### Gate

```bash
pytest -q tests/test_llm_response_v2.py tests/test_llm_validator.py
```

---

## Фаза 6. Cache key v2

### Предполагаемые файлы

- Modify: `app/userbot/llm_validator.py`
- Create: `tests/test_llm_cache_v2.py`

### Интерфейс

```python
def build_llm_cache_key(
    *,
    text: str,
    candidate_segments: tuple[str, ...],
    lead_directions: Mapping[str, str],
    profile_versions: Mapping[str, int],
    prompt_version: int,
    schema_version: int,
    model_name: str,
) -> str:
    ...
```

### Тесты

- candidate order does not change key;
- different candidate changes key;
- different lead_direction changes key;
- different profile version changes key;
- prompt version changes key;
- schema version changes key;
- model changes key;
- whitespace/case normalization remains deterministic;
- no raw message text in Redis key;
- old namespace is not reused.

### Gate

```bash
pytest -q tests/test_llm_cache_v2.py tests/test_b5_llm_cache.py
```

---

## Фаза 7. Безопасный high-confidence gate

### Предполагаемые файлы

- Modify: `app/userbot/llm_validator.py`
- Create: `tests/test_segment_aware_bypass.py`

### Интерфейс

```python
def may_bypass_llm(
    *,
    text: str,
    candidate_segments: tuple[str, ...],
    profiles: Mapping[str, SegmentLLMProfile],
    lead_directions: Mapping[str, str],
) -> bool:
    ...
```

### Требования первой версии

- профиль отсутствует → `False`;
- `requires_llm=true` → `False`;
- несколько кандидатов и хотя бы один требует LLM → `False`;
- vacancy markers → `False`;
- job-search markers → `False`;
- social markers → `False`;
- provider markers → `False`;
- buy/sell verb конфликтует с lead_direction → `False`;
- emoji в начале не должен ломать анализ;
- только доказанный безопасный случай возвращает `True`.

### Обязательные регрессии

```text
ищу партнёра по теннису
кто хочет поиграть в футбол
требуется курьер в штат
нужен бухгалтер на разовую консультацию
ищу работу бухгалтером
продам байк
куплю байк
предлагаю услуги клининга
🤖 ищем подрядчика для автоматизации
```

Для каждого примера проверить разные candidate segments и lead directions.

### Gate

```bash
pytest -q tests/test_segment_aware_bypass.py tests/test_llm_validator.py
```

---

## Фаза 8. Shadow mode

### Предполагаемые файлы

- Modify: `app/config.py`
- Modify: `app/userbot/llm_validator.py`
- Modify: `app/userbot/poller.py`
- Modify: `.env.example`
- Create: `tests/test_segment_llm_shadow.py`

### Конфигурация

Добавить отдельный режим v2:

```text
LLM_SEGMENT_PROFILES_ENABLED=false
LLM_SEGMENT_PROFILES_BLOCKING=false
LLM_PROMPT_VERSION=2
LLM_RESPONSE_SCHEMA_VERSION=2
```

Точные имена согласовать с текущим стилем settings.

### Поведение

- enabled=false: старое поведение без изменений;
- enabled=true, blocking=false: v2 вызывается и логируется, но delivery решает старый pipeline;
- enabled=true, blocking=true: v2 влияет на relevant_segments;
- ошибка v2 не меняет delivery;
- старые и новые решения связываются одним correlation id.

### Метрики

Минимально:

```text
llm_v2_total
llm_v2_accept
llm_v2_reject
llm_v2_fail_open
llm_v2_profile_missing
llm_v2_disagreement_old_accept_new_reject
llm_v2_disagreement_old_reject_new_accept
llm_v2_intent_{intent}
llm_v2_segment_{slug}_accept
llm_v2_segment_{slug}_reject
```

Не создавать неконтролируемую cardinality по raw reason или message text.

### Gate

```bash
pytest -q tests/test_segment_llm_shadow.py tests/test_llm_blocking_mode.py
```

---

## Фаза 9. Offline golden corpus

### Предполагаемые файлы

- Create: `tests/fixtures/segment_llm_profiles_ru_cases.json`
- Create: `tests/test_segment_llm_profiles_ru_cases.py`
- Modify: `tools/eval_matching.py` или создать отдельный focused eval tool
- Create: `docs/eval/segment_profiles_ru_baseline.md`

### Минимальная структура case

```json
{
  "id": "tennis-social-001",
  "segment": "tennis",
  "text": "ищу партнёра поиграть завтра",
  "expected_intent": "social_request",
  "expected_decision": "reject",
  "origin": "synthetic",
  "notes": "Не является запросом тренера или аренды корта"
}
```

### Обязательный минимум

Для каждой из 71 подкатегории:

- минимум 2 accept;
- минимум 2 reject;
- минимум 1 collision case;
- минимум 1 offer;
- минимум 1 vacancy/job-search case, если применимо.

Общее количество — не менее 350 cases.

Synthetic cases не выдавать за production evidence. Поле `origin` обязательно:

```text
synthetic
bounded_real
feedback
llm_decision
unmatched
```

### Метрики

- precision/recall по сегментам;
- macro average;
- confusion pairs;
- false negatives;
- old vs v2 disagreement;
- latency;
- prompt tokens;
- completion tokens;
- estimated cost;
- cache hit rate.

### Release-gates

- overall precision ≥ 75%;
- overall recall ≥ 80%;
- ни один сегмент не включается в blocking при precision < 60%;
- zero lost liked leads;
- fail-open rate в нормальном окружении < 5%;
- all profile accept examples pass;
- all profile reject examples reject;
- каждый regression объясним.

### Gate

```bash
pytest -q tests/test_segment_llm_profiles_ru_cases.py
python tools/eval_matching.py
```

Не включать blocking, если gates не выполнены.

---

## Фаза 10. Admin CRUD профилей

### Предполагаемые backend-файлы

- Modify/Create: `app/admin/api/` catalog profile endpoints
- Modify: `app/db/crud.py`
- Create: backend tests для profile CRUD

### Предполагаемые frontend-файлы

- каталог admin frontend;
- API types;
- React Query hooks;
- profile editor;
- profile diff/preview.

### Требования

Администратор может:

- видеть target lead;
- редактировать accept/reject examples;
- видеть conflicts;
- менять `requires_llm`;
- видеть profile version;
- сохранить draft;
- запустить preview на одном сообщении;
- увидеть diff;
- опубликовать;
- откатить предыдущую версию.

Опасные действия требуют подтверждения.

Audit log должен сохранять:

- admin;
- segment;
- before;
- after;
- timestamp;
- reason;
- version.

Нельзя позволять admin-тексту внедрять system instructions. Backend валидирует размер, количество и формат примеров.

### Gate

```bash
pytest -q tests/test_admin_segment_llm_profiles.py
cd admin-panel
npm run lint
npm run build
```

Используй фактический путь frontend после read-only аудита.

---

## Фаза 11. Управляемое включение

### Порядок

1. Dev tests.
2. Staging migration.
3. Импорт 71 профилей только в staging.
4. Shadow mode минимум 72 часа.
5. Review disagreements.
6. Исправление профилей и golden cases.
7. Blocking только для 3–5 лучших сегментов.
8. Наблюдение минимум 7 дней.
9. Следующая группа 3–5 сегментов.

### Первая рекомендуемая группа

- `cleaning`;
- `plumber`;
- `electrician`;
- `accountant`;
- `lawyer`.

Причина: ясный коммерческий intent и хорошо различимые provider/job patterns.

### Не включать первой группой

- buy/supply транспорт;
- спорт;
- `pets`;
- `design`;
- `travel-agent`;
- `currency-exchange`.

У них выше ambiguity или compliance-риск.

### Rollback

Rollback blocking не должен требовать миграции:

```text
LLM_SEGMENT_PROFILES_BLOCKING=false
```

Профили и решения сохраняются для анализа.

---

# Keyword migration

После внедрения профилей не загружай весь Markdown одним batch.

Для каждой группы 3–5 сегментов:

1. экспортировать текущие active keywords;
2. подготовить diff;
3. удалить грамматически ошибочные auto-drafted additions;
4. добавить только вручную утверждённые фразы;
5. сформировать apply manifest;
6. сформировать точный rollback;
7. запустить offline eval;
8. получить подтверждение владельца;
9. только после этого планировать production apply.

Типы:

```text
demand      — естественная клиентская фраза
stop        — однозначный provider/job/social шум конкретного сегмента
synonym     — нормальная лемма предмета сегмента
```

`domain_contextual` из Markdown не загружать как обычный synonym без отдельной runtime-семантики. В первой версии использовать его только внутри LLM-профиля или оставить вне БД.

---

# Обязательные review-вопросы

Перед завершением каждой фазы ответь:

1. Может ли изменение потерять настоящий лид?
2. Может ли одинаковый текст дать разный результат для другого candidate segment?
3. Учтён ли `lead_direction`?
4. Может ли вакансия пройти как заказ?
5. Может ли social request пройти как коммерческий лид?
6. Может ли provider offer пройти из-за цены или контакта?
7. Есть ли безопасный fail-open?
8. Инвалидируется ли кэш после изменения профиля?
9. Есть ли rollback?
10. Есть ли per-segment тест?
11. Есть ли collision test?
12. Не был ли автоматически затронут production?

---

# Формат отчёта после каждой фазы

```markdown
## Фаза N — название

### Изменено
- файл: назначение изменения

### Тесты
- команда
- фактический результат

### Не изменено
- production
- worker
- production DB

### Риски
- риск
- способ контроля

### Rollback
- точное действие

### Ручной QA
- шаг
- ожидаемый результат

### Следующий gate
- что должен подтвердить владелец
```

---

# Первый ответ Cursor

В первом ответе:

1. Подтверди, какие документы прочитаны.
2. Покажи фактический текущий pipeline.
3. Перечисли найденные расхождения с этим prompt.
4. Предложи точный file map Фазы 1.
5. Перечисли тесты Фазы 1.
6. Опиши миграцию и downgrade.
7. Опиши rollback.
8. Остановись.

Не пиши код до подтверждения владельца.
