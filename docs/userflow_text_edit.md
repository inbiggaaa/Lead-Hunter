# Редактируемый черновик текстов LeadHunter (все экраны, RU+EN)

Дата сборки: 15.07.2026. Ветка `feature/codex-userflow-v2`.
Источник: `app/locales/ru.py` + `app/locales/en.py` (актуальные значения на момент сборки).

## Как пользоваться этим файлом

1. Правь текст **между кавычками-ёлочками** `«...»` или внутри блоков. Меняй только сам текст.
2. **НЕ трогай** `{...}` (плейсхолдеры — бот подставит туда данные) и HTML-теги `<b>...</b>`, `<a ...>`. Если удалить/переименовать `{date}` — бот упадёт.
3. `\n` в блоках уже показан как реальный перенос строки — просто пиши как есть, я переведу обратно.
4. Каждый ключ есть и в RU, и в EN — правь обе версии (или скажи «EN сделай сам по смыслу»).
5. Когда закончишь (полностью или частично) — скажи мне, я перенесу изменённые ключи в `ru.py`/`en.py`, прогоню валидацию + тесты и сделаю `docker compose restart bot`.

Отметка «✏️» рядом с ключом можешь ставить сам, чтобы я видел, что именно ты правил (необязательно).

---

## ⚠️ 0. Требует восстановления (тексты повреждены)

### channels_prompt
Сейчас потеряны слово «ссылку/юзернейм» и пример. Впиши корректный текст.
```
RU: Отправь  канала. Например: .

Доступно ещё: {remaining}/{limit} ({plan})

/cancel — отмена.
```
```
EN: Send a channel , for example: .

Available: {remaining}/{limit} ({plan})

/cancel — cancel.
```

### channel_invalid
```
RU: Некорректный . Попробуй ещё раз или отправь /cancel.
```
```
EN: Invalid . Try again or send /cancel.
```

---

## A. Старт, язык, приветствие

### welcome_title  (заголовок первого экрана — сейчас один и тот же в RU и EN)
```
🎯 <b>Lead Hunter AI — клиенты уже ищут твои услуги в Telegram!</b>
```

### welcome_body  (тело приветствия — сейчас двуязычный текст в одном сообщении, RU+EN подряд)
```
Выбери направление деятельности и географию — <b>Lead Hunter AI</b> будет отслеживать новые сообщения и находить подходящие запросы клиентов.

В базе сервиса — более 5.000+ Telegram-чатов и каналов. Узнавай о новых запросах раньше и первым предлагай свои услуги! Запусти первый поиск и <b>бесплатно попробуй возможности тарифа Про</b> в течение 3 дней.


🎯 <b>Lead Hunter AI — potential clients are already looking for your services on Telegram!</b>

Choose your industry and target location — <b>Lead Hunter AI</b> will monitor new messages and find relevant customer requests.

The Lead Hunter AI database includes more than 5.000+ Telegram chats and channels. Discover new opportunities sooner and be the first to offer your services! Launch your first search and <b>try Pro features free</b> for 3 days.
```

### welcome_lang_prompt  (одинаково RU/EN)
```
Выбери язык / Choose language:
```

### Выбор языка — кнопки
- `btn_ru` — «🇷🇺 Русский» | EN «🇷🇺 Русский»
- `btn_en` — «🇬🇧 English» | EN «🇬🇧 English»
- `language_set` — RU «✅ Язык установлен: Русский» | EN «✅ Language set: English»

---

## B. Главное меню

### Строки статуса меню
- `menu_header` — RU «🎯 Lead Hunter AI» | EN «🎯 Lead Hunter AI»
- `menu_plan` — RU «Твой тариф: {plan}» | EN «Your plan: {plan}»
- `menu_searches` — RU «🎯 Активных подписок: {count}» | EN «🎯 Active subscriptions: {count}»
- `plan_until` — RU «до {date}» | EN «until {date}»
- `menu_notifications` — RU «📬 Заявок сегодня: {matched}» | EN «📬 Leads today: {matched}»
- `menu_free_hidden` — RU «🔒 Подключите платный тариф для просмотра контактов» | EN «🔒 Upgrade to a paid plan to view contact details»

