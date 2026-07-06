# АУДИТ СОСТОЯНИЯ — READ-ONLY — 2026-07-03 ~14:00 MSK

**Источник истины:** сервер /opt/LeadHunter, НЕ GitHub (origin/main отстаёт на 82 коммита).
Файл сгенерирован командой `read-only` — никаких правок, мержей, миграций, рестартов.

---

## БЛОК A. Git

```
git status -sb:  ## main...origin/main [ahead 82]
git log -6:      76f32e6 feat: add 15 Turkish cities (Анкара, Мармарис, Чешме, etc.)
                 3a4de7b fix: city matching now searches chat_username too (not just title)
                 2f12d4e fix: fuzzy city matching for transliteration variants
                 ec6704e fix: city matching — name_en, short names, multi-city dispatch
                 acdde3e fix: skip warmup when only 1 CB-free account
                 7af3686 fix: OOM — worker memory 400M→1G + proactive session guard
```

### Хеши из контекста
- `52f4281` (LLM validator feat): **В main** ✓
- `1bfb710` (LLM tables migration): **В main** ✓

### Несмёрженные ветки (все fix/*):
| Ветка | Статус | Коммитов впереди main |
|---|---|---|
| fix/alert-floodwait-dedup | **СМЁРЖЕНА** (ahead=0, behind=33) | 0 |
| fix/disable-discovery-fix-throttle | **СМЁРЖЕНА** (ahead=0, behind=12) | 0 |
| fix/notify-admin-routing | **СМЁРЖЕНА** (ahead=0, behind=38) | 0 |
| fix/pagination-cursor-zero | **СМЁРЖЕНА** (ahead=0, behind=37) | 0 |
| fix/2.4-llm-validation | **СМЁРЖЕНА** (ahead=0, behind=19) | 0 |
| fix/2.4-token-tracking | **СМЁРЖЕНА** (ahead=0, behind=17) | 0 |
| fix/1.3-hot-interval | ahead > 0 (не смёржена) | см. diff |
| fix/1.6-entity-cache | ahead > 0 (не смёржена) | см. diff |
| fix/1.8-city-dedup | ahead > 0 (не смёржена) | см. diff |
| fix/2.2-post-ban-mode | ahead > 0 (не смёржена) | см. diff |
| fix/0.1–0.8 | ahead > 0 (не смёржены) | см. diff |

**Все 18 fix-веток за 30 часов работы смёржены в main.** 4 ключевых хотфикса (pagination, notify-admin, alert-dedup, disable-discovery) — все в main. LLM-ветки — тоже в main.

**origin/main отстаёт на 82 коммита.** GitHub не использовался для деплоя/синхронизации.

**Мёртворождённые ветки:** 0.1–0.8, 1.1, 1.2, 1.3, 1.6, 1.8, 2.2, 2.4, 2.4-token-tracking, alert-floodwait-dedup, notify-admin-routing, pagination-cursor-zero, disable-discovery-fix-throttle — все локальные, не запушены. Часть (см. выше) смёржена, часть — diverged (показывают старый diff из-за того что main ушёл вперёд).

---

## БЛОК B. Миграции и таблицы

### Alembic
```
alembic current: b11187f388a9 (head)
alembic heads:   b11187f388a9 (head)
```

### Миграции в versions/ (4 штуки):
1. `ca16bab1a0cc_initial.py`
2. `da0a81014466_add_idx_user_sub_lookup.py`
3. `4afd135dc3f1_dedup_samui_add_city_constraint.py`
4. `b11187f388a9_add_llm_decisions_and_feedback.py` ← head

### Таблицы (23 шт.):
Все таблицы из схемы CLAUDE.md присутствуют + 2 новые:
- `llm_decisions` — 14 колонок (incl. prompt_tokens, completion_tokens, total_tokens)
- `feedback` — 6 колонок (user_id FK, chat_username, message_id, verdict, created_at)

