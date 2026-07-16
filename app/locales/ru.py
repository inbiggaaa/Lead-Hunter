# RU locale — все тексты интерфейса

TEXTS = {
    # ── Приветственный экран ──
    "welcome_title": "🎯 <b>Lead Hunter AI — клиенты уже ищут твои услуги в Telegram!</b>",
    "welcome_body": (
        "Выбери направление деятельности и географию — <b>Lead Hunter AI</b> будет "
        "отслеживать новые сообщения и находить подходящие запросы клиентов.\n\n"
        "В базе сервиса — более 5.000+ Telegram-чатов и каналов. "
        "Узнавай о новых запросах раньше и первым предлагай свои услуги! "
        "Запусти первый поиск и <b>бесплатно попробуй возможности тарифа Pro</b> "
        "в течение 3 дней.\n"
        "\n\n"
        "🎯 <b>Lead Hunter AI — potential clients are already looking for your "
        "services on Telegram!</b>\n\n"
        "Choose your industry and target location — <b>Lead Hunter AI</b> will "
        "monitor new messages and find relevant customer requests.\n\n"
        "The Lead Hunter AI database includes more than 5.000+ Telegram chats and channels. "
        "Discover new opportunities sooner and be the first to offer your services! "
        "Launch your first search and <b>try Pro features free</b> for 3 days."
    ),
    "welcome_lang_prompt": "Выбери язык / Choose language:",

    # ── Onboarding wizard ──
    "onb_step1_title": "Чем ты занимаешься? Выбери направление:",
    "onb_step1_placeholder": "Выбор направлений появится в Фазе 3",
    "onb_step2_title": "В какой стране ищешь клиентов?",
    "onb_step2_placeholder": "Выбор стран появится в Фазе 3",
    "onb_step3_title": (
        "🎉 Готово! Ты получил 3 дня тарифа Pro.\n"
        "Вот твои первые заявки:"
    ),
    "onb_step3_placeholder": "Заявки появятся в Фазе 5",
    "onb_skip": "⏭ Пропустить",
    "onb_next": "▶️ Далее",

    # ── Главное меню ──
    "menu_header": "🎯 Lead Hunter AI",
    "menu_plan": "Твой тариф: {plan}",
    "menu_searches": "🎯 Активных подписок: {count}",
    "plan_until": "до {date}",
    "search_delete_confirm": "Удалить этот поиск? Новые заявки по нему больше не будут приходить.",
    "btn_delete_search": "🗑 Удалить поиск",
    "btn_add_search": "➕ Добавить поиск",
    "menu_notifications": "📬 Заявок сегодня: {matched}",
    "menu_free_hidden": "🔒 Подключите платный тариф для просмотра контактов",
    "btn_search": "🚀 Настроить первый поиск",
    "btn_searches": "🎯 Мои поиски",
    "btn_results": "📥 Заявки и результаты",
    "btn_keywords": "⚙️ Мои ключевые слова",
    "btn_channels": "📢 Мои каналы",
    "btn_subscriptions": "🎯 Мои подписки",
    "btn_referral": "🎁 Пригласить друга",
    "btn_plan": "💰 Тариф и оплата",
    "btn_language": "🌐 Язык / Language",
    "btn_settings": "⚙️ Настройки",
    "btn_about": "ℹ️ О сервисе",

    # ── Общие ──
    "btn_back": "◀️ Назад",
    "btn_cancel": "❌ Отмена",
    "btn_yes": "✅ Да",
    "btn_no": "❌ Нет",
    "coming_soon": "🚧 В разработке",

    # ── Язык ──
    "btn_ru": "🇷🇺 Русский",
    "btn_en": "🇬🇧 English",
    "language_set": "✅ Язык установлен: Русский",

    # ── Экран «Тариф и оплата» (T3.1, стиль «короче и суше») ──
    "plan_title": "💰 Тариф и оплата",
    "plan_current": "Твой тариф: {plan}",
    "plan_card_start": (
        "🎯 Start — ${price}/мес\n"
        "Для специалиста в одном городе\n"
        "• 1 направление · 1 страна · города без лимита\n"
        "• 3 ключевые фразы · 1 свой канал"
    ),
    "plan_card_pro": (
        "🚀 Pro — ${price}/мес · рекомендуем\n"
        "Для активного поиска клиентов в нескольких локациях\n"
        "• до 3 направлений · 3 страны · города без лимита\n"
        "• 20 ключевых фраз · 10 своих каналов · статистика"
    ),
    "plan_card_business": (
        "🏆 Business — ${price}/мес\n"
        "Для команды или агентства с широким охватом\n"
        "• до 12 направлений · 9 стран · города без лимита\n"
        "• 50 ключевых фраз · 50 своих каналов · CSV-экспорт · полная статистика"
    ),
    "plan_discounts": "Популярный выбор: 3 месяца −10% · год −20%",
    "plan_btn_start": "🎯 Start — ${price}",
    "plan_btn_pro": "🚀 Pro — ${price}",
    "plan_btn_business": "🏆 Business — ${price}",
    "plan_btn_current": "✅ {name} · твой",

    # ── End-of-day отчёт Free (T4.2) ──
    "eod_body": (
        "📊 <b>Спрос в твоей нише за день</b>\n\n"
        "Всего найдено заявок: {total}.\n"
        "Пропущено заявок: {missed}.\n\n"
        "Не упускай новых клиентов! Оформи подписку и получай уведомления о новых заявках!"
    ),
    "eod_btn_start": "🎯 Start — ${price}/мес",
    "eod_btn_pro": "🚀 Pro — ${price}/мес",
    "eod_btn_business": "🏆 Business — ${price}/мес",
    "eod_zero": ("🔎 <b>Сегодня заявок по текущим настройкам не найдено</b>\n\n"
        "Попробуй расширить географию, проверить направления и добавить ключевые фразы или свои каналы."),
    "eod_zero_btn": "⚙️ Проверить поиски",

    # ── Статистика (T5.1) ──
    "stats_title": "📈 Статистика заявок",
    "stats_period": "За {days} дн.: {total} заявок",
    "stats_byday_header": "По дням:",
    "stats_byseg_header": "По направлениям:",
    "stats_empty": "За выбранный период заявок пока нет.",
    "btn_stats": "📈 Статистика",
    "btn_csv": "📥 CSV-экспорт",
    "btn_digest": "🔔 Режим уведомлений",
    "digest_header": "📬 {count} новых заявок за период:",
    "digest_title": "🔔 Режим получения уведомлений",
    "digest_instant": "⚡ Мгновенно",
    "digest_hourly": "🕐 Раз в час",
    "digest_daily2": "🌅 2 раза в день",
    "digest_saved": "✅ Режим обновлён",
    "csv_caption": "📥 Заявки за {days} дней ({count} шт.)",
    "csv_empty": "За {days} дней заявок для экспорта пока нет.",

    # ── Контекстные пейволлы (T4.1) ──
    "paywall_title": "🔒 Лимит текущего тарифа",
    "paywall_stats": "Статистика заявок — на тарифе {plan} (${price}/мес).",
    "paywall_csv": "CSV-экспорт заявок — на тарифе {plan} (${price}/мес).",
    "paywall_keyword": "Больше ключевых слов — на тарифе {plan} (${price}/мес).",
    "paywall_direction": "Больше направлений и стран — на тарифе {plan} (${price}/мес).",
    "paywall_country": "Несколько стран — на тарифе {plan} (${price}/мес).",
    "paywall_city": "Больше городов — на тарифе {plan} (${price}/мес).",
    "paywall_channel": "Больше своих каналов — на тарифе {plan} (${price}/мес).",

    # ── Ошибка оплаты (T2.2) ──
    "pay_error_body": (
        "❌ <b>Оплата не прошла</b>\n\n"
        "Платёж не был завершён. Попробуй ещё раз или выбери другой способ оплаты."
    ),
    "pay_error_expired": (
        "⌛️ <b>Счёт истёк</b>\n\n"
        "Оплата не поступила вовремя. Нажми «Повторить», чтобы создать новый счёт."
    ),
    "pay_err_retry": "🔄 Повторить",
    "pay_err_other": "💱 Другой способ",
    "reminder_trial_ending_2": "⏳ Пробный период заканчивается через 2 дня.\nСохрани доступ — тариф от ${start}/мес.",
    "reminder_trial_ending_1": "⏳ Завтра пробный период закончится.\nОформи подписку от ${start}/мес.",
    "reminder_subscription_ending_5": "⏳ Подписка заканчивается через 5 дней.\nПродли, чтобы получать заявки без перерыва.",
    "reminder_subscription_ending_2": "⏳ Подписка заканчивается через 2 дня.\nПродли, чтобы получать заявки без перерыва.",
    "reminder_subscription_ending_1": "⏳ Завтра подписка закончится.\nПродли, чтобы не потерять доступ к заявкам.",
    "reminder_subscription_expired": "❌ <b>Ваша подписка истекла</b>\n\nПродлите тариф, чтобы снова получать уведомления и заявки от горячих клиентов.",
    "reminder_btn_plans": "🎯 Тарифы — от ${price}/мес",
    "reminder_btn_search": "🔍 Поиск клиентов",
    "reminder_btn_renew": "🔄 Продлить",
    "reminder_btn_other_plans": "📋 Другие тарифы",
    "winback_offer": ("🎁 <b>Персональная скидка 25% на 3 месяца</b>\n\n"
        "За 30 дней в твоей нише найдено заявок: {missed}.\n"
        "Выбери тариф на 3 месяца — скидка применится автоматически.\n\n"
        "Предложение одноразовое и действует 12 часов — до {expires}."),
    "winback_btn_start": "🎯 Start на 3 мес — ${total}",
    "winback_btn_pro": "🚀 Pro на 3 мес — ${total}",
    "winback_btn_business": "🏆 Business на 3 мес — ${total}",
    "winback_expired": "⌛️ Персональное предложение закончилось. Выбери тариф по обычной цене.",
    "winback_payment_title": "🎁 Скидка 25% применена\n\nТариф: {plan}\nСрок: 3 месяца\nК оплате: ${total}\nПредложение действует до {expires}.\n\nВыбери способ оплаты:",
    "list_count": "Добавлено: {current}/{limit}",
    "list_empty_keywords": "Ключевых фраз пока нет. Добавь фразу или слово, чтобы получать совпадения из Telegram-чатов.\n\nДоступно: {current}/{limit} (<b>Тарифный план {plan}</b>)",
    "list_empty_channels": "Добавьте Telegram-канал для отслеживания сообщений по ключевым фразам.\n\nДоступно: {current}/{limit} (<b>Тарифный план {plan}</b>)",
    "keywords_title": "Твои ключевые слова ({current}/{limit}):",
    "channels_title": "Твои каналы ({current}/{limit}):",
    "keywords_prompt": "Отправь ключевой запрос. Например: «ищу повара».\n\nДоступно ещё: {remaining}/{limit} (<b>Тарифный план {plan}</b>)",
    "keyword_command_blocked": "Команды не добавляются в ключевые фразы. Отправь обычный текст.",
    "channels_prompt": "Отправь @username канала. Например: @durov.\n\nДоступно ещё: {remaining}/{limit} (<b>Тарифный план {plan}</b>)\n\n/cancel — отмена.",
    "input_too_short": "Слишком короткое значение. Попробуй ещё раз или отправь /cancel.",
    "channel_invalid": "Некорректный @username канала. Попробуй ещё раз или отправь /cancel.",
    "item_added": "✅ Добавлено: {item}",
    "item_delete_confirm": "Удалить {item}?",
    "btn_delete": "🗑 Удалить",
    "item_deleted": "Удалено",
    "item_not_found": "Не найдено",
    "btn_add_keyword": "➕ Добавить запрос",
    "btn_add_channel": "➕ Добавить канал",
    "channel_private_pending": "⏳ @{channel} выглядит приватным. Канал отправлен администратору на ручную проверку.",
    "more_items": "… и ещё {count}",
    "catalog_categories": "Выбери направления ({current}/{limit}):\n\nНажми на категорию, чтобы выбрать услуги.",
    "catalog_done": "✅ Готово ({count} выбрано)",
    "catalog_missing": "💬 Нет твоего вида деятельности? Написать в поддержку",
    "catalog_services": "{category} — выбери услуги ({current}/{limit}):",
    "catalog_continue": "✅ Продолжить ({count})",
    "catalog_select_service": "Выбери хотя бы одно направление",
    "catalog_country": "В какой стране ищешь клиентов?",
    "catalog_geo": "Ищем клиентов в конкретных городах или по всей стране?",
    "catalog_all_country": "По всей стране",
    "catalog_select_cities": "Выбрать города",
    "catalog_cities": "Выбери город (выбрано: {count}):",
    "catalog_select_city": "Выбери хотя бы один город",
    "catalog_confirm": "Подтверди поиск:",
    "catalog_new_services": "📌 Новых направлений: {count}",
    "catalog_skipped": "📎 Уже добавлено: {count} (пропущено)",
    "catalog_country_line": "🌍 Страна: {country}",
    "catalog_cities_line": "🏙 Города: {cities}",
    "search_upsell_after": "💡 Выберите тариф, чтобы открыть доступные контакты и расширить возможности поиска.",
    "catalog_activate_hint": "Начать поиск клиентов",
    "catalog_activate": "✅ Запустить поиск",
    "catalog_error_country": "Страна не выбрана. Начни настройку заново.",
    "instructions_body": ("📖 <b>Как пользоваться LeadHunter</b>\n\n"
        "1. Настрой поиск: выбери направление, страну и города.\n"
        "2. При необходимости вы можете добавить свои ключевые фразы и каналы в Настройках.\n"
        "3. Подходящие новые сообщения будут приходить автоматически.\n\n"
        "Оплата: Тариф и оплата → тариф → срок → Telegram Stars или CryptoBot. После подтверждения тариф активируется автоматически."),
    "about_body": ("ℹ️ <b>LeadHunter</b>\n\n"
        "Автоматически отслеживает новые сообщения в Telegram-источниках и отбирает обращения по твоему направлению и географии.\n\n"
        "📊 Источников в каталоге: {channels}\n"
        "🌍 Стран: {countries}\n"
        "🤖 Фильтрация нерелевантных сообщений\n"
        "🆓 Первый поиск запускает 3 дня тарифа Pro бесплатно"),
    "referral_share": "Lead Hunter AI автоматически находит обращения клиентов в Telegram-чатах по направлению и географии. По моей ссылке — {trial_days} дней тарифа Pro бесплатно.\n\n{link}",
    "referral_body": ("🎁 <b>Пригласи друга</b>\n\n"
        "Друг получит +{referral_bonus} дня к пробному периоду — всего {trial_days} дней тарифа Pro.\n"
        "После первой оплаты друга ты получишь +{bonus} дней текущего или последнего тарифа.\n\n"
        "🔗 {link}\n\n📊 Приглашено: {invited} · оплатили: {activated} · начислено: {bonus_days} дн."),
    "referral_reward": "🎁 Друг оплатил подписку!\n\nК тарифу {plan} добавлено {days} дней.\n📅 Действует до: {date}",
    "referral_share_btn": "📤 Отправить другу",

    "settings_title": "⚙️ Настройки",
    "btn_instructions": "📖 Инструкции",
    "support_sent": "📩 Сообщение передано в поддержку. Ответим в ближайшее время.",
    "search_scope_services": "📌 Направления:",
    "search_scope_country": "🌍 {country}",
    "search_scope_cities": "🏙 {cities}",
    "searches_title": "🎯 Мои подписки ({current}/{limit})",
    "searches_empty": "Создайте первый поиск, чтобы начать получать заявки.",
    "searches_countries": "🌍 Использовано стран: {current}/{limit}",
    "search_created": "✅ Поисков создано: {count}",
    "search_added": "✅ Поисков добавлено: {count}",
    "search_delivery": "Новые заявки начнут приходить после обработки новых сообщений.",
    "trial_started": "Мониторинг чатов запущен! <b>Trial действует до {date}.</b>",
    "trial_after": "Оцените качество заявок в течение пробного периода. Для дальнейшей работы подключите тариф от ${price}/мес.",
    "free_after_search": "🔒 Для просмотра контактов подключите платный тариф.",
    "catalog_error_services": "Направления не выбраны. Начни настройку заново.",
    "btn_main_menu": "🏠 Главное меню",
    "period_1m": "1 месяц",
    "period_3m": "3 месяца (−10%)",
    "period_1y": "1 год (−20%)",
    "payment_period_title": "💳 {plan} — выбери период:",
    "payment_period_line": "• {period}: ${total} (${monthly}/мес), экономия ${savings}",
    "payment_period_line_regular": "• {period}: ${total}",
    "payment_period_recommended": "🔥 3 месяца — оптимальный выбор",
    "payment_period_button": "{period} — ${total}",
    "payment_method_title": "💳 Оплата {plan}\n\nСрок: {period}\nСумма: ${total}\n\nВыбери способ оплаты:",
    "payment_crypto_unavailable": "CryptoBot временно недоступен.",
    "payment_invoice_created": "💳 Счёт создан!\n\nСумма: ${total}\n\nОплати по кнопке ниже — тариф активируется автоматически.",
    "payment_btn_pay": "💳 Оплатить",
    "annual_offer": "💡 Помесячно за год: ${monthly_total}.\nГодовой {plan}: ${year_total} (−20%).",
    "annual_offer_btn": "💳 Годовой — ${total}",
    "feedback_thanks": "👍 Спасибо!",
    "feedback_not_relevant": "👎 Спасибо, твой отзыв учтён — работаем над точностью.",
    "error_generic": "⚠️ Произошла ошибка. Попробуй ещё раз.",
    "error_user_not_found": "⚠️ Пользователь не найден. Нажми /start.",
    "payment_success": "✅ Оплата прошла!\n\nТариф: {plan}\nСрок: {period}\nДействует до: {date}",
    "lead_title": "🎯 <b>Я нашёл нового клиента! | Lead Hunter AI</b>",
    "lead_chat": "💬 {chat}",
    "lead_sender": "\n👤 <a href='https://t.me/{sender}'>@{sender}</a>",
    "lead_sender_name": "\n👤 {name}",
    "lead_contact_hidden": "\n🔒 Клиент скрыл контакты настройками приватности Telegram — написать напрямую нельзя. Открыть заявку и ответить можно, если вы участник группы.",
    "lead_hidden": "🔒 Подключите платный тариф для просмотра контактов.",
    "lead_tags": "🏷 {labels}",
    "lead_paywall_title": "🔒 Открыть контакты этой заявки",
    "lead_paywall_preview": "Заявка: «{preview}»",
    "lead_paywall_access": "Start открывает доступные контакты и ссылки в новых уведомлениях.",
    "lead_btn_unlock": "🎯 Открыть контакты — от ${price}/мес",
    "lead_btn_chat": "💬 Чат",
    "lead_btn_sender": "💬 Написать",
}