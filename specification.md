# LeadHunter — Полная спецификация проекта

> Версия документа: 2026-07-16 · Источник истины по контексту — `CLAUDE.md`, `DECISIONS.md`, `docs/SESSION_LOG.md`.
> Этот файл — сводная спецификация: что за продукт, как устроен, из чего собран и как работает.

---

## 1. Обзор продукта

**LeadHunter** — SaaS-сервис на базе Telegram-бота для лидогенерации. Отслеживает сообщения по ключевым словам и семантическим сегментам в публичных Telegram-каналах и присылает подписчикам уведомления о новых заявках (лидах). Модель монетизации — **freemium**.

- **Userbot** (Telethon / MTProto) слушает публичные каналы (без вступления, по tier-поллингу).
- **Bot API** (aiogram) управляет интерфейсом, командами и отправкой уведомлений.
- **Аудитория:** русскоязычная + международная (i18n RU/EN по `language_code`).

### Метрика ценности (решения #81, #82)
Ценность = **широта покрытия** (направления × география), а НЕ количество уведомлений.
Дневной лимит уведомлений отменён на всех тарифах.

---

## 2. Тарифная матрица v2.1 (решение #82, 14.07.2026)

| | Free (воронка) | 🎯 Старт ($9/мес) | 🚀 Профи ($19/мес) | 🏆 Бизнес ($39/мес) |
|---|---|---|---|---|
| Матчинг | безлимит | безлимит | безлимит | безлимит |
| Уведомлений/день | безлимит | безлимит | безлимит | безлимит |
| Направления (подкатегории) | 1 | 1 | 3 | 12 |
| География | 1 страна, города ∞ | 1 страна, города ∞ | до 3 стран, города ∞ | до 9 стран, города ∞ |
| Свои каналы | 1 | 1 | 10 | 50 |
| Ключевых фраз | 1 | 3 | 20 | 50 |
| Контакты | СКРЫТЫ | Полные | Полные | Полные |
| Кнопки | «🎯 Открыть контакты» | «💬 Ответить» | «💬 Ответить» | «💬 Ответить» |
| Regex | — | — | да | да |
| Статистика в боте | — | — | базовая (7 дн.) | полная (30 дн., по сегментам) |
| CSV-экспорт | — | — | — | да (метаданные без текста заявки) |
| Digest-режим | да | да | да | да |
| Trial | — | — | 3 дня; 7 по referral | — |
| End-of-day отчёт | да (19:00) | — | — | — |

- Скидки за период: 3 мес −10%, год −20%.
- Внутренние slug'и: `free` / `start` / `pro` / `business` / `trial`.
- Runtime-источник истины по лимитам: `app/config.py` + `crud._plan_limits()` (переопределяется через `.env`).
- Grandfathering: платящие дорабатывают оплаченный период на старых условиях.

### Trial и рефералы (контракт #84)
- Trial = 3 дня Про после первого поиска; referral trial = 7 дней (+4).
- По истечении → Free сразу: контакты и ссылки скрыты, поиски сохраняются.
- Без подписки: макс. 2 скрытых teaser-лида + EOD-отчёт в дни 0/3/7/14; день 30 — одноразовая скидка 25% на 3 месяца, окно 12 часов.
- После первой оплаты приглашённого referrer получает +10 дней текущего тарифа (на Free — восстановление последнего оплаченного, без истории — Start). Лимит 10/мес.
- Deep-link: `t.me/LeadHunterBot?start=ref_CODE`.

### Оплата
Старт: **Telegram Stars + CryptoBot**. Позже: карты, QR СБП, YooKassa. Интерфейс `PaymentProvider` (Protocol).

---

## 3. Архитектура

```
Пользователи (Free / Start / Pro / Business)
        │  Bot API
        ▼
┌──────────────────── VPS (Docker Compose) ────────────────────┐
│  [bot]      aiogram 3.x — управляющий бот, команды, платежи   │
│  [worker]   Telethon + sender — userbot + рассыльщик (1 loop) │
│  [admin]    FastAPI — админ-панель (React SPA + REST, :8001)  │
│  [db]       PostgreSQL — пользователи, подписки, каталог      │
│  [redis]    Redis — кэш подписок + очередь уведомлений        │
└───────────────────────────────────────────────────────────────┘
        │  userbot (MTProto)          │  Bot API
        ▼                             ▼
   Публичные каналы            Личные чаты пользователей
```

