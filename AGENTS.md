# AGENTS.md — контекст проекта для Codex

Этот файл Codex читает автоматически в начале каждой сессии. Содержит всё критичное для продолжения работы. Остальное — в сопровождающих файлах (см. ссылки ниже).

**Сопровождающие файлы:**
- `CODING_STYLE.md` — конвенции кода (обязательно к соблюдению)
- `TESTING.md` — стратегия тестирования + QA checklist
- `RECOVERY.md` — план восстановления (читать при любой поломке)
- `OPERATIONS.md` — правила эксплуатации: rate limits, защита от бана, безопасные конфиги
- `USERFLOW.md` — карта экранов, полные тексты RU+EN (⚠️ меню в боте с 30.06 — 4 кнопки, не 9)
- `DECISIONS.md` — полный архив 80 зафиксированных решений
- `fable_audit.md` — закрытый план аудита ядра (фазы 0/A/B/C/D) + чек-лист живого переключения прода
- `fable_core_plan.md` — АКТИВНЫЙ план работ (качество ядра матчинга)
- `docs/SESSION_LOG.md` — полный журнал сессий (записи о задачах — туда)
- Семантическое ядро (категории/keywords): источник истины — БД (`segments`, `segment_keywords`) + админка `/catalog`. Исторический файл segment_seed.md — в `docs/archive/2026-07/`.

---

## 0. Правила разработки (обязательно к соблюдению)

- **Анализ до реализации** — Запрещено гадать. Если что-то неясно — задавай уточняющие вопросы.
- **Минимализм** — Код только для текущей задачи. Никаких заделов на будущее без явной просьбы.
- **Точечные изменения** — Только целевой код. Не трогать соседние функции. Удалил функционал — удали ставшие ненужными зависимости.
- **Сложные задачи — композиция** — План: действие + метод проверки результата.
- **Маленькие шаги** — После каждого изменения проект должен запускаться.
- **Перед фазой:** план файлов → подтверждение → код.
- **Каждая фаза:** git commit + тег `phase-N-done`.
- **После фазы:** запустить `/skill:phase-review` — автоматические тесты + code review.
- **Стиль кода:** `CODING_STYLE.md`.
- **Тестирование:** `TESTING.md` (обязательно с Фазы 2).
- **При поломке:** `RECOVERY.md`.
- **Секреты:** только в `.env`.
- **Защита от бана Telegram:** `OPERATIONS.md` — перед ЛЮБЫМ изменением в `poller.py`, `rate_limiter.py`, `classifier.py` или `pool.py` — прочитать §2 (Hard Rules) и §5 (чек-лист). После деплоя — 2 минуты мониторить логи на `FloodWait`. При любом инциденте с Telegram API — немедленно задокументировать в `OPERATIONS.md`: причина, хронология, урок, новые правила/запреты.
- **НЕ трогать прод при работающем worker:** запрещено запускать `docker compose run/exec/restart/up -d` при работающем `worker` в проде. Тесты и миграции — ТОЛЬКО при остановленном worker, либо в отдельном dev-окружении. Вмешательство в работающий прод (пересоздание контейнера, изменение окружения, применение миграций) создаёт двойную нагрузку на Telegram API (реконнект + поллинг) и риск бана.
- **Session log (обязательно):** после КАЖДОЙ задачи — дописать краткую запись в конец `docs/SESSION_LOG.md` в формате: `**DD.MM.YYYY HH:MM — Что сделано.** Результат. Ошибки/уроки.` — и обновить краткий статус в `AGENTS.md §8`. Это обеспечивает контекст для следующей сессии. Без этой записи задача не считается завершённой.
- **Миграции:** обратимые (`downgrade()`), перед применением — `pg_dump`.

---

## 1. Что мы строим

SaaS-сервис на базе Telegram-бота. Отслеживает сообщения по ключевым словам в публичных каналах и присылает уведомления пользователям. Freemium-модель.

**Userbot** (Telethon/MTProto) слушает каналы, **Bot API** (aiogram) отправляет уведомления и управляет интерфейсом.

### Тарифы (v2.1, решение #82 — 14.07.2026)

**Метрика ценности — широта покрытия (направления × география), НЕ количество уведомлений.** Дневной лимит уведомлений отменён на всех тарифах. Полный план перехода — `fable_tariff_plan.md`.

| | Free (воронка) | 🎯 Старт ($9/мес) | 🚀 Профи ($19/мес) | 🏆 Бизнес ($39/мес) |
|---|---|---|---|---|
| Матчинг | безлимитный | безлимитный | безлимитный | безлимитный |
| Уведомлений/день | безлимит | безлимит | безлимит | безлимит |
| Направления (подкатегории) | 1 | 1 | 3 | 12 |
| География | 1 страна, города без лимита | 1 страна, города без лимита | до 3 стран, города без лимита | до 9 стран, города без лимита |
| Свои каналы | 1 | 1 | 10 | 50 |
| Ключевых фраз | 1 | 3 | 20 | 50 |
| Контакты | СКРЫТЫ | Полные | Полные | Полные |
| Кнопки | «🎯 Открыть контакты» | «💬 Ответить» | «💬 Ответить» | «💬 Ответить» |
| Regex | — | — | отложено | отложено |
| Статистика в боте | — | — | базовая (7 дн.) | полная (30 дн., по сегментам) |
| CSV-экспорт | — | — | — | да |
| Digest-режим | да | да | да | да |
| Trial | — | — | 3 дня; 7 дней по referral | — |
| End-of-day отчёт | да (19:00, «скрытые контакты») | — | — | — |

Скидки за период: 3 мес −10%, год −20%. Внутренние slug'и: `free`/`start`/`pro`/`business`/`trial`. Лимиты и цены задаются в `app/config.py` и при необходимости переопределяются через `.env`; runtime-источник истины — `_plan_limits()`.

### Trial и рефералы

- Trial: 3 дня Про после первого поиска. +4 дня по реферальной ссылке (итого 7).
- По истечении → Free сразу в `plan_expires_at`: контакты и ссылки скрыты, поиски сохраняются.
- Без подписки: максимум 2 скрытых teaser-лида и EOD-отчёт в дни 0/3/7/14; в день 30 — одноразовая скидка 25% на 3 месяца, 12 часов.
- Старые календарные weekly/niche/monthly сообщения Free отключены.
- После первой оплаты приглашённого referrer получает +10 дней текущего тарифа;
  на Free восстанавливается последний оплаченный тариф, а без истории — Start. Ограничение 10/мес.
- Механика: deep-link `t.me/LeadHunterBot?start=ref_CODE`.

### Оплата