### Кнопки меню
- `btn_search` — RU «🚀 Настроить первый поиск» | EN «🚀 Set up first search»
- `btn_searches` — RU «🎯 Мои поиски» | EN «🎯 My searches»
- `btn_results` — RU «📥 Заявки и результаты» | EN «📥 Leads & results»
- `btn_keywords` — RU «⚙️ Мои ключевые слова» | EN «⚙️ My keywords»
- `btn_channels` — RU «📢 Мои каналы» | EN «📢 My channels»
- `btn_subscriptions` — RU «🎯 Мои подписки» | EN «🎯 My subscriptions»
- `btn_referral` — RU «🎁 Пригласить друга» | EN «🎁 Invite a friend»
- `btn_plan` — RU «💰 Тариф и оплата» | EN «💰 Plan & payment»
- `btn_language` — RU «🌐 Язык / Language» | EN «🌐 Language»
- `btn_settings` — RU «⚙️ Настройки» | EN «⚙️ Settings»
- `btn_about` — RU «ℹ️ О сервисе» | EN «ℹ️ About»
- `btn_main_menu` — RU «🏠 Главное меню» | EN «🏠 Main menu»

### Общие кнопки
- `btn_back` — RU «◀️ Назад» | EN «◀️ Back»
- `btn_cancel` — RU «❌ Отмена» | EN «❌ Cancel»
- `btn_yes` — RU «✅ Да» | EN «✅ Yes»
- `btn_no` — RU «❌ Нет» | EN «❌ No»
- `btn_delete` — RU «🗑 Удалить» | EN «🗑 Delete»

---

## C. Воронка поиска (категории → страна → гео → города → подтверждение)

### catalog_categories
```
RU: Выбери направления ({current}/{limit}):

Нажми на категорию, чтобы выбрать услуги.
```
```
EN: Choose services ({current}/{limit}):

Select a category to choose services.
```

### catalog_services
- RU «{category} — выбери услуги ({current}/{limit}):» | EN «{category} — choose services ({current}/{limit}):»

### catalog_country
- RU «В какой стране ищешь клиентов?» | EN «Which country should we search in?»

### catalog_geo
- RU «Ищем клиентов в конкретных городах или по всей стране?» | EN «Should we look for clients in specific cities or across the entire country?»

### catalog_cities
- RU «Выбери город (выбрано: {count}):» | EN «Choose a city (selected: {count}):»

### Кнопки/алерты воронки
- `catalog_done` — RU «✅ Готово ({count} выбрано)» | EN «✅ Done ({count} selected)»
- `catalog_continue` — RU «✅ Продолжить ({count})» | EN «✅ Continue ({count})»
- `catalog_missing` — RU «💬 Нет твоего вида деятельности? Написать в поддержку» | EN «💬 Don’t see your service? Contact support»
- `catalog_all_country` — RU «По всей стране» | EN «Across the entire country»
- `catalog_select_cities` — RU «Выбрать города» | EN «Select cities»
- `catalog_select_service` — RU «Выбери хотя бы одно направление» | EN «Select at least one service»
- `catalog_select_city` — RU «Выбери хотя бы один город» | EN «Select at least one city»
- `catalog_error_country` — RU «Страна не выбрана. Начни настройку заново.» | EN «No country selected. Start the setup again.»
- `catalog_error_services` — RU «Направления не выбраны. Начни настройку заново.» | EN «No services selected. Start the setup again.»

### Экран подтверждения поиска
- `catalog_confirm` — RU «Подтверди поиск:» | EN «Confirm your search:»
- `search_scope_services` — RU «📌 Направления:» | EN «📌 Services:»
- `catalog_country_line` — RU «🌍 Страна: {country}» | EN «🌍 Country: {country}»
- `catalog_cities_line` — RU «🏙 Города: {cities}» | EN «🏙 Cities: {cities}»
- `catalog_new_services` — RU «📌 Новых направлений: {count}» | EN «📌 New services: {count}»
- `catalog_skipped` — RU «📎 Уже добавлено: {count} (пропущено)» | EN «📎 Already added: {count} (skipped)»
- `catalog_activate_hint` — RU «Начать поиск клиентов» | EN «Start customer search»
- `catalog_activate` — RU «✅ Запустить поиск» | EN «✅ Start search»