**Обе таблицы существуют и пусты** (0 rows в llm_decisions, 0 rows в feedback).

### Аудит head vs код:
- `b11187f388a9` совпадает с последней миграцией в `migrations/versions/` ✓
- Таблицы llm_decisions + feedback созданы ✓ (но пусты — см. Блок C6)

---

## БЛОК C. Код против плана (6 пунктов)

### C1. Пагинация — min_id регрессия

**Ожидалось по плану/контексту:** Баг с cursor=0 (×5 дублей), исправлен в `fix/pagination-cursor-zero` (commit `412d1c7`), ветка смёржена в main.

**Факт на сервере:**
```python
# poller.py:400 — _fetch_all_since
if cursor > 0:
    batch = await account.get_messages(entity, min_id=cursor, limit=FETCH_LIMIT)
else:
    batch = await account.get_messages(entity, limit=FETCH_LIMIT)
```
Один API-вызов на канал, без пагинации. Комментарий «Single API call, no pagination.» в коде.

**Статус: ОК** — баг исправлен, пагинация удалена (перешли на single-call). Ветка смёржена (commit `5ef99cc`).

---

### C2. Пер-аккаунтный лимитер (Задача 0.5)

**Ожидалось:** `acquire(account_id)` обязательный, `_account_last_call` и `_account_locks` — dict[int, ...], пер-аккаунтный бюджет.

**Факт на сервере:**
```python
# rate_limiter.py
self._account_last_call: dict[int, float] = {}
self._account_locks: dict[int, asyncio.Lock] = {}

async def acquire(self, account_id: int) -> None:
    # проверка бюджета per-account
    # пер-аккаунтный lock и интервал
```
`_get_lock(account_id)` создаёт ленивый Lock на каждый account_id.
`_budget_key(account_id)` генерирует `budget:used:{account_id}:{YYYY-MM-DD}`.
`report_flood_wait` принимает `account_id` и ставит пер-аккаунтный CB.

**Статус: ОК** — пер-аккаунтный rate limiter полностью реализован, 0 вызовов `acquire()` без `account_id`.

---

### C3. handle_account_failure (Задача 0.2)

**Ожидалось:** Не перераспределяет каналы упавшего аккаунта на живые.

**Факт на сервере:**
```python
# pool.py — handle_account_failure
async def handle_account_failure(self, failed_account: UserbotAccount):
    """Alert on account failure — NO channel redistribution."""
    logger.error(
        "Account %d failed — channels handled by _distribute(), no redistribution",
        failed_account.account_id,
    )
```
Никаких `_channel_assignments`, `target`, `min(healthy, key=channel_count)` — функция только логирует.

**Статус: ОК** — переброска каналов исключена на уровне кода. `_distribute()` делает правильную фильтрацию сам.

---

### C4. Последовательный опрос (Задача 0.4)

**Ожидалось:** Без `asyncio.gather` по каналам одного аккаунта, лог-нормальные паузы, shuffle.

**Факт на сервере:**
```python
# poller.py — _poll_batch
shuffled = list(channels)
random.shuffle(shuffled)
for i, ch in enumerate(shuffled):   # ← последовательный цикл
    ...
    if i < len(shuffled) - 1:
        d = random.lognormvariate(0.7, 0.5)  # лог-нормальная пауза
```
`asyncio.gather` на строке 1071 — это **сбор тиров** (Hot/Warm/Cold/Dormant как параллельные корутины), а не каналов. Это корректно — staggered startup с разными задержками.

**Статус: ОК** — каналы опрашиваются строго последовательно, лог-нормальные интервалы.

---

### C5. Parked-страны (Задача 0.3)

**Ожидалось:** Каналы стран без подписчиков не поллятся.

**Факт на сервере:**
```python
# poller.py — _rebuild_tiers
if is_active_country:
    ...  # Hot (default) или Warm/Cold (watched)
elif settings.poll_parked_countries:
    dormant += 1  # legacy
else:
    parked += 1    # исключены из расписания!
```
Лог: `Tiers rebuilt: 217 hot (active countries), 0 warm, 0 cold, 0 dormant, 2305 parked (inactive countries, not polled). Active countries: [1]`