Старт: Stars + CryptoBot. Позже: карты, QR СБП, YooKassa. Интерфейс `PaymentProvider` (Protocol). Фазы 1–5 без оплаты.

### Аудитория и i18n

Русскоязычная + международная. Тексты в `locales/ru.py`, `locales/en.py`. Выбор по `language_code`. Discovery: ru + en.

---

## 1а. User Flow (кратко)

**Принципы:** только inline-клавиатуры, все экраны с «◀️ Назад», FSM с `/cancel`. Картинки позже.

**Главное меню (5 кнопок, runtime):** 🔍 Поиск / Мои поиски | 📊 Результаты | 💰 Тариф | 🎁 Пригласить друга | ⚙️ Настройки (→ 6 подэкранов: ключевые слова, каналы, подписки, язык, о сервисе и др.). Команды `/keywords`, `/channels`, `/subscriptions`, `/plan`, `/settings`, `/search` открывают экраны напрямую.

**FSM-воронка:** направление (счётчик N/M) → страна → география (по всей стране / в городах) → города → подтверждение → триал/оплата. Free=1 сегмент, Pro=3, Business=∞.

**Форматы уведомлений:** Free — контакты скрыты, кнопка «🎯 Открыть контакты — от $9/мес». Paid (Старт/Профи/Бизнес/Trial) — полный формат с @отправителем и чатом, кнопки «💬 Ответить». 🔥 для срочных.

**Полная карта 21 экрана, все тексты RU+EN, пустые состояния, карта переходов → `USERFLOW.md`.**

---

## 2. Архитектура

```
Пользователи (Free / Pro / Business)
        │  Bot API
        ▼
┌─────────────────────── VPS (Docker Compose) ───────────────────────┐
│  [bot]      aiogram 3.x — управляющий бот, команды, платежи         │
│  [worker]   Telethon + sender — userbot + рассыльщик (один event loop)│
│  [admin]    FastAPI — админ-панель (React SPA + REST API, порт 8001)      │
│  [db]       PostgreSQL — пользователи, подписки, слова, каталог      │
│  [redis]    Redis — кэш подписок + очередь уведомлений               │
└─────────────────────────────────────────────────────────────────────┘
        │  userbot (MTProto)               │  Bot API
        ▼                                  ▼
   Публичные каналы                   Личные чаты пользователей
```

### Поток данных

```
userbot поллит каналы (тиры Hot/Warm/Cold, курсоры в Redis)
    │
    ▼
classify_message(text) ──→ ["catering", "cleaning"]   ← 1 раз на сообщение
    │  (или keyword_only-матч по личным keywords — минует сегменты и LLM)
    ▼
reality-фильтр (domain-слова, word-boundary) → LLM-валидатор (blocking, батч)
    │
    ▼
_dispatch → get_interested_users(chat_username)
    │  Redis-кэш sub:by_chat:{chat_username} + личные keywords
    ▼
Дедупликация: sha256(chat_username:message_id), UNIQUE(user_id, hash)
    │
    ▼
LPUSH queue:notifications → sender BRPOP + throttle → Bot API (retry/DLQ #26)
```

---

## 3. Технический стек

| Компонент | Технология |
|---|---|
| Python | 3.11+ |
| Бот | aiogram 3.x (Bot API) |
| Userbot | Telethon (MTProto) |
| ORM | SQLAlchemy 2.x (async) |
| Драйвер | asyncpg |
| HTTP | aiohttp |
| Миграции | Alembic |
| Кэш + очередь | Redis (LPUSH/BRPOP) |
| Админка | FastAPI + React 19 + Vite 8 + shadcn/ui 4 |
| Админ-UI | React 19, TypeScript, Vite 8, shadcn/ui 4, Tailwind 4, React Query 5, Chart.js 4 |
| Платежи | Stars, CryptoBot (PaymentProvider Protocol) |
| Конфиг | pydantic-settings (.env) |
| Мониторинг | Sentry |
| Тесты | pytest + pytest-asyncio |

Версии: `aiogram>=3.7,<4.0`, `telethon>=1.36,<2.0`, `SQLAlchemy>=2.0,<3.0`, `asyncpg>=0.29,<1.0`, `aiohttp>=3.9,<4.0`, `alembic>=1.13,<2.0`, `redis>=5.0,<6.0`, `fastapi>=0.110,<1.0`, `pydantic-settings>=2.2,<3.0`, `sentry-sdk>=2.0,<3.0`, `pytest>=8.0,<9.0`, `pytest-asyncio>=0.23,<1.0`

### Инфраструктура

- Docker Compose, Ubuntu 24.04, 2GB/1Core
- Memory limits: bot=300MB, worker=1GB (после OOM-инцидента; было 400MB), admin=200MB, postgres=400MB, redis=100MB
- Swap 2GB обязателен
- Admin: 127.0.0.1:8001 (SSH-туннель)
- Сессии userbot: `./sessions:/app/sessions` (bind-mount)

---

## 4. Структура репозитория

```
LeadHunter/
├── AGENTS.md                  ← этот файл (контекст)
├── DECISIONS.md               ← 80 зафиксированных решений
├── RECOVERY.md                ← план восстановления
├── CODING_STYLE.md / TESTING.md / OPERATIONS.md
├── USERFLOW.md                ← карта экранов, тексты RU+EN
├── ONBOARDING.md / SETUP.md   ← развёртывание с нуля
├── fable_audit.md             ← закрытый аудит + чек-лист переключения прода
├── fable_core_plan.md         ← активный план работ (качество ядра)
├── .env.example / .gitignore
├── docker-compose.yml / Dockerfile
├── requirements.txt / alembic.ini
├── migrations/
├── tests/                     ← conftest, unit, integration, smoke
├── seed/                      ← сиды каталога и keywords
├── tools/                     ← eval_matching.py (C1), диагностика
├── docs/                      ← SESSION_LOG.md, eval/, archive/
└── app/
    ├── config.py              ← pydantic-settings
    ├── main.py                ← точка входа бота
    ├── locales/               ← ru.py, en.py
    ├── bot/
    │   ├── handlers/          ← inline callback-хендлеры
    │   │   ├── start.py, keywords.py, channels.py, plan.py
    │   │   ├── discover.py, catalog_nav.py, feedback.py, support.py
    │   │   └── middlewares/   ← проверка подписки, лимитов
    ├── admin/                 ← FastAPI (REST API + WebSocket + static SPA)
    │   ├── app.py, api/, dashboard.py, chat.py, broadcast.py
    ├── db/
    │   ├── models.py, session.py, crud.py
    ├── userbot/
    │   ├── pool.py          ← пул аккаунтов (идентичность — USERBOT_SESSION_MAP, B1)
    │   ├── poller.py        ← умный поллинг каналов (без вступления, по tier'ам)
    │   ├── classifier.py    ← трёхпроходный NLP (предкомпилированный, B2)
    │   ├── llm_validator.py ← DeepSeek-V3 (ВКЛЮЧЁН, blocking)
    │   └── discovery.py / discovery_v2.py (выключены)
    ├── cache/subscription_cache.py
    ├── payments/              ← stars.py, cryptobot.py (PaymentProvider Protocol)
    └── worker/                ← tasks.py, sender.py, heartbeat.py, reminders.py,
                                 end_of_day.py, payment_checker.py, notify_admin.py
```

