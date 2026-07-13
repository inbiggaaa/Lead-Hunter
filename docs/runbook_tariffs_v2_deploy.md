# Runbook: деплой тарифов v2 (ветка feature/tariffs-v2 → прод)

> **Кто исполняет:** владелец (или явно авторизованная сессия с мониторингом). Деплой = запрещённые при работающем worker команды (`docker compose up/restart/exec`, стоп worker) + правка прод-`.env` + миграции. Автономно НЕ выполняется.
>
> **Состояние на 13.07.2026:** фазы T0–T5 закрыты, T6.1/T6.2/T6.4-инструментация готовы. Прод на `main` (старый код, коммит 087b9be), 4 пользователя (1 business=владелец, 3 free). Ветка `feature/tariffs-v2`, 3 миграции: `channel_account01`(в проде) → `sentlog_meta01` → `user_digest01`.

## 0. Предусловия (за день)
- [ ] Прочитать OPERATIONS.md §2 (Hard Rules) и §5 (чек-лист) — деплой трогает sender/poller-смежное.
- [ ] Убедиться, что ветка смёржена ревью/тестами: последний прогон **359 passed** (4 пред­существующих poller-фейла — не блокеры).
- [ ] Выбрать окно низкого трафика.

## 1. Бэкап (обязательно)
```bash
cd /opt/LeadHunter
docker exec leadhunter-db-1 pg_dump -U leadhunter leadhunter | gzip > backups/pre_tariffs_v2_$(date +%F_%H%M).sql.gz
cp -r sessions backups/sessions_pre_tariffs_v2_$(date +%F)   # бэкап userbot-сессий
```

## 2. Остановить worker (двойная нагрузка на Telegram = риск бана)
```bash
docker compose stop worker
```

## 3. Влить ветку в main
```bash
git checkout main && git pull
git merge --no-ff feature/tariffs-v2 -m "release: тарифы v2 (#81)"
git tag tariffs-v2-live
```

## 4. Миграции (инкрементально; прод на channel_account01)
```bash
# репетиция на копии бэкапа НЕ обязательна (только add nullable-колонки + поле с дефолтом),
# но при желании — прогнать на scratch-БД. Накат:
docker compose run --rm worker alembic upgrade head
# применит: sentlog_meta01 (sent_log +chat/sender/segment/message_id),
#           user_digest01 (users.digest_mode default 'instant').
# ⚠️ alembic С НУЛЯ не гоняется (техдолг №7) — но прод НЕ с нуля, накат от channel_account01 чистый.
```

## 5. ⚠️ БЛОКЕР: config.py + прод-.env одновременно (иначе старт упадёт)
Config = `extra_forbidden`. Убрать `notifications_per_day_*` нужно СИНХРОННО:
- [ ] В коде поля уже unused (в ветке). Убедиться, что в config.py они ещё присутствуют (да — оставлены намеренно).
- [ ] Отредактировать прод-`.env` в ОДНОМ окне:
  - удалить/закомментировать `NOTIFICATIONS_PER_DAY_FREE`, `NOTIFICATIONS_PER_DAY_PRO`;
  - обновить цены: `PRICE_START_MONTHLY_USD=9`, `PRICE_PRO_MONTHLY_USD=19`, `PRICE_BUSINESS_MONTHLY_USD=39`;
  - добавить новые лимиты (если не в .env): `MAX_SEGMENTS_START=1`, `MAX_CHANNELS_START=1`, `MAX_KEYWORDS_START=10`, `MAX_SEGMENTS_PRO=5`, `MAX_CHANNELS_PRO=10`, `MAX_COUNTRIES_START=1`, `MAX_CITIES_START=3`, `MAX_COUNTRIES_PRO=5`.
- [ ] Затем удалить `notifications_per_day_free/pro` из `app/config.py` (по желанию — можно оставить как безвредный дефолт; если удаляешь — прод-.env уже без env-строк, старт не упадёт). Закоммитить.

## 6. Сборка и запуск
```bash
docker compose build bot worker admin
docker compose up -d --no-deps bot worker admin   # --no-deps: не пересоздавать db/redis (урок 0.1)
```

## 7. Инвалидация кэша подписок (digest_mode/plan в payload изменились)
```bash
docker exec leadhunter-redis-1 redis-cli --scan --pattern 'sub:by_chat:*' | xargs -r docker exec leadhunter-redis-1 redis-cli del
# или дождаться TTL 1ч; кэш перестроится на первом поллинге
```

## 8. Верификация (15 минут логов)
- [ ] `docker compose logs -f worker` — 0 Traceback, 0 FloodWait, «Sender started», курсоры двигаются.
- [ ] `docker compose logs bot` — стартует без pydantic ValidationError (проверка блокера §5).
- [ ] Живой тест в боте: `/plan` → карточки Старт $9/Профи $19/Бизнес $39; меню → «Заявок сегодня: N» (без /50); `/stats` доступен владельцу (business).
- [ ] Оплата Stars на реальном инвойсе минимального периода (Старт 1м) — активация проходит.
- [ ] Free-уведомление живым трафиком: контакты скрыты, кнопка «Открыть контакты — от $9», без дневного лимита.
- [ ] user 152 (владелец) — доступ business сохранён, plan_expires_at не изменился.

## 9. После деплоя (отдельно, решением владельца)
- [ ] Анонс через админку /broadcast (черновик — план T6.2). Только ПОСЛЕ успешной верификации.
- [ ] Запустить 2-недельный мониторинг (T6.4): stats:paywall:*, конверсия, распределение тарифов, гео-стоимость hot-тира, жалобы на шум.

## 10. Откат
Точка отката — `main` до merge (тег до релиза) + бэкап §1. При проблемах: `docker compose stop worker` → `git checkout <pre-release>` → `alembic downgrade channel_account01` (обратимо) → восстановить прод-`.env` → build → up.

---
**Инцидент-лог:** при любом FloodWait/бане/ошибке Telegram API — немедленно в OPERATIONS.md (причина, хронология, урок).
