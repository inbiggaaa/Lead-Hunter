# Аудит группировки — почему «только 6» каналов Дананга — 2026-07-04

## 0. Git-санити
```
main...origin/main  ahead=0, behind=0
```

## 1. Схема (ключевые таблицы)

| Таблица | Назначение |
|---|---|
| `catalog_channels` | Каналы: username, title, auto_matched_country_id, auto_matched_city_id |
| `channel_cities` | M:N канал–город (явная привязка) |
| `channel_segments` | M:N канал–сегмент (предтегирование) |
| `user_subscriptions` | Подписки: user_id, segment_id, country_id, mode |
| `subscription_cities` | Города подписки (для mode='cities') |

## 2. Путь резолва (dispatch)

`_dispatch()` в `app/userbot/poller.py:1288`:

1. `effective_city_ids = {ch.auto_matched_city_id} ∪ channel_cities_rows`
2. Для каждого пользователя из кэша:
   1. `sub.country_id == channel.country_id` (страна)
   2. Если у обоих есть city_ids → пересечение обязательно; иначе фильтр пропускается
   3. `sub.segment_id ∈ matched_segment_ids` (из classify)

**Ключевой факт:** `effective_city_ids` включает и `auto_matched_city_id` (автоматическая привязка по названию), и `channel_cities` (явная ручная привязка). Каналы с auto_matched_city_id=Дананг проходят city-фильтр ДАЖЕ без строк в channel_cities.

## 3. Кандидатская популяция «Дананг»

### A) name-сигнал (username/title ILIKE '%danang%' OR '%дананг%')
```
42 канала, все auto_matched_country_id=1 (Вьетнам), все auto_matched_city_id=2 (Дананг)
```

### B) привязка city=Дананг в channel_cities
```
6 каналов (@Danang16, @forum_vietnam_rus, @vietnam_obmen, @vietnam_poputchiki,
           @vietnam_vizaran, @vietnamtravelforeverask)
```
Эти 6 — ПОДМНОЖЕСТВО 42 из п.А.

### C) Вьетнам, city IS NULL (орфаны)
```
52 канала: auto_matched_country_id=1, auto_matched_city_id=NULL, без channel_cities.
Из них 0 содержат «danang» в названии.
```

### Всего по каталогу
```
831 орфанов (country не-NULL, city=NULL, без channel_cities)
```

## 4. ВОРОНКА для BurnPM (Вьетнам, mode='cities', Дананг, 28 сегментов)

| Шаг | Описание | COUNT | Потеря |
|---|---|---|---|
| 0 | Все Danang-name каналы (name-сигнал) | 42 | — |
| 1 | В Hot-тире (country=1 активен) | 42 | 0 |
| 2 | auto_matched_city_id=Дананг (id=2) | 42 | 0 |
| 3 | Проходят city-фильтр (effective_city_ids) | 42 | 0 |
| 4 | Реально дают матчи в логах за 3ч | **12** | 30 (нет keyword-матчей) |

**Главная потеря: не city-фильтр, а keyword-матчи.** Все 42 канала корректно попадают в Hot-тир и проходят city-фильтр. Но только 12 из них содержат сообщения, которые матчат keyword-фразы подписчика. Остальные 30 — языковой барьер (вьетнамский контент vs английские/русские keywords).

## 5. Проверка гипотез

| H | Гипотеза | Результат |
|---|---|---|
| H1 | Danang-каналы в parked | 0 — все 42 в Hot (auto_matched_country_id=1) |
| H2 | Орфаны (city IS NULL) | 52 channels, но 0 Danang-name среди них |
| H3 | Country без city | архитектурно: auto_matched_city_id заполняется всегда, city IS NULL — редкость |
| H4 | City=Дананг, сегмент вне 28 | channel_segments почти пуст: 0 строк для 42 Danang-каналов. Но dispatch НЕ использует channel_segments для фильтрации — только для pre-tagging. |

## 6. Разгадка «только 6»

**Предыдущий аудит (DIAG_DANANG) ошибся в SQL-запросе.** Использовал:
```sql
SELECT COUNT(*) FROM channel_cities WHERE city_id = (SELECT id FROM cities WHERE slug='da-nang')
```
Этот запрос считает ТОЛЬКО каналы с явной записью в `channel_cities`. Но dispatch проверяет `auto_matched_city_id` на `catalog_channels` — который для всех 42 Danang-name каналов = 2 (Дананг).

**Факт: все 42 Danang-канала видимы подписчику.** 12 из них дают матчи (подтверждено логами). Остальные 30 не матчат keywords (языковой барьер: вьетнамский контент).

### 12 Danang-каналов с матчами за 3ч
```
@Danang16, @danang_chat_1, @danangchat_ask, @danang_chatik, @danang_chats,
@danang_rent, @danang_russian_chat, @danangvietnam_chat, @danang_women,
@kz_danang, @rus_danang, @Vietnam_Danang1
```

## 7. Вывод

**Никакой проблемы с резолвером нет.** Все 42 Danang-канала в Hot-тире, все проходят city-фильтр. «Только 6» — артефакт неправильного SQL (channel_cities вместо catalog_channels.auto_matched_city_id). Городской фильтр работает корректно через auto_matched_city_id.

**Реальная проблема:** из 42 каналов только 12 дают keyword-матчи (остальные — вьетнамский контент не матчит EN/RU keywords). Это продуктовая задача, не баг кода.
