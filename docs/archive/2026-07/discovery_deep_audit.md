# Углублённый аудит discovery v2 — готовность к рефакторингу — 2026-07-04

## 1. Текущее состояние discovery v2

### Что работает (функции)

| Функция | Строка | Назначение |
|---|---|---|
| `_slugify()` | 91 | Конвертация названия города в ASCII-slug |
| `_generate_queries()` | 105 | Генерация ~23K запросов: 120+ городов × 84 community-слов (RU+EN) × 8 diaspora-префиксов |
| `_search_and_store()` | 193 | Основной цикл: SearchRequest → парсинг → запись в БД |
| `_discovery_has_dedicated_session()` | 320 | Проверка наличия session-файла |
| `_create_dedicated_discovery_client()` | 325 | Создание отдельного Telethon-клиента |
| `discovery_v2_loop()` | 341 | Главный цикл с circuit breaker проверкой |

### Генерация запросов (строка 105-192)

4 паттерна на каждый город:
1. `{city_en} {community_ru}` — "da nang чат"
2. `{city_ru} {community_ru}` — "дананг болталка"
3. `{city_en} {community_en}` — "da nang chat"
4. `{diaspora_prefix}_{city_slug}` — "kz_danang"

84 community-слов (42 RU + 42 EN), 8 diaspora-префиксов, 120+ городов.

### Дедупликация запросов (в памяти)

```python
# Строка 118
seen: set[str] = set()
def _add(query, ...):
    if q and q not in seen and len(q) >= 2:
        seen.add(q)
```

**В памяти, теряется при рестарте.** При рестарте `_generate_queries()` вызывается заново, `seen` пуст — все 23K запросов генерируются заново.

### random.shuffle() (уже есть)

```python
# Строка 402
random.shuffle(queries)
```
Порядок запросов случайный каждый цикл. ✅

### Прогресс (НЕТ)

**Курсор отсутствует.** При рестарте worker цикл начинается с `queries[0]`. Redis-ключей для discovery нет.

### Что нужно добавить

- Redis-ключ `discovery:cursor:query_index` (INT) — последний обработанный индекс
- Redis SET `discovery:seen:queries` (TTL 30д) — дедупликация между рестартами
- Сохранение каждые 10 запросов

---

## 2. Режимы сна и имитация человека

### Что уже есть

```python
INTER_QUERY_PAUSE_MIN = 60   # фиксировано
INTER_QUERY_PAUSE_MAX = 120  # фиксировано
await asyncio.sleep(random.uniform(60, 120))  # строка 326
```

Стартовый stagger: 15 минут (строка 365). `random.shuffle()` — порядок хаотичен.

### Чего НЕТ

- Зависимости от времени суток (ночь/день)
- Длинных случайных перерывов («перекуры»)
- Выходных/праздничных дней

### Что нужно добавить

```python
# Паузы по времени суток (UTC)
PAUSE_SCHEDULE = {
    (2, 8):   (1800, 3600),   # ночь: 30-60 мин
    (8, 12):  (180, 600),     # утро: 3-10 мин
    (12, 18): (60, 180),      # день: 1-3 мин
    (18, 2):  (300, 900),     # вечер: 5-15 мин
}

# Случайные перекуры: каждые 50-200 запросов, 3% вероятность
BREAK_PROBABILITY = 0.03
BREAK_DURATION = (600, 3600)  # 10-60 мин
```

---

## 3. Circuit Breaker

### Что уже есть

```python
# discovery_v2.py:28 — импортирует ОБЩИЙ limiter поллера
from app.userbot.rate_limiter import limiter

# Строка 216 — проверка CB каждые 100 запросов
if await limiter.is_circuit_open(DISCOVERY_ACCOUNT_ID):
    await limiter.wait_if_circuit_open(DISCOVERY_ACCOUNT_ID)

# Строка 385 — проверка в главном цикле
if await limiter.is_circuit_open(DISCOVERY_ACCOUNT_ID):
    await limiter.wait_if_circuit_open(DISCOVERY_ACCOUNT_ID)
```

**Использует ОБЩИЙ лимитер с поллером.** `DISCOVERY_ACCOUNT_ID = 1` — тот же аккаунт, что и поллер. CB срабатывает на аккаунт #1 → блокирует И поллер, И discovery.

Redis-ключи: `circuit:open:1`, `circuit:expires:1` (общие с поллером).

### Что нужно изменить

- Создать ОТДЕЛЬНЫЙ экземпляр `TelegramRateLimiter` для discovery (свой `min_interval`, свой `daily_budget`)
- CB-ключи будут: `circuit:open:3` → только discovery

---

## 4. Обработка ошибок и FloodWait

### FloodWaitError (строка 232-238)