### Экран ПОСЛЕ запуска поиска (первый поиск → триал + приглашение к тарифу)
- `trial_started` — RU «🎉 Поиск запущен! <b>Триал Про действует до {date}.</b>» | EN «🎉 Search started! Your <b>Pro trial is active until {date}.</b>»
- `trial_after` — RU «Оцените качество заявок в течение пробного периода. Для дальнейшей работы подключите тариф от ${price}/мес.» | EN «Evaluate the quality of your leads during the trial period. To continue using the service, choose a plan starting at ${price}/month.»
- `search_created` — RU «✅ Поисков создано: {count}» | EN «✅ Searches created: {count}»
- `search_added` — RU «✅ Поисков добавлено: {count}» | EN «✅ Searches added: {count}»
- `search_delivery` — RU «Новые заявки начнут приходить после обработки новых сообщений.» | EN «New leads will arrive after new messages are processed.»
- `search_upsell_after` — RU «💡 Выберите тариф, чтобы открыть доступные контакты и расширить возможности поиска.» | EN «💡 Choose a plan to access available contact details and expand your search capabilities.»
- `free_after_search` — RU «🔒 Для просмотра контактов подключите платный тариф.» | EN «🔒 Upgrade to a paid plan to view contact details.»

---

## D. Мои поиски

- `searches_title` — RU «🎯 Мои подписки ({current}/{limit})» | EN «🎯 My subscriptions ({current}/{limit})»
- `searches_empty` — RU «Создайте первый поиск, чтобы начать получать заявки.» | EN «Create your first search to start receiving leads.»
- `searches_countries` — RU «🌍 Использовано стран: {current}/{limit}» | EN «🌍 Countries used: {current}/{limit}»
- `search_scope_country` — RU «🌍 {country}» | EN «🌍 {country}»
- `search_scope_cities` — RU «🏙 {cities}» | EN «🏙 {cities}»
- `search_delete_confirm` — RU «Удалить этот поиск? Новые заявки по нему больше не будут приходить.» | EN «Delete this search? New leads for it will no longer be delivered.»
- `btn_delete_search` — RU «🗑 Удалить поиск» | EN «🗑 Delete search»
- `btn_add_search` — RU «➕ Добавить поиск» | EN «➕ Add search»

---

## E. Ключевые слова

- `keywords_title` — RU «Твои ключевые слова ({current}/{limit}):» | EN «Your custom keywords ({current}/{limit}):»
- `keywords_prompt` — RU «Отправь ключевой запрос. Например: «ищу повара».\n\nДоступно ещё: {remaining}/{limit} ({plan})» | EN «Send a keyword or phrase, for example: “looking for a chef”.\n\nAvailable: {remaining}/{limit} ({plan})»
- `list_empty_keywords` — RU «Ключевых фраз пока нет. Добавь фразу или слово, чтобы получать совпадения из Telegram-чатов.\n\nДоступно: {current}/{limit} ({plan})» | EN «No custom keywords yet. Add a phrase or word to receive matches from Telegram chats.\n\nAvailable: {current}/{limit} ({plan})»
- `keyword_command_blocked` — RU «Команды не добавляются в ключевые фразы. Отправь обычный текст.» | EN «Commands are not added as keywords. Send plain text.»
- `btn_add_keyword` — RU «➕ Добавить запрос» | EN «➕ Add keyword»
- `input_too_short` — RU «Слишком короткое значение. Попробуй ещё раз или отправь /cancel.» | EN «That value is too short. Try again or send /cancel.»

---

## F. Свои каналы  (см. также секцию 0 — повреждённые тексты)

