# Аудит админ-панели — фича «Чаты без группы» — 2026-07-04

## 0. Git-санити
```
ahead=0, behind=0 ✓
```

## 1. Админ-панель — что уже есть

### Стек
- **Фреймворк:** FastAPI (порт 8001), SPA-статика (React) в `app/admin/static/`
- **ORM:** SQLAlchemy 2.x (async), `async_session_factory` из `app/db/session.py`
- **Запуск:** `docker compose up admin`, команда `python -m app.admin.app`
- **Аутентификация:** сессионная (пароль `ADMIN_PASSWORD`), middleware `SessionMiddleware`
- **Код:** `app/admin/app.py` (точка входа), `app/admin/api/*.py` (роутеры)

### Существующие эндпоинты для catalog_channels

| Метод | Роут | Файл:строка | Назначение |
|---|---|---|---|
| GET | `/api/channels` | `api/__init__.py:63` | Список с пагинацией, поиском, фильтром is_verified |
| GET | `/api/channels/{id}` | `api/__init__.py:109` | Детали + сегменты + города |
| PUT | `/api/channels/{id}` | `api/__init__.py:140` | Обновление полей, сегментов, городов |

**CRUD по каналам — ЧАСТИЧНЫЙ (GET+PUT, без DELETE).** Есть CRUD по странам/городам/сегментам/keywords через `create_crud_router` (line 38-45), но для каналов — кастомный роутер.

### Как админка ходит в БД
Все endpoint'ы используют `async_session_factory()` напрямую (не через репозиторий). Модели из `app/db/models.py`.

## 2. Схема под нужды панели

### catalog_channels — поля
```
id, chat_username (UNIQUE), title, participants, is_verified,
auto_matched_country_id, auto_matched_city_id, discovered_at
```

### Флаг игнора/статуса
**НЕТ.** Только `is_verified` (boolean). Нет `is_ignored`, `status`, `blacklist`, `excluded`, `is_active`.

### channel_cities
```
channel_id (FK CASCADE), city_id (FK CASCADE)
PRIMARY KEY (channel_id, city_id)
```

### cities — добавление нового города
```
Обязательные поля: slug (UNIQUE), country_id (FK RESTRICT)
Опционально: name_ru, name_en, is_active
UNIQUE: slug, + UNIQUE(country_id, slug) через uq_cities_country_slug
```

Чтобы добавить новый город: `INSERT INTO cities (slug, name_ru, name_en, country_id) VALUES (...)` — slug уникален глобально, country_id+slug тоже уникальны.

## 3. Discovery — точка вставки флага игнора

### Где новый канал попадает в каталог
`app/userbot/discovery_v2.py:266-301` — функция `discovery_v2_loop()`:

```python
# Line 266: проверка существования
existing_rows = (await session.execute(
    select(CatalogChannel).where(
        CatalogChannel.chat_username.in_(usernames)
    )
)).scalars().all()
existing_usernames = {ch.chat_username for ch in existing_rows}

# Line 278: backfill geo для существующих
if row:
    if q["country_id"] and not row.auto_matched_country_id:
        row.auto_matched_country_id = q["country_id"]
    ...

# Line 293: вставка нового
session.add(CatalogChannel(
    chat_username=uname,
    title=c["title"],
    participants=c["participants"],
    is_verified=False,
    auto_matched_country_id=q["country_id"],
    auto_matched_city_id=q["city_id"],
))
```

### Точка для фильтра is_ignored
**Line 266-268:** добавить `.where(CatalogChannel.is_ignored == False)` в запрос существующих. Тогда ignored-каналы не будут:
- получать backfill geo (line 278-290)
- учитываться в `existing_usernames` → при повторном обнаружении создадутся заново **БЕЗ** проверки на ignore (баг!). 

**Правильное место:** добавить проверку `is_ignored` ДО решения «новый/известный»:
```python
# Line 272: skip ignored channels
if uname in existing_usernames:
    row = next(r for r in existing_rows if r.chat_username == uname)
    if row and row.is_ignored:
        continue  # не backfill, не пересоздавать
```

### Где ещё читается список каналов
- `poller.py:196-220` — `_get_all_channels()`: читает `CatalogChannel.chat_username, auto_matched_country_id, participants`
- `poller.py:1187-1196` — `_tag_new_channels()`: читает каналы для geo-тегирования
- `subscription_cache.py:38-44` — `rebuild_subscription_cache()`: читает один канал по username

Все три должны проверять `is_ignored == False` (или быть дополнены).

## 4. Данные для панели

### Очередь «Чаты без группы»
По определению `[auto_matched_city_id IS NULL AND id NOT IN channel_cities]`:
```
831 канал.
```

### Username для построения URL
```
username_null_or_empty = 0
```
**Все 831 имеют валидный @username.** URL строится как `https://t.me/{chat_username}` для всех.

### Participants
```
participants_null = 627 (75%)
```
Только 204 орфана имеют числовое значение participants.

### Fuzzy-сомнительные
**Признак НЕ хранится в БД.** `catalog_channels` не имеет колонки `match_method`/`is_fuzzy_match`. Вычислить fuzzy-only можно запросом:
```sql
-- канал имеет auto_matched_city_id, но название города НЕ содержится в title/username
SELECT ... WHERE auto_matched_city_id IS NOT NULL
  AND (title ILIKE '%city_name%' OR chat_username ILIKE '%city_name%') = FALSE
```
Но этот запрос вычисляется на лету — не хранится. Можно добавить колонку `match_method ENUM('exact','fuzzy')`, но это миграция.

### Страны с наибольшим числом орфанов
```
Египет 90, Шри-Ланка 54, Вьетнам 52, Турция 51,
Таиланд 49, Черногория 41, Кипр 40, Бразилия 35
```

## 5. Ручная привязка — запись в channel_cities

### Подхватится ли dispatch?
**Да.** `_dispatch()` (poller.py:1310-1316):
```python
effective_city_ids = {channel_city_id} if channel_city_id else set()
cc_rows = await session.execute(
    sa_select(ChannelCity.city_id).where(ChannelCity.channel_id == ch.id)
)
effective_city_ids.update(cc_rows)
```
Ручная вставка в `channel_cities` попадает в `effective_city_ids` и используется при city-фильтре.

### Констрейнты
```
PRIMARY KEY (channel_id, city_id)  — безопасно для множественных городов
FK ON DELETE CASCADE → catalog_channels (при удалении канала города удаляются)
FK ON DELETE CASCADE → cities (при удалении города строки удаляются)
```
Вставка `(channel_id=5, city_id=2)` + `(channel_id=5, city_id=3)` — без конфликта. Дубликат `(5,2)` → constraint violation.

## 6. ИТОГ

| Вопрос | Ответ |
|---|---|
| (а) Стек админки | FastAPI + SQLAlchemy async, порт 8001, SPA React. GET/PUT /api/channels есть, DELETE нет |
| (б) Флаг игнора | **Нет.** Точка проверки: discovery_v2.py:266-272 |
| (в) Добавление города | slug (UNIQUE) + country_id обязательны, name_ru/name_en опциональны |
| (г) Очередь «без группы» | 831 канал, все с валидным @username, 75% без participants. Fuzzy-признак не хранится |
| (д) Ручная привязка | channel_cities читается dispatch (poller.py:1316), PK (channel_id,city_id) безопасен |