### Сервисы Docker Compose
`db` (PostgreSQL) · `redis` · `bot` (aiogram) · `worker` (Telethon+sender) · `admin` (FastAPI+SPA).
Тома: `postgres_data`, `redis_data`. Сессии userbot: bind-mount `./sessions:/app/sessions`.

### Инфраструктура
- Docker Compose, Ubuntu 24.04, 2GB RAM / 1 Core, обязательный swap 2GB.
- Memory limits: bot=300MB, worker=1GB, admin=200MB, postgres=400MB, redis=100MB.
- Admin: `127.0.0.1:8001` (SSH-туннель) / публичный порт `ADMIN_PUBLIC_PORT` (по умолчанию 17421), пароль `ADMIN_PASSWORD`.
- Деплой: сервер = dev + prod, `git push` с сервера, `docker compose up -d --build`.

### Поток данных
```
userbot поллит каналы (тиры Hot/Warm/Cold, курсоры в Redis)
    ▼
classify_message(text) → ["catering", "cleaning"]   (1 раз на сообщение)
    │  (или keyword_only-матч по личным keywords — минует сегменты и LLM)
    ▼
reality-фильтр (domain-слова, word-boundary) → LLM-валидатор (blocking, батч)
    ▼
_dispatch → get_interested_users(chat_username)   (Redis-кэш sub:by_chat:*)
    ▼
Дедуп: sha256(chat_username:message_id), UNIQUE(user_id, hash) + content_hash (репосты 24ч)
    ▼
LPUSH queue:notifications → sender BRPOP + throttle → Bot API (retry / DLQ)
```

---

## 4. Технический стек

| Компонент | Технология | Версия |
|---|---|---|
| Python | CPython | 3.11+ |
| Бот | aiogram | >=3.7,<4.0 |
| Userbot | Telethon (+cryptg) | >=1.36,<2.0 |
| ORM | SQLAlchemy (async) | >=2.0,<3.0 |
| Драйвер БД | asyncpg | >=0.29,<1.0 |
| Миграции | Alembic | >=1.13,<2.0 |
| Кэш+очередь | Redis (LPUSH/BRPOP) | >=5.0,<6.0 |
| HTTP | aiohttp | >=3.9,<4.0 |
| Админ backend | FastAPI + uvicorn | >=0.110,<1.0 |
| Админ frontend | React 19 + TS + Vite 8 + shadcn/ui 4 + Tailwind 4 + React Query 5 + Chart.js 4 | — |
| Конфиг | pydantic-settings (.env) | >=2.2,<3.0 |
| NLP | pymorphy3 | >=1.2,<2.0 |
| LLM-валидатор | DeepSeek-V3 (`deepseek-chat`) | — |
| Мониторинг | Sentry | >=2.0,<3.0 |
| Тесты | pytest + pytest-asyncio + fakeredis | >=8.0 |

---

## 5. Структура репозитория

```
LeadHunter/
├── CLAUDE.md / DECISIONS.md / RECOVERY.md / OPERATIONS.md
├── CODING_STYLE.md / TESTING.md / USERFLOW.md / ONBOARDING.md / SETUP.md
├── fable_audit.md / fable_core_plan.md / fable_tariff_plan.md / codex_userflow.md
├── docker-compose.yml / Dockerfile / requirements.txt / alembic.ini
├── migrations/versions/          ← Alembic-миграции
├── tests/                        ← conftest, unit, integration, smoke
├── seed/                         ← сиды каталога и keywords
├── tools/                        ← eval_matching.py, диагностика
├── docs/                         ← SESSION_LOG.md, eval/, archive/
└── app/
    ├── config.py                 ← pydantic-settings
    ├── main.py                   ← точка входа бота
    ├── analytics.py / lifecycle.py
    ├── locales/                  ← ru.py, en.py
    ├── bot/handlers/             ← start, keywords, channels, plan,
    │                                discover, catalog_nav, feedback, support
    │   └── middlewares/          ← проверка подписки, лимитов
    ├── admin/                    ← app.py, dashboard, chat, broadcast
    │   └── api/                  ← auth, users, stats, broadcast, chat,
    │                                crud, segments, stop_words, unmatched
    ├── db/                       ← models.py, session.py, crud.py
    ├── userbot/                  ← pool, poller, classifier, llm_validator,
    │                                rate_limiter, discovery(_v2), auth
    ├── cache/                    ← subscription_cache.py
    ├── payments/                 ← base(Protocol), stars.py, cryptobot.py
    └── worker/                   ← tasks, sender, heartbeat, reminders,
                                     end_of_day, digest, payment_checker, notify_admin
```