---

## 5. Модель данных (PostgreSQL)

```sql
users (
    id              BIGSERIAL PRIMARY KEY,
    telegram_id     BIGINT UNIQUE NOT NULL,
    username        VARCHAR(64),
    language        VARCHAR(10) DEFAULT 'ru',
    plan            VARCHAR(20) DEFAULT 'free',    -- free / pro / business
    plan_activated_at TIMESTAMPTZ,
    plan_expires_at   TIMESTAMPTZ,
    is_banned       BOOLEAN DEFAULT false,
    is_suspended    BOOLEAN DEFAULT false,
    suspended_until TIMESTAMPTZ,
    is_blocked_bot  BOOLEAN DEFAULT false,
    blocked_bot_at  TIMESTAMPTZ,
    source          VARCHAR(20) DEFAULT 'direct',  -- direct / referral / search / ad
    admin_note      TEXT,
    created_at      TIMESTAMPTZ DEFAULT now()
)

subscriptions (
    id              BIGSERIAL PRIMARY KEY,
    user_id         BIGINT REFERENCES users(id) ON DELETE CASCADE,
    plan            VARCHAR(20),
    period          VARCHAR(10),
    expires_at      TIMESTAMPTZ,
    payment_method  VARCHAR(20),
    payment_status  VARCHAR(20) DEFAULT 'pending',
    invoice_id      TEXT,
    amount          DECIMAL(10,2),
    created_at      TIMESTAMPTZ DEFAULT now()
)

keywords (
    id              BIGSERIAL PRIMARY KEY,
    user_id         BIGINT REFERENCES users(id) ON DELETE CASCADE,
    text            TEXT NOT NULL,
    is_regex        BOOLEAN DEFAULT false,
    is_active       BOOLEAN DEFAULT true,
    created_at      TIMESTAMPTZ DEFAULT now()
)

watched_chats (
    id                  BIGSERIAL PRIMARY KEY,
    user_id             BIGINT REFERENCES users(id) ON DELETE CASCADE,
    chat_username       VARCHAR(64),
    source              VARCHAR(20),              -- manual / discover
    userbot_account_id  INT,
    title               TEXT,
    status              VARCHAR(20) DEFAULT 'approved',  -- approved / pending
    is_private          BOOLEAN DEFAULT false,
    created_at          TIMESTAMPTZ DEFAULT now()
)

sent_log (
    id              BIGSERIAL PRIMARY KEY,
    user_id         BIGINT REFERENCES users(id) ON DELETE CASCADE,
    message_hash    VARCHAR(64),                  -- sha256(chat_username:message_id)
    content_hash    VARCHAR(64),                  -- sha256 текста: контентный дедуп репостов (24ч)
    is_urgent       BOOLEAN DEFAULT false,        -- 🔥 срочная заявка
    sent_at         TIMESTAMPTZ DEFAULT now(),
    UNIQUE (user_id, message_hash)
    -- + INDEX idx_sent_log_content_dedup (user_id, content_hash, sent_at)
)

-- ── КАТАЛОГ v2 ──

countries (
    id          BIGSERIAL PRIMARY KEY,
    slug        VARCHAR(50) UNIQUE,
    name_ru     TEXT,
    name_en     TEXT,
    is_active   BOOLEAN DEFAULT true
)

cities (
    id          BIGSERIAL PRIMARY KEY,
    slug        VARCHAR(50) UNIQUE,
    name_ru     TEXT,
    name_en     TEXT,
    country_id  BIGINT REFERENCES countries(id) ON DELETE RESTRICT,
    is_active   BOOLEAN DEFAULT true
)

segments (
    id          BIGSERIAL PRIMARY KEY,
    slug        VARCHAR(50) UNIQUE,
    title_ru    TEXT,
    title_en    TEXT,
    emoji       VARCHAR(8),
    sort_order  INT DEFAULT 0,
    is_active   BOOLEAN DEFAULT true,
    is_quarantined BOOLEAN DEFAULT false, -- A3: матчится+логируется, НЕ диспатчится
    lead_direction VARCHAR(10) DEFAULT 'demand' -- B4: demand/buy/supply
)

segment_keywords (
    id              BIGSERIAL PRIMARY KEY,
    segment_id      BIGINT REFERENCES segments(id) ON DELETE CASCADE,  -- NULL = универсальная
    text            TEXT NOT NULL,
    keyword_type    VARCHAR(20) DEFAULT 'demand', -- demand / stop / synonym
    is_regex        BOOLEAN DEFAULT false,
    is_active       BOOLEAN DEFAULT true,
    UNIQUE (segment_id, text, keyword_type)
)

catalog_channels (
    id              BIGSERIAL PRIMARY KEY,
    chat_username   VARCHAR(64) UNIQUE,
    title           TEXT,
    participants    INT,
    is_verified     BOOLEAN DEFAULT false,
    auto_matched_country_id BIGINT REFERENCES countries(id) ON DELETE SET NULL,
    auto_matched_city_id    BIGINT REFERENCES cities(id) ON DELETE SET NULL,
    discovered_at   TIMESTAMPTZ DEFAULT now()
)

channel_segments (
    channel_id  BIGINT REFERENCES catalog_channels(id) ON DELETE CASCADE,
    segment_id  BIGINT REFERENCES segments(id) ON DELETE CASCADE,
    PRIMARY KEY (channel_id, segment_id)
)

channel_cities (
    channel_id  BIGINT REFERENCES catalog_channels(id) ON DELETE CASCADE,
    city_id     BIGINT REFERENCES cities(id) ON DELETE CASCADE,
    PRIMARY KEY (channel_id, city_id)
)

user_subscriptions (
    id              BIGSERIAL PRIMARY KEY,
    user_id         BIGINT REFERENCES users(id) ON DELETE CASCADE,
    segment_id      BIGINT REFERENCES segments(id) ON DELETE CASCADE,
    country_id      BIGINT REFERENCES countries(id) ON DELETE CASCADE,
    mode            VARCHAR(10) DEFAULT 'all',    -- 'all' / 'cities'
    subscribed_at   TIMESTAMPTZ DEFAULT now(),
    UNIQUE (user_id, segment_id, country_id)
);
CREATE INDEX idx_user_sub_lookup ON user_subscriptions(segment_id, country_id);

subscription_cities (
    subscription_id BIGINT REFERENCES user_subscriptions(id) ON DELETE CASCADE,
    city_id         BIGINT REFERENCES cities(id) ON DELETE CASCADE,
    PRIMARY KEY (subscription_id, city_id)
)

discovered_chats (
    id              BIGSERIAL PRIMARY KEY,
    chat_username   VARCHAR(64) UNIQUE,
    title           TEXT,
    participants    INT,
    auto_matched_country_id BIGINT REFERENCES countries(id) ON DELETE SET NULL,
    auto_matched_city_id    BIGINT REFERENCES cities(id) ON DELETE SET NULL,
    discovered_at   TIMESTAMPTZ DEFAULT now()
)

referrals (
    id              BIGSERIAL PRIMARY KEY,
    referrer_id     BIGINT REFERENCES users(id) ON DELETE CASCADE,
    referral_id     BIGINT UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    ref_code        VARCHAR(20) UNIQUE NOT NULL,
    status          VARCHAR(20) DEFAULT 'pending',
    bonus_days      INT DEFAULT 10,
    referral_trial_bonus INT DEFAULT 4,
    activated_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT now()
)

support_messages (
    id              BIGSERIAL PRIMARY KEY,
    user_id         BIGINT REFERENCES users(id) ON DELETE CASCADE,
    direction       VARCHAR(10) NOT NULL,          -- 'incoming' / 'outgoing'
    text            TEXT NOT NULL,
    is_read         BOOLEAN DEFAULT false,
    created_at      TIMESTAMPTZ DEFAULT now()
)

user_ignores (
    id              BIGSERIAL PRIMARY KEY,
    user_id         BIGINT REFERENCES users(id) ON DELETE CASCADE,
    type            VARCHAR(10) NOT NULL,          -- 'sender' / 'word'
    value           TEXT NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT now()
)

reminders (
    id              BIGSERIAL PRIMARY KEY,
    user_id         BIGINT REFERENCES users(id) ON DELETE CASCADE,
    type            VARCHAR(30) NOT NULL,          -- trial_expired / subscription_expired / inactive
    day_number      INT NOT NULL,                  -- 1,3,7 (trial/подписка); 14,28 (неактивность)
    sent_at         TIMESTAMPTZ DEFAULT now(),
    is_disabled     BOOLEAN DEFAULT false
)

periodic_prefs (                                  -- настройки периодических сообщений Free
    user_id     BIGINT REFERENCES users(id) ON DELETE CASCADE,
    msg_type    VARCHAR(30) NOT NULL CHECK (msg_type IN (
                    'weekly_digest', 'niche_growth', 'monthly_summary'
                )),
    is_disabled BOOLEAN DEFAULT false,
    last_sent_at TIMESTAMPTZ,
    PRIMARY KEY (user_id, msg_type)
)
```