- `channels_title` — RU «Твои каналы ({current}/{limit}):» | EN «Your channels ({current}/{limit}):»
- `list_empty_channels` — RU «Добавьте Telegram-канал для отслеживания сообщений по ключевым фразам.\n\nДоступно: {current}/{limit} ({plan})» | EN «Add a Telegram channel to monitor messages containing your keywords.\n\nAvailable: {current}/{limit} ({plan})»
- `channel_private_pending` — RU «⏳ @{channel} выглядит приватным. Канал отправлен администратору на ручную проверку.» | EN «⏳ @{channel} appears to be private. It was sent to an administrator for manual review.»
- `btn_add_channel` — RU «➕ Добавить канал» | EN «➕ Add channel»

### Общие для списков
- `list_count` — RU «Добавлено: {current}/{limit}» | EN «Added: {current}/{limit}»
- `item_added` — RU «✅ Добавлено: {item}» | EN «✅ Added: {item}»
- `item_delete_confirm` — RU «Удалить {item}?» | EN «Delete {item}?»
- `item_deleted` — RU «Удалено» | EN «Deleted»
- `item_not_found` — RU «Не найдено» | EN «Not found»
- `more_items` — RU «… и ещё {count}» | EN «… and {count} more»

---

## G. Настройки и подэкраны

- `settings_title` — RU «⚙️ Настройки» | EN «⚙️ Settings»
- `btn_instructions` — RU «📖 Инструкции» | EN «📖 Instructions»

### instructions_body
```
RU: 📖 <b>Как пользоваться LeadHunter</b>

1. Настрой поиск: выбери направление, страну и города.
2. При необходимости вы можете добавить свои ключевые фразы и каналы в Настройках.
3. Подходящие новые сообщения будут приходить автоматически.

Оплата: Тариф и оплата → тариф → срок → Telegram Stars или CryptoBot. После подтверждения тариф активируется автоматически.
```
```
EN: 📖 <b>How to use LeadHunter</b>

1. Set up a search: choose services, a country, and cities.
2. If needed, you can add your own keywords and channels in Settings.
3. Relevant new messages will arrive automatically.

Payment: Plan & payment → plan → period → Telegram Stars or CryptoBot. Your plan activates automatically after confirmation.
```

### about_body
```
RU: ℹ️ <b>LeadHunter</b>

Автоматически отслеживает новые сообщения в Telegram-источниках и отбирает обращения по твоему направлению и географии.

📊 Источников в каталоге: {channels}
🌍 Стран: {countries}
🤖 Фильтрация нерелевантных сообщений
🆓 Первый поиск запускает 3 дня тарифа Про бесплатно
```
```
EN: ℹ️ <b>LeadHunter</b>

Automatically monitors new messages in Telegram sources and selects requests matching your services and locations.

📊 Sources in the catalog: {channels}
🌍 Countries: {countries}
🤖 Irrelevant-message filtering
🆓 Your first search starts a free 3-day Pro trial
```

### Статистика
- `stats_title` — RU «📈 Статистика заявок» | EN «📈 Lead statistics»
- `stats_period` — RU «За {days} дн.: {total} заявок» | EN «Last {days} days: {total} leads»
- `stats_byday_header` — RU «По дням:» | EN «By day:»
- `stats_byseg_header` — RU «По направлениям:» | EN «By category:»
- `stats_empty` — RU «За выбранный период заявок пока нет.» | EN «No leads in the selected period yet.»
- `btn_stats` — RU «📈 Статистика» | EN «📈 Statistics»

### CSV-экспорт
- `btn_csv` — RU «📥 CSV-экспорт» | EN «📥 CSV export»
- `csv_caption` — RU «📥 Заявки за {days} дней ({count} шт.)» | EN «📥 Leads for {days} days ({count})»
- `csv_empty` — RU «За {days} дней заявок для экспорта пока нет.» | EN «No leads to export for the last {days} days.»