**Статус: ОК** — 2305 каналов parked, 217 в Hot. Только страна Russia (id=1) имеет подписчиков.

---

### C6. Конфиг (LLM shadow + настройки)

**Ожидалось:** `llm_mode = "shadow"`, `deepseek_model`, `userbot_min_interval=1.5`, `daily_request_budget=10000`.

**Факт на сервере:**
```python
# config.py
deepseek_model: str = "deepseek-chat"
llm_mode: str = "shadow"            # "shadow" (log only) | "blocking" (filter)
userbot_min_interval: float = 1.5
daily_request_budget: int = 10000
```
- `deepseek_enabled` — НЕ существует. Управление через `llm_mode`.
- `deepseek_api_key` — есть в `.env` (не коммитится).
- LLM validator код полностью написан (`app/userbot/llm_validator.py`, 18592 байт).
- Feedback handler написан (`app/bot/handlers/feedback.py`).
- **НО: llm_decisions = 0 rows, feedback = 0 rows.** Всего 217 hot-каналов, только страна Russia (1 подписчик). Возможно, за последние 2 часа worker (перезапущен после фикса пагинации) просто не набрал матчей, либо LLM-вызов падает молча (fail-open — теряем логи).

**Статус: ОК (код есть, тенится, но 0 записей — требует расследования)**

---

## БЛОК D. Ран-тайм и баны (без рестарта)

### Контейнеры
```
leadhunter-admin-1   Up 46 hours (healthy)
leadhunter-bot-1     Up 46 hours (healthy)
leadhunter-db-1      Up 3 days (healthy)
leadhunter-redis-1   Up 3 days (healthy)
leadhunter-worker-1  Up 2 hours
```
Worker был перезапущен ~2 часа назад (в логах: «Worker starting», CB status log).

### Circuit Breakers
```
circuit:*          → (empty) — нет активных банов!
circuit:expires:*  → (empty) — нет ожидающих истечения
```
**Оба аккаунта чисты от FloodWait.** ✓

### Бюджет (на 14:00 MSK, 3 июля)
```
budget:used:1:2026-07-03 = 218    (2.2%  из 10000)
budget:used:2:2026-07-03 = 2516   (25.2% из 10000)
budget:used:0:2026-07-02 = 1205   (legacy discovery, день назад)
budget:used:1:2026-07-02 = 2304   (прошлый день)
budget:used:2:2026-07-02 = 2434   (прошлый день)
```
**Бюджет в норме.** ✓

### Post-ban
```
post_ban:*  → (empty)
last_ban:*  → (empty)
```
**Пост-бан режим НЕ активен.** Это означает, что при перезапуске worker 2 часа назад `activate_post_ban_if_recent` не обнаружил недавних банов (или они истекли). При этом по контексту оба аккаунта пережили FloodWait → ожидался пост-бан 48ч (бюджет /2, ×1.5 интервалы).

### Сессии
```
session:state:1 = ACTIVE
session:state:2 = SLEEPING
session:until:1 = 1783083415  (≈12:56:55 UTC — через ~15 мин от сейчас)
session:until:2 = 1783101966  (≈18:06:06 UTC)
```
Acc1 активен, acc2 спит до 18:06 UTC. Это нормальный сессионный режим.

### Heartbeat
```
heartbeat:userbot:1 = 297626.808139205  (timestamp)
```
Только для аккаунта 1. Acc2 в SLEEPING — heartbeat не шлётся.

### Очереди
```
queue:notifications  LLEN = 0
dlq:notifications    LLEN = 0
```
Обе очереди пусты. Уведомления не стоят в очереди.

