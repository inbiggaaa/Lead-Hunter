# SESSION_LOG.md — полный журнал сессий LeadHunter

> Полная история работ. Правило (CLAUDE.md §0): после КАЖДОЙ задачи — запись в КОНЕЦ этого файла
> в формате `**DD.MM.YYYY HH:MM — Что сделано.** Результат. Ошибки/уроки.`
> В CLAUDE.md §8 при этом обновляется краткий текущий статус (и только он).
> Записи идут в порядке добавления (внутри истории есть хронологические нестыковки — сохранены как были).
> Вынесено из CLAUDE.md §8 12.07.2026 (сжатие контекста; история не редактировалась, кроме пометки ⚠️ AOF).

### Production changes (Phase 0 — 02.07.2026)

**Poller v2 — инкрементальный, тирированный, батчевый:**
- Инкрементальный поллинг через Redis-курсоры (`cursor:msg:{chat}`) — только новые сообщения
- Тирирование: Hot (60с, каналы стран с активными подписками), Warm (5мин, >1000 участников), Cold (15мин, остальные)
- Параллельные батчи: 3 канала × `asyncio.gather`, 0.3 сек между API-вызовами
- Circuit breaker: `wait_if_circuit_open()` перед каждым батчем
- Полный обход 2014 каналов: Hot за ~80 сек, Cold за ~17 мин
- Масштабируется до N аккаунтов (`_distribute()` round-robin)

**Rate Limiter:**
- `DEFAULT_MIN_INTERVAL = 0.3` сек (было 3.0) — 3 rps, безопасно для Telegram
- `PARALLEL_BATCH = 3` на аккаунт (было 50 → бан)
- `BATCH_PAUSE = 0.3` сек между батчами

**Classifier:**
- +5 demand-сигналов: `требуется`, `кто может`, `подберите`, `порекомендуйте`, `есть у кого`
- +1 start-анкер: `^(где|куда|как|кто)\b.*\?`
- Убран `ищете/ищешь.*\?` — маркетинговый паттерн, не спрос
- Оффер-паттерны расширены: `цена\b.*?\d+`, телефон без @username
- Pass 3: `?` больше не перебивает оффер-сигнал — только глагол спроса в начале строки

**Keywords:**
- 1935 demand + 220 synonym + 102 stop = **2257 слов** в БД
- 24 оффер-ориентированных синонима удалены (`прокат мото`, `rent bike` и др.)
- Синонимы загружены для всех 29 сегментов (seed/seed_synonyms.py)

**Channel pre-tagging:**
- 29 каналов предтегированы сегментами по названию
- Названия автообновляются при поллинге (`_update_channel_title`)
- Если канал pre-tagged + demand-сигнал → матч даже без keyword в тексте

**Каталог:**
- 2014 каналов (было 2119), все с geo-привязкой (0 без страны)
- 106 мёртвых (<300 участников) удалены, 19 авто-привязаны
- +23 города в БД (Ларнака, Марбелья, Трабзон, Кордоба и др.)
- 10 активных каналов Дананга (>300 участников)

**Unmatched-логи:**
- Дедупликация через Redis SET `stats:unmatched:seen`
- TTL 7 дней на seen-хеши
- 175 уникальных unmatched в Redis

**Бот:**
- Команды `/keywords`, `/channels`, `/subscriptions`, `/plan`, `/settings` — прямой показ экрана (без emoji-мостика)
- `/search` — сразу открывает каталог направлений с FSM
- Главное меню: 4 кнопки (search, plan, referral, settings), Settings → 6 подэкранок

**Документация:**
- `OPERATIONS.md` — правила эксплуатации, защита от бана, чек-лист деплоя
- `CLAUDE.md §0` — обязательная инструкция: читать OPERATIONS.md перед изменениями в poller/rate-limiter

**Инциденты:**
- 30.06.2026 17:42 — FloodWait 18ч (Poller v2 без rate limiter). Исправлено: возвращён `limiter.acquire()`, `PARALLEL_BATCH=3`, `DEFAULT_MIN_INTERVAL=0.3`.
- 01.07.2026 10:30 — FloodWait 24ч Account 2 (все 3 тира стартовали одновременно → 2036 вызовов за 11 мин). Исправлено: staggered startup, warmup, jitter.
- Circuit breaker: Account 1 до ~12:34 MSK (повторный бан, 10ч), Account 2 до ~10:01 MSK 02.07.2026. Оба заблокированы.

**Текущие цифры:**
- Каналов: 2035 (100% geo), городов: 120 (из них 23 новых), сегментов: 29
- Ключевых слов: 2234 (1935 demand + 220 synonym + 102 stop), 96 universal stops
- Pre-tagged каналов: 33 (по названиям)
- Пользователей: 3, уведомлений всего: 33
- Hot/Warm/Cold: 208 / 308 / 1519 каналов
- Userbot-аккаунтов: 2 (@iraluxme, Sofiya) — ОБА ЗАБЛОКИРОВАНЫ
- Anti-ban: staggered startup (0/60/180s), warmup 8%→100% за 7 циклов, jitter ±15%

### Session log

**30.06.2026 15:00 — Poller v2: инкрементальный + тирированный + батчевый.**
Полный рефакторинг поллера: Redis-курсоры, 3 тира (Hot/Warm/Cold), asyncio.gather батчи.
Результат: Дананг-каналы начали поллиться, BurnPM получил 1 уведомление.

**30.06.2026 15:20 — Classifier: demand-сигналы + синонимы + оффер-детектор.**
+5 demand-паттернов, 220 synonym в БД, удалены оффер-синонимы («прокат мото»).
Pass 3: «?» больше не перебивает оффер. Результат: 4 матча/цикл вместо 1.

**30.06.2026 16:00 — Каталог: чистка + гео-привязка.**
106 мёртвых каналов удалено, 19 авто-привязаны, +23 города. 0 каналов без страны.

**30.06.2026 16:30 — Каналы: автообновление названий + pre-tagging.**
31 канал предтегирован сегментами по названию. Названия обновляются при поллинге.

**30.06.2026 17:00 — Бот: команды из меню.**
/keywords, /channels, /subscriptions, /plan, /settings — прямой показ без emoji-мостика.
/search — сразу каталог с FSM.

**30.06.2026 17:40 — ИНЦИДЕНТ: FloodWait 18ч.**
Poller v2 запущен без rate limiter → 5850 запросов за 10 сек → бан.
Исправлено: возвращён limiter, PARALLEL_BATCH=3. Создан OPERATIONS.md.
Урок: никогда не убирать rate limiter, всегда считать RPS перед деплоем.

**30.06.2026 21:00 — Security audit + документация.**
Git history чист (0 CRITICAL/HIGH). Убран dev-secret, очищен alembic.ini.
CLAUDE.md §8 актуализирован. Добавлен обязательный session log в §0.
OPERATIONS.md создан: hard rules, чек-лист деплоя, процедура FloodWait.

