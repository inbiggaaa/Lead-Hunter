# Userbot Capacity Governor и адаптивный polling

**Дата:** 24.07.2026

**Статус:** design approved in principle; owner review required before implementation plan

**Область:** userbot polling, anti-ban, capacity planning, admin dashboard, Telegram alerts

**Приоритет:** качество сервиса и минимальная задержка уведомлений при безусловном соблюдении Telegram safety

## 1. Контекст

24.07.2026 Account 2 получил `FloodWait 71565s`. Перед инцидентом:

- Hot-контур вырос с 198 до 753 чатов после добавления 54 тестовых подписок;
- account budget достиг `9843/10000`;
- полный Hot-цикл стал дольше базового интервала 300 секунд;
- между циклами оставалась минимальная пауза 5 секунд;
- переход аккаунта в `PAUSED` не прерывал уже запущенный большой chunk;
- после блокировки Account 2 оставшийся аккаунт принудительно получил весь Hot-контур.

Текущая защита ограничивает минимальный интервал между вызовами и суточный
счётчик, но не управляет безопасной ёмкостью, продолжительностью непрерывной
работы, rolling-нагрузкой и прогнозом дефицита аккаунтов.

## 2. Зафиксированные продуктовые решения

1. Реализуется вариант: дашборд + Telegram-алерты + автоматический governor.
2. После падения нагрузки или завершения cooldown аккаунт автоматически и
   плавно возвращается к полной мощности.
3. Качество и скорость доставки лидов — приоритет.
4. Страны и города без активных подписчиков не опрашиваются.
5. Безопасность аккаунта имеет приоритет над покрытием: повторный бан хуже
   временного увеличения задержки.
6. Новый userbot не подключается автоматически. Админка рассчитывает и
   показывает, сколько аккаунтов требуется; авторизацию выполняет владелец.
7. Точные лимиты Telegram не считаются известными константами. Безопасная
   мощность каждого аккаунта оценивается по его собственной истории.

## 3. Цели

- Доставлять сообщения из наиболее ценных чатов максимально быстро.
- Предотвращать длинный FloodWait до его возникновения, когда rolling-сигналы
  позволяют это сделать.
- Обрабатывать каждый `FLOOD_WAIT_X` как обязательную команду Telegram.
- Автоматически снижать и восстанавливать нагрузку без ручного рестарта.
- Показывать владельцу фактическую и прогнозную ёмкость каждого аккаунта.
- Рекомендовать подключение нового аккаунта до потери SLA.
- Повысить число полезных сообщений и лидов на 1000 Telegram RPC.
- Не опрашивать географию без получателей.

## 4. Не-цели

- Обход или маскировка ограничений Telegram.
- Автоматическая регистрация, покупка или авторизация SIM/userbot.
- Гарантия фиксированного числа допустимых запросов Telegram.
- Автоматическое вступление аккаунтов в сотни групп ради event-driven режима.
- Изменение тарифов или приоритизация пользователей по тарифу.
- Переработка matching/LLM-конвейера.

## 5. SLO скорости

Чат получает динамический класс обслуживания:

| Класс | Назначение | Целевой poll interval | SLO доставки p95 |
|---|---|---:|---:|
| A Realtime | высокая активность или высокий lead yield | 2 минуты | ≤5 минут |
| B Active | регулярные сообщения и подтверждённые лиды | 5 минут | ≤10 минут |
| C Standard | умеренная активность | 15 минут | ≤30 минут |
| D Quiet | редкие сообщения | 60–120 минут | ≤2 часов |
| E Dormant | длительно пустые, но eligible | 360–720 минут | ≤12 часов |
| Parked | нет получателей или чат невалиден | не опрашивается | не применяется |

SLO измеряется от `message.date` до успешной постановки уведомления в очередь и
отдельно до успешной отправки Bot API.

При нехватке capacity governor сначала замедляет E/D, затем C. Нарушение SLO A/B
не маскируется: дашборд показывает красный capacity deficit и требуемое число
дополнительных аккаунтов. Telegram safety всё равно остаётся абсолютным gate.

## 6. Eligibility: какие чаты разрешено опрашивать

Eligibility рассчитывается до scheduler:

1. Catalog chat с конкретным городом разрешён, только если существует хотя бы
   одна активная подписка на его страну:
   - в режиме `all`; или
   - в режиме `cities` с пересечением выбранных городов.
2. Country-wide chat без городского binding разрешён, если в стране существует
   хотя бы одна активная подписка, включая city-scoped.
3. Catalog chat страны без подписчиков получает `Parked`.
4. Catalog chat без определённой страны не опрашивается автоматически.
5. Manual watched chat разрешён, пока существует активный владелец watched chat
   и тариф допускает этот канал.
