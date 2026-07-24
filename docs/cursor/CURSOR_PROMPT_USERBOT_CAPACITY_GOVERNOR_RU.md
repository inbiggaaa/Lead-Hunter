# Prompt для Cursor Grok 5.4 — Userbot Capacity Governor

Скопируй весь текст ниже в новый Cursor Agent chat.

---

Ты работаешь как senior Python/Telegram infrastructure engineer в репозитории
LeadHunter. Реализуй Userbot Capacity Governor строго по утверждённым документам:

1. `AGENTS.md`
2. `CODING_STYLE.md`
3. `TESTING.md`
4. `OPERATIONS.md`, особенно §2, §5 и инцидент §7б
5. `docs/superpowers/specs/2026-07-24-userbot-capacity-governor-design.md`
6. `docs/superpowers/plans/2026-07-24-userbot-capacity-governor.md`

## Цель

Защитить userbot-аккаунты от повторных FloodWait, автоматически снижать и
плавно восстанавливать нагрузку, быстро доставлять лиды из активных чатов и
показывать в admin dashboard, когда требуется подключить новый аккаунт.

## Инцидент, который обязан закрыть дизайн

- Hot-контур вырос `198 → 753` чата.
- Account 2 получил `FloodWait 71565s`.
- Его budget достиг `9843/10000`.
- Текущий большой batch продолжал Telegram RPC после перехода аккаунта в PAUSED.
- После блокировки Account 2 оставшийся аккаунт получил весь Hot-контур.
- Natural circuit expiry может вернуть аккаунт сразу в полную нагрузку без
  корректного post-ban recovery.

Регрессионные тесты обязаны воспроизвести эти условия без живого Telegram.

## Жёсткие ограничения

1. Не трогай production.
2. Не запускай production Docker Compose, worker, миграции или Telegram sessions.
3. Не меняй `.env`, session-файлы и Redis production.
4. Не выполняй live Telegram-запросы.
5. Перед изменением `poller.py`, `rate_limiter.py` или `pool.py` полностью
   перечитай `OPERATIONS.md` §2 и §5.
6. Начни от актуального `origin/main`, а не от устаревшего локального main.
7. Сначала проверь `git status`; не уничтожай и не перезаписывай чужие изменения.
8. Не используй `git reset --hard`, `git checkout --`, force push и destructive
   Redis/DB-команды.
9. Никаких новых PostgreSQL-миграций в этой задаче.
10. Никакого нового worker/process/service.
11. Не добавляй ручные кнопки start/stop/reset/change-limit в dashboard.
12. Не отключай Telegram updates и не добавляй event-driven режим: только
    read-only вывод о целесообразности после измерения.
13. Не меняй matching, keywords, LLM, тарифы, платежи и user flow.
14. Не пытайся обходить Telegram limits через proxy rotation, device spoofing,
    параллельные auth sessions или сокращение FloodWait.
15. YAGNI: не добавляй ML, сложное самообучение, отдельное хранилище метрик,
    distributed queue или универсальный framework.

## Обязательная подготовка

Выполни только read-only аудит:

```bash
git fetch --all --prune
git status --short
git rev-parse HEAD
git rev-parse origin/main
git log --oneline --decorate -15
```

Если рабочая ветка не основана на актуальном `origin/main`, не начинай код.
Предложи безопасный способ перенести design/plan commits на новую ветку
`feature/userbot-capacity-governor` от `origin/main`, не затрагивая чужие
worktree/changes.

После этого прочитай целиком перечисленные документы и целевые файлы:

```text
app/config.py
app/userbot/rate_limiter.py
app/userbot/pool.py
app/userbot/poller.py
app/worker/notify_admin.py
app/worker/heartbeat.py
app/admin/api/stats.py
app/admin/api/__init__.py
admin-panel/src/pages/DashboardPage.tsx
scripts/watchdog.sh
tests/test_rate_limiter.py
tests/test_pool.py
tests/test_poller_fixes.py
tests/test_tier_geo.py
tests/test_watchdog_integrity.py
```

Сделай таблицу:

```text
Фаза | Создаваемые файлы | Изменяемые файлы | Риск | Проверка
```

Остановись и запроси подтверждение списка файлов перед написанием кода, как
требует `AGENTS.md`.

## Обязательный scope первой версии

Реализуй только пять блоков:

1. Учёт Telegram RPC и обработка всех FloodWait.
2. Governor: proactive throttle, cooldown и recovery.
3. Bounded slices, немедленный stop по state и простая адаптивная частота.
4. Capacity recommendation и Telegram alerts.
5. Компактный read-only dashboard.

## Safe defaults

```text
safe_daily_budget = 4000 RPC/account
reserve_ratio = 0.30
slice_size = 25 chats/account
soft_threshold = 70%
hard_threshold = 85%
stop_threshold = 95%
max_continuous_session = 45 minutes
stable_windows_before_power_up = 3
```