---

## 6. Модель данных (PostgreSQL)

Таблицы (по `app/db/models.py`):

**Ядро пользователя:** `users`, `subscriptions`, `keywords`, `watched_chats`, `sent_log`.
**Каталог v2 (M:N):** `countries`, `cities`, `categories`, `segments`, `segment_keywords`, `catalog_channels`, `channel_segments`, `channel_cities`.
**Подписки на сегменты:** `user_subscriptions`, `subscription_cities`.
**Discovery:** `discovered_chats`.
**Рост/реферал/поддержка:** `referrals`, `support_messages`, `user_ignores`, `reminders`, `winback_offers`, `periodic_prefs`.
**ML/качество:** `llm_decisions` (shadow-датасет для fine-tune), `feedback`.

### Ключевые сущности
- `users`: `telegram_id`, `plan` (free/start/pro/business/trial), `plan_activated_at`, `plan_expires_at`, флаги `is_banned/is_suspended/is_blocked_bot`, `source`, `free_lifecycle_at`.
- `segments`: `slug`, `title_ru/en`, `is_quarantined` (матчится+логируется, не диспатчится), `lead_direction` (`demand`/`buy`/`supply`).
- `segment_keywords`: `keyword_type` ∈ {`demand`, `stop`, `synonym`}, `is_regex`; `segment_id=NULL` → универсальная фраза.
- `sent_log`: `message_hash` = sha256(chat_username:message_id), `content_hash` (дедуп репостов 24ч), `is_urgent`; UNIQUE(user_id, message_hash).
- `user_subscriptions`: UNIQUE(user_id, segment_id, country_id), `mode` ∈ {`all`, `cities`}; индекс `idx_user_sub_lookup(segment_id, country_id)`.

### Логика раздачи
- **Вариант А (подписка):** чат в `channel_segments[segment]` И (`mode='all'` ИЛИ чат в `channel_cities` для `subscription_cities`) И текст совпадает с `segment_keywords` ИЛИ личными `keywords`.
- **Вариант Б (свой канал):** чат в `watched_chats` И текст совпадает с личными `keywords`.

---

## 7. Семантическое ядро (матчинг)

### Алгоритм: трёхпроходный rule-based NLP + LLM-валидация
Движок предкомпилирован (`compile_keyword_map` при startup + reload каждые 5 мин); hot-path только матчит.

1. **Проход 1 — demand:** поиск фраз по границе целого слова `(?<!\w)keyword(?!\w)`, Unicode, case-insensitive, лемма-формы (pymorphy3). Multi-word фразы — в окне близости `KEYWORD_MATCH_WINDOW` токенов (дефолт 20). Нет demand → игнор.
2. **Проход 2 — stop:** проверка на универсальные и сегментные stop-фразы. Переопределяет stop только СИЛЬНЫЙ сигнал спроса (глагольные паттерны); голый «?» — нет. Stop-фразы окном не ограничены.
3. **Проход 3 — структурные сигналы:** разрешение коллизий спрос/оффер. Глагол спроса в начале перебивает оффер; `?` — слабый сигнал; цена+контакт+хештеги усиливают оффер. Сегменты `lead_direction` `buy`/`supply` минуют Проход 3.

- **Направление сегмента** — конфигурация в БД (`segments.lead_direction`), не хардкод. Supply-сегменты дополнительно инвертируют DEMAND/OFFER в LLM-промпте.
- **Reality-фильтр (до LLM):** сегмент подтверждается только если в тексте есть domain-слово сегмента (synonym-словарь из БД), word-boundary.
- **Личные keywords работают всегда** (Вариант Б): минуют сегменты, reality-фильтр и LLM.
- **Срочность (🔥):** «срочно / сегодня / на завтра / asap / urgent» → `is_urgent=true`.
- **Короткие anchors** («нужен байк», «хочу тату») — только с контекстным сигналом спроса.

### Каталог
14 категорий / 69 подкатегорий-сегментов (реструктуризация 08.07.2026), ~1500 keywords в БД — единственный источник истины (`segment_keywords`, правка через админку `/catalog`).

### LLM-валидация (ВКЛЮЧЕНА, blocking)
`llm_validator.py`: DeepSeek-V3, батч-запрос после classifier и reality-фильтра. Вердикты DEMAND/MIXED пропускают, OFFER/OTHER гасят. **Fail-open** (ошибка LLM → лид проходит). Все решения → `llm_decisions`.

