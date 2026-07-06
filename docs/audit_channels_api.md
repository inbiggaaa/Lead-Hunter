# Аудит /api/channels перед расширением — 2026-07-04

## 1. Git-статус
```
## main...origin/main  (ahead=0, behind=0)
HEAD: 4364d21 docs(session-log): admin feature steps 1-2 done
```

## 2. Обвязка роутера

### app/admin/app.py — точка входа FastAPI
- `create_app()` → FastAPI на 0.0.0.0:8001
- SessionMiddleware (секрет из `ADMIN_SECRET` или random)
- Роутер: `app.include_router(api_router)` — без префикса, все API под `/api/*`
- SPA: статика из `app/admin/static/`, catch-all на `/`
- Docker: `python -m app.admin.app`

### app/admin/api/__init__.py — сборка роутеров
- `api_router = APIRouter()` (line 27)
- `require_auth` — проверка `request.session.get("authenticated")` (line 20)
- `_protected = [Depends(require_auth)]` — все роутеры кроме auth под этим
- `channels_router = APIRouter(prefix="/api/channels", tags=["channels"])` (line 59)
- Монтируется: `api_router.include_router(channels_router, dependencies=_protected)` (line 184)
- `async_session_factory` — импортируется из `app.db.session`, используется напрямую в каждом хендлере (без репозиторного слоя)

## 3. Текущий /api/channels

### GET /api/channels (line 62)
```python
@channels_router.get("")
async def list_channels(
    page: int = 1,
    per_page: int = 20,
    search: str | None = None,
    is_verified: bool | None = None,
):
```
**Фильтры:** `search` — ILIKE по `chat_username` и `title`, `is_verified` — точный булев матч.
**Пагинация:** `page`/`per_page`, подзапрос для count, offset/limit.
**Возвращает:** `{"items": [...dict...], "total": int, "page": int, "per_page": int}`.
**Поля в ответе:** id, chat_username, title, participants, is_verified, auto_matched_country_id, auto_matched_city_id, discovered_at.
**Статус:** is_ignored НЕ возвращается, НЕ фильтруется.

### GET /api/channels/{channel_id} (line 109)
Возвращает те же поля + `segments` (list[segment_id]) + `cities` (list[city_id]).
Сегменты/города читаются из `channel_segments`/`channel_cities`.

### PUT /api/channels/{channel_id} (line 140)
```python
@channels_router.put("/{channel_id}")
async def update_channel(channel_id: int, data: dict):
```
**Паттерн транзакции:** `async with async_session_factory() as session:` → `session.get(ch)` → `setattr` → `session.execute(delete...)` → `session.add(...)` → `session.commit()`.
**Обновляемые поля:** title, participants, is_verified, auto_matched_country_id, auto_matched_city_id (из сета `updatable`, line 155).
**Сегменты:** DELETE all + INSERT новые (`data["segments"]`).
**Города:** DELETE all + INSERT новые (`data["cities"]`).
**is_ignored — НЕ в списке updatable!** Нужно добавить.

## 4. ORM-поверхность

### CatalogChannel (models.py:200)
9 колонок: id, chat_username (UNIQUE), title, participants, is_verified, is_ignored, auto_matched_country_id, auto_matched_city_id, discovered_at.

### ChannelCity (models.py:233)
M2M junction: (channel_id, city_id) — composite PK, FK CASCADE.

### City (models.py:150)
slug (UNIQUE), name_ru/name_en, country_id (FK RESTRICT), is_active.
`__table_args__`: `UniqueConstraint("country_id", "slug", name="uq_cities_country_slug")`.

### Country (models.py:134)
slug (UNIQUE), name_ru/name_en, is_active.

### Выражение «нет города»
```sql
auto_matched_city_id IS NULL
AND id NOT IN (SELECT channel_id FROM channel_cities)
```

## 5. Pydantic-схемы

**Нет Channel-специфичных схем.** Есть только `LoginRequest(BaseModel)` в `app/admin/api/auth.py:29`. Все эндпоинты API возвращают сырые dict'ы. Для новых роутов схемы писать с нуля.

## 6. Сверка ORM ↔ БД

### catalog_channels
- ORM = БД: ✅ все 9 колонок совпадают
- is_ignored: ✅ boolean NOT NULL DEFAULT false (server_default = 'false')
- chat_username UNIQUE: ✅