Все значения должны быть конфигурируемыми через `app/config.py` и
задокументированными в `.env.example`, но production env не меняй.
При forecast >95% аккаунт получает `THROTTLED` с power=0 до следующего UTC
дня. После сброса окна он возвращается только через 50% → 75% → 100%;
`acquire()` обязан блокировать любой state с power=0.

## FloodWait

Telegram не даёт гарантированного предварительного предупреждения.
`FLOOD_WAIT_X` уже является обязательной командой ждать X секунд.

Требования:

- `flood_sleep_threshold=0`, чтобы короткие FloodWait не скрывались Telethon;
- любой FloodWait записывается с account, RPC kind, chat context и seconds;
- текущий запрос не retry внутри batch;
- cursor не двигается;
- аккаунт немедленно получает COOLDOWN;
- новые RPC до cooldown deadline запрещены;
- deadline содержит server wait + safety buffer + jitter;
- после deadline состояние RECOVERY, не NORMAL;
- worker restart сохраняет COOLDOWN/RECOVERY;
- повторный FloodWait откатывает recovery и повышает severity.

Recovery:

```text
short:  25% 10m → 50% 15m → 75% 30m → 100%
medium: 10% 15m → 25% 30m → 50% 60m → 75% 120m → 100%
long:   10% 30m → 25% 60m → 50% 120m → 75% 240m → 100%
```

Переход вверх разрешён только после безопасных rolling windows. При снижении
обычной нагрузки THROTTLED также снимается плавно, без скачка к 100%.
После 45 минут непрерывных Telegram RPC governor делает случайную паузу
5–10 минут; отдельная сложная session-модель для этого не нужна.

## RPC accounting

Все production RPC poller account проходят через одну границу. Минимальные kinds:

```text
get_history
resolve
health
```

Redis buckets:

```text
stats:tg_rpc:{account_id}:minute:{YYYYMMDDHHMM}
stats:tg_rpc:{account_id}:hour:{YYYYMMDDHH}
stats:tg_rpc:{account_id}:day:{YYYYMMDD}
```

Fields:

```text
total attempt success error flood_wait get_history resolve health
```

TTL:

```text
minute=2d
hour=8d
day=30d
```

Используй Redis pipeline. Не делай wildcard scan в hot path.

## Governor state

Один Redis hash на аккаунт:

```text
userbot:governor:{account_id}
```

States:

```text
NORMAL
THROTTLED
COOLDOWN
RECOVERY
QUARANTINED
OFFLINE
```

Redis unavailable означает fail-closed для Telegram RPC. Bot API sender при
этом не останавливается.

Не дублируй transition rules в poller, API, dashboard и watchdog. Одна функция
`refresh_governor()` является источником истины.

Для безопасного dry-run храни отдельно effective `state/power_percent` и
`recommended_state/recommended_power_percent`. При enforcement OFF proactive
thresholds меняют только recommendation. Настоящий FloodWait/circuit всегда
меняет effective state и блокирует RPC.

## Geo eligibility

Жёсткое правило:

- нет активных подписчиков страны → catalog chats страны не опрашиваются;
- city chat опрашивается только при `mode=all` или пересечении city IDs;
- country-wide chat опрашивается при любой активной подписке страны;
- catalog chat без страны не опрашивается автоматически;
- ignored/quarantined/invalid не опрашиваются;
- active manual watched chat остаётся eligible;
- segment binding влияет только на matching, не используется как exclusion
  без доказанного полного channel mapping.

Изменение подписки должно обновлять eligibility сразу, не через час:
существующий `invalidate_all_subscription_caches()` инкрементит
`poll:eligibility:generation`, а adaptive loop перестраивает eligible list при
смене поколения. Не дублируй эту запись в отдельных handlers.

## Простая адаптивная частота

Не добавляй EWMA или сложный score:

```text
new eligible chat → C / 15m
new_messages > 0 → A / 2m
A после 3 empty polls → B / 5m
A/B после 10 empty polls → C / 15m
30 empty polls → D / 60m
100 empty polls → E / 6h
```

Любое новое сообщение возвращает A. Пустой poll никогда не повышает частоту:
новый C остаётся C до порога замедления, если сообщений нет. Invalid/private
errors:

```text
1h → 6h → 24h → 7d → quarantine
```

Schedule хранится в одном Redis hash `poll:schedule:v1`, загружается при старте
и обновляется после poll. Не создавай отдельный scheduler service.
Маленький агрегат `poll:summary:v1` хранит `eligible`, `parked`, `quarantined`,
`class:A..E` и `assigned:{account_id}`; dashboard читает его, а не обходит все
schedule entries.

## Bounded polling

