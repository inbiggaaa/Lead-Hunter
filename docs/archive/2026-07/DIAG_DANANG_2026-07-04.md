# DIAG_DANANG — Аудит подписок и каналов — 2026-07-04

## 1. Каталог 4 каналов с ошибками

```
 id  |  chat_username  |           title           | channel_cities | channel_segments
-----+-----------------+---------------------------+----------------+------------------
 728 | danang_jobs     | Jobs Da Nang              | НЕТ            | НЕТ
 887 | hcmc_jobs       | Jobs Ho Chi Minh City     | НЕТ            | НЕТ
 885 | saigon_services | Красота и клининг         | НЕТ            | НЕТ
 400 | vietnam_jobs    | Jobs Vietnam (all cities) | НЕТ            | НЕТ
```

Все 4 есть в `catalog_channels`. Ни у одного нет привязки к городу (`channel_cities`) и к сегменту (`channel_segments`). Это **орфанные каналы**: они лежат в каталоге, но не участвуют в geo-матчинге и не размечены по тематикам. Их поллер опрашивает (т.к. страна Вьетнам = 1), но `find_interested_users()` не может привязать их к подписке BurnPM (нет совпадения по `channel_cities`).

**UsernameInvalidError** на @saigon_services — канал не существует в Telegram. Остальные 3× `ValueError` = аккаунт unhealthy — не ошибка канала.

## 2. Подписчик BurnPM (user_id=152, trial)

28 сегментов, все Вьетнам (country_id=1), mode='cities', фильтр: Дананг.
```
subscription_cities: все → city_id = (Дананг, slug=da-nang)
```

Дананг-каналов в системе: **6** (из 2522 в каталоге):
```
@Danang16, @forum_vietnam_rus, @vietnam_obmen, @vietnam_poputchiki,
@vietnam_vizaran, @vietnamtravelforeverask
```

4 канала из п.1 **НЕ входят** в данангский набор — они без city-привязки.

## 3. Ключевые слова

Таблица `segment_keywords`, поле `text`. 28 сегментов × demand-фраз = суммарно ~1800 keywords. Язык — **преимущественно английский** (примеры: `"catering needed"`, `"chef needed"`, `"massage needed"`, `"bike rental needed"`). Русские demand-фразы есть не во всех сегментах (красота — 313, кейтеринг — 147, массаж — 68, ремонт — 18).

## 4. Что льётся: матчи ЕСТЬ

За 3 часа лога:
```
@danangvietnam_chat: 9× Match (tourism, job-hiring, crypto, education)
```
@danangvietnam_chat НЕ входит в данангский набор из 6 каналов (он привязан к Вьетнаму/Хошимину по названию). Но классификатор находит demand-сигналы. LLM-вердикты: OFFER (преобладает), DEMAND (2 из 9).

Проблема: матчи есть, но `find_interested_users()` не находит BurnPM для @danangvietnam_chat (канал не в Дананге → city-фильтр отсекает). Это видно из того, что match логируются, но dispatch не происходит (нет PUSH-событий в логе sender).

## 5. Развилка

**0 матчей у BurnPM вероятнее из-за (D)** — данных достаточно, но корневая причина = **geo-фильтр**: каналы, дающие матчи (@danangvietnam_chat), не привязаны к Данангу. Данангские каналы есть (6 шт.), но их контент не матчит английские ключевики (языковой барьер: вьетнамские каналы → вьетнамский контент → английские keywords не срабатывают).

Что ещё дёрнуть:
- `SELECT * FROM channel_cities WHERE city_id=(SELECT id FROM cities WHERE slug='da-nang')` → уже сделано, 6 каналов
- `docker compose logs worker | grep -E "@(Danang16|forum_vietnam_rus|vietnam_obmen|vietnam_poput|vietnam_vizar|vietnamtravel)" | grep "Match in"` — проверить, есть ли матчи на данангских каналах