```python
except FloodWaitError as e:
    logger.warning("Discovery v2 FloodWait: %ds", e.seconds)
    await limiter.report_flood_wait(
        e.seconds, context=f"discovery_v2:{q['query']}",
        account_id=DISCOVERY_ACCOUNT_ID,
    )
    await asyncio.sleep(e.seconds)
    continue
```

- `report_flood_wait()` → circuit breaker + `notify_admin()` (с троттлингом 15 мин)
- `await asyncio.sleep(e.seconds)` — ждёт ровно столько, сколько сказал Telegram
- **НЕТ экспоненциального backoff** — каждая следующая ошибка ждёт столько же

### Другие исключения (строка 240-241)

```python
except Exception as e:
    logger.debug("Discovery v2: search failed '%s': %s", q["query"], e)
```

**Глушатся на DEBUG** — не видны в проде. TimeoutError, RPCError, ServerError теряются.

### flood_sleep_threshold

В коде discovery НЕ используется. Есть в `settings.flood_sleep_threshold = 60` (общий конфиг), но клиент создаётся без его явной передачи.

### Что нужно изменить

- `except Exception` → `logger.warning(type(e).__name__)` для видимости
- Добавить счётчик последовательных FloodWait + экспоненциальный backoff
- Передавать `flood_sleep_threshold` при создании клиента

---

## 5. Гео-привязка найденных каналов

### Как работает (строка 278-311)

Каждый запрос несёт метаданные: `country_id`, `city_id`, `country_name`, `city_name` (из `_generate_queries()`).

При нахождении канала:
```python
# Новый канал — полная привязка
session.add(CatalogChannel(
    auto_matched_country_id=q["country_id"],
    auto_matched_city_id=q["city_id"],
))
# Существующий — backfill только если NULL
if q["country_id"] and not row.auto_matched_country_id:
    row.auto_matched_country_id = q["country_id"]
if q["city_id"] and not row.auto_matched_city_id:
    row.auto_matched_city_id = q["city_id"]
```

**Поля:** `auto_matched_country_id`, `auto_matched_city_id`. Каналы без города (общие запросы) получают только `country_id`.

### Внешние API

Нет. Только локальная БД (таблицы `countries`, `cities`).

### Что работает корректно

Гео-привязка — **полностью рабочая**, менять нечего. ✅

---

## 6. Уведомления в админ-канал

### Что уже есть

```python
# Только FloodWait — через limiter.report_flood_wait() (строка 234)
# Статистика цикла — через report_discovery_stats() (строка 407)
from app.userbot.discovery import report_discovery_stats
await report_discovery_stats(found)
```

`report_discovery_stats()` (discovery.py:144-158):
```python
await notify_admin(
    f"📊 Отчёт поиска каналов\n\n"
    f"Найдено новых: {new_found}\n"
    f"Всего в каталоге: {total}\n"
    f"С гео-привязкой: {with_geo}"
)
```

### Чего НЕТ

- Уведомления о старте/стопе цикла
- Уведомления о достижении суточного лимита
- Уведомления о circuit breaker
- Троттлинга статистики (каждый цикл = одно уведомление — ОК при 46-дневном цикле)

### FloodWait-уведомления

Уже имеют троттлинг 15 мин через `limiter.report_flood_wait()` ✅

---

## 7. Изоляция от пуллера (даже без третьего аккаунта)

### Текущее состояние: НОЛЬ изоляции

```python
from app.userbot.rate_limiter import limiter  # ОБЩИЙ с поллером
DISCOVERY_ACCOUNT_ID = 1                       # аккаунт поллера
DISCOVERY_SESSION_NAME = "userbot"              # та же сессия
```

**Общий лимитер, общий CB, общая сессия.** Бан discovery = бан поллера.

### Режим «ручного запуска» (без третьего аккаунта)

Можно запускать discovery на аккаунте #1 **только когда поллер неактивен**:

```python
# Проверка: поллер в PAUSED/SLEEPING?
state = await self._get_session_state(1)
if state in ("PAUSED", "SLEEPING"):
    # Можно запускать discovery
else:
    # Поллер активен — ждать
```

**Redis-флаг поллера:** `session:state:1` (уже есть из сессионной модели поллера).

**Ручной запуск админом:**
- API-эндпоинт `POST /api/discovery/start` → проверяет `session:state:1` → запускает если поллер не ACTIVE
- Или через Redis-ключ `discovery:manual:run` (ставится админом, проверяется discovery loop)

### Рекомендация

Без третьего аккаунта — режим «только ночью» (2:00-8:00 UTC, поллер в SLEEPING). С третьим аккаунтом — полная изоляция 24/7.

---

## 8. Суточный бюджет

### Сейчас