- Один account получает не более 25 due chats на slice при power=100%.
- Slice пропорционально уменьшается на 75/50/25/10%.
- Перед каждым chat повторно проверить governor и session-state.
- PAUSED/SLEEPING/COOLDOWN/QUARANTINED прекращает текущий slice.
- Недоступный аккаунт не передаёт весь backlog оставшемуся.
- Просроченные A/B выбираются раньше C/D/E.
- Unpolled chats остаются due; cursor не меняется.
- Удали причину непрерывного полного обхода `elapsed > interval → sleep 5s`.

## Capacity planner

Используй:

```text
usable_per_account = floor(4000 × (1 - 0.30)) = 2800
required_accounts = ceil(projected_daily_rpc / usable_per_account)
additional_accounts = max(0, required_accounts - available_accounts)
```

Projected RPC рассчитывай из числа eligible chats по классам и их интервалов.
Не повышай safe budget автоматически.

## Alerts

Дедуплицированные события:

```text
throttled
capacity_85
capacity_95
flood_wait
recovery_started
recovery_step
recovery_rollback
normal_restored
quarantined
fleet_deficit
```

Alert содержит account ID, state, power, RPC 1h/24h, safe budget,
cooldown/stage deadline, assigned chats и `additional_accounts`.

## Dashboard

Добавь один read-only endpoint:

```text
GET /api/stats/userbots
```

UI:

- fleet utilization/reserve;
- available/required accounts;
- eligible/parked chats;
- карточка каждого аккаунта;
- state text+icon;
- power, RPC 1h/24h, budget, assigned chats;
- cooldown/recovery countdown;
- один RPC/minute chart с safe line;
- сообщение `Подключить ещё N userbot-аккаунта`.

Никаких управляющих кнопок.

## Порядок фаз

Следуй plan-файлу без объединения фаз:

1. Pure model + config.
2. RPC accounting + FloodWait governor.
3. Adaptive schedule + geo gate + bounded slices.
4. Automatic throttle/recovery + alerts.
5. Capacity API + dashboard.
6. Regression + runbook.

Для каждой фазы:

1. Напиши failing tests.
2. Запусти их и покажи ожидаемый RED.
3. Реализуй минимальный код.
4. Запусти targeted tests.
5. Запусти `/skill:phase-review`.
6. Исправь blockers.
7. Запусти tests повторно.
8. Commit.
9. Tag `userbot-governor-phase-N-done`.
10. Обнови `docs/SESSION_LOG.md` и `AGENTS.md §8`.

Не переходи к следующей фазе при красных тестах или blocker review.

## Обязательные регрессии

Без живого Telegram воспроизведи:

1. 753 due chats, 2 аккаунта.
2. Account 2 переходит PAUSED после 10 polls.
3. 11-й RPC Account 2 не происходит.
4. Account 1 не поглощает остаток Account 2.
5. Backlog остаётся due.
6. Natural CB expiry переводит в RECOVERY.
7. Worker restart сохраняет stage.
8. Любой короткий FloodWait виден приложению.
9. Country без подписчиков получает 0 Telegram RPC.
10. City filter соблюдается.
11. Redis failure запрещает Telegram RPC.
12. Cursor не двигается после FloodWait.

## Финальные проверки

```bash
pytest tests/ -q
cd admin-panel && npm run lint && npm run build && cd ..
git diff --check
rg -n "client\\.(get_me|get_messages|get_entity|get_input_entity)" app
rg -n "flood_sleep_threshold" app tests
```

Объясни каждый direct Telegram RPC, который не проходит через governor.

## Rollout

Только подготовь runbook. Ничего не выкатывай.

Флаги:

```text
USERBOT_RPC_METRICS_ENABLED=true
USERBOT_GOVERNOR_ENFORCING=false
USERBOT_ADAPTIVE_POLLING_ENABLED=false
```

Порядок будущего rollout:

```text
metrics shadow ≥24h
→ governor dry-run
→ enforce 25% на одном тестовом аккаунте
→ наблюдение ≥2h
→ второй аккаунт
→ adaptive polling
```

Rollback сохраняет metrics/state и выключает enforcement флагом. Нельзя удалять
Redis circuit/governor keys ради ускоренного восстановления.

Поведение флагов:

- metrics OFF — старый rate limit работает, новые buckets не пишутся;
- governor enforcement OFF — proactive решения только dry-run, но настоящий
  FloodWait/circuit всегда блокирует; effective power остаётся прежним, а
  расчёт пишется в recommended state/power;
- adaptive polling OFF — работает только legacy tier loop;
- adaptive polling ON — legacy tier loop для тех же catalog chats не запускается.

## Формат отчёта после каждой фазы

```text
Фаза:
Изменённые файлы:
Что реализовано:
RED test:
GREEN tests:
Phase review:
Commit:
Tag:
Риски/отложено:
Production touched: NO
```

Не пиши «готово», пока не покажешь свежий вывод tests/build для текущего commit.

---