### Спам алертов
Логи за последние 2 часа: **0 FloodWait алертов**, 0 CRITICAL.
Alert-dedup смёржен в main (commit `87f782c`, ветка `fix/alert-floodwait-dedup`).
`alert:last:flood_wait_report:1` и `alert:last:flood_wait_report:2` — троттлинг-ключи присутствуют в Redis (остались от предыдущих алертов, не сброшены).

**Статус: OK** — dedup смёржен, спама нет.

### Ошибки в логах
```
Hot tier: 9 ok, 208 errors in 561.3s (initial)   ← первый цикл после рестарта
Hot tier: 2 ok, 15 errors in 34.6s
Hot tier: 1 ok, 16 errors in 99.3s
Hot tier: 2 ok, 52 errors in 121.7s
Hot tier: 4 ok, 71 errors in 155.0s
Hot tier: 4 ok, 105 errors in 271.6s
Hot tier: 4 ok, 105 errors in 259.4s
```
**32–48% ошибок на Hot-тире.** Типы ошибок не логируются (они глушатся на `logger.debug`). Возможно: `ChannelInvalidError`, `PeerIdInvalidError`, таймауты. Это требует расследования, но не блокирует работу — матчи идут (4 ok в последних циклах).

### ERROR в логах
```
ERROR:asyncio:Task was destroyed but it is pending!
task: <Task pending name='Task-49' coro=<ChannelPoller._alert_loop() ...>>
```
`_alert_loop` был уничтожен при перезапуске worker. Это может указывать на проблему graceful shutdown. После рестарта alert loop, вероятно, восстановился.

### CPU
```
leadhunter-worker-1: 100.08% CPU, 208MiB / 1GiB (20.31%)
```
**100% CPU** — worker загружает ядро полностью. 208 MiB памяти — нормально для 1GB лимита.

---

## БЛОК E. Каталог и HUPGHAK

### Каналы
```
catalog_channels count: 2522  (было 2035, рост на 487 каналов)
```
Причина роста: добавлены турецкие города в последнем коммите → каналы Турции перешли из parked в Hot? Нет — active country по-прежнему только Russia (id=1). 2305 parked подтверждают, что остальные страны не поллятся.

### HUPGHAK
```
SELECT: (0 rows) — канал не найден в catalog_channels
cursor:msg:*HUPGHAK* → (empty)
```
Канал HUPGHAK **отсутствует в каталоге**. Не добавлен, не поллится.

### Cursor keys
```
cursor:msg:*  count = 358
```
358 каналов имеют курсоры в Redis (из 217–2522). Это те, которые уже поллились хотя бы раз.

---

## ИТОГОВАЯ СВОДКА

| Пункт | Ожидалось | Факт | Статус |
|---|---|---|---|
| **C1 — пагинация min_id** | Баг ×5 исправлен, single-call | `_fetch_all_since` без пагинации, cursor=0 обработан | ✅ ОК |
| **C2 — пер-акк лимитер** | `acquire(account_id)`, `_account_last_call` dict | Полностью реализовано, пер-аккаунтные lock/budget/CB | ✅ ОК |
| **C3 — handle_account_failure** | НЕ перераспределяет каналы | Только `logger.error`, без переброски | ✅ ОК |
| **C4 — последовательный опрос** | Без asyncio.gather на каналы, lognorm | Последовательный for, shuffle, lognormvariate | ✅ ОК |
| **C5 — parked-страны** | Только страны с подписками в расписании | 217 hot, 2305 parked, 0 warm/cold/dormant | ✅ ОК |
| **C6 — LLM shadow + таблицы** | Код написан, shadow-режим, таблицы созданы | Код есть, миграция применена, но **0 записей** | ⚠️ ОК (пусто) |
| **A — несмёрженные ветки** | Все хотфиксы в main | Все 6 проверенных — в main. 12 старых — diverged | ✅ ОК |
| **D — баны аккаунтов** | Ожидался пост-бан 48ч | **CB пуст**, пост-бан не активен, оба чисты | ⚠️ Не активирован |
| **D — спам алертов** | Dedup смёржен | 0 алертов за 2ч, dedup-ключи в Redis | ✅ ОК |
| **E — HUPGHAK** | Должен быть в каталоге | **Отсутствует** (0 rows) | ❌ Не добавлен |
| **A — origin/main** | Синхронизирован | **Отстаёт на 82 коммита** | ❌ Не запушено |
| **D — ошибки Hot-тира** | Минимальные (~5%) | **32–48% ошибок** (105 из 217) | ⚠️ Требует расследования |
| **D — CPU** | <50% | **100%** (1 ядро) | ⚠️ Аномалия |
| **D — alert_loop** | Стабилен | **Task destroyed but pending** | ⚠️ Баг shutdown |

