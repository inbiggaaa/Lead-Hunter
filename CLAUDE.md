# CLAUDE.md — контекст проекта для Claude Code

Этот файл Claude Code читает автоматически в начале каждой сессии. Содержит всё критичное для продолжения работы. Остальное — в сопровождающих файлах (см. ссылки ниже).

**Сопровождающие файлы:**
- `CODING_STYLE.md` — конвенции кода (обязательно к соблюдению)
- `TESTING.md` — стратегия тестирования + QA checklist
- `RECOVERY.md` — план восстановления (читать при любой поломке)
- `OPERATIONS.md` — правила эксплуатации: rate limits, защита от бана, безопасные конфиги
- `USERFLOW.md` — карта экранов, полные тексты RU+EN, UX-аудит
- `segment_seed.md` — семантическое ядро: 29 категорий, все demand/stop/synonym фразы
- `DECISIONS.md` — полный архив 74 зафиксированных решений
- `ROADMAP.md` — детальные контрольные точки всех фаз

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
- **Session log (обязательно):** после КАЖДОЙ задачи — дописать краткую запись в конец `CLAUDE.md §8` в формате: `**DD.MM.YYYY HH:MM — Что сделано.** Результат. Ошибки/уроки.` Это обеспечивает контекст для следующей сессии. Без этой записи задача не считается завершённой.
- **Миграции:** обратимые (`downgrade()`), перед применением — `pg_dump`.

---

## 1. Что мы строим

SaaS-сервис на базе Telegram-бота. Отслеживает сообщения по ключевым словам в публичных каналах и присылает уведомления пользователям. Freemium-модель.

**Userbot** (Telethon/MTProto) слушает каналы, **Bot API** (aiogram) отправляет уведомления и управляет интерфейсом.

### Тарифы

| | Free | Pro ($5/мес) | Business ($15/мес) |
|---|---|---|---|
| Матчинг | безлимитный | безлимитный | безлимитный |
| Подписки на направления | 1 | 3 | без лимита (кап: 60) |
| Свои каналы | 1 | 15 | без лимита (кап: 60) |
| Ключевых слов | 1 | 50 | без лимита (кап: 60) |
| Уведомлений/день | 50 | 150 | без лимита |
| Контакты | СКРЫТЫ | Полные | Полные |
| Кнопки | «💰 Активировать подписку» | «💬 Ответить» | «💬 Ответить» |
| Regex | — | да | да |
| CSV-экспорт | — | — | да |
| Trial | — | — | 5 дней Business |
| End-of-day отчёт | да (19:00) | — | — |

Лимиты и цены — в `.env.example`, меняются без правки кода.

### Trial и рефералы

- Trial: 5 дней Business при первом прохождении воронки. +3 дня по реферальной ссылке (итого 8).
- По истечении → Free: контакты скрыты, лимит 50/день.
- End-of-day: 19:00 по часовому поясу. Лимит достигнут → сообщение с предложением подписки.
- Периодические сообщения Free: 📊 Итоги недели (Пн 10:00), 🌱 Новое в нише (Чт, раз в 2 нед.), 📈 Твой месяц (1-е число). Benefit-oriented, без давления. Полные тексты → USERFLOW.md §5.
- Реферал: referrer +7 дней при оплате referral. Ограничение 10/мес.
- Механика: deep-link `t.me/LeadHunterBot?start=ref_CODE`.

### Оплата

Старт: Stars + CryptoBot. Позже: карты, QR СБП, YooKassa. Интерфейс `PaymentProvider` (Protocol). Фазы 1–5 без оплаты.

### Аудитория и i18n

Русскоязычная + международная. Тексты в `locales/ru.py`, `locales/en.py`. Выбор по `language_code`. Discovery: ru + en.

---

## 1а. User Flow (кратко)

**Принципы:** только inline-клавиатуры, все экраны с «◀️ Назад», FSM с `/cancel`. Картинки позже.

**Главное меню (9 кнопок):** 🔍 Поиск клиентов → FSM-воронка | ⚙️ Мои ключевые слова | 📢 Мои каналы | 📋 Мои подписки | 🎁 Пригласить друга | 💰 Тариф и оплата | 🌐 Язык | ⚙️ Настройки | ℹ️ О сервисе

**FSM-воронка:** направление (счётчик N/M) → страна → география (по всей стране / в городах) → города → подтверждение → триал/оплата. Free=1 сегмент, Pro=3, Business=∞.

**Форматы уведомлений:** Free — контакты скрыты, кнопка «💰 Активировать подписку». Paid (Pro/Business/Trial) — полный формат с @отправителем и чатом, кнопки «💬 Ответить». 🔥 для срочных.

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
userbot ловит NewMessage
    │
    ▼
classifier.classify(text) ──→ ["catering", "cleaning"]   ← 1 раз на сообщение
    │
    ▼
find_interested_users(chat_username, matched_segments)
    │  Redis-кэш sub:by_chat:{chat_username} + личные keywords
    ▼
Дедупликация: sha256(chat_username:message_id), UNIQUE(user_id, hash)
    │
    ▼
LPUSH queue:notifications → sender BRPOP + throttle 25/сек → Bot API
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
- Memory limits: bot=300MB, worker=400MB, admin=200MB, postgres=400MB, redis=100MB
- Swap 2GB обязателен
- Admin: 127.0.0.1:8001 (SSH-туннель)
- Сессии userbot: `./sessions:/app/sessions` (bind-mount)

---

## 4. Структура репозитория

