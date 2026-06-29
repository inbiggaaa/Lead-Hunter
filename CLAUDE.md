# CLAUDE.md — контекст проекта для Claude Code

Этот файл Claude Code читает автоматически в начале каждой сессии. Содержит всё критичное для продолжения работы. Остальное — в сопровождающих файлах (см. ссылки ниже).

**Сопровождающие файлы:**
- `CODING_STYLE.md` — конвенции кода (обязательно к соблюдению)
- `TESTING.md` — стратегия тестирования + QA checklist
- `RECOVERY.md` — план восстановления (читать при любой поломке)
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
│  [admin]    FastAPI + SQLAdmin — веб-панель (127.0.0.1:8001)        │
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
| Админка | FastAPI + SQLAdmin |
| Платежи | Stars, CryptoBot (PaymentProvider Protocol) |
| Конфиг | pydantic-settings (.env) |
| Мониторинг | Sentry |
| Тесты | pytest + pytest-asyncio |

Версии: `aiogram>=3.7,<4.0`, `telethon>=1.36,<2.0`, `SQLAlchemy>=2.0,<3.0`, `asyncpg>=0.29,<1.0`, `aiohttp>=3.9,<4.0`, `alembic>=1.13,<2.0`, `redis>=5.0,<6.0`, `fastapi>=0.110,<1.0`, `sqladmin>=0.16,<1.0`, `pydantic-settings>=2.2,<3.0`, `sentry-sdk>=2.0,<3.0`, `pytest>=8.0,<9.0`, `pytest-asyncio>=0.23,<1.0`

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
    ├── admin/                 ← FastAPI + SQLAdmin
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

## 5д. Админ-панель (7 разделов)

- **📊 Дашборд:** KPI (всего/новых/оплат/продлений), графики Chart.js, источники
- **👥 Пользователи:** таблица, фильтры, детали, can_edit/delete
- **💰 Подписки:** таблица, статусы, фильтры
- **🌍 Каталог:** CRUD стран, городов, сегментов, keywords, каналов (M:N матрица), discovered_chats
- **💬 Live-чат:** WebSocket + AJAX, список диалогов с 🔴, история
- **📨 Рассылки:** выборка, превью, статус. Напоминания: trial/подписка/неактивность (дни 1,3,7)
- **⚙️ Настройки:** тарифные лимиты, системные переменные

Доступ: SSH-туннель `ssh -L 8001:127.0.0.1:8001`. ADMIN_SECRET обязателен.

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
| Ф7 | Оплата (Stars + CryptoBot) | ⬜ |
| Ф8 | Надёжность (Docker, бэкапы, Sentry) | ⬜ |
| Ф9 | Масштабирование (пул userbot) | ⬜ |

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
- **Админ-доступ:** SSH-туннель `ssh -L 8001:127.0.0.1:8001`
- **Авторизация userbot:** `docker compose run --rm -it worker python -m app.userbot.auth`

---

## 8. Текущий статус

**ОБНОВЛЯТЬ ПОСЛЕ КАЖДОЙ СЕССИИ.**

Дата: **2026-06-29**

Фаза: **Фаза 6б (дашборд аналитики)** ⏳

Сделано: Фазы 0-6а завершены. SQLAdmin админка (http://127.0.0.1:8001/admin), 20 моделей в CRUD, авторизация по паролю.

Следующее: дашборд с KPI и графиками.

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
