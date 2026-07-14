# RU locale — все тексты интерфейса

TEXTS = {
    # ── Приветственный экран ──
    "welcome_title": "🎯 <b>Lead Hunter AI — мониторинг клиентских заявок в Telegram</b>",
    "welcome_body": (
        "Сервис в реальном времени отслеживает публичные Telegram-каналы "
        "и находит потенциальных клиентов по вашему направлению "
        "деятельности. Релевантные заявки поступают вам в виде уведомлений.\n\n"
        "<b>Что вы получаете:</b>\n\n"
        "✔️ Поток входящих заявок без ручного поиска\n"
        "✔️ Настройку по направлению, географии и ключевым словам\n"
        "✔️ Уведомления без лимита на любом тарифе\n"
        "✔️ Преимущество первого контакта с клиентом\n"
        "✔️ Автоматическую работу 24/7\n\n"
        "Lead Hunter AI берёт на себя поиск клиентов — "
        "вы сосредотачиваетесь на работе с ними.\n\n"
        "Доступен бесплатный пробный период — 5 дней тарифа Business.\n\n"
        "Нажмите кнопку ниже, чтобы начать. 👇"
    ),
    "welcome_lang_prompt": "Выбери язык / Choose language:",

    # ── Onboarding wizard ──
    "onb_step1_title": "Чем ты занимаешься? Выбери направление:",
    "onb_step1_placeholder": "Выбор направлений появится в Фазе 3",
    "onb_step2_title": "В какой стране ищешь клиентов?",
    "onb_step2_placeholder": "Выбор стран появится в Фазе 3",
    "onb_step3_title": (
        "🎉 Готово! Ты получил 5 дней Business-тарифа.\n"
        "Вот твои первые заявки:"
    ),
    "onb_step3_placeholder": "Заявки появятся в Фазе 5",
    "onb_skip": "⏭ Пропустить",
    "onb_next": "▶️ Далее",

    # ── Главное меню ──
    "menu_header": "🎯 LeadHunter",
    "menu_plan": "Твой тариф: {plan}",
    "menu_searches": "🎯 Активных поисков: {count}",
    "plan_until": "до {date}",
    "search_delete_confirm": "Удалить этот поиск? Новые заявки по нему больше не будут приходить.",
    "btn_delete_search": "🗑 Удалить поиск",
    "btn_add_search": "➕ Добавить поиск",
    "menu_notifications": "📬 Заявок сегодня: {matched}",
    "menu_free_hidden": "🔒 Контакты скрыты — открой их на платном тарифе",
    "btn_search": "🚀 Настроить первый поиск",
    "btn_searches": "🎯 Мои поиски",
    "btn_results": "📥 Заявки и результаты",
    "btn_keywords": "⚙️ Мои ключевые слова",
    "btn_channels": "📢 Мои каналы",
    "btn_subscriptions": "🎯 Мои поиски",
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
        "🎯 Старт — ${price}/мес\n"
        "• 1 направление · 1 страна · 1 город\n"
        "• 3 ключевые фразы · 1 канал · контакты открыты"
    ),
    "plan_card_pro": (
        "🚀 Профи — ${price}/мес\n"
        "• 3 направления · 3 страны · до 9 городов\n"
        "• 20 ключевых фраз · 10 каналов · regex · статистика"
    ),
    "plan_card_business": (
        "🏆 Бизнес — ${price}/мес\n"
        "• 12 направлений · 9 стран · города без лимита\n"
        "• 50 ключевых фраз · 50 каналов · CSV · полная статистика"
    ),
    "plan_discounts": "3 мес −10% · год −20%",
    "plan_btn_start": "🎯 Старт — ${price}",
    "plan_btn_pro": "🚀 Профи — ${price}",
    "plan_btn_business": "🏆 Бизнес — ${price}",
    "plan_btn_current": "✅ {name} · твой",

    # ── End-of-day отчёт Free (T4.2) ──
    "eod_body": (
        "📊 <b>Итоги дня</b>\n\n"
        "Сегодня новых заявок: {count}.\n"
        "Контакты скрыты — на Free виден только текст.\n\n"
        "Каждый скрытый контакт достаётся тому, кто ответит первым."
    ),
    "eod_btn": "🎯 Открыть контакты — от ${price}/мес",

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
    "reminder_trial_ending_2": "⏳ Пробный период заканчивается через 2 дня.\nПотом контакты клиентов скроются. Сохрани доступ — тариф Старт от ${start}/мес.",
    "reminder_trial_ending_1": "⏳ Завтра пробный период закончится.\nЗаявки останутся, но без контактов. Тариф Старт (${start}/мес) оставит их открытыми.",
    "reminder_trial_expired_1": "⏰ Пробный период закончился. Заявки приходят, но контакты скрыты.\nОткрой их снова — тариф Старт от ${start}/мес.",
    "reminder_trial_expired_3": "🔒 3 дня без контактов. Верни доступ — от ${start}/мес.",
    "reminder_trial_expired_7": "📊 Неделя на Free. Заявки видны, а отправитель — нет.\nОткрой контакты — тариф Старт от ${start}/мес.",
    "reminder_subscription_ending_5": "⏳ Подписка заканчивается через 5 дней.\nПродли, чтобы получать заявки без перерыва.",
    "reminder_subscription_expired_1": "⏰ Срок подписки закончился. Сейчас действует льготный период.\nПродли подписку, чтобы сохранить доступ без перерыва.",
    "reminder_subscription_expired_3": "⏳ Льготный период продолжается. Продли подписку, чтобы сохранить доступ.",
    "reminder_subscription_expired_7": "⏳ Последний день льготного периода. Продли подписку, чтобы сохранить доступ.",
    "reminder_inactive_14": "👋 Загляни в LeadHunter и проверь свои поиски.",
    "reminder_inactive_28": "📊 Проверь активные поиски и настройки LeadHunter.",
    "reminder_winback_missed_14": "📊 За 2 недели найдено заявок в твоей нише: {missed}. Контакты были скрыты.\nВерни доступ — Старт от ${start}/мес.",
    "reminder_winback_missed_28": "📊 За месяц найдено заявок в твоей нише: {missed}. Контакты были скрыты.\nВерни доступ — от ${start}/мес.",
    "reminder_btn_plans": "🎯 Тарифы — от ${price}/мес",
    "reminder_btn_search": "🔍 Поиск клиентов",
    "reminder_btn_renew": "🔄 Продлить",
    "reminder_btn_other_plans": "📋 Другие тарифы",
    "periodic_weekly_digest": "📊 Проверь результаты недели в LeadHunter.",
    "periodic_niche_growth": "🌱 Проверь актуальные источники и настройки своих поисков.",
    "periodic_monthly_summary": "📈 Проверь результаты месяца в LeadHunter.",
    "periodic_upgrade": "🔒 Контакты авторов открыты на платном тарифе — Старт от ${price}/мес.",
    "list_count": "Добавлено: {current}/{limit}",
    "list_empty_keywords": "Ключевых фраз пока нет. Добавь фразу, чтобы получать совпадения из Telegram-чатов.\n\nДоступно: {current}/{limit} ({plan})",
    "list_empty_channels": "Своих каналов пока нет. Добавь канал, чтобы отслеживать его по ключевым фразам.\n\nДоступно: {current}/{limit} ({plan})",
    "keywords_title": "Твои ключевые фразы ({current}/{limit}):",
    "channels_title": "Твои каналы ({current}/{limit}):",
    "keywords_prompt": "Отправь ключевую фразу. Например: «ищу повара».\n\nДоступно ещё: {remaining}/{limit} ({plan})\n\n/cancel — отмена.",
    "channels_prompt": "Отправь  канала. Например: .\n\nДоступно ещё: {remaining}/{limit} ({plan})\n\n/cancel — отмена.",
    "input_too_short": "Слишком короткое значение. Попробуй ещё раз или отправь /cancel.",
    "channel_invalid": "Некорректный . Попробуй ещё раз или отправь /cancel.",
    "item_added": "✅ Добавлено: {item}",
    "item_delete_confirm": "Удалить {item}?",
    "btn_delete": "🗑 Удалить",
    "item_deleted": "Удалено",
    "item_not_found": "Не найдено",
    "btn_add_keyword": "➕ Добавить фразу",
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
    "catalog_geo": "Где именно ищешь?",
    "catalog_all_country": "🌍 По всей стране",
    "catalog_select_cities": "🏙 Выбрать города",
    "catalog_cities": "Выбери города (выбрано: {count}):",
    "catalog_select_city": "Выбери хотя бы один город",
    "catalog_confirm": "Подтверди поиск:",
    "catalog_new_services": "📌 Новых направлений: {count}",
    "catalog_skipped": "📎 Уже добавлено: {count} (пропущено)",
    "catalog_country_line": "🌍 Страна: {country}",
    "catalog_cities_line": "🏙 Города: {cities}",
    "catalog_activate_hint": "Нажми «Запустить поиск» для активации.",
    "catalog_activate": "✅ Запустить поиск",
    "catalog_error_country": "Страна не выбрана. Начни настройку заново.",
    "settings_title": "⚙️ Настройки",
    "btn_instructions": "📖 Инструкции",
    "support_sent": "📩 Сообщение передано в поддержку. Ответим в ближайшее время.",
    "search_scope_services": "📌 Направления:",
    "search_scope_country": "🌍 {country}",
    "search_scope_cities": "🏙 {cities}",
    "searches_title": "🎯 Мои поиски ({current}/{limit})",
    "searches_empty": "У тебя пока нет поисков. Настрой первый поиск клиентов.",
    "searches_countries": "🌍 Использовано стран: {current}/{limit}",
    "search_created": "✅ Поисков создано: {count}",
    "search_added": "✅ Поисков добавлено: {count}",
    "search_delivery": "Релевантные заявки начнут приходить после обработки новых сообщений.",
    "trial_started": "🎉 Поиск запущен! Trial Business действует до {date}.",
    "trial_after": "После trial контакты скроются. Старт открывает их от ${price}/мес.",
    "free_after_search": "🔒 На Free контакты скрыты. Платный тариф открывает доступные контакты и ссылки.",
    "catalog_error_services": "Направления не выбраны. Начни настройку заново.",
    "btn_main_menu": "🏠 Главное меню",
    "period_1m": "1 месяц",
    "period_3m": "3 месяца (−10%)",
    "period_1y": "1 год (−20%)",
    "payment_period_title": "💳 {plan} — выбери срок:",
    "payment_period_line": "• {period}: ${total} (${monthly}/мес)",
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
    "lead_sender": " от <a href='https://t.me/{sender}'>@{sender}</a>",
    "lead_hidden": "🔒 Контакты скрыты. Автор и ссылка доступны на платном тарифе.",
    "lead_tags": "🏷 {labels}",
    "lead_btn_unlock": "🎯 Открыть контакты — от ${price}/мес",
    "lead_btn_chat": "💬 Чат",
    "lead_btn_sender": "💬 Написать",
}