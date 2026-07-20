# Аудит стабильности — baseline 20.07.2026

## Границы

Phase 0 фиксирует воспроизводимый baseline и статический реестр рисков без
изменения runtime, тестов и production. Проверки production, живых Telegram /
payment-интеграций, Redis и БД в этот этап не входят.

## Проверенный baseline

- Docker image `lh-stability:baseline` успешно собран из коммита `5c7327e`.
- Изолированный прогон с PostgreSQL и Redis: `501 passed`; один существующий
  `RuntimeWarning` в `tests/test_llm_validator.py`.
- Admin: `npm ci`, `npm run lint`, `npm run build` завершились с кодом 0.
  Остались пять существующих Fast Refresh warnings и один существующий warning
  Vite о размере chunk.
- Alembic: ровно один head; цикл
  `u94_lifecycle_optout -> pay_idempotency01 -> u94_lifecycle_optout`
  (downgrade/upgrade) прошёл успешно.
- Существующий Compose project не изменялся: bot/worker/admin находились в
  restart-состоянии, поэтому baseline получен через изолированные
  `docker build/run` resources.

В Phase 0 намеренно не добавляются постоянно падающие или `xfail`-тесты.
Regression tests добавляются test-first в фазе соответствующего исправления,
чтобы ветка оставалась зелёной.

## Confirmed

- **P1 — публичная admin-поверхность и ослабление login-защиты.**
  `docker-compose.yml` публикует admin на всех интерфейсах по HTTP;
  `app/admin/api/auth.py::_get_ip` безусловно доверяет `X-Forwarded-For`, а
  `login` при ошибке Redis переходит на password-only fail-open.
- **P1 — deploy не привязан к tested SHA.**
  `.github/workflows/deploy.yml` после успешного CI делает checkout/pull
  текущего `main`, а не `workflow_run.head_sha`.
- **P1 — отсутствует distributed singleton для worker.**
  `app/worker/tasks.py::main` сразу создаёт `ChannelPoller` и запускает pool;
  защита от второго worker существует только как operational-запрет в
  `OPERATIONS.md`, но не как runtime lease.
- **P2 — ban/suspend не участвуют в маршруте доставки.**
  `app/cache/subscription_cache.py::rebuild_subscription_cache` выбирает всех
  `User` без фильтра `is_banned`, `is_suspended`, `suspended_until` и
  `is_blocked_bot`; `app/admin/api/users.py` только изменяет эти поля.
- **P2 — referral attribution может теряться.**
  `app/bot/handlers/start.py::cmd_start` использует `timedelta.seconds` и
  перезаписывает `referral_id` в найденной строке; модель
  `app/db/models.py::Referral` хранит один mutable edge на уникальный
  `ref_code`.
- **P2 — неатомарный stamp queue claim.**
  `app/cache/subscription_cache.py::claim_notification` после атомарного
  `BLMOVE` отдельно выполняет `LREM` и `LPUSH`; падение между ними оставляет
  окно тихой потери envelope.
- **P2 — support/admin chat contracts нарушены.**
  `app/bot/handlers/support.py::on_support_message` вызывает отсутствующие
  импорты `normalize_language` и `get_text` после сохранения сообщения;
  `app/admin/api/chat.py::chat_ws` принимает `telegram_id` от клиента вместо
  получения его по `user_id` из БД.
- **P2 — winback проверяется не в каждой точке оплаты.**
  `app/bot/handlers/plan.py` проверяет offer при создании invoice, но promo
  `wb25` далее принимается в `app/payments/activate.py` и
  `app/worker/payment_checker.py` без повторной проверки активного,
  неиспользованного offer непосредственно при оплате.

## Runtime verification required

- Фактическая network exposure admin и наличие TLS/reverse proxy.
- Единственность worker и отсутствие параллельных MTProto-сессий.
- Redis AOF/ACL, возраст processing queue, DLQ и возможность replay.
- Blocking-режим LLM, доля fail-open и `stats:full_batch:*`.
- Успешность backup/restore и соответствие deployed SHA проверенному SHA.
- Живые Stars/CryptoBot, winback redemption и конкурентный referral cap.

Эти пункты не считаются подтверждёнными runtime-инцидентами до отдельной
production-проверки с разрешением владельца.

## Accepted trade-off

- Выбран контракт доставки **at-least-once**: `app/worker/sender.py` вызывает
  `mark_sent` только после успешного Telegram send. При
  `send -> crash -> mark_sent` возможен крайне редкий дубль; перенос
  `mark_sent` до send создал бы более тяжёлый риск потери лида.
- LLM fail-open и cursor gap при `limit=100` остаются осознанными trade-off и
  меняются только по метрикам.
- Текущая политика early renewal (reset-from-now) не считается дефектом без
  отдельного продуктового решения.

## Не подтверждено

Unauthenticated WebSocket bypass **не подтверждён**:
`app/admin/api/__init__.py` подключает `chat_router` через
`Depends(require_auth)`. Нужен отдельный негативный handshake-тест в фазе
исправления admin-поверхности; до него гипотеза не переводится в runtime-фикс.
