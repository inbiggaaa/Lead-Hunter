# План рефакторинга discovery v2 — 2026-07-04

## Контекст

Discovery v2 отключён (коммиты 61522a6 + 2fe673a). Причина: шарит аккаунт #1 с поллером → бан discovery = бан всего сервиса. Аудит выявил дополнительно: потеря прогресса при рестарте, ошибки глушатся на DEBUG, нет human-like паттернов, нет отдельного бюджета.

## Этап 0: Инфраструктурный (не код, а подготовка)

**Что нужно:** третий Telegram-аккаунт (отдельная SIM-карта).

**Без этого discovery включать НЕЛЬЗЯ.** Архитектура рефакторинга предполагает изолированный аккаунт, но сам аккаунт — физическая сущность, не код.

**Действия:** приобрести SIM → зарегистрировать Telegram-аккаунт → добавить в `.env`:
```
DISCOVERY_API_ID=...       # отдельное приложение или reuse существующего
DISCOVERY_API_HASH=...
DISCOVERY_PHONE=+7...
```
Если отдельное приложение не создаётся — использовать `userbot_api_id`/`userbot_api_hash` (как для аккаунта #2), но phone обязательно новый.

## Этап 1: Изоляция (минимально жизнеспособный)

### 1.1 Новый аккаунт в пуле

**Файл:** `app/config.py`
```python
# Discovery account (dedicated — never shared with poller)
discovery_api_id: int = 0
discovery_api_hash: str = ""
discovery_phone: str = ""

def get_discovery_creds(self) -> tuple[int, str, str]:
    api_id = self.discovery_api_id or self.userbot_api_id
    api_hash = self.discovery_api_hash or self.userbot_api_hash
    return (api_id, api_hash, self.discovery_phone)
```

**Файл:** `app/userbot/pool.py`
- Добавить `UserbotAccount` с `account_id=3` для discovery
- `initialize()` создаёт клиент из `get_discovery_creds()`
- `is_healthy` отслеживается отдельно

### 1.2 Отдельный rate-limiter для discovery

**Файл:** `app/userbot/discovery_v2.py`
- Убрать импорт общего `limiter`
- Создать локальный `discovery_limiter = TelegramRateLimiter(min_interval=2.0, daily_budget=500)`
- `acquire(account_id=3)` — свой бюджет, не пересекается с поллером
- `report_flood_wait(account_id=3)` — свой circuit breaker

**Файл:** `app/userbot/rate_limiter.py`
- Не менять. Просто использовать отдельный экземпляр.

### 1.3 Подключение в worker

**Файл:** `app/worker/tasks.py`
```python
# Discovery — dedicated account #3, isolated from poller
discovery_account = next((a for a in pool.accounts if a.account_id == 3), None)
if discovery_account:
    asyncio.create_task(discovery_v2_loop(discovery_account.client))
```

## Этап 2: Прогресс и состояние (Redis)

### 2.1 Курсор прогресса

**Redis-ключи:**
```
discovery:cursor:query_index → int    # последний обработанный индекс запроса
discovery:cursor:cycle_start  → float # timestamp начала текущего цикла
discovery:seen:queries        → SET   # уже выполненные query-строки (TTL 30d)
```

**Логика:**
- `_generate_queries()` → список queries (тот же)
- `_search_and_store()` читает `query_index`, стартует с него
- Каждые 10 запросов → `SET discovery:cursor:query_index <i>`
- При рестарте → продолжает с сохранённого индекса
- `seen:queries` (Redis SET) — дедупликация query-строк между циклами

### 2.2 Сброс и перегенерация

- Если список городов/стран изменился (новый город в БД) → queryset меняется → нужен сброс курсора
- Хранить `discovery:generation:id` = хеш от списка городов
- При несовпадении → сброс `query_index` в 0

## Этап 3: Human-like паттерны

### 3.1 Переменные паузы в зависимости от «времени суток»

```python
def _get_pause_range(hour: int) -> tuple[float, float]:
    """Return (min, max) pause based on simulated local time."""
    if 2 <= hour < 8:    # «ночь» — почти бездействие
        return (1800, 3600)   # 30-60 минут
    elif 8 <= hour < 12:  # «утро» — умеренно
        return (180, 600)     # 3-10 минут
    elif 12 <= hour < 18: # «день» — активная фаза
        return (60, 180)      # 1-3 минуты
    else:                  # «вечер» — умеренно
        return (300, 900)     # 5-15 минут
```

### 3.2 Случайные длинные паузы (имитация «отвлёкся»)

- Каждые 50-200 запросов: `await asyncio.sleep(random.uniform(600, 3600))` (10-60 мин перерыв)
- Вероятность: ~3% после каждого запроса

### 3.3 Сессионная модель (переиспользовать из поллера)

- `DISCOVERY_ACTIVE_HOURS = (8, 23)` — активен с 8 до 23 UTC
- Вне окна: `await asyncio.sleep(3600)` — проверка раз в час
- Можно оставить 24/7 но с ночными паузами по 30-60 мин (п.3.1)

### 3.4 Рандомизация порядка (уже есть)

- `random.shuffle(queries)` — OK, оставить
- Добавить jitter к паузам: `±20%`

## Этап 4: Обработка ошибок

### 4.1 Логирование

**Заменить все `logger.debug` → `logger.warning(type(e).__name__)`** — чтобы ошибки были видны в проде.

### 4.2 Экспоненциальный backoff для FloodWait

```python
consecutive_flood_errors = 0
try:
    await discovery_limiter.acquire(account_id=3)
    result = await client(SearchRequest(...))
    consecutive_flood_errors = 0
except FloodWaitError as e:
    consecutive_flood_errors += 1
    backoff = min(e.seconds * (2 ** (consecutive_flood_errors - 1)), 86400)
    await discovery_limiter.report_flood_wait(e.seconds, ...)
    await asyncio.sleep(backoff)
    continue
```

### 4.3 Circuit breaker (уже есть)

- `report_flood_wait()` → `is_circuit_open()` → `wait_if_circuit_open()` работают на отдельном limiter → изолированы от поллера.

## Этап 5: Суточные лимиты

### 5.1 Конфиг

**Файл:** `app/config.py`
```python
discovery_daily_budget: int = 500  # запросов/день на discovery-аккаунт
```

### 5.2 Реализация

- `discovery_limiter = TelegramRateLimiter(daily_budget=settings.discovery_daily_budget)`
- При исчерпании → `BudgetExceeded` → `await asyncio.sleep(3600)` (час сна) → проверка следующего дня
- Уведомление админу: **один раз** (с троттлингом через `alert:last:discovery_budget`)

## Этап 6: Мониторинг

### 6.1 Метрики в Redis (TTL 7 дней)

```
discovery:stats:{date}:queries    → INT  # запросов за день
discovery:stats:{date}:found      → INT  # найдено каналов
discovery:stats:{date}:errors     → INT  # ошибок
discovery:stats:{date}:floodwait  → INT  # FloodWait событий
```

### 6.2 Алерты (через notify_admin с троттлингом)

| Событие | Кулдаун |
|---|---|
| Старт цикла | 24ч |
| Завершение цикла | 24ч |
| Budget exceeded | 6ч |
| FloodWait > 1ч | 1ч |
| 10+ ошибок подряд | 30 мин |

## Этап 7: Интеграция с worker

### 7.1 Запуск

**Файл:** `app/worker/tasks.py`
```python
if discovery_account:
    # Stagger: запустить через 5 мин после поллера
    asyncio.create_task(_delayed_discovery_start(discovery_account, delay=300))
```

### 7.2 Отказоустойчивость

- `discovery_v2_loop()` обёрнут в `try/except Exception` с перезапуском через 5 мин
- Не влияет на поллер — отдельный таск в event loop, отдельный клиент

## План внедрения (порядок)

| Этап | Что | Приоритет | Безопасность |
|---|---|---|---|
| **0** | Новый аккаунт (SIM) | 🔴 Критический | Без него — стоп |
| **1** | Изоляция: свой клиент + limiter | 🔴 Критический | Без него — стоп |
| **2** | Redis-курсор прогресса | 🟡 Важный | Можно без, но перезапуск сбрасывает |
| **3** | Human-like паузы | 🟡 Важный | Можно постепенно |
| **4** | Логирование ошибок | 🟢 Желательный | Быстро |
| **5** | Суточный бюджет | 🟡 Важный | Защита от бана |
| **6** | Мониторинг | 🟢 Желательный | После стабилизации |

## Затронутые файлы

| Файл | Изменения |
|---|---|
| `app/config.py` | +`discovery_api_id/hash/phone`, +`discovery_daily_budget` |
| `app/userbot/pool.py` | +account_id=3, +`get_discovery_creds()` |
| `app/userbot/discovery_v2.py` | Основной рефакторинг: limiter, курсор, паузы, ошибки |
| `app/userbot/rate_limiter.py` | НЕ менять (использовать отдельный экземпляр) |
| `app/worker/tasks.py` | +запуск discovery loop (отдельный таск) |
| `.env` / `.env.example` | +`DISCOVERY_API_ID/HASH/PHONE` |

## Ожидаемое поведение после внедрения

- Discovery работает 24/7 с переменной интенсивностью (ночью — редкие запросы)
- При рестарте worker продолжает с того же места (Redis-курсор)
- Полный цикл ~23K запросов при 500/день = ~46 дней
- Бан discovery НЕ влияет на поллер (разные аккаунты + circuit breaker)
- FloodWait обрабатывается с backoff, критический бан → уведомление админу
- Прогресс и ошибки видны в логах и Redis-метриках
