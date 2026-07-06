# Аудит точек фильтра is_ignored — 2026-07-04

## 0. Git
```
ahead=2, behind=0
```

## Точка 1 — discovery (discovery_v2.py:266)

**Файл:** `app/userbot/discovery_v2.py:264-310`

### Контекст
Функция `discovery_v2_loop()` выполняет поиск каналов в Telegram, затем проверяет существование через batch-SELECT:

```python
existing_rows = (await session.execute(
    select(CatalogChannel).where(
        CatalogChannel.chat_username.in_(usernames)
    )
)).scalars().all()
existing_usernames = {ch.chat_username for ch in existing_rows}
```

### Куда вставить фильтр
Добавить `.where(CatalogChannel.is_ignored == False)` в SELECT (строка 267). Игнорированные каналы не попадут в `existing_usernames`, discovery попытается добавить их заново → нужно также проверять `is_ignored` ПЕРЕД `session.add()`:

```python
for c in candidates:
    uname = c["username"]
    row = next((r for r in existing_rows if r.chat_username == uname), None)
    if row and row.is_ignored:
        continue  # игнорированные не backfill и не пересоздавать
    if row:
        # backfill geo...
        continue
    # new channel
    session.add(...)
```

### Актуальная строка: 266-267

## Точка 2 — _get_all_channels (poller.py:195) — САМОЕ ГОРЯЧЕЕ

**Файл:** `app/userbot/poller.py:195-225`

### Что делает
```python
async def _get_all_channels(self) -> list[dict]:
    cat_result = await session.execute(
        select(
            CatalogChannel.chat_username,
            CatalogChannel.auto_matched_country_id,
            CatalogChannel.participants,
        )
    )
    # Возвращает список dict: {chat_username, country_id, participants}
```

### Кто вызывает
`_rebuild_tiers()` (строка 143) → `self._hot_channels = hot` (строка 167) → `_run_tier_loop("Hot", self._hot_channels, ...)` (строка 1134)

### КЭШ
**In-memory.** `self._hot_channels` — список dict'ов, обновляется только при вызове `_rebuild_tiers()`.

**Частота ребилда:**
- При старте: `start()` → `_rebuild_tiers()` (строка 132)
- По таймеру: `_maintenance_loop()` → каждые 1 час (строка 1159)
- При обновлении подписок/каталога: через `_rebuild_tiers()` (строка 1159)

### Эффект фильтра
Добавить `.where(CatalogChannel.is_ignored == False)` в SELECT (строка 202). После следующего ребилда (до 1 часа) игнорированный канал исчезнет из `self._hot_channels`.

**Нужен ли перезапуск userbot:** нет — но эффект отложен до ближайшего ребилда. Прямой вызов `_rebuild_tiers()` был бы мгновенным, но его нет в API.

### Куда вставить
Строка 202: добавить `CatalogChannel.is_ignored == False` в `select()`.

## Точка 3 — _tag_new_channels (poller.py:1189)

**Файл:** `app/userbot/poller.py:1189-1192`

```python
channels = (await session.execute(
    sa_select(CatalogChannel).where(
        CatalogChannel.auto_matched_country_id.isnot(None),
        CatalogChannel.auto_matched_city_id.is_(None),
        CatalogChannel.title.isnot(None),
    )
)).scalars().all()
```

Добавить `.where(CatalogChannel.is_ignored == False)` как дополнительное условие (строка 1192).

## Полнота — все места чтения CatalogChannel

| # | Файл:строка | Назначение | Нужен is_ignored? |
|---|---|---|---|
| 1 | `discovery_v2.py:266` | Discovery — проверка существования | ✅ Да |
| 2 | `poller.py:202` | `_get_all_channels()` — список для прослушки | ✅ Да |
| 3 | `poller.py:1189` | `_tag_new_channels()` — geo-тегирование | ✅ Да |
| 4 | `poller.py:1305` | `_dispatch()` — чтение ОДНОГО канала по username для раздачи | ❌ Нет (dispatch по конкретному каналу — если он игнорирован, он не должен был попасть в прослушку) |
| 5 | `poller.py:1437` | `_load_channel_segments()` — предтегирование сегментов | ⚠️ Желательно (чтобы не тегировать игнорированные) |
| 6 | `poller.py:1539` | `_update_channel_info()` — обновление title/participants | ❌ Нет (безвредно — обновляет метаданные) |

### Влияние на раздачу (dispatch)
`_dispatch()` (poller.py:1305) читает канал по `chat_username` для geo-матчинга. Если канал с `is_ignored=true` уже прослушивается (попал в tiers до игнора), он продолжит рассылаться до ребилда. Это допустимо — ребилд (1 час) уберёт его из прослушки. Отдельный фильтр в dispatch НЕ нужен.

### _load_channel_segments
Рекомендуется добавить фильтр для полноты (не тегировать игнорированные каналы), но это низкоприоритетно — таблица пуста (0 строк).

## Актуальные строки (после правок models.py)

| Точка | Файл | Строка | Условие |
|---|---|---|---|
| Discovery | `app/userbot/discovery_v2.py` | **266-267** | `.where(CatalogChannel.is_ignored == False)` + проверка в цикле |
| _get_all_channels | `app/userbot/poller.py` | **202** | `.where(CatalogChannel.is_ignored == False)` |
| _tag_new_channels | `app/userbot/poller.py` | **1192** | `.where(CatalogChannel.is_ignored == False)` |
| _load_channel_segments | `app/userbot/poller.py` | **1437** | опционально |