### Режим уведомлений (digest)
- `btn_digest` — RU «🔔 Режим уведомлений» | EN «🔔 Notification mode»
- `digest_title` — RU «🔔 Режим получения уведомлений» | EN «🔔 Notification delivery mode»
- `digest_header` — RU «📬 {count} новых заявок за период:» | EN «📬 {count} new leads for the period:»
- `digest_instant` — RU «⚡ Мгновенно» | EN «⚡ Instant»
- `digest_hourly` — RU «🕐 Раз в час» | EN «🕐 Hourly»
- `digest_daily2` — RU «🌅 2 раза в день» | EN «🌅 Twice a day»
- `digest_saved` — RU «✅ Режим обновлён» | EN «✅ Mode updated»

### Поддержка
- `support_sent` — RU «📩 Сообщение передано в поддержку. Ответим в ближайшее время.» | EN «📩 Your message was sent to support. We will reply as soon as possible.»

### Пригласить друга (referral)
```
RU referral_body: 🎁 <b>Пригласи друга</b>

Друг получит +{referral_bonus} дня к пробному периоду — всего {trial_days} дней тарифа Про.
После первой оплаты друга ты получишь +{bonus} дней текущего или последнего тарифа.

🔗 {link}

📊 Приглашено: {invited} · оплатили: {activated} · начислено: {bonus_days} дн.
```
```
EN referral_body: 🎁 <b>Invite a friend</b>

Your friend gets +{referral_bonus} trial days — {trial_days} days of Pro in total.
After their first payment, you get +{bonus} days on your current or previous plan.

🔗 {link}

📊 Invited: {invited} · paid: {activated} · credited: {bonus_days} days.
```
- `referral_share` — RU «Lead Hunter AI автоматически находит обращения клиентов в Telegram-чатах по направлению и географии. По моей ссылке — {trial_days} дней тарифа Про бесплатно.\n\n{link}» | EN «Lead Hunter AI automatically finds client requests in Telegram chats by service and location. My link gives you {trial_days} free days of Pro.\n\n{link}»
- `referral_reward` — RU «🎁 Друг оплатил подписку!\n\nК тарифу {plan} добавлено {days} дней.\n📅 Действует до: {date}» | EN «🎁 Your friend subscribed!\n\n{days} days were added to your {plan} plan.\n📅 Valid until: {date}»
- `referral_share_btn` — RU «📤 Отправить другу» | EN «📤 Share with a friend»

---

## H. Тариф и оплата

- `plan_title` — RU «💰 Тариф и оплата» | EN «💰 Plan & payment»
- `plan_current` — RU «Твой тариф: {plan}» | EN «Your plan: {plan}»

### plan_card_start
```
RU: 🎯 Старт — ${price}/мес
Для специалиста в одном городе
• 1 направление · 1 страна · города без лимита
• 3 ключевые фразы · 1 свой канал 
```
```
EN: 🎯 Start — ${price}/mo
For a specialist working in one city
• 1 service · 1 country · unlimited cities
• 3 keywords · 1 custom channels
```

### plan_card_pro
```
RU: 🚀 Профи — ${price}/мес · рекомендуем
Для активного поиска клиентов в нескольких локациях
• до 3 направлений · 3 страны · города без лимита
• 20 ключевых фраз · 10 своих каналов · статистика
```
```
EN: 🚀 Pro — ${price}/mo · recommended
For active client acquisition across several locations
• up to 3 services · 3 countries · unlimited cities
• 20 keywords · 10 custom channels · statistics
```

### plan_card_business
```
RU: 🏆 Бизнес — ${price}/мес
Для команды или агентства с широким охватом
• до 12 направлений · 9 стран · города без лимита
• 50 ключевых фраз · 50 своих каналов · CS экспортV · полная статистика
```
```
EN: 🏆 Business — ${price}/mo
For a team or agency with broad coverage
• up to 12 services · 9 countries · unlimited cities
• 50 keywords · 50 custom channels · CSVexport · full statistics
```

### Кнопки/скидки тарифов
- `plan_discounts` — RU Популярный выборе: 3 месяца −10% · год −20%» | EN «Save more: 3 months −10% · year −20%»
- `plan_btn_start` — RU «🎯 Старт — ${price}» | EN «🎯 Start — ${price}»
- `plan_btn_pro` — RU «🚀 Профи — ${price}» | EN «🚀 Pro — ${price}»
- `plan_btn_business` — RU «🏆 Бизнес — ${price}» | EN «🏆 Business — ${price}»
- `plan_btn_current` — RU «✅ {name} · твой» | EN «✅ {name} · yours»