### channel_cities
- PK (channel_id, city_id): ✅
- FK CASCADE: ✅

### cities
- uq_cities_country_slug: ✅ в БД и в ORM
- slug UNIQUE: ✅
- country_id FK RESTRICT: ✅

### Контрольный счёт орфанов
```
orphans = 831 (city=NULL + без channel_cities)
total   = 2522
```
Совпадает с ожидаемым (~830).

## 7. Точки вставки для новых роутов

### (a) Фильтр has_city=false + country_id/city_id/is_ignored
В `list_channels()` (line 62): добавить query-параметры и условия в stmt.
Готовый паттерн: уже есть `is_verified` — добавить аналогично `is_ignored`.
Для `has_city`: подзапрос `id NOT IN channel_cities AND auto_matched_city_id IS NULL`.
Для `country_id`/`city_id`: JOIN к channel_cities или WHERE по auto_matched.

### (b) POST мультисити → channel_cities
Новый эндпоинт, отдельный от PUT. Паттерн: `session.add(ChannelCity(...))` + `session.commit()`.
Готовый прецедент: PUT уже делает DELETE+INSERT городов (line 168-175).

### (c) POST добавить город
Через `create_crud_router(City, ...)` — **уже существует** на `/api/cities` (line 39).
Достаточно расширить фронт, бэкенд готов. UNIQUE-safe: `uq_cities_country_slug` предотвратит дубликат.

### (d) PATCH is_ignored
Добавить `is_ignored` в `updatable` сета PUT (line 156) — простейшая правка.
Или отдельный `PATCH /api/channels/{id}/ignore` с `{"is_ignored": true/false}`.

---

## Доуточнение (2026-07-04)

### 1. Орфаны — разбивка

```
metric               | count
total                 |   831
ignored_true          |     1   (id=885 @saigon_services)
ignored_false (queue) |   830
```
✅ total=831, ignored=1, queue=830.

### 2. PUT /api/channels — запись в channel_cities

**ДА, делает DELETE+INSERT.** Строки 168-175 в `api/__init__.py`:
```python
if "cities" in data:
    await session.execute(
        __import__("sqlalchemy").sql.delete(ChannelCity).where(
            ChannelCity.channel_id == channel_id
        )
    )
    for cid in data["cities"]:
        session.add(ChannelCity(channel_id=channel_id, city_id=cid))
```
Паттерн: DELETE все строки → INSERT новые. Полная перезапись, не merge.

### 3. /api/cities — create_crud_router

**POST/create — ДА, есть.** `app/admin/api/crud.py` — `create_crud_router()` генерирует полный CRUD.

**Обработка UNIQUE constraint: НЕТ.** `create_item()` (crud.py:133-148) делает прямой `table.insert()` без try/except IntegrityError. При конфликте `uq_cities_country_slug` — IntegrityError → 500 Internal Server Error.

⚠️ Клейм «UNIQUE-safe» из предыдущего отчёта неточен. Констрейнт в БД есть, но API не ловит ошибку. Нужно добавить обработку IntegrityError или проверку перед вставкой.

---

## Разведка под фильтр (a)

### 1. Предусловие — перезапись городов у орфанов

```
queue_has_city_false      | 830   (city=NULL + без channel_cities + не ignored)
edge_city_null_but_has_cc |   0   (нет каналов, где скаляр NULL а M2M не пуст)
```
✅ Перезапись безопасна: у орфанов нет строк в channel_cities, удалять нечего.

### 2. list_channels() — актуальный код (строки 62-116)

**Сигнатура:**
```python
async def list_channels(
    page: int = 1,
    per_page: int = 20,
    search: str | None = None,
    is_verified: bool | None = None,
):
```

**Образец фильтра (is_verified):**
```python
if is_verified is not None:
    stmt = stmt.where(CatalogChannel.is_verified == is_verified)
```
Паттерн: `if param is not None: stmt = stmt.where(CatalogChannel.field == param)`.

**Схема пагинации:**
```python
count_stmt = select(func.count()).select_from(stmt.subquery())
total = (await session.execute(count_stmt)).scalar() or 0
stmt = stmt.offset((page - 1) * per_page).limit(per_page)
```

**Response:** `{"items": [...], "total": int, "page": int, "per_page": int}`.

**Поля в items СЕЙЧАС:** id, chat_username, title, participants, is_verified, auto_matched_country_id, auto_matched_city_id, discovered_at.

