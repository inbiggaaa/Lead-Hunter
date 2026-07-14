# Карта экранов и текстов LeadHunter — для ручной правки

Дата: 14.07.2026. Ветка `feature/codex-userflow-v2`. Источник истины — runtime-код.
Назначение: по этой карте ты находишь **где лежит текст любого экрана** и правишь его руками.

Смежные документы: `docs/userflow_screen_registry.md` (компактный реестр «экран → callback → функция → тест»), `USERFLOW.md` (полные тексты RU+EN), `codex_userflow.md` (план флоу и воронок).

---

## 0. Как устроены тексты (прочитать один раз)

Есть **два источника** пользовательского текста:

### Источник 1 — locale-файлы (≈90% всех текстов)

- `app/locales/ru.py` — русский (продуктовый источник истины)
- `app/locales/en.py` — английский (полный паритет)

Каждый текст — это пара «ключ → строка», например:
```python
"trial_started": "🎉 Поиск запущен! Триал Про действует до {date}.",
```
В коде он вызывается как `get_text(lang, "trial_started", date=...)`.

**Как править:** находишь ключ в `ru.py`, меняешь строку. Затем меняешь **тот же ключ** в `en.py`.

**3 жёстких правила (иначе бот упадёт на старте):**
1. Ключ должен существовать в **обоих** файлах (`ru.py` и `en.py`) — набор ключей обязан совпадать.
2. Плейсхолдеры `{...}` должны быть **идентичны** в RU и EN (и по составу, и по написанию). Например, если в RU есть `{date}` и `{count}` — в EN должны быть ровно `{date}` и `{count}`.
3. Не удаляй ключ, если он ещё используется в коде.

Проверка после правки (не трогает прод):
```bash
venv/bin/python -c "from app.locales import validate_locale_schema; validate_locale_schema(); print('OK')"
```

Структура `ru.py` (секции-комментарии `# ── ... ──`):
| Строки | Секция | Экраны |
|---|---|---|
| ~4 | Приветственный экран | welcome_* |
| ~24 | Onboarding wizard | onb_* (legacy, сейчас не открывается) |
| ~37 | Главное меню | menu_*, btn_* |
| ~59 | Общие | btn_back, btn_cancel, error_* |
| ~66 | Язык | language_set, btn_ru, btn_en |
| ~71 | Тариф и оплата | plan_*, pay_* |
| ~98 | End-of-day отчёт Free | eod_* |
| ~113 | Статистика | stats_* |
| ~131 | Контекстные пейволлы | paywall_* |
| ~141 | Ошибка оплаты | pay_error_* |
| ~150+ | (без заголовков) | catalog_*, search_*, keyword*, channel*, searches_*, referral_*, digest_*, lead_*, winback_*, reminder_*, trial_*, csv_*, feedback_*, support_* |

Ключи после ~150 строки не сгруппированы комментариями — ищи по ключу (`grep`).

### Источник 2 — захардкоженный текст в хендлерах (≈10%)

Небольшая часть строк вписана прямо в `.py`-файлы (кнопки, названия тарифов, экран выбора языка). Полный список — раздел **§3** ниже.

### Чтобы правка появилась в боте

Тексты монтируются в контейнер томом, но процесс подхватывает их **только при рестарте**:
```bash
docker compose restart bot   # только bot, worker НЕ трогать при работающем worker
```
⚠️ Правило проекта: не запускать `docker compose up -d/run/build` при работающем `worker` (риск двойной нагрузки на Telegram API). Рестарт **именно `bot`** — безопасен (Bot API), worker остаётся нетронутым.

---

## 1. Карта экранов по пути пользователя

Легенда колонки «Текст»: `locale: prefix_*` → ключи в `ru.py`+`en.py`; `hardcode: file:line` → строка прямо в коде (см. §3).

### A. Старт, язык, приветствие

| Экран | Когда | Код (функция) | Текст |
|---|---|---|---|
| Приветствие | `/start`, новый пользователь | `start.cmd_start` → `start._show_welcome` | `locale: welcome_*` |
| Выбор языка | внутри приветствия | `discover.on_language` / `start` | `locale: btn_ru, btn_en, language_set` · **hardcode:** `discover.py:23-25` («Выбери язык / Choose language», кнопки 🇷🇺/🇬🇧) |
| Onboarding wizard (legacy) | `onb:*` | `discover` / callbacks | `locale: onb_*` — сейчас флоу их не открывает |

### B. Главное меню

| Экран | Когда | Код | Текст |
|---|---|---|---|
| Главное меню | `menu:main`, `/start` (returning), `/cancel` | `start._show_menu_from_db` / `start._menu_keyboard` | `locale: menu_*, btn_*` · **hardcode:** кнопки Инструкции/Настройки `start.py:380,387` |

### C. Воронка поиска (FSM CatStates)