### Периоды и способ оплаты
- `period_1m` — RU «1 месяц» | EN «1 month»
- `period_3m` — RU «3 месяца (−10%)» | EN «3 months (−10%)»
- `period_1y` — RU «1 год (−20%)» | EN «1 year (−20%)»
- `payment_period_title` — RU «💳 {plan} — выберипериодк:» | EN «💳 {plan} — choose a billing period:»
- `payment_period_line` — RU «• {period}: ${total} (${monthly}/мес), экономия ${savings}» | EN «• {period}: ${total} (${monthly}/mo), save ${savings}»
- `payment_period_line_regular` — RU «• {period}: ${total}» | EN «• {period}: ${total}»
- `payment_period_recommended` — RU «🔥 3 месяца — оптимальный выбор» | EN «🔥 3 months — best value»
- `payment_period_button` — RU «{period} — ${total}» | EN «{period} — ${total}»
- `payment_method_title` — RU «💳 Оплата {plan}\n\nСрок: {period}\nСумма: ${total}\n\nВыбери способ оплаты:» | EN «💳 Pay for {plan}\n\nPeriod: {period}\nTotal: ${total}\n\nChoose a payment method:»
- `payment_crypto_unavailable` — RU «CryptoBot временно недоступен.» | EN «CryptoBot is temporarily unavailable.»
- `payment_invoice_created` — RU «💳 Счёт создан!\n\nСумма: ${total}\n\nОплати по кнопке ниже — тариф активируется автоматически.» | EN «💳 Invoice created!\n\nTotal: ${total}\n\nPay using the button below — your plan will activate automatically.»
- `payment_btn_pay` — RU «💳 Оплатить» | EN «💳 Pay»
- `annual_offer` — RU «💡 Помесячно за год: ${monthly_total}.\nГодовой {plan}: ${year_total} (−20%).» | EN «💡 Monthly payments for a year: ${monthly_total}.\nAnnual {plan}: ${year_total} (−20%).»
- `annual_offer_btn` — RU «💳 Годовой — ${total}» | EN «💳 Annual — ${total}»
- `payment_success` — RU «✅ Оплата прошла!\n\nТариф: {plan}\nСрок: {period}\nДействует до: {date}» | EN «✅ Payment successful!\n\nPlan: {plan}\nPeriod: {period}\nValid until: {date}»

### Ошибки оплаты
```
RU pay_error_body: ❌ <b>Оплата не прошла</b>

Платёж не был завершён. Попробуй ещё раз или выбери другой способ оплаты.
```
```
EN pay_error_body: ❌ <b>Payment failed</b>

The payment didn't go through. Try again or choose another payment method.
```
```
RU pay_error_expired: ⌛️ <b>Счёт истёк</b>

Оплата не поступила вовремя. Нажми «Повторить», чтобы создать новый счёт.
```
```
EN pay_error_expired: ⌛️ <b>Invoice expired</b>

Payment wasn't received in time. Tap “Retry” to create a new invoice.
```
- `pay_err_retry` — RU «🔄 Повторить» | EN «🔄 Retry»
- `pay_err_other` — RU «💱 Другой способ» | EN «💱 Another method»

---

## I. Пейволлы (контекстные подсказки о лимите)

- `paywall_title` — RU «🔒 Лимит текущего тарифа» | EN «🔒 Current plan limit»
- `paywall_stats` — RU «Статистика заявок — на тарифе {plan} (${price}/мес).» | EN «Lead statistics — on {plan} (${price}/mo).»
- `paywall_csv` — RU «CSV-экспорт заявок — на тарифе {plan} (${price}/мес).» | EN «CSV export — on {plan} (${price}/mo).»
- `paywall_keyword` — RU «Больше ключевых слов — на тарифе {plan} (${price}/мес).» | EN «More keywords — on {plan} (${price}/mo).»
- `paywall_direction` — RU «Больше направлений и стран — на тарифе {plan} (${price}/мес).» | EN «More categories and countries — on {plan} (${price}/mo).»
- `paywall_country` — RU «Несколько стран — на тарифе {plan} (${price}/мес).» | EN «Multiple countries — on {plan} (${price}/mo).»
- `paywall_city` — RU «Больше городов — на тарифе {plan} (${price}/мес).» | EN «More cities — on {plan} (${price}/mo).»
- `paywall_channel` — RU «Больше своих каналов — на тарифе {plan} (${price}/мес).» | EN «More channels — on {plan} (${price}/mo).»

