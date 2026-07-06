# Дополнительный аудит: гео-обработка + управление без бота — 2026-07-04

## 1. Существующая гео-обработка

### Где находится

Гео-обработка — **двухслойная, и ОБА слоя уже в коде.**

**Слой 1 — в discovery (мгновенная привязка):**

- `discovery_v2.py:283-287` — backfill `auto_matched_country_id`/`auto_matched_city_id` для СУЩЕСТВУЮЩИХ каналов (если были NULL)
- `discovery_v2.py:310-311` — простановка `auto_matched_country_id` + `auto_matched_city_id` для НОВЫХ каналов (из метаданных запроса)

**Слой 2 — в поллере (отложенная привязка):**

- `poller.py:1178-1283` — `_tag_new_channels()`: автодетект города из title/username через точное вхождение + fuzzy-матч (SequenceMatcher). Вызывается при старте поллера (строка 133) и при обновлении каталога (строка 1169).

**Как работает слой 2:**
1. Читает все каналы с `auto_matched_country_id IS NOT NULL AND auto_matched_city_id IS NULL` (строка 1199-1201)
2. Для каждого — ищет названия городов (name_ru + name_en) в `chat_username + title`
3. Pass 1: точное вхождение подстроки
4. Pass 2: fuzzy-матч (SequenceMatcher, порог 0.85/0.95)
5. Результат: `auto_matched_city_id` + строки в `channel_cities` для мульти-городских каналов

**Слой 2 уже покрывает то, что discovery пропустил.** Если discovery нашёл канал по общему запросу без города (только `country_id`), `_tag_new_channels()` доопределит город по названию.

### Внешние API

**Нет.** Только локальные таблицы `countries` и `cities` (91 страна, 227 городов). Ни Nominatim, ни Google Geocoding.

### Асинхронность

Оба слоя — асинхронные (SQLAlchemy async). Блокировки нет.

### Нужно ли модифицировать

**Нет.** Механизм полностью готов. Discovery должен:
1. При создании нового канала — проставлять `auto_matched_country_id` из метаданных запроса (уже делает ✅)
2. При наличии `city_id` в запросе — проставлять `auto_matched_city_id` (уже делает ✅)
3. Для каналов без города — оставлять `auto_matched_city_id = NULL` → слой 2 подхватит при следующем `_tag_new_channels()`

**Дублирования функциональности нет.** Discovery v2 проставляет только то, что знает наверняка (из метаданных запроса). Всё остальное делает `_tag_new_channels()` по расписанию.

---

## 2. Управление без бота

### Анализ вариантов

| Вариант | Плюсы | Минусы |
|---|---|---|
| **ENV `DISCOVERY_ENABLED`** | Просто, при старте контейнера | Требует рестарта для включения/выключения |
| **Redis-флаг `discovery:enabled`** | Мгновенное переключение, не требует рестарта | Нужен redis-cli или админ-панель для изменения |
| **Cron/расписание** | Автономно, без ручного управления | Меньше гибкости |

### Рекомендация: ENV-флаг + Redis-флаг (комбинированный)

```python
# app/config.py
discovery_enabled: bool = False  # ENV: DISCOVERY_ENABLED=true

# app/worker/tasks.py
if settings.discovery_enabled and discovery_account:
    asyncio.create_task(discovery_v2_loop(discovery_account.client))
```

**ENV-флаг для включения при старте.** Redis-флаг `discovery:pause` для временной паузы (без рестарта):

```python
# В главном цикле discovery_v2_loop():
if await redis.get("discovery:pause") == b"1":
    await asyncio.sleep(300)  # проверять каждые 5 мин
    continue
```

Администратор может:
- `docker compose exec worker redis-cli SET discovery:pause 1` — поставить на паузу
- `docker compose exec worker redis-cli DEL discovery:pause` — снять с паузы
- ENV `DISCOVERY_ENABLED=false` + рестарт — полностью отключить

**Без админ-панели:** redis-cli достаточно. Без бота: команды не нужны.

### Остановка и возобновление

- Graceful shutdown: `discovery_v2_loop()` ловит `asyncio.CancelledError` → сохраняет курсор → выходит
- Прогресс: Redis `discovery:cursor:query_index` (сохраняется каждые 10 запросов)
- При рестарте: продолжает с сохранённого индекса

---

## 3. Интеграция с гео-обработкой

### Нужно ли вызывать гео-обработчик сразу после сохранения?

**Нет.** Discovery уже проставляет `auto_matched_country_id` и `auto_matched_city_id` (если известен из запроса). Если город неизвестен — оставляет NULL → слой 2 (`_tag_new_channels`) подхватит.

### Нужно ли выносить в отдельную задачу?

**Нет.** Гео-обработка — это чтение из локальной БД (таблицы `countries`/`cities`). Никаких внешних API. Синхронных блокировок нет.

### Риск нагрузки на аккаунт?

**Нет.** Гео-обработка НЕ делает Telegram API-запросов. Только SQL.

---

## 4. Текущее состояние воркера discovery

### Где запускается

`app/worker/tasks.py` — общий event loop с поллером, сендером, heartbeat. **Отдельного контейнера нет.**

### Риски общего контейнера

| Риск | Оценка |
|---|---|
| Конкуренция за CPU | Низкая: discovery делает 1 запрос в 60-120с |
| Память | Низкая: +один Telethon-клиент (~20MB) |
| Блокировка поллера | **Нулевая при отдельном аккаунте** — разные клиенты + разные лимитеры |

**Отдельный контейнер НЕ нужен.** Asyncio-таск в том же event loop достаточен. При 1 запросе в минуту CPU-нагрузка пренебрежима.

---

## 5. Обновлённый план рефакторинга

### Что УБИРАЕМ из предыдущего плана

- ❌ Команды бота `/discovery_start` / `/discovery_stop`
- ❌ Отдельный гео-обработчик (уже есть слой 1 + слой 2)
- ❌ Внешние API для гео (не нужны)
- ❌ Отдельный Docker-контейнер

### Что ДОБАВЛЯЕМ

- ✅ `discovery_enabled: bool = False` в `app/config.py`
- ✅ Redis-флаг `discovery:pause` для временной остановки
- ✅ Сохранение курсора при graceful shutdown (`CancelledError`)

### Финальный план (3 файла)

| Файл | Изменения |
|---|---|
| `app/config.py` | +`discovery_enabled: bool = False` |
| `app/userbot/discovery_v2.py` | +отдельный `discovery_limiter`, +Redis-курсор, +human-like паузы, +warning вместо debug, +`discovery:pause` проверка |
| `app/worker/tasks.py` | +`if settings.discovery_enabled: asyncio.create_task(...)` |

### Управление (без бота)

```
ВКЛЮЧИТЬ:     DISCOVERY_ENABLED=true в .env → docker compose restart worker
ПАУЗА:        redis-cli SET discovery:pause 1
ПРОДОЛЖИТЬ:   redis-cli DEL discovery:pause
ОТКЛЮЧИТЬ:    DISCOVERY_ENABLED=false → docker compose restart worker
```

### Блокирующее предусловие (без изменений)

**Третий аккаунт (SIM).** Без него discovery использует аккаунт #1 → бан = стоп всему.