### Eval-конвейер
`venv/bin/python tools/eval_matching.py` — по-сегментный отчёт качества с прод-данных (read-only). Правило: любые изменения правил классификатора / LLM-промпта сопровождаются прогоном eval (отчёты — `docs/eval/`).

---

## 8. Redis — кэш, очереди, ключи

```
sub:by_chat:{chat_username}      → JSON [{user_id, telegram_id, lang, plan, subscriptions, keyword_texts}]
stats:daily:{uid}:{date}:matched → INT (инкремент в _dispatch)
stats:daily:{uid}:{date}:sent    → INT (инкремент в sender после доставки)
stats:unmatched                  → LIST (последние 10000, dedup через :seen)
stats:full_batch:{chat}          → INT (возможные пропуски, TTL 30д)
stats:llm:total:{YYYY-MM-DDTHH}  → INT (валидаций за час UTC, TTL 48ч)
stats:llm:fail_open:{час}        → INT (fail-open; алерт >20% / >50%)
cursor:msg:{chat}                → INT (инкрементальный поллинг)
limit_reached:{uid}:{date}       → "1" (TTL до полуночи)
queue:notifications              → LPUSH/BRPOP
dlq:notifications                → LPUSH/BRPOP
heartbeat:userbot:{id}           → timestamp
budget:used:{account_id}:{date}  → INT (суточный API-бюджет)
circuit:open/expires:{id}, session:*, post_ban_until:{id}  — anti-ban
```
Инвалидация кэша подписок: `invalidate_all_subscription_caches()` во всех CRUD-точках + TTL 1ч. В кэше только пользователи с подпиской или keyword.

### Retry-логика
| Ошибка | Действие |
|---|---|
| 403 Forbidden | `is_blocked_bot=TRUE`, удалить из кэша |
| 429 Too Many Requests | `sleep(retry_after)`, повторить |
| 5xx / network | 3 ретрая (1с, 4с, 9с) → dead-letter |
| Throttle | 25/сек (`sender_throttle_per_second`) |
| Мониторинг | LLEN очереди, алерт при backlog > 100 |

---

## 9. Пользовательский интерфейс (User Flow)

**Принципы:** только inline-клавиатуры (кроме `/start`), у каждого экрана «◀️ Назад», FSM с `/cancel`.

**Главное меню (4 кнопки, с 30.06.2026):**
🔍 Поиск клиентов → FSM-воронка | 💰 Тариф и оплата | 🎁 Пригласить друга | ⚙️ Настройки (→ 6 подэкранов).
Прямые команды: `/keywords`, `/channels`, `/subscriptions`, `/plan`, `/settings`, `/search`.

**FSM-воронка (`CatStates`):**
```
choosing_segment → choosing_country → choosing_geo →
choosing_cities / confirm_subscription → trial_activation / payment_offer →
show_last_leads → done
```
- Free: single-select (1/1). Pro: multi-select (3/3). Business: unlimited.
- Первая подписка → trial_activation (3 дня Про; referral — 7 дней). Существующий Free → payment_offer.