### Логика раздачи

**Вариант А (подписка):** чат в channel_segments[segment] И (mode='all' ИЛИ чат в channel_cities для subscription_cities) И текст совпадает с segment_keywords ИЛИ личными keywords.

**Вариант Б (свой канал):** чат в watched_chats И текст совпадает с личными keywords.

---

## 5а. Семантическое ядро

### Алгоритм: трёхпроходный rule-based NLP + LLM-валидация

Движок предкомпилирован (B2): вся regex/лемма-работа по keywords — один раз при загрузке (`compile_keyword_map`, startup + reload каждые 5 мин), hot-path только матчит.

**Проход 1 — demand:** поиск фраз по границе целого слова `(?<!\w)keyword(?!\w)`, Unicode, case-insensitive, лемма-формы (pymorphy3). Multi-word фразы — только в окне близости `KEYWORD_MATCH_WINDOW` токенов (C2, дефолт 20; выбран data-driven — docs/eval/c2_diff.md). Нет demand → игнорируем.

**Проход 2 — stop:** кандидат проверяется на универсальные и сегментные stop-фразы. Переопределяет stop только СИЛЬНЫЙ сигнал спроса (глагольные паттерны); голый «?» — нет (A2). Stop-фразы окном НЕ ограничены.

**Проход 3 — структурные сигналы:** разрешение коллизий спрос/оффер. Глагол спроса в начале — перебивает оффер. `?` — слабый сигнал (только здесь). Цена+контакт+хештеги — усиливают оффер. Сегменты с `lead_direction` 'buy'/'supply' минуют Проход 3 (B4 — лид легитимно пишет с ценой/телефоном).

**Направление сегмента — конфигурация в БД** (`segments.lead_direction`: 'demand'/'buy'/'supply', B4): supply-сегменты дополнительно инвертируют DEMAND/OFFER в LLM-промпте. Не хардкодить направления в коде.

**Reality-фильтр (до LLM):** сегмент подтверждается только если в тексте есть domain-слово сегмента (synonym-словарь из БД), word-boundary (C3). Сегмент без domain-слов проходит насквозь (дыра логируется).

**Личные keywords работают всегда, независимо от classifier** (Вариант Б, A1): keyword-матч минует сегменты, reality-фильтр и LLM — уведомление доставляется. Word-boundary + леммы.

**Срочность (🔥):** слова «срочно», «сегодня», «на завтра», «asap», «urgent» → `is_urgent=true`.

**Короткие anchors:** фразы с высоким риском ложного срабатывания («нужен байк», «хочу тату»). Матчатся ТОЛЬКО с контекстным сигналом спроса (глагол в начале, «?», «подскажите»). Историческая разметка — `docs/archive/2026-07/segment_seed.md`.

**Каталог: 14 категорий / 69 подкатегорий-сегментов** (реструктуризация 08.07.2026), ~1500 ключевых слов в БД — единственный источник истины (`segment_keywords`, правка через админку `/catalog`). Историческое ядро 29 категорий — `docs/archive/2026-07/segment_seed.md`.

**Eval-конвейер (C1):** `venv/bin/python tools/eval_matching.py` — по-сегментный отчёт качества с прод-данных (read-only). ПРАВИЛО: любые изменения правил классификатора или LLM-промпта сопровождаются прогоном eval; отчёты — `docs/eval/`.

### LLM-валидация (ВКЛЮЧЕНА, blocking)

`llm_validator.py`: DeepSeek-V3 (`deepseek-chat`), включён в blocking-режиме — батч-запрос после classifier и reality-фильтра, вердикты DEMAND/MIXED пропускают, OFFER/OTHER гасят. Fail-open (ошибка LLM → лид проходит). Все решения логируются в `llm_decisions` (shadow-датасет для fine-tune). Промпт-блок supply-сегментов генерируется из БД (B4).