---

## J. Lead-уведомление (само письмо о найденном клиенте)

- `lead_title` — RU «🎯 <b>Я нашёл нового клиента! | Lead Hunter AI</b>» | EN «🎯 <b>I found a new client! | Lead Hunter AI</b>»
- `lead_chat` — RU «💬 {chat}» | EN «💬 {chat}»
- `lead_sender` — RU « от <a href='https://t.me/{sender}'>@{sender}</a>» | EN « from <a href='https://t.me/{sender}'>@{sender}</a>»
- `lead_hidden` — RU «🔒Подключите платный тариф для просмотра контактов..» | EN «🔒Upgrade to a paid plan to view contact details..»
- `lead_tags` — RU «🏷 {labels}» | EN «🏷 {labels}»
- `lead_paywall_title` — RU «🔒 Открыть контакты этой заявки» | EN «🔒 Unlock contacts for this lead»
- `lead_paywall_preview` — RU «Заявка: «{preview}»» | EN «Lead: “{preview}”»
- `lead_paywall_access` — RU «Старт открывает доступные контакты и ссылки в новых уведомлениях.» | EN «Start unlocks available contacts and links in new notifications.»
- `lead_btn_unlock` — RU «🎯 Открыть контакты — от ${price}/мес» | EN «🎯 Unlock contacts — from ${price}/mo»
- `lead_btn_chat` — RU «💬 Чат» | EN «💬 Chat»
- `lead_btn_sender` — RU «💬 Написать» | EN «💬 Message»

---

## K. End-of-day отчёт Free (в конце дня)

### eod_body
```
RU: 📊 <b>Спрос в твоей нише за день</b>

Всего найдено заявок: {total}.
Пропущено заявок: {missed}.

Оформи подписку, чтобы новые заявки приходили сразу с контактами и ссылкой на чат.
```
```
EN: 📊 <b>Demand in your niche today</b>

Total leads found: {total}.
Leads missed: {missed}.

Subscribe to receive new leads immediately with contacts and a chat link.
```
### eod_zero
```
RU: 🔎 <b>Сегодня заявок по текущим настройкам не найдено</b>

Попробуй расширить географию, проверить направления и добавить ключевые фразы или свои каналы.
```
```
EN: 🔎 <b>No leads matched your current settings today</b>

Try broadening your location, reviewing services, or adding keywords and custom channels.
```
- `eod_btn_start` — RU «🎯 Старт — ${price}/мес» | EN «🎯 Start — ${price}/mo»
- `eod_btn_pro` — RU «🚀 Профи — ${price}/мес» | EN «🚀 Pro — ${price}/mo»
- `eod_btn_business` — RU «🏆 Бизнес — ${price}/мес» | EN «🏆 Business — ${price}/mo»
- `eod_zero_btn` — RU «⚙️ Проверить поиски» | EN «⚙️ Review searches»

---

## L. Напоминания и winback (окончание триала/подписки, возврат)