| Экран | Когда | Код (`catalog_nav.py`) | Текст |
|---|---|---|---|
| Категории | `menu:search`, `/search` | `on_search` | `locale: search_*` + названия категорий из БД |
| Направления категории | `cat:open:*` | `on_category_opened` | `locale` + `title_ru/title_en` сегментов из БД |
| Выбор направлений | `cat:seg:*`, `cat:to_country` | `on_toggle_segment`, `on_to_country` | `locale` + alert'ы |
| Выбор страны | `cat:country:*` | `on_country_chosen` | `locale: catalog_country_line` + `name_ru/name_en` из БД |
| Гео: вся страна / города | `cat:geo:all`, `cat:geo:cities` | `on_geo_*` | `locale` |
| Выбор городов | `cat:city:*`, `cat:cities_done` | обработчики городов | `locale` + названия городов из БД · **hardcode:** кнопка «✅ Готово (N)» `catalog_nav.py:481` |
| **Подтверждение поиска** | состояние `confirm_subscription` | `_show_confirmation` | `locale: catalog_confirm, catalog_country_line, catalog_cities_line, search_scope_services, catalog_activate, catalog_activate_hint` |
| **Экран после запуска (+приглашение к тарифу)** | `cat:subscribe` | `on_subscribe` | `locale: trial_started, search_created, search_added, search_delivery, search_upsell_after, free_after_search` + кнопки `btn_plan, btn_searches, btn_main_menu, lead_btn_unlock` |
| Запрос новой категории | `support:missing_category` | `on_request_category` | **hardcode:** `catalog_nav.py:903,909-911` |

### D. Мои поиски

| Экран | Когда | Код (`catalog_nav.py`) | Текст |
|---|---|---|---|
| Список поисков | `menu:subs`, `/subscriptions` | `on_show_subscriptions` | `locale: searches_title, searches_empty, searches_countries` · **hardcode:** fallback-подписи `catalog_nav.py:835-836` |
| Удаление поиска | `sub:del:*` | `on_unsubscribe` | `locale` + alert |

### E. Ключевые слова

| Экран | Когда | Код (`keywords.py`) | Текст |
|---|---|---|---|
| Список / ввод / удаление | `menu:keywords`, `/keywords`, `kw:add`, `kw:del:*` | keywords handlers | `locale: keywords_title, keywords_prompt, keyword_command_blocked` + `paywall_*` |

### F. Свои каналы

| Экран | Когда | Код (`channels.py`) | Текст |
|---|---|---|---|
| Список / ввод / удаление | `menu:channels`, `/channels`, `ch:add`, `ch:del:*` | channels handlers | `locale: channels_title, channels_prompt, channel_invalid, channel_private_pending` + `paywall_*` · **hardcode:** подпись «группа …» `channels.py:58` |

### G. Настройки и подэкраны

| Экран | Когда | Код | Текст |
|---|---|---|---|
| Настройки | `menu:settings`, `/settings` | `discover` / `start` builders | `locale` (частично hardcode-кнопки) |
| Статистика | `menu:stats`, `/stats` | `discover.build_stats_screen` | `locale: stats_*` |
| CSV-экспорт | `menu:csv` | `discover.on_csv` | `locale: csv_caption, csv_empty` |
| Digest-режим | `menu:digest`, `digest:*` | `discover` digest handlers | `locale: digest_*` |
| Инструкции | `menu:instructions` | `discover` | `locale: instructions_body` |
| О сервисе | `menu:about` | `discover` | `locale: about_body` |
| Пригласить друга | `menu:referral`, deep-link | `discover` / `start` referral | `locale: referral_body, referral_reward, referral_share, referral_share_btn` |

### H. Тариф и оплата

| Экран | Когда | Код (`plan.py`) | Текст |
|---|---|---|---|
| Экран тарифов | `menu:plan`, `/plan` | `build_plan_screen` | `locale: plan_title, plan_current, plan_card_start/pro/business, plan_discounts, plan_btn_*` · **hardcode:** названия тарифов `plan.py:18-20,61` |
| Выбор периода | `pay_plan:*` | `on_plan_chosen` | `locale: plan_period_*` · **hardcode:** названия периодов `plan.py:21-23` |
| Способ оплаты | `pay_period:*` | period handler | `locale` |
| Оплата (Stars/Crypto) | `pay_exec:*`, pre-checkout | `plan` + `payments/*` | `locale` + один RU-alert |
| Успешная оплата | success / crypto checker | `plan` / `payment_checker` | `locale` (частично hardcode в Stars) |
| Ошибка оплаты | invoice error/expired | `plan._payment_error_kb` | `locale: pay_error_*` |
| Годовой апселл | 2-й месячный платёж подряд | `plan` (annual offer) | `locale` |
| Уведомление о реф-оплате (админу) | реферал оплатил | `plan` | **hardcode:** `plan.py:382-383` |

### I. Уведомления о заявках (лиды)