---

## 5б. Redis-кэш

```
sub:by_chat:{chat_username}      → JSON [{user_id, telegram_id, lang, plan, subscriptions, keyword_texts}]
stats:daily:{uid}:{date}:matched → INT (инкремент в _dispatch, D2)
stats:daily:{uid}:{date}:sent    → INT (инкремент в sender после доставки)
stats:unmatched                  → LIST (последние 10000, dedup через :seen)
stats:full_batch:{chat}          → INT (C4: возможные пропуски, TTL 30д)
stats:llm:total:{YYYY-MM-DDTHH}  → INT (A2: валидаций за час UTC, TTL 48ч)
stats:llm:fail_open:{час}        → INT (A2: из них fail-open; алерт >20%/>50%)
cursor:msg:{chat}                → INT (инкрементальный поллинг)
limit_reached:{uid}:{date}       → "1" (TTL до полуночи)
queue:notifications              → LPUSH/BRPOP
dlq:notifications                → LPUSH/BRPOP
heartbeat:userbot:{id}           → timestamp
budget:used:{account_id}:{date}  → INT (суточный бюджет API)
circuit:open/expires:{id}, session:*, post_ban_until:{id} — anti-ban
```

Инвалидация кэша подписок: `invalidate_all_subscription_caches()` во всех CRUD-точках (A4) + TTL 1ч как страховка; в кэше только пользователи с подпиской или keyword (C5).

---

## 5в. Retry-логика

| Ошибка | Действие |
|---|---|
| 403 Forbidden | is_blocked_bot=TRUE, удалить из кэша |
| 429 Too Many Requests | sleep(retry_after), повторить |
| 5xx / network | 3 ретрая (1с, 4с, 9с), затем dead-letter |
| Throttle | 25/сек (sender_throttle_per_second) |
| Мониторинг | LLEN очереди, алерт при backlog > 100 |

---

## 5г. FSM CatStates

```
choosing_segment → choosing_country → choosing_geo →
choosing_cities / confirm_subscription → trial_activation / payment_offer →
show_last_leads → done
```

- Free: single-select (1/1). Pro: multi-select (3/3→0). Business: unlimited.
- Первая подписка → trial_activation (3 дня Про; referral — 7 дней).
- Существующий на Free → payment_offer.

---

## 5д. Админ-панель (10 разделов)

**Архитектура:**
- **Фронтенд:** React 19 + TypeScript + Vite 8
- **UI:** shadcn/ui 4 (Radix Nova) + Tailwind CSS 4 + Lucide Icons
- **Данные:** @tanstack/react-query 5, WebSocket для live-чата
- **Графики:** Chart.js 4 (дашборд)
- **Бэкенд:** FastAPI (порт 8001), сессионная авторизация, Redis brute-force protection
- **Деплой:** отдельный Docker-контейнер (admin), SPA статика закоммичена в `app/admin/static/`
- **Доступ:** `ADMIN_PUBLIC_PORT` (по умолчанию 17421), пароль в `ADMIN_PASSWORD`

**Страницы:**

| Роут | Название | Функционал |
|------|----------|------------|
| `/login` | Вход | Парольная авторизация, защита от брутфорса (Redis, 5 попыток/мин) |
| `/` | 📊 Дашборд | 4 KPI-карточки, график новых пользователей (30 дней), круговая по тарифам |
| `/users` | 👥 Пользователи | Таблица с поиском, фильтр по тарифу, бан/разбан, детали |
| `/catalog` | 🌍 Каталог | 3 вкладки: Сегменты (CRUD + keywords Demand/Stop/Synonym), Страны (CRUD), Города (CRUD) |
| `/channels` | 📢 Каналы | Таблица каталога с поиском, фильтр verified, просмотр |
| `/stop-words` | 🛑 Стоп-слова | CRUD стоп-слов с привязкой к сегменту |
| `/unmatched` | 📋 Несматченные | Пагинированная таблица из Redis `stats:unmatched`, поиск, фильтр по чату |
| `/chat` | 💬 Live-чат | WebSocket, список диалогов с 🔴, история сообщений, отправка |
| `/broadcast` | 📨 Рассылки | Выборка по тарифу/источнику, textarea, превью, карточка статистики |
| `/settings` | ⚙️ Настройки | Таблица тарифных лимитов + системная информация (read-only) |

**API эндпоинты (`/api/*`):**

| Модуль | Эндпоинты |
|--------|-----------|
| `auth.py` | `POST /login`, `POST /logout`, `GET /check` |
| `users.py` | `GET /`, `GET /{id}`, `PUT /{id}` |
| `stats.py` | `GET /dashboard` |
| `broadcast.py` | `GET /stats`, `POST /send` |
| `chat.py` | `GET /dialogs`, `GET /history/{id}`, `WS /ws` |
| `crud.py` | CRUD для стран, городов, сегментов, keywords |
| `stop_words.py` | `GET/POST/PUT/DELETE /stop-words` |
| `unmatched.py` | `GET /`, `GET /chats`, `GET /count` |
| `segments.py` | `GET/POST/PUT/DELETE /segments/{id}/keywords` |
| `channels` | `GET /`, `GET /{id}`, `PUT /{id}` |

---

## 6. План фаз

| Фаза | Название | Статус |
|---|---|---|
| Ф0 | Подготовка сервера | ✅ |
| Ф1 | Скелет проекта, /start | ✅ |
| Ф2 | БД, модели, Alembic, seed, тесты | ✅ |
| Ф3 | Inline-кнопки + FSM-навигация | ✅ |
| Ф4 | Userbot + classifier, перехват | ✅ |
| Ф5 | Очередь + рассыльщик + дымовые тесты | ✅ |
| Ф6а | Админка: CRUD каталога | ✅ |
| Ф6б | Админка: дашборд | ✅ |
| Ф6в | Админка: live-чат | ✅ |
| Ф6г | Админка: рассылки + напоминания | ✅ |
| Ф7 | Оплата (Stars + CryptoBot) | ✅ |
| Ф8 | Надёжность (Docker, бэкапы, Sentry) | ✅ |
| Ф9 | Масштабирование (пул userbot) | ✅ |

**Все фазы завершены. Исторические контрольные точки → `docs/archive/2026-07/ROADMAP.md`. Работы после фаз: `fable_audit.md` (закрыт) → `fable_core_plan.md` (активный).**

---

## 7. Конвенции и правила

