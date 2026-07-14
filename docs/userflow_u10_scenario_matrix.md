# U10 — сквозная сценарная матрица user flow

Дата: 14.07.2026  
Ветка: `feature/codex-userflow-v2`  
Checkpoint перед U10: `2fa3968`

## Правила прогона

- Каждая строка выполняется отдельно на RU и EN.
- Для каждого экрана проверяются текст, клавиатура, переход вперёд, `Назад`,
  `/cancel`, пустое состояние и применимый error path.
- Фактический результат отмечается только после ручного или staging-прогона.
- Live-платежи, миграции и rollout не входят в локальный автоматический прогон.
- Любой CTA считается прошедшим только при подтверждённом server-side действии,
  а не по наличию кнопки.

Статусы: `AUTO` — покрыто автоматическим U10 gate; `STAGING` — нужен тестовый бот,
БД или платёжный sandbox; `LIVE` — проверяется только на ограниченной когорте.

## Матрица персон

| Persona | Подготовка | Основной путь | Back / cancel / empty / error | RU | EN | Gate |
|---|---|---|---|---:|---:|---|
| Новый direct | новый `source=direct` | `/start` → язык → направление → страна → города → подтверждение → первый поиск → trial | назад на каждом шаге; `/cancel`; нет категорий/стран/городов; повторный callback | ☐ | ☐ | AUTO + STAGING |
| Новый referral | новый deep-link `ref_CODE` | `/start ref_CODE` → язык → первый поиск → trial 8 дней | неверный/self/used code; отмена FSM; повторный `/start` | ☐ | ☐ | AUTO + STAGING |
| Free с лидами | Free, lifecycle day 0/3/7/14, matched > 0 | скрытый lead → contextual paywall → EOD total/delivered/missed → тариф | токен лида истёк; нет sender/link; назад из paywall | ☐ | ☐ | AUTO + STAGING |
| Free без лидов | Free, lifecycle day 0, matched = 0 | zero-lead diagnostic → «Проверить поиски» | пустые поиски; день 3/7/14 не создаёт лишнее сообщение | ☐ | ☐ | AUTO + STAGING |
| Trial ending | Trial, expiry через 2/1 день | reminder → планы → период → способ оплаты | назад до plan; invoice failure/expiry | ☐ | ☐ | AUTO + STAGING |
| Start | активный Start | меню → поиски → lead с контактами → renewal | лимит второго направления/страны/города; пустая статистика; cancel input | ☐ | ☐ | AUTO + STAGING |
| Pro | активный Pro | 3 направления/3 страны/9 городов → stats → renewal | 10-й distinct-город; CSV paywall; пустые stats | ☐ | ☐ | AUTO + STAGING |
| Business | активный Business | 12 направлений/9 стран → stats → CSV → renewal | превышение страны/направления; пустой CSV | ☐ | ☐ | AUTO + STAGING |
| Paid in grace | expiry достигнут | точный downgrade в Free → новые leads без контактов | старый callback; повторный scheduler run; кэш после downgrade | ☐ | ☐ | AUTO + STAGING |
| Former paid | Free после expiry, lifecycle day 30 | one-time 25%/3m offer → тариф → оплата | offer expired/redeemed; повторный scheduler run | ☐ | ☐ | AUTO + STAGING |
| Payment failed/expired | invoice failed или expired | retry → другой способ → назад → успешная активация | provider unavailable; повторный webhook; неверный payload | ☐ | ☐ | AUTO + STAGING |
| Private/numeric chat | payload с `-100…`, есть/нет title | lead показывает title, private `t.me/c` только paid | title отсутствует; нет sender; Free не содержит ссылок | ☐ | ☐ | AUTO + STAGING |

## Обязательные поверхности на каждую persona

| Семейство | Happy path | Empty/error path | Навигация |
|---|---|---|---|
| Welcome / language | язык сохраняется, следующий экран локализован | неизвестный язык → RU fallback | новый → catalog; returning → menu |
| Catalog FSM | категория → услуга → страна → geo → confirm → commit | лимиты, отсутствующие сущности, повторный callback | back не теряет корректный state; `/cancel` очищает FSM |
| Searches | список отражает committed subscriptions | пустой список; delete missing | add/delete confirm/back |
| Keywords / channels | add/delete в пределах тарифа | short/invalid/private/limit | cancel и back в settings |
| Menu / settings | план, expiry, счётчики и кнопки соответствуют persona | нулевые счётчики | все callbacks существуют |
| Lead | Free скрывает ссылки; paid показывает только доступные ссылки | numeric/private/no sender | feedback и paywall callbacks валидны |
| Plans / payment | цены и скидки из runtime settings | failed/expired/unavailable | plan ↔ period ↔ method ↔ retry |
| Lifecycle | trial ending, exact expiry, EOD, renewal, winback | дедуп, zero leads, expired offer | CTA ведёт в ожидаемый plan/search |

## Автоматический U10 gate

`tests/test_userflow_u10_snapshots.py` генерирует RU/EN text+keyboard snapshots
из locale schema и чистых runtime builders. Он проверяет:

- одинаковые locale keys и placeholders;
- отсутствие неразрешённых placeholders;
- Telegram message/caption и callback limits;
- сбалансированный разрешённый HTML;
- отсутствие кириллицы в EN, кроме намеренно двуязычного language picker;
- отсутствие неподтверждённых обещаний из deny-list;
- цены, тарифные CTA, back actions и Free/Paid/private lead contract.

Автоматический gate не заменяет ручные `STAGING`/`LIVE` отметки выше.

## Rollout checklist (не выполнять без отдельной команды владельца)

1. Применить `winback_u89` в staging после backup и проверить single head.
2. Пройти все строки матрицы RU/EN на internal test users.
3. Выполнить Stars sandbox/minimal invoice и CryptoBot testnet сценарии.
4. Включить ограниченную когорту новых пользователей с rollback на checkpoint.
5. Сравнить completion/payment/support/error metrics до расширения до 100%.
6. Не менять polling/core matching и не выполнять production-команды в рамках U10.