**Форматы уведомлений:**
- Free — контакты скрыты, ни одной ссылки (решение #79), кнопка «🎯 Открыть контакты — от $9/мес».
- Paid/Trial — полный формат: @отправитель (или имя-fallback при отсутствии username) + название чата, кнопки «💬 Ответить». 🔥 для срочных.

Полная карта 21 экрана и все тексты RU+EN — `USERFLOW.md`.

---

## 10. Админ-панель (10 разделов)

Backend: FastAPI (:8001), сессионная авторизация, Redis brute-force protection (5 попыток/мин).
Frontend: React 19 SPA (статика в `app/admin/static/`), WebSocket для live-чата, Chart.js для дашборда.

| Роут | Раздел | Функционал |
|---|---|---|
| `/login` | Вход | Пароль + защита от брутфорса |
| `/` | 📊 Дашборд | 4 KPI, график новых юзеров (30д), pie по тарифам |
| `/users` | 👥 Пользователи | Поиск, фильтр по тарифу, бан/разбан, детали |
| `/catalog` | 🌍 Каталог | Сегменты (CRUD + keywords Demand/Stop/Synonym), Страны, Города |
| `/channels` | 📢 Каналы | Каталог, поиск, фильтр verified |
| `/stop-words` | 🛑 Стоп-слова | CRUD с привязкой к сегменту |
| `/unmatched` | 📋 Несматченные | Из Redis `stats:unmatched`, поиск, фильтр |
| `/chat` | 💬 Live-чат | WebSocket, диалоги с 🔴, история, отправка |
| `/broadcast` | 📨 Рассылки | Выборка по тарифу/источнику, превью, статистика |
| `/settings` | ⚙️ Настройки | Тарифные лимиты + system info (read-only) |

API (`/api/*`): `auth`, `users`, `stats`, `broadcast`, `chat`, `crud` (страны/города/сегменты/keywords), `stop_words`, `unmatched`, `segments`, `channels`.

---

## 11. Правила эксплуатации и разработки

### Защита от бана Telegram (критично)
- Userbot: задержки 3–5 сек, `FloodWait → sleep(seconds)`, только публичные каналы, поллинг без вступления (лимит ~500 каналов/аккаунт, решение #80).
- Перед ЛЮБЫМ изменением в `poller.py` / `rate_limiter.py` / `classifier.py` / `pool.py` — читать `OPERATIONS.md` §2 (Hard Rules) и §5 (чек-лист). После деплоя — 2 мин мониторить логи на `FloodWait`.
- **НЕ трогать прод при работающем worker:** запрещено `docker compose run/exec/restart/up -d` при живом `worker`. Тесты и миграции — только при остановленном worker или в dev-окружении.
- Безопасно при работающем worker: `docker compose restart bot` (правки только бота).

### Конвенции кода (`CODING_STYLE.md`)
Функции ≤30 строк, ранний возврат, типизация без `Any`, Protocol для интерфейсов, секреты только в `.env`.

### Тестирование (`TESTING.md`)
pytest + pytest-asyncio; unit (с Ф2), integration, smoke (с Ф5); pre-commit checklist.

### Эксплуатация
- Heartbeat: 15 мин, проверка раз в минуту, алерт владельцу.
- Бэкапы: `pg_dump` раз в сутки, ротация 7 дней; перед миграцией — обязательный `pg_dump`.
- Миграции обратимые (`downgrade()`).
- Авторизация userbot: `docker compose run --rm -it worker python -m app.userbot.auth`.
- Session log: после каждой задачи — запись в `docs/SESSION_LOG.md` + обновление статуса в `CLAUDE.md §8`.

---

## 12. Статус проекта (на 2026-07-16)

- Все 9 фаз разработки завершены (Ф0–Ф9). Аудит `fable_audit.md` закрыт. Активный план качества ядра — `fable_core_plan.md`.
- Тарифы v2 задеплоены в прод 13.07.2026; userflow v2 + lifecycle (U0–U10) внедрены; ветки консолидированы на `main` (это прод).
- Прод работает штатно: bot/worker/admin/db/redis Up, поллинг чистый (0 FloodWait), pool 2 healthy, LLM-валидатор активен, ~3361 keyword / 71 сегмент / 95 pre-tagged каналов.
- Последний коммит: `c87cc9f — feat(admin): remove delivery-latency block, show real DeepSeek key balance`.

### Открытые хвосты
- Анонс тарифов через админку `/broadcast`; живой тест оплаты Stars; 2-нед. мониторинг конверсий.
- Чистка каталога от битых каналов (`docs/broken_channels_2026-07-14.md`).
- Отложено: Sentry, TLS/домен для админки, fine-tune LLM из `llm_decisions`, разметка каналов без города.

---

## 13. Ключевые решения (выдержка, полный архив — `DECISIONS.md`)

| # | Решение |
|---|---|
| 3 | Redis-кэш подписок с инвалидацией |
| 4 | Каталог сразу v2 (M:N) |
| 16 | segment_keywords.keyword_type ∈ {demand, stop, synonym} |
| 18/19 | Трёхпроходный классификатор, per-message классификация |
| 26 | Retry: 403→блок, 429→retry_after, 5xx→3 ретрая + DLQ |
| 27 | Только inline-клавиатуры (кроме /start) |
| 65 | LLM-валидация — ВКЛЮЧЕНА в blocking с 02.07.2026 |
| 79 | Free-пейволл: ни одной ссылки в Free-уведомлении |
| 80 | Поллинг без вступления в каналы (не event-push) |
| 81 | Тарифы v2: отказ от дневного лимита уведомлений |
| 82 | Тарифы v2.1: финальная матрица лимитов (см. §2) |
| 84 | Trial 3 дня / referral 7 дней; referrer +10 дней после первой оплаты |

---

*Документ отражает состояние на 2026-07-16. При расхождении с кодом источник истины — сам код и `CLAUDE.md`.*
