# Ран-лист: живое переключение прода на audit/fable-fixes — 12.07.2026

Задача 0.1 fable_core_plan.md. Исполняется по шагам сверху вниз; после каждого шага — чекпоинт.
Не прошёл чекпоинт → СТОП, читать секцию «Откат». Оценка: 30–45 мин работ + 30 мин наблюдения.

## Почему окно срочное (находка 12.07, 07:30 MSK)

Worker стартовал 09.07 16:02 MSK на коде `main`, а в 17:24 рабочая директория переключена на
`audit/fable-fixes`. Через bind-mount `./app:/app/app` работающие контейнеры уже видят на диске
код ветки — в памяти у них main, но **любой непреднамеренный рестарт worker (краш, OOM, ребут)
загрузит код аудита БЕЗ миграции lead_direction01 → crash-loop** (проверено: в БД head =
cat_hierarchy_v1, колонки нет). Переключение обезвреживает эту мину.

## Предполётная подготовка — ВЫПОЛНЕНО 12.07 утром

- [x] Репетиция миграции на копии ночного бэкапа (lh_mig_test): upgrade → 65 demand / 4 buy / 2 supply;
      downgrade → колонка снята чисто; повторный upgrade OK. Чинить нечего.
- [x] Diff main..ветка по инфре: только `migrations/versions/lead_direction01.py` + `.env.example`.
      Dockerfile/requirements не менялись — билд лёгкий, новых зависимостей нет.
- [x] Compose: Redis AOF (`appendonly yes`, `everysec`) + том `redis_data` закоммичены в ветку.
- [x] `chmod 600 .env`.
- [x] Эталонные цифры перед окном: Redis dbsize=1023, queue=0, dlq=0, CB clear, оба аккаунта без FloodWait.
- [x] Полный сьют ветки: 231 passed / 3 pre-existing failed / 1 deselected (10.07, офлайн-верификация фаз).

## Решения владельца ДО окна

1. **Биндинг админки**: `127.0.0.1:17421` + SSH-туннель (рекомендация) ИЛИ оставить публичным
   (TLS — отдельной задачей). Если localhost — правка compose вносится до шага 1.
2. **SENTRY_DSN**: если DSN есть — добавить в `.env` до шага 5 (подхватится стартом). Нет — пропустить.

---

## Шаг 0. Пред-чеки (worker ещё работает — только чтение)

```bash
cd /opt/LeadHunter
git branch --show-current            # = audit/fable-fixes
git status -sb                       # чисто, синхронно с origin
docker exec leadhunter-redis-1 redis-cli keys "circuit:open*"   # пусто
docker logs leadhunter-worker-1 --since 30m 2>&1 | grep -ci floodwait  # 0
df -h / | tail -1                    # ≥2GB свободно (билд)
```

Свежий бэкап (не полагаться на ночной 03:00):

```bash
docker exec leadhunter-db-1 pg_dump -U leadhunter leadhunter | gzip > backups/pre_switch_$(date +%Y%m%d_%H%M).sql.gz
ls -la backups/pre_switch_*          # размер ≥ ночного (~1.7MB+)
tar czf - -C sessions . | gpg --batch --symmetric --cipher-algo AES256 \
  --passphrase "$(grep SESSION_BACKUP_PASSPHRASE .env | cut -d= -f2)" \
  > backups/sessions_pre_switch_$(date +%Y%m%d_%H%M).tar.gz.gpg
```

**Чекпоинт:** оба файла созданы, ненулевые; CB clear; FloodWait 0.

## Шаг 1. Остановка producer/consumer

```bash
docker compose stop worker bot admin      # db и redis ПРОДОЛЖАЮТ работать
```

**Чекпоинт:** `docker ps` — только db и redis. С этого момента постим в @leadhunterai_admin вручную,
алертов не будет (watchdog заорёт через ≤10 мин — это ожидаемо, игнорировать до конца окна).

## Шаг 2. Переезд Redis на AOF + том (с сохранением ключей)

```bash
docker exec leadhunter-redis-1 redis-cli dbsize          # эталон, ~1023
docker exec leadhunter-redis-1 redis-cli bgsave && sleep 3
docker cp leadhunter-redis-1:/data/dump.rdb backups/redis_pre_switch.rdb
docker compose stop redis
docker volume create leadhunter_redis_data
docker run --rm -v leadhunter_redis_data:/data -v /opt/LeadHunter/backups:/b alpine \
  cp /b/redis_pre_switch.rdb /data/dump.rdb
docker compose up -d redis                               # пересоздаст: AOF + том
sleep 3 && docker exec leadhunter-redis-1 redis-cli dbsize && \
  docker exec leadhunter-redis-1 redis-cli config get appendonly
```

