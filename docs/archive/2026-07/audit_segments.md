# Аудит модели сегментов/направлений — 2026-07-04

## 0. Git-санити
```
ahead=0, behind=0 ✓
```

## 1. Схема сегментов

### Таблицы
- `segments` — справочник (29 записей)
- `segment_keywords` — связь сегмент→keywords (UNIQUE на segment_id+text+keyword_type)
- `channel_segments` — M:N канал↔сегмент (таблица ЕСТЬ, но **0 строк**)
- `user_subscriptions` — связь пользователь→сегмент

### Все 29 сегментов
```
catering, massage, bike-rental, moto-purchase, car-rental, cleaning, beauty,
real-estate-rent, real-estate-buy, job-hiring, job-seeking, tattoo, tourism,
visa, translation, repair, photo-video, fitness, pets, education, medical,
legal, it-services, design, logistics, childcare, events, crypto, driving-lessons
```
BurnPM подписан на 28 (все кроме real-estate-rent). Это **почти все** сегменты системы — 28 из 29.

## 2. Связь канал→сегмент — ГЛАВНЫЙ ВОПРОС

### channel_segments: 0 строк

```
total_cs_rows              | 0
distinct_channels_with_seg | 0
channels_without_any_seg   | 2522 (ВСЕ)
```

**Сегмент — свойство ТОЛЬКО ПОДПИСЧИКА.** Канал НЕ привязан к сегменту в БД. Таблица `channel_segments` существует (код предтегирования `_load_channel_segments()` в poller.py:1430), но НИКОГДА не заполнялась (0 строк).

### Как тогда работает матчинг канал→сегмент?

Путь в `_dispatch()` (poller.py:1288-1365):

1. **Classify** (classifier.py:202): анализирует текст сообщения → `matched_segment_ids` (какие сегменты обнаружены в тексте)
2. **Segment match** (poller.py:1343-1347):
```python
for sub in subscriptions:
    if sub["country_id"] != channel_country_id:   # страна
        continue
    if sub.get("city_ids") and effective_city_ids: # город
        if not (effective_city_ids & set(sub["city_ids"])):
            continue
    if sub["segment_id"] in matched_segment_ids:    # ← СЕГМЕНТ через classify
        interested = True
        break
```

**Сегмент матчится через keywords в тексте сообщения, а не через предтегирование канала.** `matched_segment_ids` — результат классификации текста против `segment_keywords`. Если сообщение содержит demand-фразы сегмента "job-hiring" (например, "hiring needed", "вакансия открыта") → классификатор возвращает "job-hiring" → dispatch проверяет, подписан ли пользователь на "job-hiring".

## 3. Связь сегмент↔keywords

### segment_keywords
```
PK: id
FK: segment_id → segments(id) ON DELETE CASCADE
UNIQUE: (segment_id, text, keyword_type)
Поля: text, keyword_type ENUM(demand/stop/synonym), is_regex, is_active
```

### Распределение keywords по сегментам (demand-фразы)
| Сегмент | Demand-фраз |
|---|---|
| beauty | 313 |
| catering | 147 |
| job-hiring | 91 |
| crypto | 108 |
| ... | ... |

Всего ~1935 demand-фраз + ~220 synonym = ~2155 активных keywords.

### Ключевой вывод
Фильтр «HR-чаты» в будущем экспорте **НЕ МОЖЕТ** опираться на сегмент канала (каналы безсегментны). Возможные опоры:
1. **Keyword-матчинг рантайма:** какие сообщения из канала сматчили сегмент "job-hiring" (нужен лог матчей, а не статический сегмент)
2. **Ручное предтегирование:** заполнить `channel_segments` через админку (ручной выбор сегментов для канала)
3. **Keyword в названии:** `_load_channel_segments()` уже умеет предтегировать канал по его title через те же keywords — но это не используется (0 строк в БД)

**На практике для панели «Чаты без группы» нужно решение #2** — ручное предтегирование каналов через заполнение `channel_segments` в админке.

## 4. Готовность к селектору/экспорту

### Измерения для фильтрации канала СЕГОДНЯ (реальные поля в БД)

| Измерение | Источник | Статус |
|---|---|---|
| Страна | `auto_matched_country_id` | ✅ в API |
| Город | `channel_cities` + `auto_matched_city_id` | ✅ в API (PUT) |
| Tier (hot/parked) | вычисляется `_rebuild_tiers()` | ❌ не в БД, не в API |
| Участники | `participants` | ✅ в API |
| Верифицирован | `is_verified` | ✅ в API (фильтр) |
| Игнорирован | НЕТ колонки | ❌ нужна миграция |
| Сегмент | `channel_segments` (0 строк) | ❌ таблица пуста |
| Fuzzy-привязка | НЕТ колонки | ❌ не хранится |
| Тип чата | НЕТ колонки | ❌ не хранится |
| Дата обнаружения | `discovered_at` | ✅ в API |

### Готовый листинг-эндпоинт
`GET /api/channels` (api/__init__.py:63) — **есть.** Фильтры: `search` (ILIKE по username/title), `is_verified` (boolean). Пагинация. **Нет** фильтров по стране/городу/сегменту/ignored/participants.

Ответ API: `{items: [...], total, page, per_page}`. Для экспорта нужно добавить query-параметры (country_id, city_id, is_ignored, segment_id, has_city — булев флаг «без группы»).

## ИТОГ

| Вопрос | Ответ |
|---|---|
| (а) Сегмент — свойство канала или подписчика? | **Только подписчика.** channel_segments = 0 строк |
| (б) Сколько каналов засегментировано? | **0 из 2522** |
| (в) По каким измерениям фильтруется? | Сегодня: search + is_verified. Нужно добавить: country, city, has_city, is_ignored, segment (после заполнения) |
| (г) Готовый эндпоинт? | `GET /api/channels` есть, но фильтры минимальны — расширять |