6. `is_ignored`, удалённые, permanently invalid и quarantined chats исключаются.
7. Segment binding влияет на priority, но не является жёстким exclusion gate,
   пока полнота `channel_segments` не доказана eval-данными. Это защищает recall.

Eligibility snapshot пересчитывается после CRUD подписок/каналов и страховочно
по TTL. Изменение подписки не должно ждать часового rebuild.

## 7. Архитектура

### 7.1 Telegram RPC Gateway

Единственная граница для исходящих Telegram API-вызовов poller:

- принимает `account_id`, RPC kind, chat identifier и callback запроса;
- проверяет governor permit;
- считает попытку, успех, ошибку и latency;
- сохраняет точный RPC kind;
- перехватывает все FloodWait;
- не содержит scheduler-логики.

Через gateway должны проходить `get_messages`, entity resolution, health-check
RPC и другие production-вызовы polling account. Discovery остаётся изолированным
аккаунтом и получает собственный governor namespace.

`flood_sleep_threshold` устанавливается так, чтобы короткие FloodWait не
скрывались внутри Telethon. Все ожидания выполняет governor. Это изменение
вводится только после теста, подтверждающего отсутствие двойного retry.

### 7.2 Account Governor

Governor принимает решение, можно ли выполнить следующий RPC конкретного
аккаунта. Он не выбирает чат.

Состояния:

- `NORMAL`;
- `THROTTLED`;
- `COOLDOWN`;
- `RECOVERY`;
- `QUARANTINED`;
- `OFFLINE`.

Состояние и дедлайны хранятся в Redis/AOF и переживают worker restart.
Недоступность Redis означает fail-closed для Telegram polling, но не останавливает
Bot API sender.

### 7.3 Adaptive Scheduler

Scheduler выбирает только eligible chats и работает по `next_poll_at`.

- Основной порядок — earliest deadline first.
- При одинаковом deadline выше чат с большим priority score.
- Один чат одновременно имеет не более одного active poll lease.
- После poll scheduler пересчитывает activity EWMA, lead yield и следующий срок.
- Больших account chunks больше нет; работа выдаётся небольшими slices.
- Между slices повторно проверяются governor, session-state и eligibility.
- Переход в `PAUSED`, `SLEEPING`, `COOLDOWN` или `QUARANTINED` прекращает выдачу
  новых RPC немедленно.

### 7.4 Capacity Planner

Planner прогнозирует:

- RPC за оставшуюся часть часа/суток;
- capacity utilization каждого аккаунта;
- достижимый SLO по каждому классу;
- общий резерв;
- требуемое число дополнительных аккаунтов.

Расчёт использует фактическую стоимость poll:

`required_accounts = ceil(projected_daily_rpc / usable_daily_capacity)`

`usable_daily_capacity` включает 30% reserve и индивидуальный learned safe limit.
Во время восстановления базовый безопасный предел — 4000 RPC/сутки на аккаунт.
Повышение возможно только по историческим данным без FloodWait, а не вручную
одним изменением env.

### 7.5 Metrics Store

Redis хранит оперативные minute/hour buckets и state. PostgreSQL хранит
долгосрочные события состояния и FloodWait для аудита. Никакие phone, api_hash,
session contents или тексты сообщений в metrics не сохраняются.

### 7.6 Admin API и Dashboard

Отдельный read-only endpoint userbot capacity возвращает:

- fleet summary;
- карточки аккаунтов;
- rolling series;
- scheduler/SLO summary;
- capacity recommendation;
- последние state transitions и FloodWait.

Dashboard обновляется каждые 15–30 секунд. Управляющие кнопки start/stop,
reset circuit и изменение лимитов не входят в первую версию: опасные действия
остаются через runbook.

### 7.7 Telegram Alerts

Алерты отправляются в закрытый admin channel и дедуплицируются:

- переход `NORMAL → THROTTLED`;
- прогноз исчерпания capacity;
- capacity deficit и рекомендация добавить N аккаунтов;
- любой FloodWait;
- начало/ступень/завершение recovery;
- rollback recovery;
- quarantine/offline/stale heartbeat.

## 8. Сигналы и метрики

Для каждого аккаунта:

- RPC attempts/success/errors за 5м, 1ч, 6ч, 24ч;
- RPC breakdown: history, resolve, health, updates/other;
- rolling RPS и p95 inter-request interval;
- continuous active time;
- polls и unique chats;
- assigned eligible chats по классам A/B/C/D/E;
- budget used, safe limit, utilization;
- forecast EOD и time-to-limit;
- last successful RPC/poll;
- FloodWait count и seconds за 7/30 дней;
- governor state, power level, cooldown/recovery deadline;
- useful messages / 1000 RPC;
- delivered leads / 1000 RPC;
- full batches и message gaps;
- heartbeat.

Fleet:

- eligible/parked/quarantined chats;
- SLO attainment A/B/C/D/E;
- queue overdue by class;
- current/required/reserve accounts;
- projected RPC/day;
- coverage lost because of safety throttling.

## 9. Priority score и адаптивная частота

Priority score формируется из:

- SLO deadline;
- recent messages/hour EWMA;
- leads/100 polls EWMA;
- число потенциальных получателей;
- overdue duration;
- error penalty;
- quiet streak.

Правила:

1. Новый eligible chat начинает с C, не с A.
2. Высокая активность или lead yield повышают до B/A.
3. Последовательные пустые polls дают exponential backoff до D/E.
4. Новое сообщение сокращает interval.
5. Invalid/private/username errors получают возрастающий retry:
   1ч → 6ч → 24ч → 7д → quarantine.
6. Успешный poll сбрасывает transient error streak.
7. Full batch повышает приоритет и создаёт data-quality alert.
8. Chat с несколькими подписчиками не опрашивается несколько раз.

## 10. Превентивное throttling

Начальные thresholds конфигурируемы и консервативны:

- `NORMAL`: forecast ≤70% safe capacity, continuous session <45 минут;
- `THROTTLED`: forecast >70%, 1h burst выше профиля или session ≥45 минут;
- hard pause: forecast >85%, session ≥60 минут или rolling anomaly;
- emergency stop: forecast >95%, любой FloodWait или потеря state storage.

Действия по порядку:

1. увеличить interval E/D;
2. временно отложить E, затем D;
3. увеличить interval C;
4. ограничить account slice;
5. обязательная randomized pause;
6. сохранить A/B, если permit остаётся безопасным;
7. при отсутствии capacity остановить polling и поднять CRITICAL.

Последний доступный аккаунт не наследует автоматически весь backlog другого.

## 11. Обработка FloodWait

`FLOOD_WAIT_X` — не предварительное предупреждение, а обязательный server
throttle. Алгоритм:

1. Зафиксировать событие до ожидания.
2. Остановить новые RPC аккаунта.
3. Не retry текущий запрос внутри batch.
4. Оставить cursor неизменным и вернуть chat в scheduler.
5. Установить:
   `cooldown_until = now + X + safety_buffer + jitter`.
6. Safety buffer:
   - short `X ≤60с`: 2–5 минут;
   - medium `61–1800с`: 10% X, минимум 5, максимум 30 минут;
   - long `X >1800с`: 10% X, минимум 30 минут, максимум 2 часа.
7. После cooldown перейти в `RECOVERY`, не в `NORMAL`.
8. Повторный FloodWait повышает severity и может включить quarantine.

## 12. Автоматическое восстановление мощности

Power level ограничивает число permits и классы чатов:

| Уровень | Доступные классы | Доля safe capacity |
|---:|---|---:|
| 10% | только просроченные A | 10% |
| 25% | A + часть B | 25% |
| 50% | A + B | 50% |
| 75% | A + B + часть C | 75% |
| 100% | все eligible A/B/C/D/E по scheduler | 100% |

Recovery profile:

- после short FloodWait: 25% 10м → 50% 15м → 75% 30м → 100%;
- после medium: 10% 15м → 25% 30м → 50% 60м → 75% 120м → 100%;
- после long: 10% 30м → 25% 60м → 50% 120м → 75% 240м → 100%.

Переход вверх разрешён, только если:

- не было нового FloodWait;
- rolling 5м/1ч ниже threshold текущей ступени;
- forecast остаётся ниже safe capacity;
- continuous active time допустим;
- heartbeat свежий;
- Redis state доступен.

При падении обычной нагрузки proactive throttle снимается после трёх
последовательных стабильных окон. Рост также идёт ступенчато, чтобы не создавать
резкий паттерн. Нарушение условия откатывает на предыдущую ступень; FloodWait
возвращает в `COOLDOWN`.

## 13. Повышение полезной мощности аккаунта

Разрешённые способы:

1. Adaptive interval по активности и lead yield.
2. Жёсткий geo eligibility.
3. Повторное использование account-scoped entity/access hash между рестартами.
4. Отказ от повторного resolve при валидном cache.
5. Quarantine недоступных чатов.
6. Один poll на chat для всех пользователей.
7. Ограниченные slices вместо непрерывного полного обхода.
8. Снижение background RPC.
9. Гибрид event-driven только для чатов, где аккаунт уже является участником,
   если это снижает RPC и проходит отдельный safety gate.

Запрещённые способы:

- уменьшение пауз после FloodWait;
- параллельные основные sessions одной auth key;
- автоматическое вступление в массовое число групп;
- подмена device identity;
- rotating proxy как средство обхода лимитов;
- повторный запрос до `cooldown_until`.

## 14. Проверка фоновых Telegram updates

Перед отключением updates проводится staging/shadow измерение:

