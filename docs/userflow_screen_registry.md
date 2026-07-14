# Реестр пользовательских поверхностей LeadHunter

Дата baseline: 14.07.2026. Фаза: U0. Источник истины — runtime-код. Одна строка описывает экран или семейство однотипных состояний; все перечисленные callbacks и команды входят в это семейство.

| ID | Entry points / события | Аудитория | RU / EN | Данные | Primary CTA / назад | Functional proof |
|---|---|---|---|---|---|---|
| START-01 | `/start`, новый пользователь | все | `welcome_*`, `btn_ru`, `btn_en` | User, referral code, config | выбрать язык / — | `start.cmd_start`, `test_language.py` |
| START-02 | `lang:ru`, `lang:en`, `menu:language` | все | `language_set`, language screen + buttons | `users.language` | продолжить / settings | `start.on_language_select`, `discover.on_language` |
| ONB-LEGACY | `onb:cat:*`, `onb:country:*`, `onb:skip:*` | новый | `onb_*` | Country, config | закончить onboarding | callbacks существуют, но текущий `lang:*` их не открывает |
| MENU-01 | `menu:main`, `/start` returning, `/cancel` | все | `menu_*`, `btn_*` | User, Redis matched today | поиск / — | `start._show_menu_from_db`, menu tests |
| SEARCH-01 | `menu:search`, `/search`, `cat:back:to_categories` | все | частично locale, частично hardcode | Category, User, tariff limits | выбрать категорию / main | `catalog_nav.on_search`, `start.cmd_search` |
| SEARCH-02 | `cat:open:*` | все | hardcode + localized DB titles | Segment, current searches | выбрать направления / categories | `catalog_nav.on_category_opened` |
| SEARCH-03 | `cat:seg:*`, `cat:to_country` | все | hardcode alerts | selected segments, limits | выбрать страну / category | `catalog_nav.on_toggle_segment`, `on_to_country` |
| SEARCH-04 | `cat:country:*` | все | localized DB names, hardcode frame | Country, existing countries | выбрать географию / categories | `catalog_nav.on_country_chosen` |
| SEARCH-05 | `cat:geo:cities`, `cat:geo:all` | все; оба режима доступны всем | RU/EN inline | plan, Country | города или вся страна / country | server guard + geo tests |
| SEARCH-06 | `cat:city:*`, `cat:cities_done` | Free/Start/Pro/Trial/Business | hardcode + DB names | selected cities, no city limit | подтвердить города / geo | `get_user_city_ids`, geo tests |
| SEARCH-07 | confirmation state | все | hardcode | FSM selection, DB names | создать поиск / categories | `_show_confirmation` |
| SEARCH-08 | `cat:subscribe` | все | hardcode | User, Subscription, cache | открыть список поисков / main | `on_subscribe`, повторная server validation |
| SEARCH-ERR | search callback alerts, missing category | все | mixed hardcode | validation/support target | исправить выбор / предыдущий шаг | catalog router branches |
| SEARCHES-01 | `menu:subs`, `/subscriptions` | все | mixed hardcode | subscriptions, countries, cities | добавить/удалить / settings or main | `on_subscriptions`, `_show_subscriptions_via_message` |
| SEARCHES-02 | `sub:del:*` | все | RU hardcode alert | Subscription | удалить / список | `on_unsubscribe` |
| KEYWORDS-01 | `menu:keywords`, `/keywords` | все | mixed | Keyword, plan limits | добавить/удалить / settings | keywords handlers |
| KEYWORDS-02 | `kw:add`, FSM text, `kw:del:*` | все | RU hardcode + paywall locale | Keyword, limits | сохранить / список | keywords handlers + tariff tests |
| CHANNELS-01 | `menu:channels`, `/channels` | все | mixed | WatchedChat, limits | добавить/удалить / settings | channels handlers |
| CHANNELS-02 | `ch:add`, FSM username, `ch:del:*` | все | RU hardcode + paywall locale | Telegram entity, limits | сохранить / список | channels handlers/tests |
| SETTINGS-01 | `menu:settings`, `/settings` | все | mixed | User | открыть настройку / main | discover/start settings builders |
| STATS-01 | `menu:stats`, `/stats` | Pro/Trial/Business; paywall others | locale | sent_log, Redis segment stats | тариф или назад / settings | `build_stats_screen`, tariff tests |
| CSV-01 | `menu:csv` | Business; paywall others | locale | sent_log metadata, 30 days | получить CSV / settings | `on_csv`, CSV tests |
| DIGEST-01 | `menu:digest`, `digest:*` | все | locale | `users.digest_mode` | выбрать режим / settings | discover + digest worker tests |
| HELP-01 | `menu:instructions` | все | inline RU/EN | config | поиск / settings | discover handler |
| ABOUT-01 | `menu:about` | все | inline RU/EN | config prices/trial | поиск / settings | discover handler |
| SUPPORT-01 | свободный текст, `support:missing_category` | все | RU hardcode/mixed | support channel | отправить обращение / search | support/catalog handlers |
| REF-01 | `menu:referral`, referral deep link | все | inline RU/EN | Referral, config bonus | поделиться / main | discover + start referral processing |
| PLAN-01 | `menu:plan`, `/plan` | все | `plan_*` | User, config prices | выбрать тариф / main | shared `build_plan_screen`, plan tests |
| PLAN-02 | `pay_plan:*` | все | mixed; back RU-hardcode | PLANS, current plan | выбрать период / plan | plan handler/tests |
| PLAN-03 | `pay_period:*` | все | locale | configured discounts | способ оплаты / plan | plan handler/tests |
| PAY-01 | `pay_exec:*`, pre-checkout | все | locale + one RU alert | provider/config | оплатить / period | Stars/Crypto handlers |
| PAY-02 | successful payment, crypto checker | payer | RU-hardcode in Stars; locale partial in crypto | Payment, User expiry, cache | открыть bot/menu | plan/payment_checker tests |
| PAY-ERR | invoice error/expired/provider unavailable | payer | locale + RU alert | provider response | повторить / plan | error branches |
| PAYWALL-01 | keyword/channel/direction/country/city/stats/csv | restricted plans | `paywall_*` | trigger, next plan, config price | upgrade / source screen | paywall component/tests |
| LEAD-FREE | queue/digest lead | Free | RU-hardcode | event payload, plan | открыть тариф, feedback | sender tests; no contact links by decision #79 |
| LEAD-PAID | queue/digest lead | Start/Pro/Trial/Business | RU-hardcode | payload with chat/sender/title | чат/автор, feedback | sender tests |
| FEEDBACK-01 | `fb:*:*:*` | все | mixed RU/EN hardcode | Feedback, message identity | confirm rating | feedback handler |
| EOD-01 | daily Free report | Free with leads | locale | daily matched/sent counters | upgrade | end_of_day + tests |
| TRIAL-01 | trial ending 2/1 days | Trial | RU-hardcode | expiry/config | upgrade | reminders + tests |
| TRIAL-02 | trial expired 1/3/7 | downgraded Free | RU-hardcode | expiry/sent_log | upgrade/search | reminders + tests |
| RENEW-01 | paid ending 5 days | paid | RU-hardcode | plan expiry/config | renew current plan | reminders + tests |
| GRACE-01 | paid expired 1/3/7 | expired paid during grace | RU-hardcode | expiry | renew | reminders; downgrade after day 7 |
| WINBACK-01 | missed leads 14/28 after downgrade | former payer | RU-hardcode | sent_log, payment history | subscribe | reminders + metric |
| PERIODIC-01 | weekly/niche/monthly scheduler | Free | RU-hardcode | schedule, PeriodicPref | upgrade | reminders scheduler |
| INACTIVE-01 | day 14/28 | all matching query | RU-hardcode | currently `created_at` | return | known defect: not real activity |
| CALLBACK-ERR | generic Error/not found/deleted alerts | all | mixed/RU-hardcode | branch-specific | retry/back | inventoried in handlers; localization U1 |

## Правило покрытия

Каждый пользовательский `@router` относится к одной из строк START, MENU, SEARCH, SEARCHES, KEYWORDS, CHANNELS, SETTINGS, STATS, CSV, DIGEST, HELP, ABOUT, SUPPORT, REF, PLAN, PAY, FEEDBACK или CALLBACK-ERR. Каждая отправка из `sender`, `digest`, `end_of_day`, `reminders` и `payment_checker` относится к LEAD, EOD, TRIAL, RENEW, GRACE, WINBACK, PERIODIC, INACTIVE или PAY. `notify_admin.py` исключён: это admin-only поверхность.

## Известные системные долги baseline

- Locale schema отсутствует: handlers и workers содержат пользовательский hardcode.
- Команды и callbacks иногда рендерят разные реализации одного экрана.
- Нет автоматического snapshot-покрытия реестра; оно запланировано в U10.
- Реестр фиксирует baseline U0; статусы меняются при каждой следующей фазе.