**НЕТ.** Используется общий `limiter.acquire()` с бюджетом 10000/день (для поллера).

### Что нужно добавить

```python
# app/config.py
discovery_daily_budget: int = 500  # запросов/день

# app/userbot/discovery_v2.py — отдельный limiter
discovery_limiter = TelegramRateLimiter(
    min_interval=2.0,
    daily_budget=settings.discovery_daily_budget,
)

# При исчерпании — BudgetExceeded → сон до следующего дня
except BudgetExceeded:
    logger.warning("Discovery daily budget exhausted — sleeping 1h")
    await asyncio.sleep(3600)
    continue
```

Redis-ключ: `budget:used:3:{YYYY-MM-DD}` (автоматически через `limiter.acquire()`).

---

## 9. Мониторинг и метрики

### Что уже есть

```python
# Каждые 100 запросов — лог (строка 224)
logger.info("Discovery v2: %d/%d queries (%d new, %d skipped)", ...)

# В конце цикла — лог (строка 414)
logger.info("Discovery v2: cycle complete — %d new channels from %d queries", ...)

# Статистика через notify_admin (строка 407)
await report_discovery_stats(found)
```

### Чего НЕТ

- Redis-метрик (запросы/найдено/ошибки за день)
- Алертов при аномалиях (10+ ошибок подряд, FloodWait > 1ч)
- Prometheus/Grafana (не нужно на старте)

### Что добавить (минимально)

```python
# Redis-ключи с TTL 7 дней
discovery:stats:{date}:queries    # INT
discovery:stats:{date}:found      # INT
discovery:stats:{date}:errors     # INT
discovery:stats:{date}:floodwait  # INT
```

---

## 10. Интеграция с основным приложением

### Как запускается сейчас

**НИКАК.** Вызовы удалены из `app/worker/tasks.py` (строка 24-25).

### Как запустить

```python
# app/worker/tasks.py — добавить:
if discovery_account:
    asyncio.create_task(discovery_v2_loop(discovery_account.client))
```

Запуск как часть основного event loop worker. Отдельный контейнер НЕ нужен — достаточно отдельного таска в том же event loop (asyncio).

### Как остановить

- Redis-ключ `discovery:pause` (ставится админом, проверяется в loop)
- Или просто не запускать таск

---

## СВОДКА

### Что уже есть и работает ✅

| Компонент | Статус |
|---|---|
| Генерация запросов (города × слова × языки) | ✅ Полностью рабочая |
| `SearchRequest` с лимитами | ✅ |
| Гео-привязка (country_id + city_id) | ✅ |
| `random.shuffle()` — случайный порядок | ✅ |
| Фиксированные паузы 60-120с | ✅ |
| FloodWait-обработка (базовая) | ✅ |
| `is_ignored` проверка | ✅ |
| Circuit breaker (общий с поллером) | ⚠️ Работает, но ОБЩИЙ |

### Что нужно добавить/изменить (приоритеты)

| Приоритет | Что |
|---|---|
| 🔴 Критический | Отдельный аккаунт #3 (SIM) — без него полная изоляция невозможна |
| 🔴 Критический | Отдельный `TelegramRateLimiter` для discovery |
| 🔴 Критический | `DISCOVERY_ACCOUNT_ID = 3`, отдельная сессия |
| 🟡 Важный | Redis-курсор прогресса (`discovery:cursor:query_index`) |
| 🟡 Важный | Суточный бюджет 500 запросов |
| 🟡 Важный | Human-like паузы (ночь/день) |
| 🟡 Важный | `except Exception` → `logger.warning` |
| 🟢 Желательный | Экспоненциальный backoff для FloodWait |
| 🟢 Желательный | Redis-метрики |
| 🟢 Желательный | Режим «ручного запуска» для админа |

### Риски запуска прямо сейчас (без изменений)

**Категорически НЕЛЬЗЯ.** Общий аккаунт + общий лимитер + общий CB = гарантированный бан обоих сервисов при первой же ошибке discovery. Именно поэтому discovery отключён.

### Первый шаг рефакторинга

1. Получить третий аккаунт (SIM) — **блокирующее предусловие**
2. Добавить креды в `.env` → `app/config.py`
3. Создать `discovery_limiter` (отдельный экземпляр `TelegramRateLimiter`)
4. `DISCOVERY_ACCOUNT_ID = 3`
5. Подключить в `tasks.py` как отдельный таск
6. Запустить в режиме «только ночью» на 1 неделю для проверки

**Без третьего аккаунта:** можно запускать discovery только когда поллер в SLEEPING (Redis `session:state:1`), но это нестабильно — при пробуждении поллера оба сервиса делят аккаунт. Рекомендуется ждать SIM.