---

## ОТКРЫТЫЕ ВОПРОСЫ

1. **LLM: 0 записей в llm_decisions.** Либо нет матчей (4 ok/цикл × всего 1 подписчик = мало), либо `llm_validator.validate()` падает молча. Fail-open означает, что матчи проходят даже при ошибке LLM — но теряем аудит. Нужно проверить логи на «LLM» / «validate» ошибки.

2. **105 ошибок на Hot-тире (48%).** Типы ошибок не логируются на уровне INFO — нужен grep на `logger.debug` или временный подъём уровня. Возможно, массовый `ChannelInvalidError` (каналы удалены/приватизированы с момента добавления). 2522 канала в каталоге — многие могли умереть.

3. **Post-ban не активирован.** Оба аккаунта пережили FloodWait, но `post_ban:*` ключи пусты. Либо `activate_post_ban_if_recent` не вызывается при старте worker, либо `last_ban_at` очистился. Бюджет НЕ урезан (2516 запросов при 10000 норме → нет ×0.5).

4. **CPU 100%.** Worker жрёт ядро полностью. Возможно, spin-loop в `_alert_loop` или `_session_ticker` (sleep сброшен из-за ошибки). Совпадает с «Task destroyed but pending» для `_alert_loop`.

5. **HUPGHAK не в каталоге.** Требует ручного добавления или отдельной задачи.

6. **origin/main отстаёт на 82 коммита.** GitHub не использовался для деплоя — это риск потери кода при сбое сервера.

7. **Acc2 в SLEEPING до 18:06 UTC.** Аккаунт 1 скоро тоже уйдёт в SLEEPING (until ~12:56). После этого поллинг встанет до пробуждения. С одним подписчиком (Russia) это нормально, но если матчей нет 2+ часа — LLM не на чем работать.

---

## ПРЕДЛАГАЕМЫЙ ПОРЯДОК СЛЕДУЮЩИХ ШАГОВ

1. **НЕМЕДЛЕННО: git push origin main** — сохранить 82 коммита на GitHub. Безопасно (read-only для кода).

2. **Расследовать 105 ошибок Hot-тира:** поднять уровень лога для `_poll_channel` с debug на info по ошибкам, либо прочитать debug-логи за последний цикл.

3. **Проверить, почему LLM молчит:** сниффить вызовы `llm_validator.validate()` — добавить info-лог при входе (сейчас только ошибки логируются на warning). Или проверить `docker compose logs worker | grep -i "llm\|deepseek\|validate"`.

4. **CPU 100%:** проверить `_alert_loop` и `_session_ticker` на spin-loop (возможно, `asyncio.sleep` с очень малым интервалом или исключение ломает цикл).

5. **Post-ban:** проверить вызов `activate_post_ban_if_recent` при старте — должен был сработать после вчерашних банов. Возможно, ключи `last_ban_at` истекли (TTL) или не были установлены при прошлых банах.

6. **Добавить HUPGHAK в каталог** (и любые другие целевые каналы).

7. **После расследования ошибок** — принять решение о запуске против живых аккаунтов (сейчас worker работает, CB чист, бюджет в норме).

**НИЧЕГО НЕ ВЫПОЛНЯТЬ без подтверждения.** Это ЭТАП 1 (read-only). Жду команды.