1. Посчитать background RPC/update volume отдельно от polling.
2. Определить, используются ли updates для manual/private watched chats.
3. Сравнить режимы на тестовом аккаунте без production traffic.
4. Если updates не дают полезных событий — отключить их для poll-only clients.
5. Если дают — оставить только для уже joined watched chats и использовать
   low-frequency polling как reconciliation.

Решение не принимается предположением и не выкатывается сразу на все аккаунты.

## 15. Dashboard UX

Верхний блок «Мощность userbot»:

- `Используется: 68%`;
- `Резерв: 32%`;
- `SLO A/B: 97%`;
- `Аккаунтов: 2 доступно / 5 требуется`;
- рекомендация с причиной.

Карточка аккаунта:

- имя/ID без телефона;
- крупный status badge;
- текущая мощность;
- budget gauge;
- RPC 1ч/24ч;
- чаты A/B/C/D/E;
- continuous session;
- forecast;
- последний FloodWait;
- cooldown/recovery countdown;
- lead efficiency.

Графики:

- RPC/minute по аккаунтам;
- capacity utilization и safe line;
- SLO latency A/B/C/D/E;
- useful messages/leads per 1000 RPC;
- FloodWait/state transition timeline.

Цвет не является единственным носителем статуса; используются текст и иконка.

## 16. Надёжность и fail-safe

- Redis unavailable → новые Telegram RPC запрещены.
- PostgreSQL unavailable → используется последний eligibility snapshot с
  коротким TTL; после TTL polling останавливается.
- Worker restart не сбрасывает cooldown/recovery.
- Второй worker блокируется leader lease.
- Clock calculations используют UTC epoch.
- State transitions идемпотентны.
- Alert failure не меняет governor decision.
- Admin endpoint не выполняет Telegram RPC.

## 17. Тестирование

Обязательные уровни:

### Unit

- state machine transitions;
- recovery profiles;
- capacity forecast;
- priority score;
- chat backoff;
- geo eligibility;
- required account calculation;
- safety thresholds.

### Integration с Fake Telegram

- short/medium/long FloodWait;
- отсутствие hidden Telethon retry;
- cursor не двигается на неуспешном poll;
- PAUSED прерывает slice;
- CB expiry всегда ведёт в RECOVERY;
- restart сохраняет state;
- один аккаунт не наследует весь backlog;
- Redis failure = fail-closed;
- подписка CRUD немедленно обновляет eligibility.

### Admin

- API schema;
- account status cards;
- countdown;
- stale metrics;
- recommendation N;
- accessibility/status without color.

### Live owner-gated

- отдельный тестовый аккаунт;
- ограниченный список чатов;
- shadow metrics;
- controlled short cooldown simulation без искусственного вызова FloodWait;
- staged power ramp;
- минимум 24 часа наблюдения перед расширением.

Нельзя намеренно вызывать FloodWait в production для проверки.

## 18. Rollout

1. Зафиксировать baseline и оставить пострадавший аккаунт вне полной нагрузки.
2. Включить RPC metrics в shadow без изменения scheduling.
3. Проверить accounting по RPC kind и hidden Telethon retry.
4. Включить governor decisions в dry-run.
5. Сравнить predicted throttling с фактической историей инцидента.
6. Enforce на одном тестовом аккаунте и ограниченных чатах.
7. Включить adaptive scheduler для E/D/C.
8. Включить A/B после проверки SLO и capacity.
9. Добавить dashboard/alerts.
10. Расширять fleet только по рекомендации planner.

Rollback каждого runtime-шага — config flag без удаления state/history.

## 19. Критерии приёмки

- Все Telegram RPC polling path учитываются по account и kind.
- Любой FloodWait виден в metrics и немедленно блокирует аккаунт.
- Ни один RPC не выполняется до `cooldown_until`.
- Long FloodWait не возвращается сразу в 100%.
- PAUSED/SLEEPING останавливает текущую выдачу задач.
- География без подписчиков даёт ноль polling RPC.
- Dashboard показывает current/required/reserve accounts.
- Recommendation совпадает с тестовой capacity-моделью.
- При падении нагрузки мощность автоматически восстанавливается ступенчато.
- SLO A/B измеряется и не маскируется усреднением.
- Полный regression suite и admin build зелёные.
- Production rollout соблюдает `OPERATIONS.md`, worker stop и отдельное
  подтверждение владельца.

## 20. Следующий артефакт

После review этого design-spec создаётся подробный implementation plan и единый
промпт для Cursor Grok 5.4. Промпт обязан:

- запретить одномоментную реализацию без фаз;
- требовать TDD;
- перечислить файлы только после повторного аудита актуального `origin/main`;
- включить миграции, API, UI, alerts, tests и rollout;
- запрещать production mutation;
- требовать чтение `OPERATIONS.md` перед poller/rate-limiter изменениями;
- завершать каждую фазу commit, tag и phase review.