- **Стиль кода:** `CODING_STYLE.md` (именование, типизация, функции ≤30 строк, ранний возврат, без Any, Protocol для интерфейсов)
- **Тестирование:** `TESTING.md` (unit с Ф2, integration, smoke с Ф5, pre-commit checklist)
- **Восстановление:** `RECOVERY.md` (БД из бэкапа, OOM, userbot бан, Redis)
- **Userbot:** задержки 3-5 сек, FloodWait → sleep(seconds), только публичные каналы, отдельный аккаунт
- **Heartbeat:** 15 минут, проверка раз в минуту, алерт владельцу
- **Бэкапы:** pg_dump раз в сутки, ротация 7 дней
- **Деплой:** сервер = dev + prod, git push с сервера, docker compose up -d --build
- **Админ-доступ:** `ADMIN_PUBLIC_PORT` (по умолчанию 17421), авторизация по паролю (`ADMIN_PASSWORD`)
- **Админ-технологии:** React 19 + TypeScript + Vite 8 + shadcn/ui 4 + Tailwind 4 + React Query 5 + Chart.js
- **Авторизация userbot:** `docker compose run --rm -it worker python -m app.userbot.auth`

---

## 8. Текущий статус

**ОБНОВЛЯТЬ ПОСЛЕ КАЖДОЙ СЕССИИ.** Полная история — `docs/SESSION_LOG.md` (записи о задачах — туда, в конец файла).

Дата: **2026-07-24**

Статус: **Фазы 1–10 segment-aware LLM на `feature/segment-llm-profiles` (не в prod).** Фаза 10: admin CRUD LLM-профилей — draft/publish/rollback + audit table `segment_llm_profile_audits`, migration `segment_profile_audit01`, API `/api/segments/{id}/llm-profile*`, UI вкладка в Categories. Preview offline. Prod migration/worker не применялись. Следующее: Фаза 11 staged enable (shadow → blocking 3–5 сегментов).

Предыдущий статус: **Этап 4 — CI release gate (16.07):** 5 parallel CI jobs; deploy ждёт approve `production`; P0 очередь/оплата в коде.