**01.07.2026 02:47 — Аудит FloodWait + защита discovery.**
Проверен статус бана: circuit breaker активен, истекает 09:32 UTC (6ч 45мин осталось).
Обнаружена дыра: discovery.py не использовал limiter вообще (0 из 3 проверок).
Исправлено: +limiter.acquire() перед SearchRequest, +wait_if_circuit_open() на входе,
+report_flood_wait() в обоих except FloodWaitError. Теперь все API-вызовы Telegram под защитой.
Прочитаны и применены: OPERATIONS.md §2 (Hard Rules #1, #6, #7), CODING_STYLE.md.

**01.07.2026 09:50 — Второй userbot-аккаунт +84326376814 (Sofiya).**
Добавлен USERBOT_2_PHONE в .env, авторизация через docker compose run.
Fallback API-кредов первого аккаунта (api_id=32062916) — отдельное приложение не нужно.
Исправлен SSH (MaxSessions 10) для одновременной работы.
Pool: 2 healthy accounts, каналы распределятся round-robin после закрытия circuit breaker.
Урок: docker compose restart не подхватывает новые env vars — нужен up -d.

**01.07.2026 10:15 — Per-account circuit breaker (FloodWait одного аккаунта не блокирует остальные).**
Рефакторинг rate_limiter: Redis-ключи per-account (circuit:open:{id}, circuit:expires:{id}).
Poller: пропускает аккаунты с открытым CB, wait_if_circuit_open per-account.
Discovery: is_any_circuit_open() вместо глобального wait — пропускает цикл если хоть один заблокирован.
Backward compat: account_id=0 → legacy global keys.
Результат: Account 1 (@iraluxme) ещё под баном ~2.5ч, Account 2 (@Sofiya) свободно поллит и приносит матчи.
33 уведомления всего, 3 пользователя, worker стабилен.

**01.07.2026 10:30 — ИНЦИДЕНТ: Account 2 (@Sofiya) тоже получил FloodWait 24ч.**
Корневая причина: при старте воркера все 3 тира запускались одновременно.
Account 2 получал 1018 каналов (Hot 104 + Warm 154 + Cold 760) × 2 API-вызова = 2036 вызовов.
11 минут непрерывного потока API-вызовов → Telegram anti-spam detection.

**01.07.2026 11:30 — Discovery v2: выделенный аккаунт + защита от бана.**
Исправлен discovery_v2: выделенный userbot2, per-account circuit breaker, 30-сек пауза.
23K запросов за 8.3 дня, 0.033 rps — в 908 раз ниже лимита Telegram.
Бан discovery не заденет поллер (разные аккаунты + per-account CB).

**01.07.2026 11:00 — Пагинация сообщений: 100% покрытие, 0 риск бана.**
Заменил фиксированный limit=3 на TIER_LIMITS (Hot=30, Warm=80, Cold=150) с авто-пагинацией.
Если батч возвращается полным — добираем остаток через max_id-окно за доп. API-вызов.
Для 99% каналов — ровно столько же вызовов (2 на канал). Rate limiter (3 rps) не менялся.
Добавлен канал @kz_danang (Вьетнам, Дананг) в каталог (id=2142, Hot-тир).
Исправлен SSH keepalive: ClientAliveInterval=30, ClientAliveCountMax=720 (6ч).

**01.07.2026 10:45 — Anti-ban protection (3 уровня) + метки категорий в уведомлениях.**
Staggered startup: Hot@0s, Warm@60s, Cold@180s.
Warmup: 7 циклов рампы (8%→16%→25%→35%→50%→70%→100%).
Jitter: ±15% случайной вариации интервалов.
Уведомления: строка 🏷 с названием категории (или 🔑 для персональных keyword).
Результат: Hot стартует с 16 каналов вместо 208, плавный выход на полную за 7 мин.
Оба аккаунта под баном: Acc1 ~2ч, Acc2 ~23.5ч. Уведомления не идут. Ждём снятия.

**02.07.2026 03:12 — Статус-чек: оба аккаунта под баном, расследование причины бана Acc1.**
Acc1 (@iraluxme): FloodWait до 12:34 MSK (10ч). Acc2 (@Sofiya): до 10:01 MSK (7ч).
Acc2 не имеет heartbeat и не упоминается в логах — полностью бездействует (CB открыт).
Причина ПОВТОРНОГО бана Acc1 (после истечения 18ч от 30.06):
- Acc1 непрерывно поллил 209 Hot-каналов 12.5ч (36K+ API-вызовов)
- В 02:35 MSK Dormant-тир (warmup 2/7, 292 канала) стартовал поверх Hot → шторм
- `_distribute()` включал Acc2 (healthy) но его чанк пропускался (CB) — каналы терялись
- Rate limiter (3 rps) капал скорость, но не спас от sustained-pattern detection
Решение: 4 исправления в poller.py — per-account try-lock, `_distribute` фильтрует blocked до раздачи, динамический Hot-интервал (120с при 1 аккаунте), jitter внутри `_poll_batch`.
Деплой — ТОЛЬКО после снятия бана с обоих аккаунтов (см. OPERATIONS.md §4).

**02.07.2026 03:30 — Прочитаны все referenced-файлы CLAUDE.md.**
RECOVERY.md, OPERATIONS.md, CODING_STYLE.md, TESTING.md, USERFLOW.md,
segment_seed.md (первые 100 строк), DECISIONS.md, ROADMAP.md.
Обнаружена опасная рекомендация от предыдущего ответа: «перезапустить воркер после 10:01» —
противоречит OPERATIONS.md §4 Шаг 1. Исправлено.

**02.07.2026 04:30 — Задача 0.5: пер-аккаунтный rate limiter + суточный бюджет.**
Фундаментальный фикс. Первопричина всех банов: `TelegramRateLimiter` был синглтоном с одним `_last_call` и одним `_lock` на все аккаунты. `DEFAULT_MIN_INTERVAL=0.3` ограничивал суммарный темп двух аккаунтов до 3 rps, а не каждого.
Что сделано:
- `rate_limiter.py`: `acquire(account_id)` — обязательный параметр, per-account `_last_call` и `_lock` (ленивые dict), `BudgetExceeded` (raise при превышении daily_budget), `budget_remaining()`.
- Порядок в `acquire()`: проверка бюджета → BudgetExceeded → пер-аккаунтный интервал → инкремент Redis-счётчика.
- Ключ бюджета: `budget:used:{account_id}:{YYYY-MM-DD}`, TTL 172800, обнуление за счёт смены даты в имени.
- `config.py`: +`userbot_min_interval=1.5`, +`daily_request_budget=10000`.
- Обновлены все 4 точки вызова: poller.py (2), discovery_v2.py (1), discovery.py (1).
- `_poll_batch` ловит `BudgetExceeded` → лог + `notify_admin`.
- `account_id=0` (legacy discovery v1) получает свой слот — обратная совместимость.
- 7 новых unit-тестов в `tests/test_rate_limiter.py`: 3 на пер-аккаунтный интервал, 4 на бюджет (fakeredis).
- `requirements.txt`: +`fakeredis>=2.0`.
Результат: pytest 7/7 зелёный, 44 существующих unit-теста без регрессий. 0 вызовов `acquire()` без `account_id`.
Уроки: синглтон-лимитер — антипаттерн для multi-account. Circuit breaker был пер-аккаунтным, а лимитер нет — несоответствие архитектуры.

**02.07.2026 05:15 — Задача 0.1: тесты на фиксы инцидента #3.**
Только тесты, без правок production-кода. 9 новых unit-тестов в `tests/test_poller_fixes.py`:
- `_distribute`: 4 теста — blocked-аккаунт исключается, каналы не теряются, round-robin сохранён, unhealthy исключается, все-blocked → пустой список.
- `_account_locks` try-lock: 1 тест `test_locked_account_lock_state` — проверяет состояние `lock.locked()` (вариант B: честно документирует ограничение — реальный skip-путь требует рефакторинга `_run_tier_loop`, запланирован в задаче 1.1).
- `_get_effective_interval`: 4 теста — ×2 при 1 healthy, без изменений при 2+, не-Hot тиры не меняются, unhealthy не считаются.
Результат: 9/9 зелёные локально и в Docker, 49 существующих unit-тестов без регрессий.

**02.07.2026 06:00 — Задача 0.2: развести конфликт деградации (_distribute vs handle_account_failure).**
Корень инцидентов #2/#3: `handle_account_failure()` перекидывал каналы упавшего аккаунта на выжившего через `min(healthy, key=channel_count)`.
Что сделано:
- `handle_account_failure` → только `logger.error`, без перераспределения.
- `health_check_loop` → алерт без вызова переброски.
- `_should_poll_tier()`: Hot всегда, Warm/Cold/Dormant — только при 2+ healthy.
- Guard clause в `_run_tier_loop`: пауза не-Hot тиров при 1 аккаунте.
- Удалён мёртвый код: `redistribute_channels`, `get_account_for_channel`, `_channel_assignments`, `channel_count`, `total_channels`. Grep-подтверждение: 0 внешних вызовов для каждой сущности.
- 17 новых тестов (2 pool + 6 `_should_poll_tier` + 9 из 0.1).
Результат: 56 тестов в Docker, 0 регрессий. Переброска каналов исключена на уровне кода.
Уроки: два противоречащих механизма (`_distribute` исключает blocked, `handle_account_failure` перекидывает) — классический race condition в архитектуре. Пул не должен управлять распределением — это зона ответственности поллера.

**02.07.2026 05:30 — Задача 0.3: исключить parked-каналы из расписания.**
Каталожные каналы стран без подписчиков больше не поллятся (1827 Dormant → 0 при `poll_parked_countries=False`).
Что сделано:
- `config.py`: +`poll_parked_countries: bool = False`.
- `_rebuild_tiers`: `elif settings.poll_parked_countries` → dormant (legacy), `else` → `parked += 1` (исключены).
- `is_watched` (country_id=None) не задет — ручные каналы всегда поллятся.
- Лог ребилда: `%d parked (inactive countries, not polled)`.
- 3 теста: исключение неактивных, защита watched, откат через флаг. 18/18 зелёные.
- ⚠️ Активация parked-страны имеет задержку до TIER_REBUILD (1 час) — будет устранено в Задаче 1.5.
Результат: при текущих подписках в расписании 200-400 каналов вместо 2035.
Уроки: Dormant-тир (12ч цикл) жёг 73% бюджета вхолостую. Флаг отката — страховка на случай ошибки классификации стран.

**02.07.2026 05:40 — Задача 0.4: последовательный опрос + лог-нормальные паузы.**
Убран `asyncio.gather` по каналам одного аккаунта — три одновременных запроса заменены на строго последовательный цикл. Это последний «машинный» паттерн, за который Telegram банил.
Что сделано:
- `_poll_batch`: последовательный `for ch in shuffled` вместо `asyncio.gather`.
- `next_delay()`: `lognormvariate(0.7, 0.5)`, медиана ~2с, диапазон 0.8–6с.
- `random.shuffle` порядка каналов на каждом цикле.
- Удалены: `PARALLEL_BATCH`, `BATCH_PAUSE`, `BATCH_PAUSE`-jitter.
- `min_interval=1.5` НЕ тронут — остаётся safety floor.
- 3 теста: диапазон, медиана, spread распределения. 21/21 зелёные.
Результат: с одного аккаунта запросы строго последовательны, интервалы лог-нормальные. Разные аккаунты по-прежнему параллельны (уровень `_run_tier_loop`).
Уроки: `asyncio.gather` на одном аккаунте — антипаттерн для MTProto. Три одновременных запроса + равномерный jitter = детектируемый бот. Лог-нормальное распределение с тяжёлым правым хвостом неотличимо от человека, листающего чаты.

**02.07.2026 06:00 — Задача 0.6: Redis AOF-персистентность.**
⚠️ **ПОПРАВКА 12.07.2026:** изменение ПОТЕРЯНО при позднейшей перезаписи docker-compose.yml — в проде `appendonly no`, тома нет. Повторное включение — задача 0.1 fable_core_plan.md.
Включён AOF: `appendonly yes`, `appendfsync everysec`. Добавлен именованный том `redis_data:/data` в docker-compose.yml. Очередь `queue:notifications` теперь переживает рестарт Redis (раньше LPUSH/BRPOP in-memory терялись при любом рестарте контейнера). `appendfsync everysec` — компромисс: теряем ≤1 сек данных при крахе, не платим fsync на каждой записи. Памяти хватает: 2.5MB used при лимите 100MB.

**02.07.2026 06:15 — Задача 0.7: шифрованный бэкап сессий userbot.**
Session-файлы (userbot.session + userbot2.session) теперь бэкапятся вместе с БД: tar + gpg --symmetric AES256, пароль из SESSION_BACKUP_PASSPHRASE в .env. Самопроверка непустого архива (decrypt → tar tzf → grep '.session\$') — исключает повторение бага с пустым бэкапом. Ротация 7 дней. Восстановление задокументировано в RECOVERY.md.
Баг (найден и исправлен): `*.session` раскрывался шеллом в CWD, а не в SESSION_DIR — `tar -C` меняет каталог ПОСЛЕ раскрытия glob. 2>/dev/null скрывал ошибку, скрипт рапортовал успех на пустом архиве. Исправлено: `( cd "$SESSION_DIR" && tar czf - *.session )` + проверка числа файлов после шифрования.
Известные ограничения: S3-выгрузка — placeholder (B2 требует awscli/b2 CLI, не реализован), бэкап на том же диске — единственная точка отказа до настройки offsite.
Урок в OPERATIONS.md: 2>/dev/null на критичных операциях скрывает фатальные ошибки; проверка восстановлением обязательна.

**02.07.2026 06:30 — Задача 0.8: CB-статус при старте worker.**
Минимальная правка: `start()` логирует состояние CB для каждого аккаунта после инициализации пула. «circuit breaker OPEN — blocked for ~Ns (until HH:MM:SS UTC)» или «clear — ready to poll». Весь механизм защиты уже покрыт предыдущими задачами: `_distribute` (0.1) исключает blocked-аккаунты, `wait_if_circuit_open` в `_poll_batch` — двойная страховка, AOF (0.6) сохраняет CB-ключи при рестарте Redis, warmup (8%→100%) обеспечивает плавный старт после любого рестарта.
⚠️ «Пониженная скорость после рестарта» реализована через warmup-охват (мало каналов → мало запросов), а не через per-request tempo. Полноценный пост-бан режим (50% бюджета, ×1.5 интервалы на 48ч) — Задача 2.2 в Фазе 2.
Что сделано: `start()` + лог CB, `config.py` +`session_backup_passphrase`, 2 теста. 64 теста, 0 регрессий.
Уроки: задача 0.8 оказалась на 90% уже решена предыдущими — честный scope-анализ сэкономил ненужный код.

**02.07.2026 06:45 — Задача 1.6: entity-кэш — убрать ResolveUsername из цикла.**
Каждый опрос канала делал 2 API-вызова: ResolveUsername + GetHistory. Теперь ResolveUsername — один раз за жизнь worker (per account). `_entity_cache[chat_username][account_id] = (channel_id, access_hash)`. При попадании — `InputPeerChannel` напрямую, без `limiter.acquire()`. При `ChannelInvalidError` (stale hash) — инвалидация кэша, следующий цикл перерезолвит. Экономия: −1 ResolveUsername на канал на цикл; при 200 каналах и 120s интервале ≈ −144K запросов/сутки. 3 теста: cache hit, per-account независимость, реальная экономия в `_poll_channel` (get_entity 1 раз за 2 цикла). 67 тестов, 0 регрессий.
Уроки: `InputPeerChannel(channel_id, access_hash)` идёт в GetHistory напрямую — Telethon НЕ резолвит повторно. Кэш in-memory достаточен — access_hash меняется только при миграции канала.

**02.07.2026 07:00 — Задача 1.1: сессионная модель планировщика.**
Главная правка перед живым прогоном — ломает непрерывный 24/7 паттерн из инцидента #3. Пер-аккаунтная сессия: ACTIVE (20-60 мин) ↔ PAUSED (15-60 мин) вне сна, SLEEPING (4-6ч) в окне 02:00-08:00 UTC. `_session_ticker` — единственный владелец переходов (Redis), `_get_session_state` — только чтение. Переживает рестарт: ticker досыпает `session:until`, не сбрасывает сон. SLEEPING→ACTIVE безусловно, until продлён за конец sleep-окна. Wraparound для 1.2. Крючок: `_get_sleep_start_hour(account_id)`. 9 тестов. 77 всего, 0 регрессий.
Уроки: разделение ticker/reader устранило гонки 4 тиров. Redis как источник истины для сессий — естественно после AOF (0.6).

**02.07.2026 09:00 — Задача 1.2: stagger sleep windows.**
`_get_sleep_start_hour`: `(idx * (24 // N)) % 24` — acc1=12:00, acc2=00:00, окна сна 6ч не пересекаются (проверено через `_is_in_sleep_window`). 3 теста. ⚠️ Неполное покрытие каналов спящего аккаунта — сознательный компромисс (безопасность > полнота). Переброска на активный через `_distribute` ОТВЕРГНУТА — sustained-pattern #3. Каналы спящего ждут пробуждения (до 6ч). 83 теста, 0 регрессий.

**02.07.2026 09:30 — Задача 1.4: alert loop — мониторинг здоровья системы.**
6 проверок каждые 5 мин в @leadhunterai_admin: очередь > 100 / dead-letter / FloodWait / бюджет / поллер stuck (ACTIVE + last_poll > 30m WARNING, > 60m CRITICAL). Защита: молчит при PAUSED/SLEEPING. `stats:last_poll_at` в `_poll_batch`. Троттлинг Redis `alert:last:{type}`. `notify_admin` не тронут. 6 тестов, 89 всего, 0 регрессий.

**02.07.2026 10:00 — Задача 2.2: пост-бан режим (48ч пониженной активности).**
Последняя защита перед живым прогоном. 3 слоя: `last_ban_at` при бане / `post_ban_until` при истечении CB / `activate_post_ban_if_recent` при старте. Бюджет /2 (5K), интервалы ×1.5. `_is_post_ban` кэш 60с. 8 тестов (ключевой `budget_halved` доказывает урезание). 97 всего, 0 регрессий. ⚠️ Текущие аккаунты требуют ручной установки `post_ban_until` перед запуском. Урок: без теста `budget_halved` рискнули бы четвёртым баном.

**02.07.2026 10:45 — fix: баг пагинации при cursor=0 (дубли в логах).**
При cursor=0 все 5 раундов `_fetch_all_since` попадали в `else` → те же 30 сообщений ×5. Лог: 5× матчей; пользователей НЕ задело (`sent_log UNIQUE` отсёк). Фикс: `if rounds > 0` вместо `fetch_min_id > 0 and rounds > 0`. Тест с Telethon-точным моком падает на старом коде (150→30), проходит на новом (106→106).

**02.07.2026 11:00 — ТОЧКА ВОЗОБНОВЛЕНИЯ (перерыв, worker РАБОТАЕТ).**
Второй живой прогон идёт. acc2 поллит, acc1 под CB до ~12:34 MSK. Пагинация + notify_admin применены (worker перезапущен). notify_admin: алерты только в канал ✓. Match ×5: НЕ подтверждено (аккаунты в PAUSED при проверке). Ждёт: fix/alert-floodwait-dedup (дубль CRITICAL+WARNING) при след. рестарте. Бюджет acc2: 325/5000 (6.5%). FloodWait: нет. СЛЕДУЮЩИЙ ШАГ: проверить логи на Match ×5.

**02.07.2026 15:20 — ТОЧКА ВОЗОБНОВЛЕНИЯ (перерыв 3ч, worker РАБОТАЕТ).**
ЯДРО/Фаза 2: LLM-валидатор написан (shadow-режим), ветка fix/2.4-llm-validation,
НЕ вычитан владельцем, НЕ смержен в main, миграция НЕ применена, БД не тронута.
Ключ DeepSeek в .env (sk-986...e5fc), модель deepseek-chat, API работает.
Промпт проверен на РЕАЛЬНОЙ DeepSeek: 37/40=92.5%, 0 ошибок типа A (потеря лида).
СЛЕДУЮЩИЙ ШАГ: вычитать diff (6 пунктов) → бэкап → миграция → shadow.
alert-floodwait-dedup уже в main (87f782c).
Ложный stuck-алерт задокументирован — баг в _check_poller_stuck (не сбрасывает
last_poll_at при рестарте), fix в отдельной ветке. Не блокирует прод.
Прод: worker Up 26 мин (рестарт для подхвата API-ключа), FloodWait нет,
бюджет acc1=231, acc2=762 из 5000, CB clear, матчи идут (6 за 15 мин).
Discovery v2: баг INTER_QUERY_PAUSE (не критично, только discovery).

**02.07.2026 14:30 — 🚀 ПЕРВЫЙ РАБОЧИЙ ЗАПУСК УСПЕШЕН.**
Worker в штатной работе на 2 аккаунтах (acc1 @iraluxme, acc2 @mill_sofi), оба CB clear.
Подтверждено в бою за 2+ часа живого прогона:
- Пагинация без дублей: msg_id один раз, paginated rounds тянут разное, без ×5.
- notify_admin: алерты только в @leadhunterai_admin (исправлен if→elif).
- alert-dedup: один эскалационный алерт на FloodWait вместо дубля CRITICAL+WARNING.
- _distribute: 218 hot-каналов делятся поровну между acc1 и acc2.
- Post_ban: активен на обоих (50% бюджет = 5000, ×1.5 интервалы) до 04.07 ~14:06 MSK.
- Бюджет здоров: acc1 ~21 запросов, acc2 ~890 запросов из 5000 за день.
- FloodWait: 0 за 2+ часа, оба аккаунта чисты.
Фаза 0 (8/8) + 1.6/1.1/1.2/1.3/1.4/1.8 + 2.2 done. Три hotfix'а из живого прогона (пагинация, notify_admin, alert-dedup) применены в main.
Режим: пассивный мониторинг через @leadhunterai_admin.
ОСТАЛОСЬ (штатно, без аврала): 1.5 (активация страны), 1.7 (dead-man switch),
Фаза 2 (LLM, feedback, классификатор), Фаза 3 (продукт), 3-й аккаунт при появлении SIM.

**02.07.2026 14:15 — Task 1.3: Hot interval 10min, adaptive + cap.**
Снят последний агрессивный параметр в проде — Hot 60с → 10мин (600с).
Формула: min(base × max(degraded, post_ban), cap). max() вместо перемножения —
множители не стакаются (1акк+post_ban = max(2, 1.5) = 2, не 3).
3 аккаунта → 7мин (420с), 2 → 10мин (600с), 1 → 20мин (1200с).
Cap 20мин — жёсткий потолок при любых условиях.
Warm/Cold/Dormant: 50мин/2.5ч/12ч — все из config.py, 0 хардкода.
8 новых тестов, 140 всего, 0 регрессий. Тег task-1.3-done.

**02.07.2026 14:35 — Task 1.8: dedup Samui + UNIQUE(country_id, slug).**
Слит дубль «Самуи» (id=70 → канонический id=13): 24 channel_cities удалены
(дубли — те же каналы под обоими id), 2 catalog_channels перенесены 70→13.
UNIQUE(country_id, slug) на cities — защита от будущих дублей.
«Вся страна» (id=63) проверена — фича «подписка на всю страну», 1 запись,
корректна, не тронута. Миграция Alembic обратимая, бэкап pg_dump был.
Worker не останавливался, ошибок 0. Тег task-1.8-done.
Фаза 1 завершена (1.3, 1.6, 1.1, 1.2, 1.4, 1.8 done; 1.5 и 1.7 отложены).

**02.07.2026 07:15 — ТОЧКА ВОЗОБНОВЛЕНИЯ.**
Фаза 0: завершена (phase-0-done, 8/8).
Фаза 1: 1.6 done (merged). 1.1 — В РАБОТЕ на fix/1.1-session-model (80 тестов зелёные, _run_tier_once готов, 3 реальных интеграционных теста).
Осталось по 1.1: review → merge → task-1.1-done.
Следующие: 1.2 (таймзоны, _get_sleep_start_hour), 1.4 (алерты) → живой прогон.
Бан: acc2 ~07:01 MSK, acc1 ~09:34 MSK (проверить circuit:expires перед запуском).

**02.07.2026 07:00 — Phase review: 2 blocker'а найдены и исправлены.**
`/skill:phase-review` выявил: (1) `effective_city_ids` — NameError в `_dispatch` (не определён, но используется в city-фильтрации; не падал т.к. у текущих пользователей mode='all'); (2) `UserbotAccount.get_messages` не принимал `min_id`/`max_id` → `_fetch_all_since` с инкрементальным поллингом падал бы с TypeError (не падал т.к. оба аккаунта под CB). Исправлено: `+**kwargs` в `get_messages`, `+effective_city_ids` в `_dispatch`. 64 теста после исправлений — 0 регрессий.

**03.07.2026 02:30 — Диагностика бана + три фикса (ветка fix/disable-discovery-fix-throttle, НЕ смержена).**
Диагностика: оба аккаунта НЕ под активным FloodWait. Acc1 — 17ч бан от discovery (уже истёк, сейчас SLEEPING). Acc2 — чист, ACTIVE, поллит. 35 errors/цикл на Hot-тире (32%) — глушатся на logger.debug, требуют расследования.
Фикс 1: discovery v1/v2 удалены из tasks.py полностью (импорты + client creation). Были закомментированы (61522a6, 2fe673a), теперь не могут быть случайно включены.
Фикс 2: report_flood_wait в rate_limiter.py — добавлен 15-мин троттлинг на notify_admin (ключ alert:last:flood_wait_report:{account_id}). Ранее спамил 100+ уведомлений.
Фикс 3: CLAUDE.md §0 — новое правило: не трогать прод при работающем worker.
⚠️ Применять осторожно: остановить worker → пересобрать → запустить. Acc2 продолжит работать, acc1 под CB/SLEEPING подождёт.

### 2026-07-04 — Группировка: полный аудит + план админ-фичи

ИТОГ ПО ГРУППИРОВКЕ: механизм ЗДОРОВ. 4 захода аудита сняли все подозрения.
Over-dispatch=0, покрытие effective 100-140% по всем городам Вьетнама, мультисити
разбирает перечисления, город/страна-подписка работают. «6 каналов Дананга» и
«недобор Ханоя» — артефакты счёта только по auto_matched без channel_cities.
Правило «проверять напрямую, не верить на слово» сработало 4×.

ПОДТВЕРЖДЁННАЯ ФАКТУРА:
- Привязка: _tag_new_channels() poller.py:1169 — точное вхождение + fuzzy по
  username+title. URL не читается, поля url в БД нет. 91 страна, 227 городов.
- Мультисити: auto_matched_city_id (скаляр) ∪ channel_cities (M2M, PK
  channel_id+city_id) = effective_city_ids, читается dispatch poller.py:1316.
  44 канала мультисити.
- 831 орфан (city=NULL): реально безгородние ПО ИМЕНИ (сырой ILIKE=0), не жертвы
  fuzzy. Все со страной. Топ: Египет 90, Шри-Ланка 54, Вьетнам 52. У всех валидный
  @username. 627 (75%) без participants.
- channel_segments ПУСТА (0/2522). Сегмент — свойство только подписчика,
  релевантность = keyword-матчинг рантайм. _load_channel_segments() poller.py:1430
  заложена, но БД не наполняет.
- Админка: FastAPI:8001 + SQLAlchemy async + React. GET/PUT /api/channels
  (api/__init__.py:63), фильтры search+is_verified+пагинация. БД через
  async_session_factory.
- Справочник городов: slug (UNIQUE) + country_id (FK RESTRICT) обязательны;
  name_ru/name_en/is_active опц; UNIQUE(country_id, slug).

НОВЫЙ ТЕХДОЛГ (не срочно):
4. Fuzzy-ложняки: короткие токены с «nn» → Нижний Новгород (@nnw_chat «Neural
   Chat», @NNR_chat, @nnmidletschat). Подтверждено в 2 независимых выборках.
   Порог poller.py:1237 (0.95 при <5 букв / 0.85 при ≥5). Масштаб не измерен
   (~5-10 видимых). Также @byinpt → Порту вместо Кашкайш.
5. Кашкайш и, вероятно, др. города отсутствуют в справочнике 227 — пополнить.
6. 627 орфанов без participants — если показывать подписчиков в панели, userbot
   должен дотягивать (лезет в Telethon/путь опроса, отложено).

ROADMAP (порядок очереди):
- АКТИВНАЯ: админ-фича «Чаты без группы» (план ниже).
- СЛЕД. ОТДЕЛЬНЫЙ ЧАТ: ключевики (техдолг №3), чистка EN/RU перекоса.
  Предусловие для авто-направлений.
- ПОСЛЕ КЛЮЧЕВИКОВ: авто-направления — оживить channel_segments /
  _load_channel_segments, наполнить предтегирование каналов. Ручная разметка из
  админ-фичи = эталонная выборка для проверки качества.
- ПОСЛЕ АВТО-НАПРАВЛЕНИЙ: селектор + экспорт csv/md — отбор подмножеств
  (страна/город/направление) под новые продукты-боты (HR, IT-заказы, дизайн).
  Данные в схеме, ждёт чистых направлений.

ПЛАН АКТИВНОЙ ЗАДАЧИ — админ-фича «Чаты без группы» (шаги, каждый отд. заход):
1. Миграция: колонка is_ignored bool default false в catalog_channels. Только это.
   Штатным механизмом миграций (Alembic?), не руками в psql.
2. ГОРЯЧИЙ ШАГ: проверка is_ignored=false в 3 точках — discovery_v2.py:266,
   _get_all_channels() poller.py:196, _tag_new_channels() poller.py:1187. Тест:
   игнорированный канал исчезает из всех 3 выборок И не слушается userbot'ом.
   Отдельный заход, отдельный тест.
3. Бэкенд-роуты (расширить /api/channels): фильтр has_city=false +
   country_id/city_id/is_ignored; POST привязки мультисити (в channel_cities,
   ≥1 город + country); POST «добавить город» (slug+country_id, UNIQUE-safe);
   PATCH is_ignored=true («Удалить»). url = t.me/{chat_username}, participants
   число или null→«—».
4. Фронт «Чаты без группы»: список (title, кликабельный url, participants/«—»),
   очередь = 831 орфан + fuzzy-сомнительные (вычислять запросом, признак в БД не
   хранится). Дропдауны страна→город (мультиселект), «добавить город», «Удалить»
   (→is_ignored). Обновление сразу. Поле «направление» ЗАЛОЖИТЬ в разметку, НЕ
   активировать (ждёт авто-направлений; будущая обучающая выборка).
КРЮЧОК (закладываем, не строим): листинг-эндпоинт шага 3 проектировать так,
чтобы фильтры переиспользовались будущим экспортом csv/md.

### 2026-07-04 (продолжение) — Админ-фича «Чаты без группы»: шаги 1-2 СДЕЛАНЫ

СТАТУС ЗАДАЧИ: шаг 1 (миграция) + шаг 2 (фильтр) закрыты и в origin.
Осталось: шаг 3 (роуты API), шаг 4 (фронт).

СДЕЛАНО (в БД/коде, на origin):
- Колонка is_ignored в catalog_channels: bool, NOT NULL, server_default false.
  Миграция ccb7137d7d5c (down=c2a1d3b4e5f6). Все 2522 = false на момент наката.
- Alembic ВЫЛЕЧЕН по пути: были двойные головы в alembic_version [4afd,b111] при
  линейной цепочке + незаписанный c2a1 (реально применён через docker compose run).
  Исправлено прямой правкой alembic_version → одна голова. Затем дрейф моделей:
  City/SentLog не декларировали uq_cities_country_slug и idx_sent_log_content_dedup,
  autogenerate генерил их DROP — дописали в ORM (models.py), дрейф устранён.
  ВАЖНО: миграции писать ВРУЧНУЮ на хост, НЕ autogenerate вслепую (см. долг №7).
- Фильтр is_ignored=False в 4 точках: discovery_v2.py (+guard перед session.add,
  т.к. usernames из Telegram Search API — внешний источник), _get_all_channels
  (poller, прослушка), _tag_new (poller), _load_channel_segments (poller).
  Discovery делает INSERT (не UPSERT) → игнорированный канал НЕ воскрешается.
- @saigon_services (id=885) помечен is_ignored=true (мёртв, подтверждён вручную).
  Закрывает часть долга №1. Сейчас в БД ровно 1 ignored канал.

ПОВЕДЕНИЕ (согласовано с владельцем):
- Прослушка обновляется на часовом ребилде self._hot_channels (poller). Задержка
  «Удалить»→канал перестал слушаться до 1ч — ДОПУСТИМО. Фронт ДОЛЖЕН показывать
  пользователю, что изменения применятся в течение часа.
- Dispatch/раздачу is_ignored НЕ фильтрует (не требуется при часовой задержке).

НОВЫЙ ТЕХДОЛГ:
7. bind-mount ./migrations:/app/migrations МЁРТВ (overlay2-конфликт: COPY . . в
   Dockerfile кладёт migrations в образ, mount поверх не работает; host uid 1000 vs
   container root). Следствие: alembic upgrade в контейнере читает миграции ИЗ
   ОБРАЗА, не с хоста. Обход: писать файл на хост (для git) + docker compose cp в
   контейнер + upgrade. Вероятная КОРНЕВАЯ причина всего рассинхрона Alembic.
   Чинить осознанно (правка Dockerfile/compose + пересборка = красная линия +
   перезапуск userbot). Кандидат — совместить с передеплоем под ключевики.

АДМИН-ФИЧА «ЧАТЫ БЕЗ ГРУППЫ» — ЗАКРЫТА (шаги 1-4).

### 2026-07-04 — Шаг 3: роуты API (СДЕЛАНО)

- (a) GET /api/channels: фильтры has_city/country_id/city_id/is_ignored, is_ignored в ответе.
  city_id ловит мультисити через channel_cities. Очередь = has_city=false AND is_ignored=false = 830.
  Коммит 745cfc0.
- (c) POST /api/cities UNIQUE-safe: 409 при конфликте country_id+slug, сессия не виснет.
  Коммит 161aa99.
- (b)+(d) PUT /api/channels: привязка городов перезаписью (DELETE-all→INSERT),
  country auto-set если пуст; is_ignored в updatable («Удалить»). Коммит 745cfc0.
- Все правки — admin-слой (FastAPI), схему БД не трогали, миграций нет.
- Отложено (не потерять): экспорт csv/md по стране/городу — дорабатываем потом, не скоро.
  Направления/сегменты ждут долга №3 (ключевики).

### 2026-07-04 — Шаг 4: фронт «Чаты без группы» (СДЕЛАНО, коммит локально, ждёт push)

Один файл: admin-panel/src/pages/ChannelsPage.tsx (160→~310).
- Фильтры: has_city (все/без/с), is_ignored (активные/игнор/все). Вместе =
  очередь орфанов 830. + счётчик «Найдено N».
- Таблица: +колонка «Игнор» (badge), +колонка «Направление» (disabled,
  плейсхолдер, ждёт долга №3). url строкой t.me/{chat_username}.
- Строка: страна→город мультиселект, «Привязать», «Удалить» (is_ignored=true),
  «+ город» (POST /api/cities, 409-safe toast). Баннер «изменения в теч. часа».
- ⚠️ Фикс перезаписи: «Привязать» активна ТОЛЬКО для орфанов
  (auto_matched_city_id==null). У каналов с городом — disabled + тултип.
  Причина: PUT cities=перезапись; мультисити (44) хранят набор в
  channel_cities, UI его не подгружает → сотрёт.
- Тест: смоук с откатами. Привязка 830→829→830, ignored 830→829→830. Зелёно.
  Сборка vite чистая, статика в app/admin/static.

НОВЫЙ ТЕХДОЛГ (8): редактирование существующих привязок канала
(мультисити-safe): подгружать channel_cities в мультиселект перед PUT cities —
отдельная задача. Сейчас привязка через UI разрешена только орфанам.

АКТИВНОЕ СЛЕДУЮЩЕЕ: ключевики (долг №3), чистка EN/RU перекоса.

---


**04.07.2026 — DIAG-1 разобран + фича 7-day. Итог: из 4 симптомов DIAG-1 живых багов НЕТ.**
 - (a) CPU 100% — норма для 217 Hot-каналов на 1-Core, не spin. Task-destroyed для _alert_loop — косметика shutdown. Правки не нужно.
 - (b) Hot-тир «32-48% ошибок» — УСТАРЕЛО. Цифра снята до рестарта с hotfix 2e08849 (get_input_entity в UserbotAccount). После рестарта: 4 ошибки / 380 опросов = 1%. get_input_entity уже везде, get_entity в опросе нет.
 - (c) LLM «0 матчей» — ЛОЖНОЕ измерение (grep-паттерн). Реально: 110 матчей/3ч, sent_log шлёт. Диспатч работает.
 - (d) post-ban «не активен» — ОШИБКА АУДИТА (искали Redis KEYS post_ban:* вместо post_ban_until:*). Работает: оба акка post-ban до 04.07 10:06 MSK, бюджет 5000, интервал ×2.
 - Фича «новые + ≤7 дней» — коммит 49e1781 (+тесты t1-t5), лог 0f1a3f3, запушено. Курсор теперь по полной серверной выдаче (чинит пре-баг с безтекстовым хвостом, анти-петля на stale-батчах, доказано t2).

ОСТАТКИ (техдолг, НЕ срочно):
 1. 4 орфанных канала без city/segment (@vietnam_jobs, @danang_jobs, @hcmc_jobs, @saigon_services). @saigon_services — мёртв (UsernameInvalid), удалить. Остальные 3 живы, но без привязки → относится к задаче ГРУППИРОВКА по городам.
 2. ~~_fetch_all_since — немой except Exception: return []~~ ЗАКРЫТ 10.07.2026 (задача C4 аудита: logger.warning, поток не изменён).
 3. Ключевики перекошены в EN (~1800 demand-фраз EN; RU полн. только «красота»313, «кейтеринг»147). Продуктовое решение, не баг.
СЛЕДУЮЩАЯ ЗАДАЧА (план пользователя): группировка чатов по городам/странам.

**04.07.2026 06:22 — feat: 7-day freshness gate + cursor advance fix (commit 49e1781).**
Добавлен фильтр «не старше 7 дней» в _poll_channel: cutoff из settings.message_max_age_days, датовый гейт перед classify (не трогает курсор). Курсор переведён на server_max по ПОЛНОЙ серверной выдаче (безусловно на непустом батче) — чинит pre-existing баг с безтекстовым хвостом и flood-петлю на залежалых каналах. 5 тестов (t1-t5) покрывают свежие/старые/смешанные/пустые/date=None. 6/6 PASS. +4 коммита в сессии, разрыв с origin: 10. Worker НЕ деплоился — только код и тесты.

**04.07.2026 02:45 — Fix: CB-aware availability, escalating post-ban, cryptg, get_input_entity.**
Задача из прерванной сессии — 6 пунктов. Результат:
1. `_get_available_account_count()` → async, проверяет CB через `limiter.is_circuit_open()`. Корень проблемы: после бана Acc1 метод возвращал 2 → интервал не деградировал → Acc2 работал 10.8ч на полной скорости → бан.
2. `_get_effective_interval()` → async, `max_pb_mult` через `limiter.get_post_ban_interval_multiplier()` по всем аккаунтам, 0 CB-free → cap 1200s + CRITICAL.
3. Эскалация post-ban: Redis счётчик `ban_count:{id}` (TTL 7д). Бюджет: 1 бан → /2, 2 → /4, 3+ → /8. Интервал: ×1.5, ×3.0, ×5.0. 3+ → алерт о риске перманентного бана.
4. cryptg v0.6.0 установлен.
5. `_resolve_entity`: `get_input_entity` вместо `get_entity`. БАГ: в `UserbotAccount` не было `get_input_entity` → AttributeError на 217 каналах. Исправлено: добавлен метод в pool.py.
6. Тесты: rate_limiter 13/13, poller 60/64 (4 не прошли из-за pre-existing сигнатурных mismatch в тестах `_run_tier_once`).
Прогон: worker запущен, Acc1 active (CB clear), Acc2 blocked до 07:10 UTC. Hot: 217 каналов, интервал ×2 деградация. 0 AttributeError. 0 FloodWait.

**05.07.2026 04:00 — Resume handoff: keyword recon, orphan retag, admin frontend cleanup (commit 44a65c7).**
Доделано с предыдущей сессии:
- Smoke test unignore→verify→re-ignore через admin API: зелёный (канал id=885 saigon_services).
- API login путь: `/api/auth/login` (не `/api/login`), порт 17421.
- Коммит: удалена колонка «Направление» (disabled placeholder), добавлена кнопка «Восстановить»
  (handleUnignore, PUT is_ignored=false) для ignored-каналов, кнопка «Удалить» только при !is_ignored.
- Старые статик-ассеты удалены из git (index-BC1Mf4p9.js, index-C-wCZOeF.css, index-C2dFgfOB.css, index-D0xiouDV.js).
- 9 каналов перепривязаны по транслитерации (Valencia, Casablanca, Tehran, Paphos×4, Samui×2) — DB-only, без миграций.
- Документация: kw_recon.txt, orphans_diag.txt, matcher_anatomy.txt, retag_dryrun.txt, admin_front_recon.txt в docs/.
Результат: админ-фича «Чаты без группы» полностью закрыта (шаги 1-4). Орфаны: 830→821.

**05.07.2026 ~11:30 — Админ-панель: масштабный UI/UX-оверхаул ChannelsPage + фикс краша worker.**
Backend (FastAPI + SQLAlchemy):
- +city_ids в list_channels (auto_matched ∪ channel_cities M2M).
- +manually_reviewed bool (модель + GET/PUT + миграция manrev01).
- +discovered_after ISO-фильтр, индекс idx_disc_at01.
- per_page max 100→500 для countries/cities (фикс 422).
- order_by(is_ignored ASC, participants DESC NULLS LAST).
Frontend (ChannelsPage.tsx, 524 строки, полный рерайт):
- Фильтры: статус (Все/Активные/Игнор/Без привязки), страна (dropdown 91), город (зависимый dropdown), «Новые (7д)», perPage (20/100/200/500, default 100), поиск с X.
- Счётчики: «Без привязки: N · Найдено: N». Секция «+ Город».
- 3-цветная точка статуса: фиолетовая (ignored) / зелёная (reviewed) / оранжевая (pending).
- Per-row: Select страны, MultiSelect городов (Popover+Command+Badge, M2M-safe, pre-fill из city_ids), кнопки Save/Trash2/RotateCcw (icon-only size-4).
- 6 колонок: @username(+dot) | Название | Участники | Страна | Города | Действия.
- Убрано: колонка «Привязан», badge «Игнор», verified-фильтр, баннер.
- Новые shadcn-компоненты: command.tsx, popover.tsx, input-group.tsx, multi-select.tsx (кастомный).
Bursa retag: канал 1595 → city_id=59, орфаны 821→820→813.
ИНЦИДЕНТ: worker crash-loop из-за NameError (settings не импортирован в tasks.py:27).
Коммит c626dfd добавил settings.discovery_enabled без импорта. Исправлено: +from app.config import settings, rebuild, restart.
Оба аккаунта CB clear, worker стабилен.
Git: куча немерженных файлов (backend + frontend + migrations + удалённые/новые статик-ассеты + docs).
Handoff: .rpiv/artifacts/handoffs/2026-07-05_channels-ux-overhaul.md.

**08.07.2026 16:30 — Каталог v2: Фаза 1 (миграция) + Фаза 2 (ключевые слова) завершены.**
Реструктуризация каталога: 14 категорий, 69 подкатегорий.
- Миграция cat_hierarchy_v1: таблица categories, FK category_id в segments
- Старые 29 сегментов удалены, 69 новых созданы с привязкой к категориям
- Страны: оставлена 21 фокус-страна (миграция focus_countries)
- 1524 ключевых слова (1491 demand/stop + 33 universal stop) загружены в БД
- LLM-промпт обновлён: все старые slugs заменены на новые
- poll_parked_countries = True: все 21 страна поллятся (Hot/Dormant)
- Config: TIER1_COUNTRY_SLUGS расширен до 21 страны
- 4 unit-теста исправлены (Segment теперь требует category_id)
- Worker стабилен: 1491 keywords, 69 segments, 33 universal stops
- Следующее: Фаза 3 (бот — двухуровневый выбор категорий/подкатегорий)

**09.07.2026 — Аудит: Фаза A завершена целиком (ветка audit/fable-fixes, прод НЕ трогался).**
План и пометки — fable_audit.md. Все 6 задач закрыты, по коммиту на задачу:
- A1 (439c3fe): «Вариант Б» работает end-to-end — keyword-матчи без сегментов идут в dispatch (PendingMatch.keyword_only, минуя reality-фильтр и LLM), keyword-ветка в _dispatch вне цикла подписок и без гео, word-boundary+леммы вместо substring. 5 тестов test_variant_b.py.
- A2 (код в 439c3fe/5bf079d, отчёт ea33854): обход stop-слов через «?» закрыт — _has_strong_demand_signal для Pass 2 и pre-tag boost, «?» остался только в Pass 3. Corpus-diff 1000 сообщений: 20 BLOCKED + 4 PARTIAL — все офферы, newly_matched=0, лидов не потеряно (docs/eval/a2_diff.md). 7 тестов test_stop_bypass.py.
- A3 (5a17a5d): sender — html.escape всего пользовательского контента + retry/DLQ по DECISIONS #26 (403→is_blocked_bot, 429→sleep+повтор, прочее→3 ретрая 1/4/9с→dlq). 6 тестов test_sender.py.
- A4 (5bf079d): invalidate_all_subscription_caches() (SCAN collect-then-delete) во всех CRUD-точках: keywords, channels, catalog_nav (создание/удаление подписок), admin users PUT, mark_user_blocked. 3 теста test_cache_invalidation.py.
- A5 (b3cbafa): stuck-алерт — min-семантика («все молчат ⟺ даже самый свежий молчит»), 4 теста; убран ложный алерт при одном молчащем аккаунте.
- A6 (e82f972): параметр initial удалён из цепочки поллинга, режим первого знакомства по cursor==0 — рестарт worker больше не гонит до 100×218 старых сообщений в blocking-LLM. 2 теста.
Итог сьюта: 182 passed / 3 pre-existing failed (baseline 0.3: 155/4; один из старых failed заменён в A5) / 1 hanging deselected (test_session_ticker_transitions). Тест-окружение: одноразовые контейнеры lh_test_db (5433) + lh_test_redis (6380), снесены после прогона. Ветка запушена (e82f972). Деплой фазы НЕ выполнялся — по git-стратегии офлайн-верификация, живое переключение отдельным решением владельца.
Уроки: pymorphy3 отсутствовал в хостовом venv — классификатор тихо деградировал (try/except на импорте); corpus-diff как приёмка правок классификатора работает отлично (ловит и регрессии, и подтверждает пользу).

**10.07.2026 — Аудит: Фаза B завершена целиком (ветка audit/fable-fixes, прод НЕ трогался).**
Все 5 задач закрыты, по коммиту на задачу:
- B1 (5bd6a55): явная идентичность аккаунтов — USERBOT_SESSION_MAP (`1:userbot,2:userbot2`) в config.py + property userbot_sessions с валидацией; pool.initialize идёт по маппингу, отсутствующий файл → warning+skip; discover_sessions только для диагностики неизвестных файлов. Дефолт сохраняет текущие Redis-ключи (бюджеты/CB не слетают). 7 тестов test_pool_identity.py (главный — aaa.session не сдвигает ID). Разблокирует добавление discovery-аккаунта.
- B2 (55ebf82): предкомпилированный движок классификатора — CompiledKeywordMap строится один раз в _load_keywords (startup + 5-мин reload, компиляция 1.1с), вся regex/лемма-работа по keywords убрана из hot-path, universal stops проверяются один раз на сообщение, явный _word_cache вместо re-кэша. Golden-верификация: 0/1000 расхождений с прежним поведением, ускорение 9.3× (798.8→85.8 мс/сообщение), остаток — лемматизация самого сообщения (сохранена по плану). Отчёт docs/eval/b2_golden.md.
- B3 (d06817f): единый Redis-клиент на процесс — ленивый синглтон в app/cache/__init__.py, все парные get_redis()/aclose() удалены по репо. conftest: autouse-сброс синглтона между тестами. Урок: удаление aclose оставляло пустые finally/if-блоки → SyntaxError; чинилось скриптом + ast-проверкой всех файлов app/.
- B4 (71ca52c): lead_direction из БД — колонка segments.lead_direction ('demand'/'buy'/'supply', server_default='demand'), миграция lead_direction01 (обратимая, прогнана up/down). Poller собирает pass3-skip и supply-set из БД вместо хардкода PURCHASE_SEGMENTS; LLM-промпт (блок инверсии DEMAND/OFFER) генерируется из supply-set (llm_validator.set_supply_segments, rebuild при изменении). Попутно найден и исправлен ЖИВОЙ баг: housing-buy стоял в инвертированном блоке промпта, хотя его лид — покупатель («куплю квартиру») → blocking-LLM гасил бы реальные лиды; moto-sale/car-sale теперь минуют Pass 3. Отклонение от плана: 3 значения вместо 2 — задокументировано в миграции. 8 тестов test_lead_direction.py.
- B5 (345ef41): мёртвый warmup удалён — skip_warmup=(cb_free>=1) был истинен всегда, кроме «все под баном»; рампа не работала с session-модели и сама выглядела бы как калибровка бота. OPERATIONS.md: Правило #11 переписано, чек-лист §5 обновлён.
Итог сьюта: 196 passed / 3 pre-existing failed (тот же кластер моков из baseline 0.3) / 1 hanging deselected. Тест-окружение: одноразовые lh_test_db (5433) + lh_test_redis (6380), снесены. Деплой фазы НЕ выполнялся — офлайн-верификация по git-стратегии.
⚠️ К живому переключению: миграцию lead_direction01 применить ДО старта нового worker — иначе SELECT Segment упадёт на отсутствующей колонке (worker не стартует, громкий отказ).
Уроки: полная цепочка Alembic-миграций с нуля не воспроизводится (idx_user_sub_lookup на несуществующей таблице) — pre-existing техдолг, обходится stamp cat_hierarchy_v1; данные о направлении лида в БД сразу вскрыли ошибку хардкода (housing-buy), которую никто не видел в промпте.

**10.07.2026 — Аудит: Фаза C завершена целиком (ветка audit/fable-fixes, прод НЕ трогался).**
Все 5 задач закрыты, по коммиту на задачу:
- C1 (38a142b): eval-конвейер — tools/eval_matching.py (read-only к прод-БД/Redis, одна команда): корпус llm_decisions(1000)+feedback(259)+unmatched(500), по-сегментно pass1/stop-блок/pass3-блок/reality-блок/LLM-вердикты/precision по 👍👎, шаблон ручной разметки 100 unmatched. Инструментированная классификация сверяется assert'ом с classify_message на каждом сообщении. Первый отчёт docs/eval/report_2026-07-10.md: precision по feedback 17% (44👍/215👎). Правило: изменения правил/промпта — только с прогоном eval.
- C2 (338c98e): окно близости multi-word матчинга — все слова demand-фразы в окне N токенов (finditer+bisect по токен-оффсетам, two-pointer); fuzzy — тоже в окне; stop-фразы и short anchors НЕ ограничены. ⚠️ N=20 вместо плановых 12 — data-driven: окно 12 теряло 2 👍-лида (разлёт 15-17 токенов) и живые заявки; окно 20 — lost 80 / gained 0 / liked_lost 0 на корпусе 1541 (docs/eval/c2_diff.md). Асимметрия цены: rules до blocking-LLM — потерянный лид невосполним, возвращённый спам режет LLM. KEYWORD_MATCH_WINDOW в config.
- C3 (797fc95): reality-фильтр на word-boundary — _match_keyword вместо substring («спа» больше не подтверждается «спасибо»); сегмент без domain-слов — pass-through + logger.debug. Корпус: +131 ложное подтверждение устранено, 0 задетых 👍-лидов.
- C4 (a94ae31): полный батч на инкрементальном опросе → warning + Redis `stats:full_batch:{chat}` (TTL 30д); cursor==0 — тишина (ожидаемо). Пагинации нет — решение DECISIONS #78, пересмотр по данным счётчика. Попутно закрыт техдолг №2: немой except в _fetch_all_since → logger.warning.
- C5 (a24c493): rebuild_subscription_cache — 4 плоских SELECT + join в памяти вместо 3×N, пустые пользователи не кэшируются, формат не изменён; _dispatch — сегментные словари in-memory (из seg_rows _load_keywords) + мемо гео канала (сброс при reload); на тёплых кэшах 0 DB-запросов на матч.
Итог сьюта: 222 passed / 3 pre-existing failed (кластер моков из baseline 0.3) / 1 hanging deselected. +26 новых тестов. Контейнеры lh_test_db/lh_test_redis снесены. Деплой фазы НЕ выполнялся — офлайн-верификация по git-стратегии.
Уроки: план задавал N=12, но обязательный eval-прогон поймал потерю 👍-лидов — data-driven выбор N=20 и есть смысл C1; окно построено на инвариант «_lemmatize_text сохраняет число токенов» — при смене лемматизатора проверить.

**10.07.2026 — Аудит: Фаза D завершена целиком — ВЕСЬ ПЛАН fable_audit.md ЗАКРЫТ (ветка audit/fable-fixes, прод НЕ трогался).**
Все 3 задачи закрыты, по коммиту на задачу:
- D1 (0e78034): честный Free-пейволл (DECISIONS #79) — в Free-уведомлении ни одной ссылки: чат plain-текстом, отправитель скрыт полностью, кнопки «💬 Чат» нет. До этого Free-формат содержал и ссылку на сообщение, и ссылку на отправителя — «контакты скрыты» было номинальным. Paid/Trial-формат не изменён. 4 теста в test_sender.py.
- D2 (7d19e40): счётчик stats:daily:{uid}:{date}:matched — _dispatch инкрементит при постановке в очередь (раньше писался только sent — EOD/недельные отчёты Free были бы пусты). Ветка plan=='trial' НЕ удалена — вывод аудита о «мёртвой ветке» опровергнут в A4 (trial реально пишется в users.plan), план скорректирован.
- D3 (db7ac87): актуализация документации — CLAUDE.md §2 (поток данных без несуществующего find_interested_users), §5а (фактический классификатор после аудита: B2/C2/A2/B4/C3/C1), §5б (реальные Redis-ключи, class:cache не существует), §8 шапка, §9 (+#78/79/80, отмена #65), §10; DECISIONS #80 (поллинг без вступления vs event-push — трейд-офф задокументирован).
Итог сьюта: 231 passed / 3 pre-existing failed (кластер моков из baseline 0.3) / 1 hanging deselected. Контейнеры lh_test_db/lh_test_redis снесены. Деплой фазы НЕ выполнялся — офлайн-верификация по git-стратегии.
Аудит завершён: фазы 0/A/B/C/D — 22 задачи, все [x] в fable_audit.md. Живое переключение прода на ветку — отдельное решение владельца. ⚠️ При переключении: миграцию lead_direction01 накатить ДО старта worker.

**12.07.2026 — Анализ проекта + план качества ядра + большая уборка документации.**
Глубокий анализ прода (read-only): precision 17% (44 из 259 оценок, 3 пользователя); ~60% Pass1-объёма — три buy-сегмента (moto-purchase/car-purchase/moto-sale) с precision ~0% («продам/продаю» как demand, коммит 1abf5fe); Redis AOF в проде фактически ВЫКЛЮЧЕН (вопреки записи 0.6 — потерян при перезаписи compose); таблица keywords пуста (Вариант Б не используется); LLM 13,4M токенов/нед; админка на 0.0.0.0:17421 без TLS; SENTRY_DSN пуст; .env 664.
Создан `fable_core_plan.md`: Ф0 (деплой audit/fable-fixes + AOF + baseline v2) → ФА (голова FP, fail-open метрика, карантин сегментов) → ФB (петля фидбека, разметка recall, кэш LLM-вердиктов, латентность) → ФC (event-push/скоринг/дистилляция за gate). Цель precision ≥50% при liked_lost=0.
Уборка: session log вынесен в docs/SESSION_LOG.md (правило §0 обновлено); LEADHUNTER_FIX_PLAN, AGENT_WORKFLOW, CLAUDE-2, ROADMAP, SEED, DISCOVERY, segment_seed, SEGMENT_KEYWORDS_NEW, docs/audit_* (~20 md) + 27 .txt → docs/archive/2026-07/; удалены PROMPT_task_0.5.md, no_city_channels.csv, ChannelsPage.tsx.bak; check_cursors.py → tools/. CLAUDE.md 1194→641 строк + актуализация фактов (worker 1G, handlers, content_hash, 80 решений, меню 4 кнопки). USERFLOW.md — блок актуализации в шапке.
Коммиты: 2c1fbd5 (архив), f82e6e0 (session log + CLAUDE.md), 616ac58 (core-план). Код приложения НЕ трогался, прод НЕ трогался.

**12.07.2026 09:05 — 🚀 ЖИВОЕ ПЕРЕКЛЮЧЕНИЕ ПРОДА НА КОД АУДИТА (fable_core_plan 0.1 закрыта).**
Окно 07:50–09:00 MSK по docs/runlist_switch_2026-07-12.md. Бэкапы (pg_dump 2.4MB + сессии gpg, самопроверены) → стоп worker/bot/admin → Redis переехал на AOF+том (1029 ключей; фолбэк: Redis 7 с appendonly=yes игнорирует dump.rdb — восстановлено через temp-контейнер + CONFIG SET appendonly yes) → build → миграция lead_direction01 (65 demand/4 buy/2 supply) → up. Верификация: CB clear оба аккаунта, движок B2 скомпилирован (3317 kw/71 сегм.), курсоры двигаются, LLM 15 решений, 2 уведомления доставлены, FloodWait/Traceback 0. Merge audit/fable-fixes → main (ff 5ae3f67..75e931e), тег audit-fixes-live, запушено.
ИНЦИДЕНТ (без последствий): docker compose up -d redis пересоздал зависимые сервисы → worker 14 рестартов crash-loop на отсутствующей колонке (~6 мин, до миграции). FloodWait 0. Урок: --no-deps обязателен. Второй урок: предсказанная «мина bind-mount» (checkout ветки при живом проде) реально сработала бы на любом рестарте — переключение её обезвредило.
Отложено решением владельца: живой тест сценария Б/HTML/Free (тест-канал my_leadalert_test_xxx = watched id=144, keyword «фотограф» user 152 загружен в поллер — довести позже), Sentry (напомнить), TLS админки (оставлена публичной).
Найдено: 85 bulk-каналов (insert_sofi_groups) на владельце → лимит 85/60, добавление каналов через бота заблокировано; детекция приватности — заглушка; экран каналов кажет -100…-ID. Всё — в fable_core_plan «Найдено попутно».

**12.07.2026 09:40 — Задача 0.2: precision-метрика очищена от legacy-slug'ов (ветка core/quality-v2).**
eval_matching.py: фидбек, все сегменты которого отсутствуют в текущей segments, — в справочную legacy-корзину (вне общего precision, вне по-сегментной таблицы). current_slugs — свежий SELECT slug FROM segments в main. Приёмка: 259 оценок = 77 актуальных + 182 legacy (сумма бьётся); строки crypto/logistics/education и пр. из таблицы исчезли. НАХОДКА: честный precision актуального каталога = 13% (10👍/67👎) — хуже смешанных 17% (legacy-эпоха давала 19%). Реальный baseline фазы A — 13%, задача A1 (голова FP moto/car) подтверждена и этой разрезкой.

**12.07.2026 11:30 — Задача A1: гейт одиночных слов в buy/supply-сегментах (ветка core/quality-v2).**
Правило расширено против плана (data-driven): гейтируются все одиночные слова, не только глаголы — главный шум давали 30+ синонимов-одиночек («байк», «хонда»), каждый из которых триггерил Pass 1 сам. Новая семантика: одиночный глагол — только рядом с domain-словом (match_near, окно C2); одиночное не-глагольное слово не триггерит; multi-word и сегменты без словаря — как раньше. Общий _segment_pass1 для классификатора и eval-зеркала. Eval-diff: голова 1067→172 (16% при приёмке ≤40%), gained 0, liked_lost 0 фактически (4 аренды-лида матчились в неправильные сегменты, все живы — 3 в правильном scooter-rental). 11 тестов, сьют 242/3/1, 0 регрессий. Урок: «правка по букве плана» дала бы жалкий эффект — 2 глагола из 300+ ключей; проверка данных перед реализацией окупилась.

**12.07.2026 12:00 — Задача A2: метрика + алерт fail-open LLM (ветка core/quality-v2).**
Одна точка записи в _flush_pending_matches (все fail-open пути ставят LLMResult.error): почасовые stats:llm:{total,fail_open}:{YYYY-MM-DDTHH}, TTL 48ч. _check_llm_fail_open в alert loop: <20 валидаций/час — молчит, >20% WARNING, >50% CRITICAL. 7 тестов (fakeredis + мок llm_validator.enabled). Деградация единственного precision-барьера больше не невидима.

**12.07.2026 13:00 — Задача A3: карантин сегментов + отчёт 👎-rate. ФАЗА A ЗАКРЫТА ЦЕЛИКОМ (ветка core/quality-v2).**
Миграция quarantine01 (обратимая, репетиция на копии бэкапа), Segment.is_quarantined; generic CRUD подхватил колонку без правок API. Поллер: _quarantined_slugs в _set_seg_maps, фильтр после _log_llm_decision и до _dispatch (датасет копится, раздача стоит), keyword_only не задет. GET /api/stats/segment-feedback (LATERAL, legacy отсечён) — живые кандидаты: design 0/16, repair 1/9, massage 0/8, fitness 0/7. Фронт: колонки 👍/👎 и карантин-toggle с подсказкой «кандидат», статика пересобрана. 6 тестов; сьют 255/3/1. Урок: застоявшаяся схема тест-контейнера дала ложные 8 failed — контейнеры пересоздавать после изменения моделей.
Фаза A: A1 (голова FP → 16%), A2 (fail-open метрика+алерт), A3 (карантин). Деплой фазы — батчем по OPERATIONS.md, миграцию quarantine01 накатить до старта worker.

**12.07.2026 14:00 — Phase-review фазы A (code-review, 8 углов): 10 findings, 6 исправлено (ветка core/quality-v2).**
Исправлено: (1) карантин глушил личные keywords — теперь _matches_personal_keyword спасает матч в keyword-ветку _dispatch; (2) КОРНЕВОЕ: происхождение keyword вместо POS-эвристики (CompiledKeyword.from_synonym) — pymorphy тегает «дукати»/«хендай» глаголами (подтверждено на БД) и они самоподтверждались через match_near; synonym-одиночки теперь никогда не триггерят Pass 1, demand-существительные не гейтируются, без pymorphy — деградация к старому поведению; (3) знаменатель fail-open — счётчики в validate_batch только по реально ходившим к LLM; (4) алерт только в llm_mode=blocking; (5) фолбэк на предыдущий час при <20 валидаций; (6) мусорный .claude/*.tmp из git + .gitignore. Не чинено (задокументировано): domain-слова выводятся 3 способами (classifier/reality/eval), SQL stats дублирует eval-агрегацию, pre-tag boost обходит A1-гейт (pre-existing). Перегон eval-diff: голова 16%, gained 0, liked_lost 0 по доставляемости. Сьют 262/3/1. Уроки: происхождение данных надёжнее морфологической эвристики; git add -A затащил tmp-файл — не использовать с грязным .claude.

**12.07.2026 14:40 — Задача B5: кэш LLM-вердиктов по тексту (ветка core/quality-v2).**
_llm_cache_key = sha256 нормализованного текста БЕЗ chat_username (существующий content_hash per-chat — не подошёл, отклонение задокументировано). validate_batch: mget → хиты from_cache=True (llm_mode='cache' в датасете), промахи → LLM → setex не-fail-open, TTL 24ч; Redis-ошибки = промах. Кэш-хиты вне знаменателя A2. Счётчик stats:llm:cache_hit:{date}. 6 тестов. Ожидание: заметный срез 13,4M токенов/нед (репосты объявлений в N чатов).

**12.07.2026 15:10 — Задача B6: латентность доставки как метрика (ветка core/quality-v2).**
msg_ts из Telegram-сообщения прокинут PendingMatch → _dispatch → payload → sender; бакеты stats:latency:{date}:{lt5m/lt30m/lt2h/ge2h}, TTL 14д; карточка на админ-дашборде (latency_today в /api/stats/dashboard). Данные — gate для C1 (event-push). 6 тестов; сьют 273/3/1.

**12.07.2026 15:40 — Задача B1: кандидаты в стоп-слова из 👎 (ветка core/quality-v2).**
GET /api/stats/stop-candidates: n-граммы 1-3 из 215 👎-текстов, документная частота, отсев существующих стопов/FUZZY_NOISE/маск-токенов. Секция-карточка на /stop-words. Живые кандидаты уже видны: «доставка», «оплата», «usdt», «онлайн», «рубли» — реклама обменников и доставки, главный источник 👎. Добавление стоп-слов — ручное (по плану). Сьют 273/3/1.

**12.07.2026 16:10 — Задачи B4 (done) + B3 (шаблон готов, ждёт владельца) — ветка core/quality-v2.**
B4 (docs/eval/reality_audit.md): фильтр НЕ душит — блоки по 3000 свежих unmatched малочисленны и мусорны, «delivery 32/32» из C1 не воспроизводится после A1. ГЛАВНОЕ: 49/71 сегментов (70%) без synonym-словаря — reality-фильтр и A1-гейт для них не работают (housing-rent 298/30д, currency-exchange 296, design 288...). Доливка seed/synonyms_passthrough_b4.sql подготовлена — применять СТРОГО после деплоя origin-split (на старом коде синонимы = demand-триггеры → рост спама). B3: шаблон docs/eval/recall_template_2026-07-12.md (100 строк) — заполняет владелец.
Фаза B: B1/B5/B6/B4 done, B3 ждёт разметки, B2 (few-shot в промпт) — отдельный заход (живой DeepSeek + обязательный батч-тест 37/40 + eval).

**12.07.2026 14:15 — 🚀 ДЕПЛОЙ ФАЗ A+B (fable_core_plan) — окно 13:54–14:10 MSK, без инцидентов.**
Бэкапы (pre_ab: pg_dump 2.4MB + сессии) → стоп worker/bot/admin → build → alembic upgrade quarantine01 (71/71 false) → up → seed/synonyms_passthrough_b4.sql (INSERT 44) → reload подхватил: 3361 keywords / 428 domain words (+44). Верификация: пул 2/2, CB clear, 1 personal keyword, тест-канал в Cold (78), FloodWait 0, Traceback 0, admin 200, llm_decisions пишутся. Merge core/quality-v2 → main (ff 82cfec1..5af39fe), тег core-phase-ab-live. В проде теперь: гейт одиночных слов (голова FP 16%), карантин сегментов, fail-open метрика+алерт, кэш LLM-вердиктов, латентность на дашборде, стоп-кандидаты из 👎, словари 6 pass-through сегментов.
Дальше: B2 (few-shot) отдельным заходом; B3 ждёт разметки владельца; снапшот латентности ~15.07; baseline v2 (0.3) ~19-22.07.

**12.07.2026 14:35 — fix: экран «Мои каналы» показывает названия вместо -100…-ID.**
Причина: названия ВСЕГДА были в watched_chats.title (85/86 заполнены bulk-вставкой insert_sofi_groups), но show_channels рендерил chat_username. Не регрессия деплоя — дисплей-баг с 04.07. Фикс: _channel_label (title приоритетнее; «title (@username)» для публичных; «группа -100…» только без title), список ограничен 60 строками (4096-лимит Telegram — названия длиннее id), кнопки удаления тоже с названиями. 5 тестов. Рестарт только bot-контейнера (Bot API, MTProto не задет).

**12.07.2026 15:00 — Гео-аудит каталога: инварианты чисты, 13 каналов исправлено (DB-only, по прецеденту retag 05.07).**
Проверки: (1) SQL-инварианты город↔страна (скаляр + M2M), (2) текстовый анализ «город в названии vs привязка» по всем 1851 активным, (3) fuzzy-подозреваемые техдолга №4 — все 4 уже ignored, чисто. Исправлено: @kutaisi_ads_baraholka_chat Испания→Грузия (единственный живой критикал); @shambary_agency_chat (DUBAI MEDIA) Барселона/Испания→Дубай/ОАЭ; @apartmentsfromme +Милан (M2M); @Rusvipeskort +Анкара+Анталья (M2M); 8 орфанов привязаны по названию (5×Дахаб, 2×Шарм — один мультисити с Дахабом, 1×Пхи-Пхи); @chatae_paphosr_singlmf (2 участника, мёртв) → ignored; 2 ignored-канала Кипра получили country (гигиена). Итог: конфликты 0/0, «город без страны» 0, орфаны 526→518. Единственный оставшийся «конфликт» — @alexandria_residence_chat: ложный (Alexandria — название ЖК в Сиде/Турция, не Египет), не тронут. Привязки подхватятся dispatch'ем на 5-мин reload (C5 memo reset).

**12.07.2026 15:30 — Тест-пользователь приведён к «только Дананг, все направления» (DB-only).**
Диагноз: подписки БЫЛИ правильными (69 × Вьетнам × mode=cities × Дананг) — «много стран» в боте давали 85 bulk watched-каналов insert_sofi_groups (TravelAsk Испания/Казахстан/Грузия/Китай + Кипр): висели в «Мои каналы», поллились Cold-тиром, слали бы «фотографа» из любой страны по личному keyword. Сделано: 85 каналов удалены из watched (restore-SQL: backups/watched_bulk_152_restore.sql; тестовый my_leadalert_test_xxx оставлен), добавлены 2 недостающих сегмента (moto-sale, car-sale) → 71/71 × Дананг, кэш подписок инвалидирован. ПОПУТНО ЗАКРЫТ блокер «лимит 85/60»: бот снова позволяет владельцу добавлять каналы (1/60). Cold-тир похудеет на 84 канала на часовом ребилде — экономия бюджета API.

**13.07.2026 07:00 — Гео-тиеринг поллера по фактическим подпискам + фикс проглоченного BudgetExceeded (деплой).**
Разбор ночных алертов «суточный бюджет исчерпан (11812/10000)»: оба аккаунта 12.07 превысили бюджет (13070/11683), спрос ~25k req/день при 2×10k. Корень: hot-тир строился по СТРАНЕ подписки — Дананг-подписчик включал все 205 каналов Вьетнама, из них ~120 (чужие города) не могли доставить никому. Второй дефект: BudgetExceeded перехватывался generic `except Exception` в `_poll_one` → задуманный break батча был мёртвым кодом, поллер вхолостую молотил Redis INCR + алерт-спам (рост счётчика после лимита — это заблокированные попытки, НЕ реальные запросы; риска бана не было). Фикс (087b9be): (1) `_get_active_geo()` вместо `_get_active_countries()` — mode='all' → вся страна hot; только city-подписки → каналы городов + общестрановые (без города), чужие города → parked; правило зеркалит гео-фильтр `_dispatch` (включая «mode='cities' без городов = вся страна»); (2) `except BudgetExceeded: raise` перед generic except. Тесты: 9 новых в test_tier_geo.py, все зелёные; 6 падений test_poller_fixes — pre-existing (нет тест-Redis). Верификация: SQL-симуляция предсказала hot=85 (40 общестрановых + 45 Дананг), после деплоя лог подтвердил «85 hot, 1765 parked», циклы «42 ok, 0 errors», 0 FloodWait за 10 мин. Экономия −59% бюджета API. Попутные находки: гео-аудит каталога чист (0 нарушений инвариантов), но 516 активных каналов без города (общестрановые по дизайну — доставляют city-подписчикам); @vietnam_jobs и @danang_movers падают ValueError (битые username) — кандидаты в is_ignored. Урок: тиеринг обязан повторять правило доставки, иначе бюджет горит на недоставляемое.

**13.07.2026 07:40 — Черновик гео-разметки 518 каналов без города (docs/geo_markup_draft_2026-07-13.md, НЕ применён).**
Ручная разметка всех активных каналов каталога без города по username+названию. Итог: 21 — привязка к существующим городам (SQL готов в §2: БА, Батуми, Каир, Шарм, Дахаб, Фукуок, Бали/Чангу, Убуд, Абу-Даби, Фуджейра, Бар, Муйне/Фантьет и др.); 107 — мусор → is_ignored (SQL в §3: серия «страны мира» в ОАЭ ×24, московские ЖК в Испании ×6, оптовые доски РФ в Юж. Корее ×15, аниме/гемблинг во Вьетнаме и пр.); 3 — смена страны Кипр→Северный Кипр (caesar_resort_chat, kiriniya, cyprusfood); 49 — города отсутствуют в справочнике (Китай ×14, Шри-Ланка ×14, Египет ×6, Индия ×5; у Юж. Кореи нет НИ ОДНОГО города, даже Сеула); 5 пограничных; 333 — легитимно общестрановые. Ничего не применено — ждёт решения владельца по §2/§3/§4 (SQL готов) и §5 (добавлять ли города в справочник → влияет на FSM-воронку).

**13.07.2026 08:20 — Ignore 107 мусорных каналов ПРИМЕНЁН + анализ недостающих городов + аудит приватных watched.**
(1) Приватные чаты с ручных подписок @mill_sofi/@iraluxme: в watched_chats только 2 записи — тестовый my_leadalert_test_xxx и приватный «Дананг TravelAsk» (-1002046178126), ОБА без country_id (гео не распределено); 85 TravelAsk-чатов сняты 12.07 и тоже были без гео (schema watched_chats города не имеет, только country_id). Рекомендация: выставить country_id=Вьетнам данангскому чату → попадёт в hot по новому тирингу (сейчас Cold 2.5ч). (2) 107 мусорных → is_ignored=true (бэкап-откат: backups/geo_ignore_107_restore_2026-07-13.sql; все 107 до апдейта были is_ignored=false). Бонус: 14 вьетнамских из них уйдут из hot на ближайшем ребилде (85→71). Урок: ручной список id разошёлся с классификатором в 2 позициях — брать списки только генерацией из источника. (3) Счётчики участников 49 каналов недостающих городов сняты через t.me веб-превью (curl, БЕЗ Telegram API — нулевой риск): Шри-Ланка — главный кандидат (12 городов, ~20,5K участников, Велигама 5578); Шэньчжэнь 1651, Чэнду 994, Сахл-Хашиш 1037 (390 онлайн), Ансан 1085; Сеул/Пусан/Гуанчжоу/Мумбаи — ни одного канала в каталоге вообще; sumatra_ru не существует. Таблица → docs/geo_markup_draft_2026-07-13.md §8.

**13.07.2026 09:00 — 84 приватных TravelAsk-чата распределены по странам/городам и внесены в каталог (ПРИМЕНЕНО).**
Запрос владельца (повторный): гео-распределение закрытых чатов с ручных подписок @mill_sofi/@iraluxme. Причина «нераспределённости»: 12.07 их сняли с watched целиком (лимит 85/60 + гео-дыра Варианта Б), а watched_chats города не имеет. Решение БЕЗ кода: приватные -100…-ID внесены в catalog_channels с гео из названий (84 канала: все со страной, 59 с городом) — классификация глобальна (channel_segments лишь буст по названию, проверено по poller.py:515), гео-фильтр _dispatch и гео-тиеринг работают для каталожных записей, _resolve_entity уже умеет -100 (аккаунт-участник). Создано is_active=false (вне FSM до активации): 5 стран (Израиль, Германия, Гонконг, Катар, Камбоджа), 18 городов (Гуанчжоу, Мумбаи, Бентота, Тель-Авив, Берлин…). watched id145 (Дананг) получил country_id=1. В hot добавятся 2 канала (Дананг + Вьетнам TravelAsk), остальные 82 спят до подписчиков. Грабли: cities.slug в проде БЕЗ unique (ON CONFLICT не работает — через NOT EXISTS), catalog_channels.is_verified NOT NULL без default. Откат: backups/private_chats_84_rollback_2026-07-13.sql. Доки: geo_markup_draft §9. Мониторинг: ближайший часовой ребилд тиров должен показать hot=73 (71+2); ValueError по -100 в логах = аккаунт не участник чата.

**13.07.2026 09:40 — Привязка приватных каналов к аккаунту-участнику (миграция + деплой).**
Владелец сообщил: вся сеть TravelAsk приватная, выделенный агент — @mill_sofi (account 2; @iraluxme = account 1). _distribute раздавал каналы слепым round-robin → половина -100…-чатов уходила бы аккаунту 1 без членства (ValueError каждый цикл). Сделано: миграция channel_account01 (catalog_channels.userbot_account_id, nullable, downgrade есть), _get_all_channels пробрасывает account_id (catalog + watched.userbot_account_id), _distribute пиннит закреплённые каналы к своему аккаунту (недоступен → канал пропускает цикл, НЕ мигрирует), 84 чата закреплены за account 2. +3 теста (12 в test_tier_geo.py). Деплой по регламенту: pg_dump (backups/pre_channel_account01_2026-07-13.sql.gz) → stop worker → build → alembic upgrade → UPDATE → up. После старта: «Tiers rebuilt: 73 hot» (71+2 TravelAsk), 0 FloodWait. Факт про аккаунты сохранён в память проекта (userbot-accounts.md).

**13.07.2026 10:30 — Тарифы v2: решение владельца + полный план перехода (fable_tariff_plan.md, Fable).**
Стратегическая сессия (роль: маркетолог/директор/аналитик), кода не писали. Решение владельца: отказ от дневного лимита уведомлений (метрика ценности = широта покрытия: направления × гео — совпадает с себестоимостью поллинга/LLM; лимит уведомлений наказывал за успех и не защищал издержки); линейка Старт $9 (1 направление, 1 страна или ≤3 городов, 10 слов) / Профи $19 (5 направлений, ≤5 стран, regex, статистика) / Бизнес $39 (без лимитов, кап 60, полная статистика + CSV); Free = широта Старта с безлимитом уведомлений, контакты скрыты; скидки 3м −10% / год −20%; grandfathering платящих. Создан `fable_tariff_plan.md` — фазы T0–T6 с чекбоксами (конфиг → бэкенд матрицы лимитов и гео-гейты FSM → оплата → все экраны → контекстные пейволлы/воронки → статистика/CSV/digest → миграция+деплой+мониторинг), реестр экрана→файла (инвентаризация кода снята по факту), черновики ключевых текстов, риски. Исполнитель — Sonnet/Opus по этому файлу. Найдено при инвентаризации: CSV-экспорт обещан в текстах триала, но НЕ реализован; экран /plan существует в двух копиях (plan.py + start.py:442) с разными текстами; гео сейчас не ограничено ни на одном тарифе. DECISIONS #81 и правка таблицы CLAUDE.md §1 — задача T0.1 исполнителя (единая точка входа в работы).

**13.07.2026 11:15 — Тарифы v2, ФАЗА T0 закрыта (ветка feature/tariffs-v2, Opus). Прод НЕ трогался.**
Начата разработка по fable_tariff_plan.md. Ветка feature/tariffs-v2 от main.
- **T0.1** (eaab538): DECISIONS #81 (тарифы v2, отказ от дневного лимита); #31/#32/#67 помечены как отменённые лимитной частью со ссылкой на #81; таблица тарифов CLAUDE.md §1 → v2 (Старт $9 / Профи $19 / Бизнес $39, безлимит уведомлений); шапка USERFLOW.md о переходе (экраны 6/14/16/17/18/19 устарели, переписываются в T3).
- **T0.2** (2ced856): config.py — тариф start ($9), цены pro/business дефолты $19/$39, лимиты max_*_start, гео-лимиты (max_countries/cities_*), pro segments=5/channels=10. `notifications_per_day_*` НЕ удалены (осознанное отклонение: ещё читаются sender/end_of_day; удаление — в T4.2 с последним использованием; §0 «проект запускается после каждого шага»). .env.example синхронизирован. Тест tests/test_tariffs_v2_config.py (4 assert). ⚠️ Прод-.env переопределяет: сейчас в проде pro=$7, business=$15 — обновится в T6.3, grandfathering (T6.1) считать от $7/$15.
- **T0.3** (см. коммит ниже): верификация инвентаризации §2. Найдено 5 расхождений: (1) рефералка и все misc-callbacks — в discover.py, НЕ start.py; (2) счётчик уведомлений в главном меню захардкожен «0/50» (не живой — баг); (3) reminders.py шлёт напоминания/периодику plain-текстом БЕЗ кнопок, Free ошибочно назван «10/день»; (4) геттеры business/trial читают business_hidden_cap_*=60, не max_*_pro; (5) мелкий дрейф строк. §2 плана и «Найдено попутно» обновлены. Отклонение от регламента: session log за фазу T0 одной записью (не по каждой из 3 микрозадач) — они образуют один связный шаг конфигурации.
Далее: ФАЗА T1 (бэкенд матрицы лимитов, снятие дневного лимита, гео-гейты FSM). Тесты не гонялись сверх нового (T0 — только docs+config); полный сьют — на T1.

**13.07.2026 12:30 — Тарифы v2, ФАЗА T1 закрыта (бэкенд матрицы лимитов). Ветка feature/tariffs-v2, прод НЕ трогался.**
- **T1.1** (df645ab): crud.py — единая `_plan_limits(plan)` (5 планов × 5 лимитов) вместо if/elif-геттеров; +get_max_countries/cities_per_sub; неизвестный план→free (least privilege). Аудит start=платный: исправлены 3 точки (crud-геттеры, реферальный бонус plan.py:115, отображение срока start.py:244). PLANS += start (RU-имена Старт/Профи/Бизнес; EN-i18n имён → T3.1). Тесты матрицы (monkeypatch, независимы от .env) + settings-относительный test_catalog.
- **T1.2** (3ffdf0f): sender.py — удалён блок дневного лимита + _send_limit_warning; счётчик sent сохранён (статистика/EOD). subscription_cache.py — удалены check_daily_limit, LIMIT_REACHED_KEY. Free больше не гасится по 50/день. +2 теста. notifications_per_day остался только в config.py (устар.) + end_of_day.py (снос в T4.2).
- **T1.3** (44134f1): гео-лимиты в FSM-воронке. Чистые предикаты cities/countries_within_limit; enforcement в 3 точках (выбор страны, переключение города, финальная подписка). ВАЖНО: count_user_subscriptions считает строки (сегмент×страна), distinct-стран ≤ подписок ≤ max_seg → при числах v2 (страны=сегментам) лимит стран подчинён лимиту сегментов, реально биндит только город-на-подписку (start=3, pro/business=∞). Проверка стран оставлена по спецификации (защита при смене чисел). Интерим-alert, TODO T4.1 пейволл. +8 тестов.
- **T1.4** (см. ниже): верификация start→Paid-формат (is_free=plan==free, кода менять не нужно; start добавлен в параметризацию paid-тестов). НАЙДЕН+ИСПРАВЛЕН пред­существующий баг: _activate_by_msg (plan.py) не инвалидировал кэш подписок при оплате → оплативший до 1ч видел Free-формат; добавлен invalidate_all_subscription_caches (касается всех апгрейдов, не только start).
Тесты в изолированных контейнерах lh_test_db(5433)/lh_test_redis(6380): **312 passed**, 4 пред­существующих poller-фейла (test_poller_fixes.py — async-сигнатура _should_poll_tier, poller не трогался), 1 deselected. Тег tariffs-T1-done. Далее — T2 (оплата: 3 тарифа в платёжном потоке, экран ошибки оплаты). Контейнеры сняты после прогона.

**13.07.2026 13:15 — Тарифы v2, ФАЗА T2 закрыта (оплата). Ветка feature/tariffs-v2, прод НЕ трогался.**
- **T2.1** (a03de64): три тарифа в платёжном потоке. Механика start уже работала после T1.1 (Stars-провайдер оборачивает payload start:1m→sub:start:1m:uid; _activate_by_msg пишет любой план). Даунгрейд-политика задокументирована (оплата = план+срок от текущего момента). НАЙДЕНЫ+ИСПРАВЛЕНЫ 2 активных бага крипто-пути (CryptoBot-токен в проде задан): (1) _get_user_id вызывался, но не был определён → крипто-оплата падала NameError; определён helper (DB users.id, т.к. payment_checker активирует по User.id); (2) payment_checker._activate не инвалидировал кэш подписок → крипто-оплативший до 1ч видел Free-формат (Stars-путь закрыт в T1.4). Тест 9 комбинаций план×период ($9/24.3/86.4·$19/51.3/182.4·$39/105.3/374.4).
- **T2.2** (см. ниже): экран ошибки оплаты (давний долг USERFLOW). Тексты в locales RU+EN (впервые plan.py использует get_text — минимальный lang-fetch, не глобальный рефактор). on_pay_execute: провалы Stars/CryptoBot → edit_text экрана ошибки с [🔄 Повторить][💱 Другой способ][◀️ Назад]. payment_checker: expired-инвойс теперь уведомляет пользователя «Счёт истёк» + кнопка повтора (раньше молча удалялся). Тест клавиатуры+локалей.
Сьют в изолированных контейнерах: **320 passed**, 4 пред­существующих poller-фейла, 1 deselected. Тег tariffs-T2-done. Далее — T3 (экраны и тексты: карточки тарифов, счётчик меню, счётчики лимитов, триал/оффер, Free-CTA, USERFLOW v2). Контейнеры сняты.

**13.07.2026 14:30 — Тарифы v2, ФАЗА T3 закрыта (экраны и тексты). Ветка feature/tariffs-v2, прод НЕ трогался.**
Тон текстов согласован с владельцем: «короче и суше» (факты+буллеты, без эмоциональных подзаголовков).
- **T3.1** (e7887ee): единый build_plan_screen (menu:plan + /plan, дубль устранён) — 3 карточки тарифов, цены из settings, текущий план отмечен. RU+EN locales, plan_display_name (Старт/Профи/Бизнес).
- **T3.2** (63ee0d6): захардкоженный счётчик меню «0/50» → живой «📬 Заявок сегодня: {matched}» из stats:daily:matched; Free — пометка о скрытых контактах.
- **T3.3** (a1f3601): plan_display_name в счётчиках keywords/channels; гео-строка «Стран задействовано: X/N» на подписках. Кнопки пейволла при лимите — отложены на T4.1 (по плану).
- **T3.4** (910bc2d): экран триала (trial_days из settings + честная строка о скрытии контактов); апселл-блок free → кнопка «Открыть контакты — от $9». Оффер-после-истечения со статистикой — в T4.3.
- **T3.5** (f723453): Free-CTA уведомления «этому клиенту ответит кто-то другой» + кнопка «🎯 Открыть контакты — от $9/мес». Paid #79 не тронут.
- **T3.6** (b423917): welcome +«уведомления без лимита»; «О сервисе»: (Pro/Business)→«на платном тарифе» + CTA «Поиск клиентов». Устаревшие Pro/Business вне reminders убраны (reminders — T4).
- **T3.7**: USERFLOW.md — экран 6 (карточки v2), 17 (Free-CTA), удалён «Лимит достигнут»; источник истины по строкам — locales. Экраны 16/18/19 и §5 — в T4.
Сьют: **328 passed**, 4 пред­существующих poller-фейла, 1 deselected. Тег tariffs-T3-done. Далее — T4 (воронки продаж: контекстные пейволлы T4.1, End-of-day v2, trial-воронка, периодика/winback, годовой апселл, истечение). Контейнеры сняты.

**13.07.2026 16:00 — Тарифы v2, ФАЗА T4 закрыта (воронки продаж). Ветка feature/tariffs-v2, прод НЕ трогался.**
- **T4.1** (e4d97e3): единый компонент пейволла (build_paywall/paywall_text/next_plan_for) — маршрут апгрейда по триггеру+плану, кнопка pay_plan:<next>. Полноэкранный в keyword/channel-add; унифицированный alert в FSM-воронке (сохраняет выбор). RU+EN.
- **T4.2** (8feeccc): End-of-day v2 — только Free с заявками>0, «скрытые контакты» вместо лимита + кнопка апгрейда (RU+EN). notifications_per_day_* больше не читаются, но НЕ удалены из config (прод-.env + extra_forbidden → удаление в окне T6.3; блокер записан в T6.3).
- **T4.3** (264fc65): trial-воронка — новый trial_ending (за 2/1 дня). ФИКС бага: trial_expired 1/3/7 никогда не срабатывал (выборка plan==trial после даунгрейда) → теперь free+expiry. Кнопки в _maybe_send, цены из settings.
- **T4.4** (f0639fd): периодика CTA-подвал «Старт от $9» + кнопка; winback 14/28 кнопка «Поиск клиентов». grep $5/$15 по worker пуст.
- **T4.5** (9670063): годовой апселл — на 2-м подряд месячном платеже плана однократное предложение годовой (−20%), кнопка pay_period:plan:1y, флаг в Redis. Вызов из Stars и крипто путей.
- **T4.6** (см. ниже): subscription_ending (за 5 дней) + subscription_expired кнопки продления текущего плана; ОБЕ выборки теперь включают start. Статистика месяца отложена (инфра T5.1).
Сьют: **347 passed**, 4 пред­существующих poller-фейла, 1 deselected. Тег tariffs-T4-done.
**⚠️ НАЙДЕНО (вне скоупа, в «Найдено попутно» плана):** платные подписки при истечении НЕ даунгрейдятся в free (downgrade только для trial) → платный доступ фактически бессрочен после истечения. Требует отдельного решения владельца (billing/access-контроль).
Далее — T5 (платные фичи: статистика в боте, CSV-экспорт, digest-режим). Контейнеры сняты.

**13.07.2026 17:30 — Тарифы v2, ФАЗА T5 закрыта (платные фичи-дифференциаторы). Ветка feature/tariffs-v2, прод НЕ трогался.**
- **T5.1** (a2d19fb): статистика в боте (menu:stats + /stats). Тоталы по дням из sent_log (персистентно — matched/sent гаснут в полночь!); по-сегментная разбивка (Бизнес) — новый ключ stats:seg TTL 35д, минимальный INCR в _dispatch (гард по segment-матчу). Free/Старт → пейволл, Профи 7д, Бизнес/Trial 30д+сегменты.
- **T5.2** (d08dc0c): CSV-экспорт Бизнеса. РЕШЕНИЕ ВЛАДЕЛЬЦА — метаданные БЕЗ текста заявки. Миграция sentlog_meta01 (+chat/sender/segment/message_id nullable); mark_sent/sender заполняют. Хендлер menu:csv → документ 30д, гейт на Бизнес.
- **T5.3** (см. ниже): digest-режим. Миграция user_digest01 (users.digest_mode). instant/hourly/daily2, экран настроек. sender буферизует не-срочные (digest:{uid}), 🔥 мгновенно; app/worker/digest.py flush-loop (зарегистрирован в tasks.py) — каждый час, daily2 в 10/19. Не сжимаю в 1-3 сообщения (сохранение per-lead кнопок).
Сьют: **359 passed**, 4 пред­существующих poller-фейла, 1 deselected. Три миграции в ветке (channel_account01 → sentlog_meta01 → user_digest01); up/down проверены изолированно; alembic-с-нуля падает на ранней (техдолг №7, прод не с нуля). Тег tariffs-T5-done.
**Развилка CSV решена владельцем** (метаданные без текста). Далее — T6 (миграция/анонс/деплой) + ОТДЕЛЬНО T7 (реактивация платных — запрос владельца). ⚠️ Блокеры T6.3: (1) удалить NOTIFICATIONS_PER_DAY_* из прод-.env + поля config одновременно; (2) alembic upgrade head; (3) обновить цены прод-.env 9/19/39. Контейнеры сняты.

**13.07.2026 18:30 — Тарифы v2, ФАЗА T6 подготовлена (кроме живого деплоя). Ветка feature/tariffs-v2, прод НЕ трогался (только read-only SELECT).**
- **T6.1** (verified read-only): grandfathering N/A. В проде 4 пользователя, единственный платящий — user 152 (@BurnPM, business до 06.08) = сам владелец. Внешних клиентов нет; код сохраняет доступ 152 при деплое. Действий не требуется.
- **T6.2** (черновик): текст анонса «лимит отменён» + линейка + CTA готов в плане. Отправка — post-deploy, владельцем (не автономно).
- **T6.4** (0667269): инструментация пейволлов — record_paywall (fail-safe) + обёртка paywall_screen во всех 6 экранных пейволлах (INCR stats:paywall:{trigger}). Сырьё для мониторинга готово; сам 2-нед мониторинг — post-launch.
- **T6.3** (runbook): `docs/runbook_tariffs_v2_deploy.md` — точный пошаговый деплой (бэкап → стоп worker → merge → alembic upgrade head → config+.env синхронно [блокер notifications_per_day] → build → up --no-deps → инвалидация → верификация → откат). ⚠️ САМ ДЕПЛОЙ НЕ ВЫПОЛНЕН: запрещённые при работающем worker команды + правка прод-.env → исполняет владелец.
Сьют не гонялся заново (T6 — инструментация+доки; логические тесты пейволла/статы/csv зелёные 15 passed). Тег tariffs-T6-prep. **Разработка тарифов v2 в ветке ЗАВЕРШЕНА (T0–T6 подготовка). Осталось: живой деплой (владелец, по runbook) + T7 (реактивация платных, запрос владельца).**

**13.07.2026 19:30 — Тарифы v2, ФАЗА T7 закрыта (реактивация платных — запрос владельца). Ветка feature/tariffs-v2, прод НЕ трогался.**
- **T7.1**: даунгрейд платных при истечении. send_reminders: start/pro/business с истечением >grace(7д) → free + инвалидация кэша; подписки (ниша) СОХРАНЯЮТСЯ. Закрыта revenue-дыра (бессрочный доступ). Владелец 152 не затронут (не истёк).
- **T7.2**: воронка winback_missed (14/28 день) для бывших платящих. Разграничение платящий/триал через get_paid_subscriber_ids (payment_status='paid'). {missed} из sent_log (count_leads_since от plan_expires_at). Честная формулировка: free видит заявки, но контакты скрыты («прошло N заявок, ты их видел, но контакты были скрыты»). missed=0 → не слать.
- **T7.3**: record_paywall("winback") — метрика реактивации.
Сьют: **360 passed**, 4 пред­существующих poller-фейла. +тест winback. Коммит один (T7.1-T7.3 связаны). Тег tariffs-T7-done.
**ВСЯ РАЗРАБОТКА ТАРИФОВ v2 (T0–T7) ЗАВЕРШЕНА.** Осталось живьём: деплой владельцем по docs/runbook_tariffs_v2_deploy.md.

**13.07.2026 ~17:15 MSK — 🚀 ДЕПЛОЙ ТАРИФОВ v2 ВЫПОЛНЕН (с явной авторизацией владельца). Прод на tariffs-v2-live.**
Разработка T0–T7 завершена → живой деплой. Бэкапы: backups/pre_tariffs_v2_2026-07-13_1711.* (БД+сессии+.env).
Порядок (build ДО миграции — миграции в новом образе): стоп worker → merge→main+тег tariffs-v2-live → build bot/worker/admin → alembic upgrade head (channel_account01→sentlog_meta01→user_digest01, чисто) → правка прод-.env (цены 9/19/39, +start/гео-лимиты, MAX_SEGMENTS_PRO 3→5/CHANNELS 15→10, удалены NOTIFICATIONS_PER_DAY_*) → up -d --no-deps → инвалидация sub:by_chat.
ВЕРИФИКАЦИЯ: bot «Start polling» без ValidationError; worker «Pool initialized: 2 healthy»/«Tiers rebuilt: 73 hot»; **0 FloodWait/Traceback**; контейнер: PRICE_START=9/PRO=19/BUSINESS=39, NOTIFICATIONS_PER_DAY отсутствует. Постдеплой: удалены мёртвые поля notifications_per_day_* из config.py (безопасно — прод-.env уже без них).
⚠️ ОСТАЛОСЬ (решением владельца, НЕ автономно): (1) анонс через /broadcast (черновик — план T6.2); (2) живой тест оплаты Stars на минимальном инвойсе; (3) 2-нед мониторинг T6.4 (stats:paywall:*, конверсия, гео-стоимость). Прод-.env новый — commit main НЕ содержит секретов (.env в .gitignore).

**14.07.2026 — fix: в уведомлениях название чата вместо «-100…»-ID (приватные группы).**
Жалоба: Free/Paid-уведомления показывали `@-1002046178126` вместо названия. Причина: приватные группы (подписки @mill_sofi/@iraluxme в каталоге по внутреннему -100…-ID) хранят peer-ID в `chat_username`; фикс 12.07 (`_channel_label`) правил ТОЛЬКО экран «Мои каналы», а `sender.py` печатал `@{chat_username}` дословно. Фикс: живой `title` из entity протянут `PendingMatch.chat_title`→`_dispatch`→payload→sender; хелперы `_chat_label` (title приоритетнее, конвенция как на экране каналов) и `_chat_link` (приватные → корректный `t.me/c/<id>` вместо битого `t.me/-100…`). Применены в тексте, кнопке «💬 Чат» и digest (общий `_format_notification`). Free — название plain-текстом без ссылок (#79 сохранён). Файлы: sender.py, poller.py, llm_validator.py. +5 тестов, test_sender.py 23 passed. 6 фейлов test_poller_fixes + 4 ERROR test_variant_b — pre-existing (проверено `git stash`: те же на чистом main; async-сигнатура + socket/redis в песочнице), НЕ регрессия. ✅ ЗАДЕПЛОЕНО (авторизация владельца ~07:28 MSK): стоп worker → build worker → up -d --no-deps worker. Верификация (правило #8 OPERATIONS): «Pool initialized: 2 healthy», «Tiers rebuilt: 73 hot», «Sender started», Hot-loop 73 канала, первый цикл поллинга + LLM batch flush прошли — **0 FloodWait / 0 ERROR / 0 Traceback**. Правки в poller чисто аддитивные (проброс chat_title), rate-limiting/батчинг/circuit не тронуты. ⚠️ Изменения в рабочем дереве НЕ закоммичены (docker build берёт файлы из дерева; git commit — по запросу владельца).


**14.07.2026 — тарифная матрица v2.1 и актуализация user flow. Ветка `feature/codex-userflow-v2`, прод НЕ трогался.**
- Runtime-лимиты: Start — 1 направление / 1 страна / 1 город / 3 фразы; Pro — 3 направления / 3 страны / 9 distinct-городов суммарно / 20 фраз; Business — 12 направлений / 9 стран / города без отдельного лимита / 50 фраз / 50 каналов. Уведомления без лимита; Trial = Business.
- Гео-FSM теперь считает distinct-города по всем поискам пользователя; режим «по всей стране» доступен только Business/Trial и защищён повторной серверной проверкой.
- RU/EN-карточки тарифов, `.env.example`, `USERFLOW.md`, `codex_userflow.md`, `CLAUDE.md` и решение #82 синхронизированы с кодом. Локальный `.env` также актуализирован без изменения секретов.
- Точечный suite: 61 passed, 4 deselected. Полный baseline: 335 passed; 8 прежних failures и 27 errors связаны со старыми Redis-моками и недоступными Docker-hostname `db`/`redis`, новых тарифных регрессий нет.


**14.07.2026 — Userflow, ФАЗА U0 закрыта. Ветка `feature/codex-userflow-v2`, прод НЕ трогался.**
- Зафиксирован консервативный продуктовый контракт: термин «Мои поиски», trial только после первого созданного поиска, Free data contract, grace baseline 7 дней, запрет обещать возврат к скрытому лиду и неподтверждённые бонусы.
- Созданы `docs/userflow_u0_contract.md` и полный реестр пользовательских поверхностей `docs/userflow_screen_registry.md`; проведён promise-to-function audit и описан baseline аналитики без выдуманных конверсий.
- Подтверждены долги следующих фаз: trial сейчас стартует после языка; onboarding callbacks не входят в живой flow; sender/reminders и callback-alerts смешивают языки; inactivity использует `created_at`; return-to-lead отсутствует.
- Memory владельца: после завершения базового userflow напомнить про отдельный этап маркетинговых текстов/функционала, expiry-уведомлений, renewal и повторной подписки. Следующая фаза: U1 i18n/RU-EN parity.


**14.07.2026 — Userflow U1, промежуточный checkpoint U1.1/U1.3 (фаза НЕ закрыта).**
- Введён строгий locale contract: normalize_language с RU fallback+warning, неизвестные ключи вызывают ошибку, validate_locale_schema проверяет RU/EN keys и placeholders.
- Lead sender использует существующий `payload.lang`: локализованы заголовок, Free hidden-state, chat/sender labels и CTA-кнопки для RU/EN. Matching/polling/частота не менялись.
- Проверка: locale-schema-ok; sender/EOD/plan suite 29 passed.
- Дальше внутри U1: reminders/periodic, payment success, handlers/callback alerts, parity/snapshot tests. U2 не начинать до Gate U1.


**14.07.2026 — Userflow U1 checkpoint 2 (фаза НЕ закрыта).**
- Локализованы lifecycle reminders, periodic messages и их CTA по `User.language`; расписание и бизнес-логика не менялись. Grace copy теперь честно говорит о действующем льготном периоде.
- CryptoBot payment success переведён на locale `payment_success`; RU/EN schema и placeholders совпадают.
- Проверка worker-блока: 32 passed. Осталось U1: bot handlers/callback alerts, Stars success, финальные parity/snapshot tests и удаление неиспользуемого legacy hardcode.


**14.07.2026 — Userflow U1 checkpoint 3 (фаза НЕ закрыта).**
- Локализованы Stars payment success и feedback callback states по persisted language. Добавлены общие locale errors без показа технических ключей.
- Проверка sender/plan/paywall: 34 passed; locale schema valid.
- Осталось: period/payment method screens, catalog FSM, keywords, channels, settings/support callbacks, статический hardcode gate и snapshots.


**14.07.2026 — Userflow U1 checkpoint 4 (фаза НЕ закрыта).**
- Полностью локализована платежная воронка: период, строки расчёта, способ оплаты, CryptoBot invoice/unavailable, Stars/Crypto success и annual offer. Динамические plan/period values также на выбранном языке.
- Проверка объединённого payment/sender/trial блока: 41 passed; locale schema valid.
- Следующий блок U1: catalog FSM, keywords, channels, settings/support, hardcode gate и snapshots.


**14.07.2026 — Userflow U1 checkpoint 5 (фаза НЕ закрыта).**
- Catalog FSM локализован от входа до подтверждения: категории, услуги, страна, гео, города, CTA и validation errors используют RU/EN locale keys. Тарифные/гео проверки не менялись.
- Проверка: 15 geo/matrix tests passed; locale schema valid.
- Осталось в catalog: success first-search/regular и список/удаление поисков. Затем keywords/channels/settings/support и финальный hardcode gate.


**14.07.2026 — Userflow, ФАЗА U1 ЗАКРЫТА. Ветка `feature/codex-userflow-v2`, прод НЕ трогался.**
- Сквозной persisted language внедрён в sender, digest, reminders/periodic, Stars/Crypto payments, catalog FSM, keywords, channels, settings/support и feedback.
- Locale contract fail-fast: RU/EN keys и placeholders равны, unknown key = ошибка разработки, invalid language → RU + warning.
- Gate exceptions только нейтральные: provider names, emoji-only feedback, билингвальный первый language screen, dynamic user data, technical `/chatid`.
- Проверка: U1 suite 66 passed; imports/schema valid; diff check clean. Следующая фаза U2 analytics. Memory владельца про маркетинг/expiry/renewal после базового userflow сохраняется.
