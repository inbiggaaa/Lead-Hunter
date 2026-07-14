# U10.3 — editorial and functional review backlog

Дата аудита: 14.07.2026
Ветка: `feature/codex-userflow-v2`
Режим: read-only review; точечные правки отложены до ручного userflow-теста владельца.

## Статус

U10.3 не закрыта. Этот документ фиксирует кандидатов, которые нужно проверить
на реальном экране RU и EN. Текст меняется только после подтверждения владельцем
во время ручного прогона.

Метки:

- `BUG` — текст явно повреждён или не соответствует входным данным;
- `CLAIM` — формулировку нужно сверить с фактической гарантией продукта;
- `EDITORIAL` — естественность и единообразие без изменения функции;
- `FUNCTIONAL` — CTA нужно пройти до server-side результата.

## Подтверждённые находки для ручного прогона

| ID | Экран / locale key | Тип | Наблюдение | Что проверить руками | Решение |
|---|---|---|---|---|---|
| E-01 | RU `channels_prompt` | BUG | «Отправь  канала. Например: .» — потеряны тип входа и пример | Экран добавления канала и `/cancel` | ☐ |
| E-02 | EN `channels_prompt` | BUG | “Send a channel , for example: .” — та же потеря | Add channel screen and `/cancel` | ☐ |
| E-03 | RU/EN `channel_invalid` | BUG | «Некорректный .» / “Invalid .” — потерян объект ошибки | Невалидный username, invite link, numeric id | ☐ |
| E-04 | EN `plan_card_start` | CLAIM | “full contacts” сильнее фактического контракта: Telegram может не дать sender/link | Start plan card + paid lead без sender | ☐ |
| E-05 | RU `plan_card_start` | CLAIM | «контакты открыты» может читаться как гарантия наличия контакта | Start plan card + paid lead без sender | ☐ |
| E-06 | RU/EN `welcome_body` | CLAIM | «контакты, ссылки» / “contacts, chat links” без оговорки об их доступности | Новый пользователь до первого поиска | ☐ |
| E-07 | RU/EN `eod_body` | CLAIM | CTA обещает новые заявки «с контактами и ссылкой» без оговорки available | Free с matched/delivered/missed | ☐ |
| E-08 | RU/EN plan cards | EDITORIAL | «рекомендуем» / “recommended” — продуктовая рекомендация, не измеренное “most popular” | Согласовать, оставлять ли editorial recommendation | ☐ |
| E-09 | RU/EN period | EDITORIAL | «оптимальный выбор» / “best value” подтверждается скидкой, но тон нужно оценить в общей воронке | 1m → 3m → 1y экран | ☐ |

## Business review

- Цены `$9/$19/$39`, скидки 3 месяца −10% и год −20% берутся из runtime
  settings/builders; менять их в U10.3 нельзя.
- «Уведомления без лимита» соответствует тарифной модели v2.1.
- Business «города без лимита в этих странах» квалифицировано выбранными девятью
  странами и не нарушает deny-list.
- Winback 25% на 3 месяца/12 часов — согласованная серверная механика; countdown
  не искусственный.
- Частоту lifecycle-сообщений в редакционном проходе не увеличивать.

## Functional CTA review

Статический аудит показал пары emitter/handler для основных callback families:

- `menu:*`: main/search/subs/stats/plan/referral/settings/language/keywords/
  channels/digest/csv/instructions/about;
- `cat:*`: category/segment/country/geo/city/confirm/back;
- `kw:*`, `ch:*`, `sub:*`: add/delete/confirm/cancel;
- `pay_plan:*`, `pay_period:*`, `pay_exec:*`: plan/period/provider/error retry;
- `winback:buy:*`, `winback:pay:*`: offer/plan/provider;
- `lead:unlock:*`, `fb:*`: contextual paywall and feedback.

Статическое наличие handler не закрывает FUNCTIONAL gate. При ручном прогоне для
каждого CTA фиксируются: экран назначения, сохранение state, server-side guard,
analytics event и повторный callback.

## Порядок совместного ручного прохода

1. Новый direct RU, затем EN; записывать текст до нажатия каждой кнопки.
2. Channel add/error paths — принять решения E-01–E-03.
3. Free lead → EOD → paywall и paid lead без sender — E-04–E-07.
4. Plan → period → payment error — E-08–E-09 и CTA chain.
5. Referral, trial ending, exact expiry, former paid/winback.
6. После согласования внести только подтверждённые точечные locale/test changes.

## Ограничения checkpoint

- Locale и production-код не изменялись.
- Автоматический suite не запускался: исполняемый код не менялся.
- Ручные RU/EN отметки сценарной матрицы остаются пустыми.
- U10.4 rollout и U10.5 сравнение метрик не начинались.