Предыдущий статус: **🚀 ТАРИФЫ v2 ЗАДЕПЛОЕНЫ В ПРОД 13.07.2026 ~17:15 MSK (тег `tariffs-v2-live`, main 4144e7b). Деплой чистый: 0 FloodWait, worker «Pool initialized: 2 healthy»/«Tiers rebuilt: 73 hot», bot polling без ошибок.**
Линейка: 🎯 Старт $9 / 🚀 Профи $19 / 🏆 Бизнес $39, дневной лимит уведомлений ОТМЕНЁН (метрика ценности = широта покрытия; DECISIONS #81). Реализация T0–T7 (план `fable_tariff_plan.md`, все фазы [x]): единая матрица лимитов + план start (crud `_plan_limits`); гео-лимиты FSM (реально биндит город-на-подписку); 3 тарифа в оплате Stars/CryptoBot; экраны «короче и суше» (build_plan_screen, живой счётчик меню, Free-CTA «Открыть контакты — от $9»); воронки (build_paywall контекстные пейволлы, End-of-day v2, trial-воронка, годовой апселл, subscription_ending); платные фичи (статистика menu:stats/​/stats, CSV-экспорт Бизнеса = метаданные без текста заявки, digest-режим instant/hourly/daily2); T7 реактивация (даунгрейд платных после grace 7д с сохранением ниши + winback_missed с числом пропущенных заявок из sent_log). 3 миграции применены (sentlog_meta01, user_digest01). Сьют 360 passed (4 пред­существующих poller-фейла test_poller_fixes — async-сигнатура, НЕ регрессия). **Попутно исправлено 4 живых бага:** крипто-оплата NameError (`_get_user_id`), кэш не инвалидировался при оплате (Stars+крипто), trial_expired-напоминания никогда не срабатывали.
ОСТАЛОСЬ (решением владельца, НЕ автономно): (1) анонс через админку /broadcast — черновик в плане T6.2; (2) живой тест оплаты Stars на минимальном инвойсе; (3) 2-нед мониторинг T6.4 (stats:paywall:*, конверсия trial→paid и Free→Старт, гео-стоимость hot-тира, жалобы на шум). ОТЛОЖЕНО (не тариф): fable_core_plan.md B2/B3/0.3, Sentry, TLS админки, разметка каналов без города.**

**ПАМЯТЬ USERFLOW (14.07.2026):** U0 завершена, коммит `b0ea4c0` в `feature/codex-userflow-v2`. После завершения базового userflow обязательно напомнить владельцу перейти к отдельному этапу: маркетинговые тексты и функционал, уведомления об окончании подписки, стимулы renewal и механики повторной подписки. До этого этапа не добавлять новые маркетинговые обещания.
**BASE USERFLOW COMPLETE:** функциональные U0–U5 завершены в `feature/codex-userflow-v2`. STOP перед маркетингом: согласовать welcome/0-lead, тарифные офферы U6, trial/EOD U7, expiry/renewal/winback U8, referral/help/trust U9. Прод не трогать без отдельной команды.
**U1 CHECKPOINT:** locale schema и RU/EN lead sender внедрены; 29 tests passed. U1 НЕ закрыта. Осталось: reminders, periodic, payment success, handlers/alerts и полные parity tests. U2 не начинать.
**U1 CHECKPOINT 2:** reminders/periodic и CryptoBot payment success локализованы; 32 tests passed. Фаза НЕ закрыта: handlers/alerts, Stars success, parity snapshots, legacy cleanup.
**U1 CHECKPOINT 3:** Stars success и feedback callbacks локализованы; 34 tests passed. U1 НЕ закрыта; следующий блок — payment screens + catalog/keywords/channels.
**U1 CHECKPOINT 4:** payment flow полностью RU/EN, включая динамические plan/period и annual offer; 41 tests passed. U1 НЕ закрыта; далее catalog/keywords/channels/settings.
**U1 COMPLETE (14.07.2026):** коммит `dc67f8b`; Gate пройден; sender/workers/payments/catalog/keywords/channels/settings/support/feedback сквозно RU/EN. Suite 66 passed. Следующая фаза U2 analytics; маркетинг/expiry/renewal остаются после базового userflow.

### Последние записи (полный журнал — docs/SESSION_LOG.md)

**16.07.2026 — Прод консолидирован на `main` + пересборка образа.** `main` = бывший `feature/codex-userflow-v2` (FF, `b932d01`); удалены ветки core/quality-v2, feat/discovery-shared-account, feature/codex-userflow-v2 — осталась только `main` (это прод). Добавлен `.dockerignore` (`e44c3b2`): `.env`/секреты/junk не пекутся в образ (env из compose env_file). Образ пересобран, контейнеры пересозданы `--no-deps`: admin/bot/worker чисто (0 FloodWait/CRITICAL, Pool 2 healthy). Ранее в сессии задеплоены: названия чатов, контакт-fallback отправителя, напоминания подписки −2/−1, «подписка истекла», обновлённые тексты, латинизация тарифов; crash-loop admin (baked `.env`) закрыт `.dockerignore` + `config extra="ignore"`. Admin публичный (до домена+SSL).

**16.07.2026 — feat: честный fallback контакта + имя автора при отсутствии @username.** У части лидов нет `@username` → было пусто. Телефон/id-ссылки/invite Telegram надёжно не даёт (приватность), парсинг текста — по решению владельца НЕ делаем. Внедрено: захват имени автора (`_sender_display_name`→`PendingMatch.sender_name`→`_dispatch`→payload); в paid-уведомлении без username показываем имя (`lead_sender_name`) + честную строку `lead_contact_hidden`. Новых API-вызовов нет. ⚠️ poller → рестарт worker; bot → `restart bot`.

**16.07.2026 — fix: реальное название чата в уведомлениях (было «группа -100…»).** Корень фикса 14.07: `_poll_channel` брал title из `entity` (`InputPeerChannel` без `.title`) → `chat_title` всегда пустой → fallback на числовой id. Правка без доп. API: title из `msg.chat.title` (Telethon прикрепляет `.chat` к сообщениям) + DB-fallback (`CatalogChannel/WatchedChat.title` через `_get_all_channels`→`_poll_channel(db_title=…)`). Отправитель вынесен на новую строку (`lead_sender`). ⚠️ poller-правки → рестарт worker; bot-часть — `restart bot`.

**14.07.2026 — fix: название чата вместо «-100…»-ID в уведомлениях (приватные группы).** `sender.py` печатал `chat_username` дословно (фикс 12.07 правил только экран «Мои каналы»). Живой `title` протянут `PendingMatch.chat_title`→`_dispatch`→payload→sender; хелперы `_chat_label`/`_chat_link` (приватные → `t.me/c/<id>`). test_sender.py 23 passed. ⚠️ НЕ задеплоено (правки в poller → рестарт worker решением владельца).


**10.07.2026 — Аудит: Фаза D завершена целиком — ВЕСЬ ПЛАН fable_audit.md ЗАКРЫТ (ветка audit/fable-fixes, прод НЕ трогался).**
Все 3 задачи закрыты, по коммиту на задачу:
- D1 (0e78034): честный Free-пейволл (DECISIONS #79) — в Free-уведомлении ни одной ссылки: чат plain-текстом, отправитель скрыт полностью, кнопки «💬 Чат» нет. До этого Free-формат содержал и ссылку на сообщение, и ссылку на отправителя — «контакты скрыты» было номинальным. Paid/Trial-формат не изменён. 4 теста в test_sender.py.
- D2 (7d19e40): счётчик stats:daily:{uid}:{date}:matched — _dispatch инкрементит при постановке в очередь (раньше писался только sent — EOD/недельные отчёты Free были бы пусты). Ветка plan=='trial' НЕ удалена — вывод аудита о «мёртвой ветке» опровергнут в A4 (trial реально пишется в users.plan), план скорректирован.
- D3 (db7ac87): актуализация документации — AGENTS.md §2 (поток данных без несуществующего find_interested_users), §5а (фактический классификатор после аудита: B2/C2/A2/B4/C3/C1), §5б (реальные Redis-ключи, class:cache не существует), §8 шапка, §9 (+#78/79/80, отмена #65), §10; DECISIONS #80 (поллинг без вступления vs event-push — трейд-офф задокументирован).
Итог сьюта: 231 passed / 3 pre-existing failed (кластер моков из baseline 0.3) / 1 hanging deselected. Контейнеры lh_test_db/lh_test_redis снесены. Деплой фазы НЕ выполнялся — офлайн-верификация по git-стратегии.
Аудит завершён: фазы 0/A/B/C/D — 22 задачи, все [x] в fable_audit.md. Живое переключение прода на ветку — отдельное решение владельца. ⚠️ При переключении: миграцию lead_direction01 накатить ДО старта worker.
**12.07.2026 — Анализ проекта + план качества ядра + большая уборка документации.**
Глубокий анализ прода (read-only): precision 17% (44 из 259 оценок), ~60% Pass1-объёма — три buy-сегмента с precision ~0% («продам/продаю» как demand, коммит 1abf5fe); Redis AOF фактически выключен; таблица keywords пуста (Вариант Б не используется); LLM 13,4M токенов/нед. Создан `fable_core_plan.md` (Ф0 деплой+baseline v2 → ФА голова FP → ФB петля качества → ФC gate-задачи). Уборка: session log вынесен в `docs/SESSION_LOG.md`; выполненные планы (LEADHUNTER_FIX_PLAN, AGENT_WORKFLOW, Codex-2, ROADMAP), устаревшие каталоги (SEED, DISCOVERY, segment_seed, SEGMENT_KEYWORDS_NEW) и разведрапорты docs/ (~20 md + 27 txt) — в `docs/archive/2026-07/`; удалены PROMPT_task_0.5, no_city_channels.csv; check_cursors.py → tools/. AGENTS.md актуализирован (worker 1G, handlers-дерево, content_hash в sent_log, 80 решений, меню 4 кнопки) и сжат ~1200 → ~640 строк.

---

## 9. Ключевые решения (полный архив — DECISIONS.md)

| # | Решение |
|---|---|
| 3 | Redis-кэш подписок с инвалидацией |
| 4 | Каталог сразу v2 (M:N) |
| 16 | segment_keywords: keyword_type ENUM('demand','stop','synonym') |
| 18 | Трёхпроходный классификатор (без LLM на старте) |
| 19 | Per-message классификация |
| 23 | FSM CatStates с /cancel |
| 26 | Retry: 403→блок, 429→retry_after, 5xx→3 ретрая + dead-letter |
| 27 | Только inline-клавиатуры (кроме /start) |
| 30 | Trial: 5 дней Business — ЗАМЕНЕНО решением #84: 3 дня, referral 7 |
| 31 | Free: контакты скрыты, лимит 50/день — ЛИМИТНАЯ ЧАСТЬ ОТМЕНЕНА решением #81 (уведомления безлимитны); скрытые контакты остаются |
| 49 | Напоминания: дни 1,3,7, кнопка отключения |
| 53 | Рефералы: deep-link, двусторонний бонус |
| 57 | Onboarding wizard: 3 шага |
| 65 | LLM-валидация отложена (DEEPSEEK_ENABLED=false) — ОТМЕНЕНО: включена в blocking с 02.07.2026 |
| 71 | Индекс idx_user_sub_lookup (lookup по segment_id+country_id в кэше подписок) |
| 78 | Поллинг без пагинации: полный батч → warning + stats:full_batch:{chat}, пересмотр по данным |
| 79 | Free-пейволл: ни одной ссылки в Free-уведомлении (чат plain-текстом, отправитель скрыт) |
| 80 | Поллинг без вступления в каналы (не event-push): лимит ~500 каналов/аккаунт и join-бан |
| 81 | Тарифы v2 (13.07.2026): отказ от дневного лимита уведомлений — метрика ценности = широта покрытия (направления × гео), совпадает с себестоимостью поллинга/LLM. Линейка: Старт $9 (1 направление, 1 страна или ≤3 городов, 10 keywords) / Профи $19 (5 направлений, ≤5 стран, 50 keywords, regex, статистика) / Бизнес $39 (без лимитов, кап 60, полная статистика + CSV). Free = широта Старта, контакты скрыты, безлимит уведомлений. Скидки 3 мес −10% / год −20%. Grandfathering платящих до конца оплаченного периода. Отменяет лимитную часть #31 и #67 (скрытые контакты остаются). План перехода — fable_tariff_plan.md |
| 82 | Тарифы v2.1 (14.07.2026): уведомления остаются без лимита. Старт: 1 направление, 1 страна, города без лимита, 3 ключевые фразы, 1 свой канал. Профи: до 3 направлений, 3 стран, города без лимита, 20 фраз, 10 каналов. Бизнес : до 12 направлений, 9 стран, города без отдельного лимита в этих странах, 50 фраз и 50 каналов. Trial повторяет Pro (часть решения заменена #85). Runtime-источник истины: app/config.py + crud._plan_limits(). |

---

## 10. Предложения развития

- **Webhook/API (Business):** POST уведомлений на внешний URL. После стабилизации.
- **Интеграции:** Slack, Google Sheets, CRM. После стабилизации.
- **LLM-валидация:** ВКЛЮЧЕНА (blocking) с 02.07.2026 — см. §5а. Следующий шаг: fine-tune датасет из llm_decisions + feedback.
- **Безопасность:** отдельная grilling-сессия (SSH по ключу, UFW, Fail2ban, 2FA).
- **Мобильная админка:** адаптация после десктопной версии.


**U6–U9 LIFECYCLE COMPLETE (14.07.2026, feature/codex-userflow-v2):** контакты скрываются точно после expiry; Free lifecycle = до 2 уникальных скрытых лидов + EOD `total/delivered/missed` в дни 0/3/7/14; старые periodic broadcasts отключены; день 30 = одноразовая серверная скидка 25% на любой 3-месячный тариф, 12 часов, Stars/CryptoBot. Миграция `winback_u89` (`users.free_lifecycle_at`, `winback_offers`). Welcome/tariffs/period/referral/help/about обновлены RU-first с EN parity. Не считать старое описание 7-дневного full-access grace и winback 14/28 актуальным. **U9.4 закрыт 20.07.2026:** opt-out lifecycle-маркетинга в Настройках. U10 rollout/snapshots остаются отдельно.
**U10.1–U10.2 COMPLETE (14.07.2026, `4156208`):** создана исполнимая матрица 12 persona × RU/EN с AUTO/STAGING/LIVE gate и автоматические text+keyboard snapshots. Новый suite 80 passed; расширенный userflow regression 134 passed. Production/main/Docker не менялись. U10 НЕ закрыта: далее U10.3 ручная RU/EN/business/functional редактура, затем только по отдельной команде владельца U10.4 staging/live rollout и U10.5 сравнение метрик.
**U10.3 REVIEW CHECKPOINT (14.07.2026):** read-only RU/EN/business/CTA аудит выполнен; находки записаны в `docs/userflow_u10_editorial_review.md`. По решению владельца пользовательские тексты сейчас не меняются: E-01–E-09 проверяются и согласуются во время совместного ручного userflow-прогона. U10.3 остаётся открытой.
**U10 PRODUCTION MANUAL QA ACTIVE (14.07.2026 ~12:42 MSK):** production bot переключён на `feature/codex-userflow-v2`, Alembic `winback_u89`; backup `backups/pre_userflow_u10_2026-07-14_1230.sql`. Тестовый `BurnPM` (старый users.id=152) удалён после backup для чистого `/start`. Bot healthy/polling. Worker ОСТАНОВЛЕН на время UI-прохода; не запускать до отдельного шага lead QA. При rollout исправлены два Python 3.11 f-string blocker-а (`bd7aed1`). Compose трижды неожиданно автозапустил worker (`run`, `up`, даже `build`); каждый раз остановлен, FloodWait/ERROR/CRITICAL нет, инцидент записан в OPERATIONS.md §7.

**СТАТУС ПРОДА (14.07.2026, актуально):** lead-этап QA пройден — **worker снова РАБОТАЕТ штатно**. `docker compose ps`: bot/worker/admin/db/redis все Up (healthy). Поллинг чистый: `Hot tier: 70 ok, 0 errors`, FloodWait/ERROR/CRITICAL нет, circuit clear, pool 2 healthy, Account 1 в плановом PAUSED (anti-ban ритм). Загружено 3361 keyword / 71 сегмент / 95 pre-tagged каналов, LLM-валидатор активен. Матчинг и рассылка идут. Прежняя запись «Worker ОСТАНОВЛЕН» — устарела. Открыт хвост на чистку каталога: битые каналы — см. `docs/broken_channels_2026-07-14.md`.
**TRIAL/REFERRAL CONTRACT #84 (14.07.2026):** trial = 3 дня Про после первого поиска; referral trial = 7 дней (+4). После первой оплаты приглашённого referrer однократно получает 10 дней: текущий тариф продлевается, на Free восстанавливается последний оплаченный, без истории активируется Start. Настройки сохраняются; RU/EN уведомление обязательно. Заменяет duration/bonus части решений #30/#54.

**GPT-TASK AUDIT + PLAN-UPSELL (14.07.2026, ветка `feature/codex-userflow-v2`, НЕ закоммичено):** аудит последней задачи GPT — userflow-реестр/trial-once/полный режим ГОТОВЫ; «приглашение к подписке» было мёртвым кодом, доведено до рабочего. Выбран вариант «отдельный экран ПОСЛЕ запуска поиска»: в ветке `is_first` (`on_subscribe`) добавлены текст `search_upsell_after` + кнопки Тариф/Мои поиски; удалены dead-хендлеры `cat:plan`/`cat:return_confirm` и RU-only ключи `catalog_plan_*` (заменены одним паритетным `search_upsell_after`). 13+115 tests passed. ⚠️ НЕ задеплоено — рестарт bot при работающем worker решает владелец.