**Чекпоинт:** dbsize ≈ эталону (±несколько истёкших TTL), appendonly=yes.
**Если dbsize=0** (Redis 7 должен грузить RDB при отсутствии AOF-манифеста, но проверяем):
≤15 мин на спасение — `docker compose stop redis`, очистить `appendonlydir` в томе
(`docker run --rm -v leadhunter_redis_data:/data alpine rm -rf /data/appendonlydir`), поднять redis
с командой без appendonly (временно в compose), убедиться что ключи загрузились,
`redis-cli config set appendonly yes` (перепишет AOF из памяти), вернуть compose-команду.
**Не вышло → принять потерю ключей и идти дальше:** это безопасно — курсоры пересоздадутся
(режим первого знакомства, A6 не флудит LLM), дедуп доставки в Postgres (sent_log — дублей
пользователям НЕ будет), бюджеты/сессии/кэши пересоздаются сами. Потеря: stats:unmatched,
stats:daily за сегодня.

## Шаг 3. Билд

```bash
git pull                              # ветка синхронна с origin
docker compose build                  # один образ для bot/worker/admin
```

**Чекпоинт:** билд без ошибок.

## Шаг 4. Миграция (СТРОГО до старта worker)

```bash
docker compose run --rm --no-deps worker alembic upgrade lead_direction01
docker exec leadhunter-db-1 psql -U leadhunter -d leadhunter -tAc \
  "select lead_direction, count(*) from segments group by 1 order by 2 desc"
```

**Чекпоинт:** ровно `demand|65, buy|4, supply|2` (как на репетиции). Иное → СТОП, откат.
Свежесобранный образ содержит миграцию из ветки — мёртвый bind-mount migrations (техдолг №7) обойдён.

## Шаг 5. Запуск

```bash
docker compose up -d
docker logs -f leadhunter-worker-1 --since 1m     # смотреть 2-3 минуты
```

**Чекпоинт (логи worker):** пул инициализирован, «circuit breaker … clear — ready to poll» по обоим
аккаунтам, компиляция keyword map (~1с, B2), сессионные состояния подняты, НЕТ traceback'ов,
НЕТ FloodWait. Логи bot: polling стартовал. `curl -s localhost:8001/health` — OK.

## Шаг 6. Живая верификация (15–30 мин, чек-лист fable_audit §5)

1. **Курсоры двигаются:** `redis-cli --scan --pattern "cursor:msg:*" | head` + повторить через 5 мин —
   значения растут; в логах идут опросы каналов.
2. **Сценарий А:** существующая подписка (сегмент+гео) получает живой матч → карточка корректна,
   метка 🏷 категории на месте.
3. **Сценарий Б (впервые в проде!):** владелец добавляет личный keyword + watched-чат → тестовое
   сообщение в чате → уведомление приходит (путь keyword_only, минуя LLM).
4. **HTML-лид (A3):** тестовое сообщение с `<b>test</b> & co` → доставлено, не потеряно.
5. **Free-формат (D1):** уведомление Free-пользователю — ни одной ссылки (чат plain-текстом).
6. **Логи 15-30 мин:** FloodWait=0, Redis/DB ошибок нет, CPU не хуже обычного (~100% на 1 core — норма).
7. **LLM:** в логах идут батчи валидатора, в `llm_decisions` появляются свежие строки.

**Чекпоинт:** пункты 1, 6, 7 обязательны; 2-5 — по мере трафика (Б/HTML/Free — управляемые, сделать сразу).

## Шаг 7. Финализация

```bash
git checkout main && git merge audit/fable-fixes   # ff-merge
git tag audit-fixes-live && git push origin main --tags
# остаёмся на main — прод-правило: рабочая директория прода = main
```

Затем: session log (docs/SESSION_LOG.md + CLAUDE.md §8 статус), в fable_core_plan.md задача 0.1 → [x],
в fable_audit.md — пометка о живом переключении. Мониторинг @leadhunterai_admin до конца дня.

---

## Откат (из любой точки до шага 7; простой — секунды-минуты)

```bash
docker compose stop worker bot admin
git checkout main
docker compose build
# если шаг 4 успел выполниться:
docker compose run --rm --no-deps worker alembic downgrade cat_hierarchy_v1   # проверен на копии
docker compose up -d
```

- Redis-переезд (шаг 2) откатывать НЕ нужно: AOF+том совместимы со старым кодом.
- `pg_restore` из `pre_switch_*.sql.gz` — только при порче данных (миграция аддитивная, сценарий маловероятен).
- После отката вернуться на ветку `audit/fable-fixes` в рабочей директории НЕЛЬЗЯ, пока прод жив на main
  (та же bind-mount мина). Разбор полётов — на копиях.