- `reminder_trial_ending_2` — RU «⏳ Пробный период заканчивается через 2 дня.\ Сохрани доступ — тариыт от ${start}/мес.» | EN «⏳ Your trial ends in 2 days.\n Keep access from ${start}/mo.»
- `reminder_trial_ending_1` — RU «⏳ Завтра пробный период закончится.\Оформи подписку отт (${start}/меси.» | EN «⏳ Your trial ends tomorrow.\Subscription from (${start}/mon.»
- `reminder_subscription_ending_5` — RU «⏳ Подписка заканчивается через 5 дней.\nПродли, чтобы получать заявки без перерыва.» | EN «⏳ Your subscription ends in 5 days.\nRenew to keep receiving leads without interruption.»
- `reminder_btn_plans` — RU «🎯 Тарифы — от ${price}/мес» | EN «🎯 Plans — from ${price}/mo»
- `reminder_btn_search` — RU «🔍 Поиск клиентов» | EN «🔍 Find clients»
- `reminder_btn_renew` — RU «🔄 Продлить» | EN «🔄 Renew»
- `reminder_btn_other_plans` — RU «📋 Другие тарифы» | EN «📋 Other plans»

### winback_offer
```
RU: 🎁 <b>Персональная скидка 25% на 3 месяца</b>

За 30 дней в твоей нише найдено заявок: {missed}.
Выбери тариф на 3 месяца — скидка применится автоматически.

Предложение одноразовое и действует 12 часов — до {expires}.
```
```
EN: 🎁 <b>Personal 25% discount on a 3-month plan</b>

Leads found in your niche over 30 days: {missed}.
Choose a 3-month plan — the discount is applied automatically.

This is a one-time offer valid for 12 hours, until {expires}.
```
- `winback_btn_start` — RU «🎯 Старт на 3 мес — ${total}» | EN «🎯 Start for 3 months — ${total}»
- `winback_btn_pro` — RU «🚀 Профи на 3 мес — ${total}» | EN «🚀 Pro for 3 months — ${total}»
- `winback_btn_business` — RU «🏆 Бизнес на 3 мес — ${total}» | EN «🏆 Business for 3 months — ${total}»
- `winback_expired` — RU «⌛️ Персональное предложение закончилось. Выбери тариф по обычной цене.» | EN «⌛️ Your personal offer has expired. Choose a plan at the regular price.»
- `winback_payment_title` — RU «🎁 Скидка 25% применена\n\nТариф: {plan}\nСрок: 3 месяца\nК оплате: ${total}\nПредложение действует до {expires}.\n\nВыбери способ оплаты:» | EN «🎁 25% discount applied\n\nPlan: {plan}\nTerm: 3 months\nTotal: ${total}\nOffer valid until {expires}.\n\nChoose a payment method:»

---

## M. Прочее / служебное

- `error_generic` — RU «⚠️ Произошла ошибка. Попробуй ещё раз.» | EN «⚠️ Something went wrong. Please try again.»
- `error_user_not_found` — RU «⚠️ Пользователь не найден. Нажми /start.» | EN «⚠️ User not found. Tap /start.»
- `coming_soon` — RU «🚧 В разработке» | EN «🚧 Coming soon»
- `feedback_thanks` — RU «👍 Спасибо!» | EN «👍 Thank you!»
- `feedback_not_relevant` — RU «👎 Спасибо, твой отзыв учтён — работаем над точностью.» | EN «👎 Thank you, your feedback was saved — we are improving accuracy.»

---

## Легаси (сейчас в боте НЕ показываются — можно игнорировать)

`onb_step1_title`, `onb_step1_placeholder`, `onb_step2_title`, `onb_step2_placeholder`, `onb_step3_title`, `onb_step3_placeholder`, `onb_skip`, `onb_next` — старый onboarding wizard, флоу их не открывает.

---

## Захардкоженные тексты (НЕ в locale — правлю точечно в коде по запросу)

Эти строки вписаны прямо в `.py` и не лежат в этом файле. Если нужно поправить — назови, я найду и поменяю в коде:
- Экран выбора языка «Выбери язык / Choose language» + кнопки 🇷🇺/🇬🇧 — `discover.py:23-25`
- Кнопки «Инструкции»/«Настройки» в меню — `start.py:380,387`
- Названия тарифов/периодов на некоторых экранах — `plan.py:18-23,61`
- Кнопка «✅ Готово (N)» при выборе городов — `catalog_nav.py:481`
- Подпись «группа …» для каналов — `channels.py:58`
- Запрос новой категории — `catalog_nav.py:903,909-911`
- Fallback-подписи поисков — `catalog_nav.py:835-836`