| Экран | Кому | Код (`worker/sender.py`) | Текст |
|---|---|---|---|
| Лид Free (контакты скрыты) | Free | `sender` | `locale: lead_title, lead_hidden, lead_tags, lead_btn_unlock` (без ссылок, решение #79) |
| Лид Paid | Старт/Профи/Бизнес/Trial | `sender` | `locale: lead_title, lead_chat, lead_sender, lead_tags, lead_btn_chat, lead_btn_sender` · **hardcode:** подпись «группа …» `sender.py:47` |

### J. Оценка лида (feedback)

| Экран | Когда | Код (`feedback.py`) | Текст |
|---|---|---|---|
| Кнопки/благодарность | `fb:*` | feedback handler | `locale: feedback_thanks, feedback_not_relevant` |

### K. Поддержка

| Экран | Когда | Код (`support.py`) | Текст |
|---|---|---|---|
| Приём обращения | свободный текст | support handler | `locale: support_sent` · **hardcode:** уведомление админу `support.py:33` |

### L. Lifecycle-сообщения (авто, воркеры)

| Сообщение | Когда | Код | Текст |
|---|---|---|---|
| End-of-day отчёт Free | 19:00, дни 0/3/7/14 | `worker/end_of_day.py` | `locale: eod_body, eod_zero, eod_btn_*, eod_zero_btn` |
| Триал заканчивается | за 2/1 дня | `worker/reminders.py` | `locale: trial_after` + `reminder_btn_*` |
| Триал истёк / подписка истекла | дни 1/3/7 | `worker/reminders.py` | `locale` + `reminder_btn_renew/plans/other_plans` |
| Winback (день 30, скидка 25%) | после даунгрейда | `worker/reminders.py` | `locale: winback_offer, winback_expired, winback_payment_title, winback_btn_*` |
| Digest-дайджест | по расписанию | `worker/digest.py` | `locale: digest_header, digest_instant/hourly` |

### M. Пейволлы и ошибки

| Экран | Когда | Код (`plan.py`) | Текст |
|---|---|---|---|
| Контекстный пейволл | лимит направлений/стран/keywords/каналов/stats/csv | `paywall_text`, `build_paywall` | `locale: paywall_*` |
| Общие alert-ошибки | not found / deleted / generic | во всех хендлерах | `locale: error_*` (частично RU-hardcode alert'ы) |

---

## 2. Быстрый workflow правки текста

1. Найди ключ по фрагменту текста:
   ```bash
   grep -rn "часть текста" app/locales/ru.py
   ```
2. Правишь строку в `app/locales/ru.py`.
3. Правишь **тот же ключ** в `app/locales/en.py` (плейсхолдеры `{...}` — идентичны).
4. Проверка паритета: `venv/bin/python -c "from app.locales import validate_locale_schema; validate_locale_schema(); print('OK')"`
5. Применить в проде: `docker compose restart bot` (worker не трогать).

Для захардкоженных строк (§3) — правь прямо в `.py`-файле по указанному адресу, RU и EN обычно в одной строке через `if lang == "ru" else`.

---

## 3. Индекс захардкоженных пользовательских строк (не в locale)

Эти тексты правятся прямо в коде:

| Файл:строка | Что это |
|---|---|
| `app/bot/handlers/discover.py:23-25` | Экран выбора языка: «Выбери язык / Choose language», кнопки 🇷🇺 Русский / 🇬🇧 |
| `app/bot/handlers/start.py:228` | Кнопка «💬 Нет вашего вида деятельности? Связаться с поддержкой» (RU/EN inline) |
| `app/bot/handlers/start.py:380` | Кнопка «📖 Инструкции / Instructions» |
| `app/bot/handlers/start.py:387` | Кнопка «⚙️ Настройки / Settings» |
| `app/bot/handlers/catalog_nav.py:481` | Кнопка «✅ Готово (N)» на выборе городов |
| `app/bot/handlers/catalog_nav.py:835-836` | Fallback-подписи «Сегмент #N» / «Страна #N» в списке поисков |
| `app/bot/handlers/catalog_nav.py:903,909-911` | Экран «Запрос новой категории» |
| `app/bot/handlers/channels.py:58` | Подпись «группа {username}» для приватных групп |
| `app/bot/handlers/plan.py:18-20` | Названия тарифов: «Старт», «Профи», «Бизнес» (dict `PLANS`) |
| `app/bot/handlers/plan.py:21-23` | Названия периодов: «1 месяц», «3 месяца (-10%)», «1 год (-20%)» |
| `app/bot/handlers/plan.py:59-62` | Отображаемые имена планов (dict `PLAN_DISPLAY`, RU+EN) |
| `app/bot/handlers/plan.py:382-383` | Уведомление админу о реферальной оплате |
| `app/bot/handlers/support.py:33` | Уведомление админу о новом обращении |
| `app/worker/sender.py:47` | Подпись «группа {chat}» в уведомлении о лиде |

Названия категорий/направлений, стран и городов — **не в коде и не в locale**, а в БД (таблицы `segments`, `countries`, `cities`, поля `*_ru`/`*_en`). Правятся через админку `/catalog`.