```
LeadHunter/
├── CLAUDE.md                  ← этот файл (контекст)
├── DECISIONS.md               ← 74 зафиксированных решения
├── ROADMAP.md                 ← контрольные точки фаз
├── RECOVERY.md                ← план восстановления
├── CODING_STYLE.md            ← конвенции кода
├── TESTING.md                 ← стратегия тестирования
├── USERFLOW.md                ← карта экранов, тексты RU+EN
├── segment_seed.md            ← семантическое ядро (29 категорий)
├── .env.example / .gitignore
├── docker-compose.yml / Dockerfile
├── requirements.txt / alembic.ini
├── migrations/
├── tests/                     ← conftest, unit, integration, smoke
├── seed/seed_catalog.py
└── app/
    ├── config.py              ← pydantic-settings
    ├── main.py                ← точка входа бота
    ├── locales/               ← ru.py, en.py
    ├── bot/
    │   ├── handlers/          ← inline callback-хендлеры
    │   │   ├── start.py, keywords.py, channels.py, plan.py
    │   │   ├── discover.py, catalog_nav.py, referrals.py
    │   │   ├── settings.py, language.py
    │   │   └── middlewares/   ← проверка подписки, лимитов
    ├── admin/                 ← FastAPI (REST API + WebSocket + static SPA)
    │   ├── app.py, views.py, dashboard.py, chat.py
    ├── db/
    │   ├── models.py, session.py, crud.py
    ├── userbot/
    │   ├── pool.py          ← пул аккаунтов (Фаза 9)
    │   ├── poller.py        ← умный поллинг каналов (без вступления, по tier'ам)
    │   ├── classifier.py    ← трёхпроходный NLP
    │   ├── llm_validator.py ← DeepSeek-V3 (выключен)
    │   └── discovery.py
    ├── cache/subscription_cache.py
    ├── payments/              ← stars.py, cryptobot.py (PaymentProvider Protocol)
    └── worker/                ← tasks.py, sender.py, heartbeat.py
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
    is_urgent       BOOLEAN DEFAULT false,        -- 🔥 срочная заявка
    sent_at         TIMESTAMPTZ DEFAULT now(),
    UNIQUE (user_id, message_hash)
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
    is_active   BOOLEAN DEFAULT true
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
    bonus_days      INT DEFAULT 7,
    referral_trial_bonus INT DEFAULT 3,
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

### Алгоритм: трёхпроходный rule-based NLP (без LLM на старте)

**Проход 1 — demand:** поиск фраз по границе целого слова `(?<!\w)keyword(?!\w)`, Unicode, case-insensitive. Нет demand → игнорируем.

**Проход 2 — stop:** кандидат проверяется на универсальные и сегментные stop-фразы. Stop-фраза без глагола спроса → гасим.

**Проход 3 — структурные сигналы:** разрешение коллизий спрос/оффер. Глагол спроса в начале — перебивает оффер. `?` — усиливает спрос. Цена+контакт+хештеги — усиливают оффер.

**Личные keywords работают всегда, независимо от classifier.** Если слово совпало — уведомление доставляется.

**Срочность (🔥):** слова «срочно», «сегодня», «на завтра», «asap», «urgent» → `is_urgent=true`.

**Короткие anchors:** фразы с высоким риском ложного срабатывания («нужен байк», «хочу тату»). Матчатся ТОЛЬКО с контекстным сигналом спроса (глагол в начале, «?», «подскажите»). Размечены в `segment_seed.md`.

**Полный список 29 категорий, всех demand/stop/synonym фраз и контекстных правил → `segment_seed.md`.**

### LLM-валидация (опционально, на будущее)

Код `llm_validator.py` закладывается с Фазы 4, но выключен (`DEEPSEEK_ENABLED=false`). При включении: один батч-запрос к DeepSeek-V3 после classifier — «Какие из [candidates] реально ищет автор?». Стоимость ~$0.40/мес при 200 каналах. Решение о включении — после статистики false positives.

---

## 5б. Redis-кэш

```
sub:by_chat:{chat_username}      → JSON [{user_id, segment_ids, keyword_texts, lang}]
class:cache:{message_hash}       → JSON ["slug1", "slug2"] (TTL 60 сек)
stats:daily:{uid}:{date}:matched → INT
stats:daily:{uid}:{date}:sent    → INT
limit_reached:{uid}:{date}       → "1" (TTL до полуночи)
queue:notifications              → LPUSH/BRPOP
dlq:notifications                → LPUSH/BRPOP
heartbeat:userbot:{id}           → timestamp
```

Инвалидация кэша подписок при изменении каталога/подписок. Перестроение раз в час.

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
- Первая подписка → trial_activation (5 дней Business).
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

**Детальные контрольные точки всех фаз → `ROADMAP.md`.**

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

**ОБНОВЛЯТЬ ПОСЛЕ КАЖДОЙ СЕССИИ.**

Дата: **2026-07-02**

Фаза: **Фаза 0 завершена (8/8) ✅ | Фаза 1 — готова к старту**

### Production changes (Phase 0 — 02.07.2026)

**Poller v2 — инкрементальный, тирированный, батчевый:**
- Инкрементальный поллинг через Redis-курсоры (`cursor:msg:{chat}`) — только новые сообщения
- Тирирование: Hot (60с, каналы стран с активными подписками), Warm (5мин, >1000 участников), Cold (15мин, остальные)
- Параллельные батчи: 3 канала × `asyncio.gather`, 0.3 сек между API-вызовами
- Circuit breaker: `wait_if_circuit_open()` перед каждым батчем
- Полный обход 2014 каналов: Hot за ~80 сек, Cold за ~17 мин
- Масштабируется до N аккаунтов (`_distribute()` round-robin)

**Rate Limiter:**
- `DEFAULT_MIN_INTERVAL = 0.3` сек (было 3.0) — 3 rps, безопасно для Telegram
- `PARALLEL_BATCH = 3` на аккаунт (было 50 → бан)
- `BATCH_PAUSE = 0.3` сек между батчами

**Classifier:**
- +5 demand-сигналов: `требуется`, `кто может`, `подберите`, `порекомендуйте`, `есть у кого`
- +1 start-анкер: `^(где|куда|как|кто)\b.*\?`
- Убран `ищете/ищешь.*\?` — маркетинговый паттерн, не спрос
- Оффер-паттерны расширены: `цена\b.*?\d+`, телефон без @username
- Pass 3: `?` больше не перебивает оффер-сигнал — только глагол спроса в начале строки

**Keywords:**
- 1935 demand + 220 synonym + 102 stop = **2257 слов** в БД
- 24 оффер-ориентированных синонима удалены (`прокат мото`, `rent bike` и др.)
- Синонимы загружены для всех 29 сегментов (seed/seed_synonyms.py)

**Channel pre-tagging:**
- 29 каналов предтегированы сегментами по названию
- Названия автообновляются при поллинге (`_update_channel_title`)
- Если канал pre-tagged + demand-сигнал → матч даже без keyword в тексте

**Каталог:**
- 2014 каналов (было 2119), все с geo-привязкой (0 без страны)
- 106 мёртвых (<300 участников) удалены, 19 авто-привязаны
- +23 города в БД (Ларнака, Марбелья, Трабзон, Кордоба и др.)
- 10 активных каналов Дананга (>300 участников)

**Unmatched-логи:**
- Дедупликация через Redis SET `stats:unmatched:seen`
- TTL 7 дней на seen-хеши
- 175 уникальных unmatched в Redis

**Бот:**
- Команды `/keywords`, `/channels`, `/subscriptions`, `/plan`, `/settings` — прямой показ экрана (без emoji-мостика)
- `/search` — сразу открывает каталог направлений с FSM
- Главное меню: 4 кнопки (search, plan, referral, settings), Settings → 6 подэкранок

**Документация:**
- `OPERATIONS.md` — правила эксплуатации, защита от бана, чек-лист деплоя
- `CLAUDE.md §0` — обязательная инструкция: читать OPERATIONS.md перед изменениями в poller/rate-limiter

**Инциденты:**
- 30.06.2026 17:42 — FloodWait 18ч (Poller v2 без rate limiter). Исправлено: возвращён `limiter.acquire()`, `PARALLEL_BATCH=3`, `DEFAULT_MIN_INTERVAL=0.3`.
- 01.07.2026 10:30 — FloodWait 24ч Account 2 (все 3 тира стартовали одновременно → 2036 вызовов за 11 мин). Исправлено: staggered startup, warmup, jitter.
- Circuit breaker: Account 1 до ~12:34 MSK (повторный бан, 10ч), Account 2 до ~10:01 MSK 02.07.2026. Оба заблокированы.

**Текущие цифры:**
- Каналов: 2035 (100% geo), городов: 120 (из них 23 новых), сегментов: 29
- Ключевых слов: 2234 (1935 demand + 220 synonym + 102 stop), 96 universal stops
- Pre-tagged каналов: 33 (по названиям)
- Пользователей: 3, уведомлений всего: 33
- Hot/Warm/Cold: 208 / 308 / 1519 каналов
- Userbot-аккаунтов: 2 (@iraluxme, Sofiya) — ОБА ЗАБЛОКИРОВАНЫ
- Anti-ban: staggered startup (0/60/180s), warmup 8%→100% за 7 циклов, jitter ±15%

### Session log

**30.06.2026 15:00 — Poller v2: инкрементальный + тирированный + батчевый.**
Полный рефакторинг поллера: Redis-курсоры, 3 тира (Hot/Warm/Cold), asyncio.gather батчи.
Результат: Дананг-каналы начали поллиться, BurnPM получил 1 уведомление.

**30.06.2026 15:20 — Classifier: demand-сигналы + синонимы + оффер-детектор.**
+5 demand-паттернов, 220 synonym в БД, удалены оффер-синонимы («прокат мото»).
Pass 3: «?» больше не перебивает оффер. Результат: 4 матча/цикл вместо 1.

**30.06.2026 16:00 — Каталог: чистка + гео-привязка.**
106 мёртвых каналов удалено, 19 авто-привязаны, +23 города. 0 каналов без страны.

**30.06.2026 16:30 — Каналы: автообновление названий + pre-tagging.**
31 канал предтегирован сегментами по названию. Названия обновляются при поллинге.

**30.06.2026 17:00 — Бот: команды из меню.**
/keywords, /channels, /subscriptions, /plan, /settings — прямой показ без emoji-мостика.
/search — сразу каталог с FSM.

**30.06.2026 17:40 — ИНЦИДЕНТ: FloodWait 18ч.**
Poller v2 запущен без rate limiter → 5850 запросов за 10 сек → бан.
Исправлено: возвращён limiter, PARALLEL_BATCH=3. Создан OPERATIONS.md.
Урок: никогда не убирать rate limiter, всегда считать RPS перед деплоем.

**30.06.2026 21:00 — Security audit + документация.**
Git history чист (0 CRITICAL/HIGH). Убран dev-secret, очищен alembic.ini.
CLAUDE.md §8 актуализирован. Добавлен обязательный session log в §0.
OPERATIONS.md создан: hard rules, чек-лист деплоя, процедура FloodWait.

**01.07.2026 02:47 — Аудит FloodWait + защита discovery.**
Проверен статус бана: circuit breaker активен, истекает 09:32 UTC (6ч 45мин осталось).
Обнаружена дыра: discovery.py не использовал limiter вообще (0 из 3 проверок).
Исправлено: +limiter.acquire() перед SearchRequest, +wait_if_circuit_open() на входе,
+report_flood_wait() в обоих except FloodWaitError. Теперь все API-вызовы Telegram под защитой.
Прочитаны и применены: OPERATIONS.md §2 (Hard Rules #1, #6, #7), CODING_STYLE.md.

**01.07.2026 09:50 — Второй userbot-аккаунт +84326376814 (Sofiya).**
Добавлен USERBOT_2_PHONE в .env, авторизация через docker compose run.
Fallback API-кредов первого аккаунта (api_id=32062916) — отдельное приложение не нужно.
Исправлен SSH (MaxSessions 10) для одновременной работы.
Pool: 2 healthy accounts, каналы распределятся round-robin после закрытия circuit breaker.
Урок: docker compose restart не подхватывает новые env vars — нужен up -d.

**01.07.2026 10:15 — Per-account circuit breaker (FloodWait одного аккаунта не блокирует остальные).**
Рефакторинг rate_limiter: Redis-ключи per-account (circuit:open:{id}, circuit:expires:{id}).
Poller: пропускает аккаунты с открытым CB, wait_if_circuit_open per-account.
Discovery: is_any_circuit_open() вместо глобального wait — пропускает цикл если хоть один заблокирован.
Backward compat: account_id=0 → legacy global keys.
Результат: Account 1 (@iraluxme) ещё под баном ~2.5ч, Account 2 (@Sofiya) свободно поллит и приносит матчи.
33 уведомления всего, 3 пользователя, worker стабилен.

**01.07.2026 10:30 — ИНЦИДЕНТ: Account 2 (@Sofiya) тоже получил FloodWait 24ч.**
Корневая причина: при старте воркера все 3 тира запускались одновременно.
Account 2 получал 1018 каналов (Hot 104 + Warm 154 + Cold 760) × 2 API-вызова = 2036 вызовов.
11 минут непрерывного потока API-вызовов → Telegram anti-spam detection.

**01.07.2026 11:30 — Discovery v2: выделенный аккаунт + защита от бана.**
Исправлен discovery_v2: выделенный userbot2, per-account circuit breaker, 30-сек пауза.
23K запросов за 8.3 дня, 0.033 rps — в 908 раз ниже лимита Telegram.
Бан discovery не заденет поллер (разные аккаунты + per-account CB).

**01.07.2026 11:00 — Пагинация сообщений: 100% покрытие, 0 риск бана.**
Заменил фиксированный limit=3 на TIER_LIMITS (Hot=30, Warm=80, Cold=150) с авто-пагинацией.
Если батч возвращается полным — добираем остаток через max_id-окно за доп. API-вызов.
Для 99% каналов — ровно столько же вызовов (2 на канал). Rate limiter (3 rps) не менялся.
Добавлен канал @kz_danang (Вьетнам, Дананг) в каталог (id=2142, Hot-тир).
Исправлен SSH keepalive: ClientAliveInterval=30, ClientAliveCountMax=720 (6ч).

**01.07.2026 10:45 — Anti-ban protection (3 уровня) + метки категорий в уведомлениях.**
Staggered startup: Hot@0s, Warm@60s, Cold@180s.
Warmup: 7 циклов рампы (8%→16%→25%→35%→50%→70%→100%).
Jitter: ±15% случайной вариации интервалов.
Уведомления: строка 🏷 с названием категории (или 🔑 для персональных keyword).
Результат: Hot стартует с 16 каналов вместо 208, плавный выход на полную за 7 мин.
Оба аккаунта под баном: Acc1 ~2ч, Acc2 ~23.5ч. Уведомления не идут. Ждём снятия.

**02.07.2026 03:12 — Статус-чек: оба аккаунта под баном, расследование причины бана Acc1.**
Acc1 (@iraluxme): FloodWait до 12:34 MSK (10ч). Acc2 (@Sofiya): до 10:01 MSK (7ч).
Acc2 не имеет heartbeat и не упоминается в логах — полностью бездействует (CB открыт).
Причина ПОВТОРНОГО бана Acc1 (после истечения 18ч от 30.06):
- Acc1 непрерывно поллил 209 Hot-каналов 12.5ч (36K+ API-вызовов)
- В 02:35 MSK Dormant-тир (warmup 2/7, 292 канала) стартовал поверх Hot → шторм
- `_distribute()` включал Acc2 (healthy) но его чанк пропускался (CB) — каналы терялись
- Rate limiter (3 rps) капал скорость, но не спас от sustained-pattern detection
Решение: 4 исправления в poller.py — per-account try-lock, `_distribute` фильтрует blocked до раздачи, динамический Hot-интервал (120с при 1 аккаунте), jitter внутри `_poll_batch`.
Деплой — ТОЛЬКО после снятия бана с обоих аккаунтов (см. OPERATIONS.md §4).

**02.07.2026 03:30 — Прочитаны все referenced-файлы CLAUDE.md.**
RECOVERY.md, OPERATIONS.md, CODING_STYLE.md, TESTING.md, USERFLOW.md,
segment_seed.md (первые 100 строк), DECISIONS.md, ROADMAP.md.
Обнаружена опасная рекомендация от предыдущего ответа: «перезапустить воркер после 10:01» —
противоречит OPERATIONS.md §4 Шаг 1. Исправлено.

**02.07.2026 04:30 — Задача 0.5: пер-аккаунтный rate limiter + суточный бюджет.**
Фундаментальный фикс. Первопричина всех банов: `TelegramRateLimiter` был синглтоном с одним `_last_call` и одним `_lock` на все аккаунты. `DEFAULT_MIN_INTERVAL=0.3` ограничивал суммарный темп двух аккаунтов до 3 rps, а не каждого.
Что сделано:
- `rate_limiter.py`: `acquire(account_id)` — обязательный параметр, per-account `_last_call` и `_lock` (ленивые dict), `BudgetExceeded` (raise при превышении daily_budget), `budget_remaining()`.
- Порядок в `acquire()`: проверка бюджета → BudgetExceeded → пер-аккаунтный интервал → инкремент Redis-счётчика.
- Ключ бюджета: `budget:used:{account_id}:{YYYY-MM-DD}`, TTL 172800, обнуление за счёт смены даты в имени.
- `config.py`: +`userbot_min_interval=1.5`, +`daily_request_budget=10000`.
- Обновлены все 4 точки вызова: poller.py (2), discovery_v2.py (1), discovery.py (1).
- `_poll_batch` ловит `BudgetExceeded` → лог + `notify_admin`.
- `account_id=0` (legacy discovery v1) получает свой слот — обратная совместимость.
- 7 новых unit-тестов в `tests/test_rate_limiter.py`: 3 на пер-аккаунтный интервал, 4 на бюджет (fakeredis).
- `requirements.txt`: +`fakeredis>=2.0`.
Результат: pytest 7/7 зелёный, 44 существующих unit-теста без регрессий. 0 вызовов `acquire()` без `account_id`.
Уроки: синглтон-лимитер — антипаттерн для multi-account. Circuit breaker был пер-аккаунтным, а лимитер нет — несоответствие архитектуры.

**02.07.2026 05:15 — Задача 0.1: тесты на фиксы инцидента #3.**
Только тесты, без правок production-кода. 9 новых unit-тестов в `tests/test_poller_fixes.py`:
- `_distribute`: 4 теста — blocked-аккаунт исключается, каналы не теряются, round-robin сохранён, unhealthy исключается, все-blocked → пустой список.
- `_account_locks` try-lock: 1 тест `test_locked_account_lock_state` — проверяет состояние `lock.locked()` (вариант B: честно документирует ограничение — реальный skip-путь требует рефакторинга `_run_tier_loop`, запланирован в задаче 1.1).
- `_get_effective_interval`: 4 теста — ×2 при 1 healthy, без изменений при 2+, не-Hot тиры не меняются, unhealthy не считаются.
Результат: 9/9 зелёные локально и в Docker, 49 существующих unit-тестов без регрессий.

**02.07.2026 06:00 — Задача 0.2: развести конфликт деградации (_distribute vs handle_account_failure).**
Корень инцидентов #2/#3: `handle_account_failure()` перекидывал каналы упавшего аккаунта на выжившего через `min(healthy, key=channel_count)`.
Что сделано:
- `handle_account_failure` → только `logger.error`, без перераспределения.
- `health_check_loop` → алерт без вызова переброски.
- `_should_poll_tier()`: Hot всегда, Warm/Cold/Dormant — только при 2+ healthy.
- Guard clause в `_run_tier_loop`: пауза не-Hot тиров при 1 аккаунте.
- Удалён мёртвый код: `redistribute_channels`, `get_account_for_channel`, `_channel_assignments`, `channel_count`, `total_channels`. Grep-подтверждение: 0 внешних вызовов для каждой сущности.
- 17 новых тестов (2 pool + 6 `_should_poll_tier` + 9 из 0.1).
Результат: 56 тестов в Docker, 0 регрессий. Переброска каналов исключена на уровне кода.
Уроки: два противоречащих механизма (`_distribute` исключает blocked, `handle_account_failure` перекидывает) — классический race condition в архитектуре. Пул не должен управлять распределением — это зона ответственности поллера.

**02.07.2026 05:30 — Задача 0.3: исключить parked-каналы из расписания.**
Каталожные каналы стран без подписчиков больше не поллятся (1827 Dormant → 0 при `poll_parked_countries=False`).
Что сделано:
- `config.py`: +`poll_parked_countries: bool = False`.
- `_rebuild_tiers`: `elif settings.poll_parked_countries` → dormant (legacy), `else` → `parked += 1` (исключены).
- `is_watched` (country_id=None) не задет — ручные каналы всегда поллятся.
- Лог ребилда: `%d parked (inactive countries, not polled)`.
- 3 теста: исключение неактивных, защита watched, откат через флаг. 18/18 зелёные.
- ⚠️ Активация parked-страны имеет задержку до TIER_REBUILD (1 час) — будет устранено в Задаче 1.5.
Результат: при текущих подписках в расписании 200-400 каналов вместо 2035.
Уроки: Dormant-тир (12ч цикл) жёг 73% бюджета вхолостую. Флаг отката — страховка на случай ошибки классификации стран.

**02.07.2026 05:40 — Задача 0.4: последовательный опрос + лог-нормальные паузы.**
Убран `asyncio.gather` по каналам одного аккаунта — три одновременных запроса заменены на строго последовательный цикл. Это последний «машинный» паттерн, за который Telegram банил.
Что сделано:
- `_poll_batch`: последовательный `for ch in shuffled` вместо `asyncio.gather`.
- `next_delay()`: `lognormvariate(0.7, 0.5)`, медиана ~2с, диапазон 0.8–6с.
- `random.shuffle` порядка каналов на каждом цикле.
- Удалены: `PARALLEL_BATCH`, `BATCH_PAUSE`, `BATCH_PAUSE`-jitter.
- `min_interval=1.5` НЕ тронут — остаётся safety floor.
- 3 теста: диапазон, медиана, spread распределения. 21/21 зелёные.
Результат: с одного аккаунта запросы строго последовательны, интервалы лог-нормальные. Разные аккаунты по-прежнему параллельны (уровень `_run_tier_loop`).
Уроки: `asyncio.gather` на одном аккаунте — антипаттерн для MTProto. Три одновременных запроса + равномерный jitter = детектируемый бот. Лог-нормальное распределение с тяжёлым правым хвостом неотличимо от человека, листающего чаты.

**02.07.2026 06:00 — Задача 0.6: Redis AOF-персистентность.**
Включён AOF: `appendonly yes`, `appendfsync everysec`. Добавлен именованный том `redis_data:/data` в docker-compose.yml. Очередь `queue:notifications` теперь переживает рестарт Redis (раньше LPUSH/BRPOP in-memory терялись при любом рестарте контейнера). `appendfsync everysec` — компромисс: теряем ≤1 сек данных при крахе, не платим fsync на каждой записи. Памяти хватает: 2.5MB used при лимите 100MB.

**02.07.2026 06:15 — Задача 0.7: шифрованный бэкап сессий userbot.**
Session-файлы (userbot.session + userbot2.session) теперь бэкапятся вместе с БД: tar + gpg --symmetric AES256, пароль из SESSION_BACKUP_PASSPHRASE в .env. Самопроверка непустого архива (decrypt → tar tzf → grep '.session\$') — исключает повторение бага с пустым бэкапом. Ротация 7 дней. Восстановление задокументировано в RECOVERY.md.
Баг (найден и исправлен): `*.session` раскрывался шеллом в CWD, а не в SESSION_DIR — `tar -C` меняет каталог ПОСЛЕ раскрытия glob. 2>/dev/null скрывал ошибку, скрипт рапортовал успех на пустом архиве. Исправлено: `( cd "$SESSION_DIR" && tar czf - *.session )` + проверка числа файлов после шифрования.
Известные ограничения: S3-выгрузка — placeholder (B2 требует awscli/b2 CLI, не реализован), бэкап на том же диске — единственная точка отказа до настройки offsite.
Урок в OPERATIONS.md: 2>/dev/null на критичных операциях скрывает фатальные ошибки; проверка восстановлением обязательна.

**02.07.2026 06:30 — Задача 0.8: CB-статус при старте worker.**
Минимальная правка: `start()` логирует состояние CB для каждого аккаунта после инициализации пула. «circuit breaker OPEN — blocked for ~Ns (until HH:MM:SS UTC)» или «clear — ready to poll». Весь механизм защиты уже покрыт предыдущими задачами: `_distribute` (0.1) исключает blocked-аккаунты, `wait_if_circuit_open` в `_poll_batch` — двойная страховка, AOF (0.6) сохраняет CB-ключи при рестарте Redis, warmup (8%→100%) обеспечивает плавный старт после любого рестарта.
⚠️ «Пониженная скорость после рестарта» реализована через warmup-охват (мало каналов → мало запросов), а не через per-request tempo. Полноценный пост-бан режим (50% бюджета, ×1.5 интервалы на 48ч) — Задача 2.2 в Фазе 2.
Что сделано: `start()` + лог CB, `config.py` +`session_backup_passphrase`, 2 теста. 64 теста, 0 регрессий.
Уроки: задача 0.8 оказалась на 90% уже решена предыдущими — честный scope-анализ сэкономил ненужный код.

**02.07.2026 06:45 — Задача 1.6: entity-кэш — убрать ResolveUsername из цикла.**
Каждый опрос канала делал 2 API-вызова: ResolveUsername + GetHistory. Теперь ResolveUsername — один раз за жизнь worker (per account). `_entity_cache[chat_username][account_id] = (channel_id, access_hash)`. При попадании — `InputPeerChannel` напрямую, без `limiter.acquire()`. При `ChannelInvalidError` (stale hash) — инвалидация кэша, следующий цикл перерезолвит. Экономия: −1 ResolveUsername на канал на цикл; при 200 каналах и 120s интервале ≈ −144K запросов/сутки. 3 теста: cache hit, per-account независимость, реальная экономия в `_poll_channel` (get_entity 1 раз за 2 цикла). 67 тестов, 0 регрессий.
Уроки: `InputPeerChannel(channel_id, access_hash)` идёт в GetHistory напрямую — Telethon НЕ резолвит повторно. Кэш in-memory достаточен — access_hash меняется только при миграции канала.

**02.07.2026 07:00 — Задача 1.1: сессионная модель планировщика.**
Главная правка перед живым прогоном — ломает непрерывный 24/7 паттерн из инцидента #3. Пер-аккаунтная сессия: ACTIVE (20-60 мин) ↔ PAUSED (15-60 мин) вне сна, SLEEPING (4-6ч) в окне 02:00-08:00 UTC. `_session_ticker` — единственный владелец переходов (Redis), `_get_session_state` — только чтение. Переживает рестарт: ticker досыпает `session:until`, не сбрасывает сон. SLEEPING→ACTIVE безусловно, until продлён за конец sleep-окна. Wraparound для 1.2. Крючок: `_get_sleep_start_hour(account_id)`. 9 тестов. 77 всего, 0 регрессий.
Уроки: разделение ticker/reader устранило гонки 4 тиров. Redis как источник истины для сессий — естественно после AOF (0.6).

**02.07.2026 09:00 — Задача 1.2: stagger sleep windows.**
`_get_sleep_start_hour`: `(idx * (24 // N)) % 24` — acc1=12:00, acc2=00:00, окна сна 6ч не пересекаются (проверено через `_is_in_sleep_window`). 3 теста. ⚠️ Неполное покрытие каналов спящего аккаунта — сознательный компромисс (безопасность > полнота). Переброска на активный через `_distribute` ОТВЕРГНУТА — sustained-pattern #3. Каналы спящего ждут пробуждения (до 6ч). 83 теста, 0 регрессий.

**02.07.2026 09:30 — Задача 1.4: alert loop — мониторинг здоровья системы.**
6 проверок каждые 5 мин в @leadhunterai_admin: очередь > 100 / dead-letter / FloodWait / бюджет / поллер stuck (ACTIVE + last_poll > 30m WARNING, > 60m CRITICAL). Защита: молчит при PAUSED/SLEEPING. `stats:last_poll_at` в `_poll_batch`. Троттлинг Redis `alert:last:{type}`. `notify_admin` не тронут. 6 тестов, 89 всего, 0 регрессий.

**02.07.2026 10:00 — Задача 2.2: пост-бан режим (48ч пониженной активности).**
Последняя защита перед живым прогоном. 3 слоя: `last_ban_at` при бане / `post_ban_until` при истечении CB / `activate_post_ban_if_recent` при старте. Бюджет /2 (5K), интервалы ×1.5. `_is_post_ban` кэш 60с. 8 тестов (ключевой `budget_halved` доказывает урезание). 97 всего, 0 регрессий. ⚠️ Текущие аккаунты требуют ручной установки `post_ban_until` перед запуском. Урок: без теста `budget_halved` рискнули бы четвёртым баном.

**02.07.2026 10:45 — fix: баг пагинации при cursor=0 (дубли в логах).**
При cursor=0 все 5 раундов `_fetch_all_since` попадали в `else` → те же 30 сообщений ×5. Лог: 5× матчей; пользователей НЕ задело (`sent_log UNIQUE` отсёк). Фикс: `if rounds > 0` вместо `fetch_min_id > 0 and rounds > 0`. Тест с Telethon-точным моком падает на старом коде (150→30), проходит на новом (106→106).

**02.07.2026 11:00 — ТОЧКА ВОЗОБНОВЛЕНИЯ (перерыв, worker РАБОТАЕТ).**
Второй живой прогон идёт. acc2 поллит, acc1 под CB до ~12:34 MSK. Пагинация + notify_admin применены (worker перезапущен). notify_admin: алерты только в канал ✓. Match ×5: НЕ подтверждено (аккаунты в PAUSED при проверке). Ждёт: fix/alert-floodwait-dedup (дубль CRITICAL+WARNING) при след. рестарте. Бюджет acc2: 325/5000 (6.5%). FloodWait: нет. СЛЕДУЮЩИЙ ШАГ: проверить логи на Match ×5.

**02.07.2026 15:20 — ТОЧКА ВОЗОБНОВЛЕНИЯ (перерыв 3ч, worker РАБОТАЕТ).**
ЯДРО/Фаза 2: LLM-валидатор написан (shadow-режим), ветка fix/2.4-llm-validation,
НЕ вычитан владельцем, НЕ смержен в main, миграция НЕ применена, БД не тронута.
Ключ DeepSeek в .env (sk-986...e5fc), модель deepseek-chat, API работает.
Промпт проверен на РЕАЛЬНОЙ DeepSeek: 37/40=92.5%, 0 ошибок типа A (потеря лида).
СЛЕДУЮЩИЙ ШАГ: вычитать diff (6 пунктов) → бэкап → миграция → shadow.
alert-floodwait-dedup уже в main (87f782c).
Ложный stuck-алерт задокументирован — баг в _check_poller_stuck (не сбрасывает
last_poll_at при рестарте), fix в отдельной ветке. Не блокирует прод.
Прод: worker Up 26 мин (рестарт для подхвата API-ключа), FloodWait нет,
бюджет acc1=231, acc2=762 из 5000, CB clear, матчи идут (6 за 15 мин).
Discovery v2: баг INTER_QUERY_PAUSE (не критично, только discovery).

**02.07.2026 14:30 — 🚀 ПЕРВЫЙ РАБОЧИЙ ЗАПУСК УСПЕШЕН.**
Worker в штатной работе на 2 аккаунтах (acc1 @iraluxme, acc2 @mill_sofi), оба CB clear.
Подтверждено в бою за 2+ часа живого прогона:
- Пагинация без дублей: msg_id один раз, paginated rounds тянут разное, без ×5.
- notify_admin: алерты только в @leadhunterai_admin (исправлен if→elif).
- alert-dedup: один эскалационный алерт на FloodWait вместо дубля CRITICAL+WARNING.
- _distribute: 218 hot-каналов делятся поровну между acc1 и acc2.
- Post_ban: активен на обоих (50% бюджет = 5000, ×1.5 интервалы) до 04.07 ~14:06 MSK.
- Бюджет здоров: acc1 ~21 запросов, acc2 ~890 запросов из 5000 за день.
- FloodWait: 0 за 2+ часа, оба аккаунта чисты.
Фаза 0 (8/8) + 1.6/1.1/1.2/1.3/1.4/1.8 + 2.2 done. Три hotfix'а из живого прогона (пагинация, notify_admin, alert-dedup) применены в main.
Режим: пассивный мониторинг через @leadhunterai_admin.
ОСТАЛОСЬ (штатно, без аврала): 1.5 (активация страны), 1.7 (dead-man switch),
Фаза 2 (LLM, feedback, классификатор), Фаза 3 (продукт), 3-й аккаунт при появлении SIM.

**02.07.2026 14:15 — Task 1.3: Hot interval 10min, adaptive + cap.**
Снят последний агрессивный параметр в проде — Hot 60с → 10мин (600с).
Формула: min(base × max(degraded, post_ban), cap). max() вместо перемножения —
множители не стакаются (1акк+post_ban = max(2, 1.5) = 2, не 3).
3 аккаунта → 7мин (420с), 2 → 10мин (600с), 1 → 20мин (1200с).
Cap 20мин — жёсткий потолок при любых условиях.
Warm/Cold/Dormant: 50мин/2.5ч/12ч — все из config.py, 0 хардкода.
8 новых тестов, 140 всего, 0 регрессий. Тег task-1.3-done.

**02.07.2026 14:35 — Task 1.8: dedup Samui + UNIQUE(country_id, slug).**
Слит дубль «Самуи» (id=70 → канонический id=13): 24 channel_cities удалены
(дубли — те же каналы под обоими id), 2 catalog_channels перенесены 70→13.
UNIQUE(country_id, slug) на cities — защита от будущих дублей.
«Вся страна» (id=63) проверена — фича «подписка на всю страну», 1 запись,
корректна, не тронута. Миграция Alembic обратимая, бэкап pg_dump был.
Worker не останавливался, ошибок 0. Тег task-1.8-done.
Фаза 1 завершена (1.3, 1.6, 1.1, 1.2, 1.4, 1.8 done; 1.5 и 1.7 отложены).

**02.07.2026 07:15 — ТОЧКА ВОЗОБНОВЛЕНИЯ.**
Фаза 0: завершена (phase-0-done, 8/8).
Фаза 1: 1.6 done (merged). 1.1 — В РАБОТЕ на fix/1.1-session-model (80 тестов зелёные, _run_tier_once готов, 3 реальных интеграционных теста).
Осталось по 1.1: review → merge → task-1.1-done.
Следующие: 1.2 (таймзоны, _get_sleep_start_hour), 1.4 (алерты) → живой прогон.
Бан: acc2 ~07:01 MSK, acc1 ~09:34 MSK (проверить circuit:expires перед запуском).

**02.07.2026 07:00 — Phase review: 2 blocker'а найдены и исправлены.**
`/skill:phase-review` выявил: (1) `effective_city_ids` — NameError в `_dispatch` (не определён, но используется в city-фильтрации; не падал т.к. у текущих пользователей mode='all'); (2) `UserbotAccount.get_messages` не принимал `min_id`/`max_id` → `_fetch_all_since` с инкрементальным поллингом падал бы с TypeError (не падал т.к. оба аккаунта под CB). Исправлено: `+**kwargs` в `get_messages`, `+effective_city_ids` в `_dispatch`. 64 теста после исправлений — 0 регрессий.

**03.07.2026 02:30 — Диагностика бана + три фикса (ветка fix/disable-discovery-fix-throttle, НЕ смержена).**
Диагностика: оба аккаунта НЕ под активным FloodWait. Acc1 — 17ч бан от discovery (уже истёк, сейчас SLEEPING). Acc2 — чист, ACTIVE, поллит. 35 errors/цикл на Hot-тире (32%) — глушатся на logger.debug, требуют расследования.
Фикс 1: discovery v1/v2 удалены из tasks.py полностью (импорты + client creation). Были закомментированы (61522a6, 2fe673a), теперь не могут быть случайно включены.
Фикс 2: report_flood_wait в rate_limiter.py — добавлен 15-мин троттлинг на notify_admin (ключ alert:last:flood_wait_report:{account_id}). Ранее спамил 100+ уведомлений.
Фикс 3: CLAUDE.md §0 — новое правило: не трогать прод при работающем worker.
⚠️ Применять осторожно: остановить worker → пересобрать → запустить. Acc2 продолжит работать, acc1 под CB/SLEEPING подождёт.

### 2026-07-04 — Группировка: полный аудит + план админ-фичи

ИТОГ ПО ГРУППИРОВКЕ: механизм ЗДОРОВ. 4 захода аудита сняли все подозрения.
Over-dispatch=0, покрытие effective 100-140% по всем городам Вьетнама, мультисити
разбирает перечисления, город/страна-подписка работают. «6 каналов Дананга» и
«недобор Ханоя» — артефакты счёта только по auto_matched без channel_cities.
Правило «проверять напрямую, не верить на слово» сработало 4×.

ПОДТВЕРЖДЁННАЯ ФАКТУРА:
- Привязка: _tag_new_channels() poller.py:1169 — точное вхождение + fuzzy по
  username+title. URL не читается, поля url в БД нет. 91 страна, 227 городов.
- Мультисити: auto_matched_city_id (скаляр) ∪ channel_cities (M2M, PK
  channel_id+city_id) = effective_city_ids, читается dispatch poller.py:1316.
  44 канала мультисити.
- 831 орфан (city=NULL): реально безгородние ПО ИМЕНИ (сырой ILIKE=0), не жертвы
  fuzzy. Все со страной. Топ: Египет 90, Шри-Ланка 54, Вьетнам 52. У всех валидный
  @username. 627 (75%) без participants.
- channel_segments ПУСТА (0/2522). Сегмент — свойство только подписчика,
  релевантность = keyword-матчинг рантайм. _load_channel_segments() poller.py:1430
  заложена, но БД не наполняет.
- Админка: FastAPI:8001 + SQLAlchemy async + React. GET/PUT /api/channels
  (api/__init__.py:63), фильтры search+is_verified+пагинация. БД через
  async_session_factory.
- Справочник городов: slug (UNIQUE) + country_id (FK RESTRICT) обязательны;
  name_ru/name_en/is_active опц; UNIQUE(country_id, slug).

НОВЫЙ ТЕХДОЛГ (не срочно):
4. Fuzzy-ложняки: короткие токены с «nn» → Нижний Новгород (@nnw_chat «Neural
   Chat», @NNR_chat, @nnmidletschat). Подтверждено в 2 независимых выборках.
   Порог poller.py:1237 (0.95 при <5 букв / 0.85 при ≥5). Масштаб не измерен
   (~5-10 видимых). Также @byinpt → Порту вместо Кашкайш.
5. Кашкайш и, вероятно, др. города отсутствуют в справочнике 227 — пополнить.
6. 627 орфанов без participants — если показывать подписчиков в панели, userbot
   должен дотягивать (лезет в Telethon/путь опроса, отложено).

ROADMAP (порядок очереди):
- АКТИВНАЯ: админ-фича «Чаты без группы» (план ниже).
- СЛЕД. ОТДЕЛЬНЫЙ ЧАТ: ключевики (техдолг №3), чистка EN/RU перекоса.
  Предусловие для авто-направлений.
- ПОСЛЕ КЛЮЧЕВИКОВ: авто-направления — оживить channel_segments /
  _load_channel_segments, наполнить предтегирование каналов. Ручная разметка из
  админ-фичи = эталонная выборка для проверки качества.
- ПОСЛЕ АВТО-НАПРАВЛЕНИЙ: селектор + экспорт csv/md — отбор подмножеств
  (страна/город/направление) под новые продукты-боты (HR, IT-заказы, дизайн).
  Данные в схеме, ждёт чистых направлений.

ПЛАН АКТИВНОЙ ЗАДАЧИ — админ-фича «Чаты без группы» (шаги, каждый отд. заход):
1. Миграция: колонка is_ignored bool default false в catalog_channels. Только это.
   Штатным механизмом миграций (Alembic?), не руками в psql.
2. ГОРЯЧИЙ ШАГ: проверка is_ignored=false в 3 точках — discovery_v2.py:266,
   _get_all_channels() poller.py:196, _tag_new_channels() poller.py:1187. Тест:
   игнорированный канал исчезает из всех 3 выборок И не слушается userbot'ом.
   Отдельный заход, отдельный тест.
3. Бэкенд-роуты (расширить /api/channels): фильтр has_city=false +
   country_id/city_id/is_ignored; POST привязки мультисити (в channel_cities,
   ≥1 город + country); POST «добавить город» (slug+country_id, UNIQUE-safe);
   PATCH is_ignored=true («Удалить»). url = t.me/{chat_username}, participants
   число или null→«—».
4. Фронт «Чаты без группы»: список (title, кликабельный url, participants/«—»),
   очередь = 831 орфан + fuzzy-сомнительные (вычислять запросом, признак в БД не
   хранится). Дропдауны страна→город (мультиселект), «добавить город», «Удалить»
   (→is_ignored). Обновление сразу. Поле «направление» ЗАЛОЖИТЬ в разметку, НЕ
   активировать (ждёт авто-направлений; будущая обучающая выборка).
КРЮЧОК (закладываем, не строим): листинг-эндпоинт шага 3 проектировать так,
чтобы фильтры переиспользовались будущим экспортом csv/md.

### 2026-07-04 (продолжение) — Админ-фича «Чаты без группы»: шаги 1-2 СДЕЛАНЫ

СТАТУС ЗАДАЧИ: шаг 1 (миграция) + шаг 2 (фильтр) закрыты и в origin.
Осталось: шаг 3 (роуты API), шаг 4 (фронт).

СДЕЛАНО (в БД/коде, на origin):
- Колонка is_ignored в catalog_channels: bool, NOT NULL, server_default false.
  Миграция ccb7137d7d5c (down=c2a1d3b4e5f6). Все 2522 = false на момент наката.
- Alembic ВЫЛЕЧЕН по пути: были двойные головы в alembic_version [4afd,b111] при
  линейной цепочке + незаписанный c2a1 (реально применён через docker compose run).
  Исправлено прямой правкой alembic_version → одна голова. Затем дрейф моделей:
  City/SentLog не декларировали uq_cities_country_slug и idx_sent_log_content_dedup,
  autogenerate генерил их DROP — дописали в ORM (models.py), дрейф устранён.
  ВАЖНО: миграции писать ВРУЧНУЮ на хост, НЕ autogenerate вслепую (см. долг №7).
- Фильтр is_ignored=False в 4 точках: discovery_v2.py (+guard перед session.add,
  т.к. usernames из Telegram Search API — внешний источник), _get_all_channels
  (poller, прослушка), _tag_new (poller), _load_channel_segments (poller).
  Discovery делает INSERT (не UPSERT) → игнорированный канал НЕ воскрешается.
- @saigon_services (id=885) помечен is_ignored=true (мёртв, подтверждён вручную).
  Закрывает часть долга №1. Сейчас в БД ровно 1 ignored канал.

ПОВЕДЕНИЕ (согласовано с владельцем):
- Прослушка обновляется на часовом ребилде self._hot_channels (poller). Задержка
  «Удалить»→канал перестал слушаться до 1ч — ДОПУСТИМО. Фронт ДОЛЖЕН показывать
  пользователю, что изменения применятся в течение часа.
- Dispatch/раздачу is_ignored НЕ фильтрует (не требуется при часовой задержке).

НОВЫЙ ТЕХДОЛГ:
7. bind-mount ./migrations:/app/migrations МЁРТВ (overlay2-конфликт: COPY . . в
   Dockerfile кладёт migrations в образ, mount поверх не работает; host uid 1000 vs
   container root). Следствие: alembic upgrade в контейнере читает миграции ИЗ
   ОБРАЗА, не с хоста. Обход: писать файл на хост (для git) + docker compose cp в
   контейнер + upgrade. Вероятная КОРНЕВАЯ причина всего рассинхрона Alembic.
   Чинить осознанно (правка Dockerfile/compose + пересборка = красная линия +
   перезапуск userbot). Кандидат — совместить с передеплоем под ключевики.

АДМИН-ФИЧА «ЧАТЫ БЕЗ ГРУППЫ» — ЗАКРЫТА (шаги 1-4).

### 2026-07-04 — Шаг 3: роуты API (СДЕЛАНО)

- (a) GET /api/channels: фильтры has_city/country_id/city_id/is_ignored, is_ignored в ответе.
  city_id ловит мультисити через channel_cities. Очередь = has_city=false AND is_ignored=false = 830.
  Коммит 745cfc0.
- (c) POST /api/cities UNIQUE-safe: 409 при конфликте country_id+slug, сессия не виснет.
  Коммит 161aa99.
- (b)+(d) PUT /api/channels: привязка городов перезаписью (DELETE-all→INSERT),
  country auto-set если пуст; is_ignored в updatable («Удалить»). Коммит 745cfc0.
- Все правки — admin-слой (FastAPI), схему БД не трогали, миграций нет.
- Отложено (не потерять): экспорт csv/md по стране/городу — дорабатываем потом, не скоро.
  Направления/сегменты ждут долга №3 (ключевики).

### 2026-07-04 — Шаг 4: фронт «Чаты без группы» (СДЕЛАНО, коммит локально, ждёт push)

Один файл: admin-panel/src/pages/ChannelsPage.tsx (160→~310).
- Фильтры: has_city (все/без/с), is_ignored (активные/игнор/все). Вместе =
  очередь орфанов 830. + счётчик «Найдено N».
- Таблица: +колонка «Игнор» (badge), +колонка «Направление» (disabled,
  плейсхолдер, ждёт долга №3). url строкой t.me/{chat_username}.
- Строка: страна→город мультиселект, «Привязать», «Удалить» (is_ignored=true),
  «+ город» (POST /api/cities, 409-safe toast). Баннер «изменения в теч. часа».
- ⚠️ Фикс перезаписи: «Привязать» активна ТОЛЬКО для орфанов
  (auto_matched_city_id==null). У каналов с городом — disabled + тултип.
  Причина: PUT cities=перезапись; мультисити (44) хранят набор в
  channel_cities, UI его не подгружает → сотрёт.
- Тест: смоук с откатами. Привязка 830→829→830, ignored 830→829→830. Зелёно.
  Сборка vite чистая, статика в app/admin/static.

НОВЫЙ ТЕХДОЛГ (8): редактирование существующих привязок канала
(мультисити-safe): подгружать channel_cities в мультиселект перед PUT cities —
отдельная задача. Сейчас привязка через UI разрешена только орфанам.

АКТИВНОЕ СЛЕДУЮЩЕЕ: ключевики (долг №3), чистка EN/RU перекоса.

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
| 30 | Trial: 5 дней Business, понижение до Free |
| 31 | Free: контакты скрыты, лимит 50/день |
| 49 | Напоминания: дни 1,3,7, кнопка отключения |
| 53 | Рефералы: deep-link, двусторонний бонус |
| 57 | Onboarding wizard: 3 шага |
| 65 | LLM-валидация отложена (DEEPSEEK_ENABLED=false) |
| 71 | Индекс idx_user_sub_lookup для find_interested_users() |

---

## 10. Предложения развития

- **Webhook/API (Business):** POST уведомлений на внешний URL. После стабилизации.
- **Интеграции:** Slack, Google Sheets, CRM. После стабилизации.
- **LLM-валидация:** включить DEEPSEEK_ENABLED=true после сбора статистики false positives.
- **Безопасность:** отдельная grilling-сессия (SSH по ключу, UFW, Fail2ban, 2FA).
- **Мобильная админка:** адаптация после десктопной версии.

**04.07.2026 — DIAG-1 разобран + фича 7-day. Итог: из 4 симптомов DIAG-1 живых багов НЕТ.**
 - (a) CPU 100% — норма для 217 Hot-каналов на 1-Core, не spin. Task-destroyed для _alert_loop — косметика shutdown. Правки не нужно.
 - (b) Hot-тир «32-48% ошибок» — УСТАРЕЛО. Цифра снята до рестарта с hotfix 2e08849 (get_input_entity в UserbotAccount). После рестарта: 4 ошибки / 380 опросов = 1%. get_input_entity уже везде, get_entity в опросе нет.
 - (c) LLM «0 матчей» — ЛОЖНОЕ измерение (grep-паттерн). Реально: 110 матчей/3ч, sent_log шлёт. Диспатч работает.
 - (d) post-ban «не активен» — ОШИБКА АУДИТА (искали Redis KEYS post_ban:* вместо post_ban_until:*). Работает: оба акка post-ban до 04.07 10:06 MSK, бюджет 5000, интервал ×2.
 - Фича «новые + ≤7 дней» — коммит 49e1781 (+тесты t1-t5), лог 0f1a3f3, запушено. Курсор теперь по полной серверной выдаче (чинит пре-баг с безтекстовым хвостом, анти-петля на stale-батчах, доказано t2).

ОСТАТКИ (техдолг, НЕ срочно):
 1. 4 орфанных канала без city/segment (@vietnam_jobs, @danang_jobs, @hcmc_jobs, @saigon_services). @saigon_services — мёртв (UsernameInvalid), удалить. Остальные 3 живы, но без привязки → относится к задаче ГРУППИРОВКА по городам.
 2. _fetch_all_since:452 — немой except Exception: return []. Сейчас не стреляет, расглушить на будущее (logger.warning, поток НЕ менять).
 3. Ключевики перекошены в EN (~1800 demand-фраз EN; RU полн. только «красота»313, «кейтеринг»147). Продуктовое решение, не баг.
СЛЕДУЮЩАЯ ЗАДАЧА (план пользователя): группировка чатов по городам/странам.

**04.07.2026 06:22 — feat: 7-day freshness gate + cursor advance fix (commit 49e1781).**
Добавлен фильтр «не старше 7 дней» в _poll_channel: cutoff из settings.message_max_age_days, датовый гейт перед classify (не трогает курсор). Курсор переведён на server_max по ПОЛНОЙ серверной выдаче (безусловно на непустом батче) — чинит pre-existing баг с безтекстовым хвостом и flood-петлю на залежалых каналах. 5 тестов (t1-t5) покрывают свежие/старые/смешанные/пустые/date=None. 6/6 PASS. +4 коммита в сессии, разрыв с origin: 10. Worker НЕ деплоился — только код и тесты.

**04.07.2026 02:45 — Fix: CB-aware availability, escalating post-ban, cryptg, get_input_entity.**
Задача из прерванной сессии — 6 пунктов. Результат:
1. `_get_available_account_count()` → async, проверяет CB через `limiter.is_circuit_open()`. Корень проблемы: после бана Acc1 метод возвращал 2 → интервал не деградировал → Acc2 работал 10.8ч на полной скорости → бан.
2. `_get_effective_interval()` → async, `max_pb_mult` через `limiter.get_post_ban_interval_multiplier()` по всем аккаунтам, 0 CB-free → cap 1200s + CRITICAL.
3. Эскалация post-ban: Redis счётчик `ban_count:{id}` (TTL 7д). Бюджет: 1 бан → /2, 2 → /4, 3+ → /8. Интервал: ×1.5, ×3.0, ×5.0. 3+ → алерт о риске перманентного бана.
4. cryptg v0.6.0 установлен.
5. `_resolve_entity`: `get_input_entity` вместо `get_entity`. БАГ: в `UserbotAccount` не было `get_input_entity` → AttributeError на 217 каналах. Исправлено: добавлен метод в pool.py.
6. Тесты: rate_limiter 13/13, poller 60/64 (4 не прошли из-за pre-existing сигнатурных mismatch в тестах `_run_tier_once`).
Прогон: worker запущен, Acc1 active (CB clear), Acc2 blocked до 07:10 UTC. Hot: 217 каналов, интервал ×2 деградация. 0 AttributeError. 0 FloodWait.

**05.07.2026 04:00 — Resume handoff: keyword recon, orphan retag, admin frontend cleanup (commit 44a65c7).**
Доделано с предыдущей сессии:
- Smoke test unignore→verify→re-ignore через admin API: зелёный (канал id=885 saigon_services).
- API login путь: `/api/auth/login` (не `/api/login`), порт 17421.
- Коммит: удалена колонка «Направление» (disabled placeholder), добавлена кнопка «Восстановить»
  (handleUnignore, PUT is_ignored=false) для ignored-каналов, кнопка «Удалить» только при !is_ignored.
- Старые статик-ассеты удалены из git (index-BC1Mf4p9.js, index-C-wCZOeF.css, index-C2dFgfOB.css, index-D0xiouDV.js).
- 9 каналов перепривязаны по транслитерации (Valencia, Casablanca, Tehran, Paphos×4, Samui×2) — DB-only, без миграций.
- Документация: kw_recon.txt, orphans_diag.txt, matcher_anatomy.txt, retag_dryrun.txt, admin_front_recon.txt в docs/.
Результат: админ-фича «Чаты без группы» полностью закрыта (шаги 1-4). Орфаны: 830→821.

**05.07.2026 ~11:30 — Админ-панель: масштабный UI/UX-оверхаул ChannelsPage + фикс краша worker.**
Backend (FastAPI + SQLAlchemy):
- +city_ids в list_channels (auto_matched ∪ channel_cities M2M).
- +manually_reviewed bool (модель + GET/PUT + миграция manrev01).
- +discovered_after ISO-фильтр, индекс idx_disc_at01.
- per_page max 100→500 для countries/cities (фикс 422).
- order_by(is_ignored ASC, participants DESC NULLS LAST).
Frontend (ChannelsPage.tsx, 524 строки, полный рерайт):
- Фильтры: статус (Все/Активные/Игнор/Без привязки), страна (dropdown 91), город (зависимый dropdown), «Новые (7д)», perPage (20/100/200/500, default 100), поиск с X.
- Счётчики: «Без привязки: N · Найдено: N». Секция «+ Город».
- 3-цветная точка статуса: фиолетовая (ignored) / зелёная (reviewed) / оранжевая (pending).
- Per-row: Select страны, MultiSelect городов (Popover+Command+Badge, M2M-safe, pre-fill из city_ids), кнопки Save/Trash2/RotateCcw (icon-only size-4).
- 6 колонок: @username(+dot) | Название | Участники | Страна | Города | Действия.
- Убрано: колонка «Привязан», badge «Игнор», verified-фильтр, баннер.
- Новые shadcn-компоненты: command.tsx, popover.tsx, input-group.tsx, multi-select.tsx (кастомный).
Bursa retag: канал 1595 → city_id=59, орфаны 821→820→813.
ИНЦИДЕНТ: worker crash-loop из-за NameError (settings не импортирован в tasks.py:27).
Коммит c626dfd добавил settings.discovery_enabled без импорта. Исправлено: +from app.config import settings, rebuild, restart.
Оба аккаунта CB clear, worker стабилен.
Git: куча немерженных файлов (backend + frontend + migrations + удалённые/новые статик-ассеты + docs).
Handoff: .rpiv/artifacts/handoffs/2026-07-05_channels-ux-overhaul.md.