**Отсутствуют:** `is_ignored` ❌, url (t.me/chat_username) ❌, города через channel_cities ❌.

### 3. Чтение effective (auto_matched ∪ channel_cities)

**В админке — НЕТ.** `list_channels()` читает только `CatalogChannel.auto_matched_city_id` (скаляр). `get_channel()` читает `channel_cities` отдельно (массив city_id). Ни один endpoint не считает effective. Фильтр `city_id` должен использовать EXISTS по `channel_cities` для захвата мультисити-каналов.

**В dispatch (poller.py:1312-1318) — ДА.** Там effective вычисляется:
```python
effective_city_ids = {channel_city_id} if channel_city_id else set()
cc_rows = await session.execute(sa_select(ChannelCity.city_id).where(ChannelCity.channel_id == ch.id))
effective_city_ids.update(cc_rows)
```
Но этот код в поллере, не в админке. Для админ-фильтра нужно реализовать аналогичную логику: `auto_matched_city_id = :city OR EXISTS(SELECT 1 FROM channel_cities WHERE channel_id = catalog_channels.id AND city_id = :city)`.

---

## Правка (a) — результаты теста

### Добавленные query-параметры
`has_city: bool`, `country_id: int`, `city_id: int`, `is_ignored: bool` — все опциональные.

### WHERE для city_id (мультисити)
```python
CatalogChannel.auto_matched_city_id == city_id
| CatalogChannel.id.in_(select(ChannelCity.channel_id).where(ChannelCity.city_id == city_id))
```

### WHERE для has_city
- `True`: `auto_matched_city_id.isnot(None) | id.in_(select(ChannelCity.channel_id))`
- `False`: `auto_matched_city_id.is_(None) & ~id.in_(select(ChannelCity.channel_id))`

### Тест 1 — очередь
`GET /api/channels?has_city=false&is_ignored=false`
- total=**830** ✅
- saigon_services (id=885, is_ignored=true) — **отсутствует** ✅
- is_ignored поле в ответе — **присутствует** ✅

### Тест 2 — мультисити
`GET /api/channels?city_id=65` (Тбилиси)
- @forum_georgia (id=110, auto_city=Батуми) — **присутствует** ✅
- @mybatumi_apartments (id=112) — **присутствует** ✅
- @gryziya (id=111) — **присутствует** ✅

EXISTS сработал: каналы с auto_matched_city_id ≠ Тбилиси, но со строкой в channel_cities для Тбилиси — попали в выдачу.

---

## Правка (c) — POST /api/cities UNIQUE-safe

### Метод
`try/except IntegrityError` + `session.rollback()` → 409 Conflict. В crud.py `create_item()`:
```python
try:
    stmt = table.insert().values(**clean)
    result = await session.execute(stmt)
    await session.commit()
except IntegrityError:
    await session.rollback()
    raise HTTPException(status_code=409, detail=f"{model_name} already exists — unique constraint violated")
```

### Тест 1 — новый город
`POST {"slug":"testcity42","country_id":1}` → id=384, slug=testcity42 ✅

### Тест 2 — дубликат
Тот же slug+country_id → 409 `"cities already exists — unique constraint violated"` ✅
Сессия жива: следующий GET /api/cities работает ✅

### Тест 3 — тот же slug, другая страна
`{"slug":"testcity42","country_id":2}` → id=387, создан ✅ (uq только на паре country_id+slug)

---

## Правка (b)+(d) — PUT cities + is_ignored

### Изменения
`is_ignored` добавлен в updatable. `country_id`: если передан и `auto_matched_country_id IS NULL` → проставить. Cities: DELETE all → INSERT новые (уже было в строках 172-180).

### Тест 1 — мультисити
PUT `{"cities":[48,49],"country_id":96}` на орфан id=46 (@avto_tursia) → 2 строки channel_cities. GET ?city_id=48 и ?city_id=49 → канал в обеих выдачах ✅

### Тест 2 — «Удалить»
PUT `{"is_ignored":true}` → канал исчез из очереди (total 830→829) ✅

### Тест 3 — перезапись
PUT `{"cities":[48]}` → осталась 1 строка (49 удалён) ✅

### Тест 4 — откат
PUT `{"cities":[],"is_ignored":false}` → channel_cities=0, очередь=830 ✅
