# EN locale — all UI texts

TEXTS = {
    # ── Welcome screen ──
    "welcome_title": "🎯 <b>Lead Hunter AI — клиенты уже ищут твои услуги в Telegram!</b>",
    "welcome_body": (
        "Выбери направление деятельности и географию — <b>Lead Hunter AI</b> будет "
        "отслеживать новые сообщения и находить подходящие запросы клиентов.\n\n"
        "В базе сервиса — более 5.000+ Telegram-чатов и каналов.\n\n"
        "Узнавай о новых запросах раньше и первым предлагай свои услуги!\n\n"
        "Запусти первый поиск и бесплатно попробуй возможности тарифа Business "
        "в течение 3 дней.\n\n"
        "--//--//--\n\n"
        "🎯 <b>Lead Hunter AI — potential clients are already looking for your "
        "services on Telegram!</b>\n\n"
        "Choose your industry and target location — <b>Lead Hunter AI</b> will "
        "monitor new messages and find relevant customer requests.\n\n"
        "The Lead Hunter AI database includes more than 5.000+ Telegram chats and channels.\n\n"
        "Discover new opportunities sooner and be the first to offer your services!\n\n"
        "Launch your first search and try Business features free for 3 days."
    ),
    "welcome_lang_prompt": "Выбери язык / Choose language:",

    # ── Onboarding wizard ──
    "onb_step1_title": "What do you do? Choose a category:",
    "onb_step1_placeholder": "Category selection coming in Phase 3",
    "onb_step2_title": "Which country are you looking for clients in?",
    "onb_step2_placeholder": "Country selection coming in Phase 3",
    "onb_step3_title": (
        "🎉 Done! You got 3 days of Business plan.\n"
        "Here are your first leads:"
    ),
    "onb_step3_placeholder": "Leads coming in Phase 5",
    "onb_skip": "⏭ Skip",
    "onb_next": "▶️ Next",

    # ── Main menu ──
    "menu_header": "🎯 LeadHunter",
    "menu_plan": "Your plan: {plan}",
    "menu_searches": "🎯 Active searches: {count}",
    "plan_until": "until {date}",
    "search_delete_confirm": "Delete this search? New leads for it will no longer be delivered.",
    "btn_delete_search": "🗑 Delete search",
    "btn_add_search": "➕ Add search",
    "menu_notifications": "📬 Leads today: {matched}",
    "menu_free_hidden": "🔒 Contacts hidden — unlock them on a paid plan",
    "btn_search": "🚀 Set up first search",
    "btn_searches": "🎯 My searches",
    "btn_results": "📥 Leads & results",
    "btn_keywords": "⚙️ My keywords",
    "btn_channels": "📢 My channels",
    "btn_subscriptions": "🎯 My searches",
    "btn_referral": "🎁 Invite a friend",
    "btn_plan": "💰 Plan & payment",
    "btn_language": "🌐 Language",
    "btn_settings": "⚙️ Settings",
    "btn_about": "ℹ️ About",

    # ── Common ──
    "btn_back": "◀️ Back",
    "btn_cancel": "❌ Cancel",
    "btn_yes": "✅ Yes",
    "btn_no": "❌ No",
    "coming_soon": "🚧 Coming soon",

    # ── Language ──
    "btn_ru": "🇷🇺 Русский",
    "btn_en": "🇬🇧 English",
    "language_set": "✅ Language set: English",

    # ── Plan & payment screen (T3.1) ──
    "plan_title": "💰 Plan & payment",
    "plan_current": "Your plan: {plan}",
    "plan_card_start": (
        "🎯 Start — ${price}/mo\n"
        "For a specialist working in one city\n"
        "• 1 service · 1 country · 1 city\n"
        "• 3 keywords · 1 custom channel · full contacts"
    ),
    "plan_card_pro": (
        "🚀 Pro — ${price}/mo · recommended\n"
        "For active client acquisition across several locations\n"
        "• up to 3 services · 3 countries · 9 cities\n"
        "• 20 keywords · 10 custom channels · regex · statistics"
    ),
    "plan_card_business": (
        "🏆 Business — ${price}/mo\n"
        "For a team or agency with broad coverage\n"
        "• up to 12 services · 9 countries · unlimited cities within them\n"
        "• 50 keywords · 50 custom channels · CSV · full statistics"
    ),
    "plan_discounts": "Save more: 3 months −10% · year −20%",
    "plan_btn_start": "🎯 Start — ${price}",
    "plan_btn_pro": "🚀 Pro — ${price}",
    "plan_btn_business": "🏆 Business — ${price}",
    "plan_btn_current": "✅ {name} · yours",

    # ── End-of-day report for Free (T4.2) ──
    "eod_body": (
        "📊 <b>Demand in your niche today</b>\n\n"
        "Total leads found: {total}.\n"
        "Shown with hidden contacts: {delivered}.\n"
        "Leads missed: {missed}.\n\n"
        "Subscribe to receive new leads immediately with contacts and a chat link."
    ),
    "eod_btn_start": "🎯 Start — ${price}/mo",
    "eod_btn_pro": "🚀 Pro — ${price}/mo",
    "eod_btn_business": "🏆 Business — ${price}/mo",
    "eod_zero": ("🔎 <b>No leads matched your current settings today</b>\n\n"
        "Try broadening your location, reviewing services, or adding keywords and custom channels."),
    "eod_zero_btn": "⚙️ Review searches",

    # ── Statistics (T5.1) ──
    "stats_title": "📈 Lead statistics",
    "stats_period": "Last {days} days: {total} leads",
    "stats_byday_header": "By day:",
    "stats_byseg_header": "By category:",
    "stats_empty": "No leads in the selected period yet.",
    "btn_stats": "📈 Statistics",
    "btn_csv": "📥 CSV export",
    "btn_digest": "🔔 Notification mode",
    "digest_header": "📬 {count} new leads for the period:",
    "digest_title": "🔔 Notification delivery mode",
    "digest_instant": "⚡ Instant",
    "digest_hourly": "🕐 Hourly",
    "digest_daily2": "🌅 Twice a day",
    "digest_saved": "✅ Mode updated",
    "csv_caption": "📥 Leads for {days} days ({count})",
    "csv_empty": "No leads to export for the last {days} days.",

    # ── Contextual paywalls (T4.1) ──
    "paywall_title": "🔒 Current plan limit",
    "paywall_stats": "Lead statistics — on {plan} (${price}/mo).",
    "paywall_csv": "CSV export — on {plan} (${price}/mo).",
    "paywall_keyword": "More keywords — on {plan} (${price}/mo).",
    "paywall_direction": "More categories and countries — on {plan} (${price}/mo).",
    "paywall_country": "Multiple countries — on {plan} (${price}/mo).",
    "paywall_city": "More cities — on {plan} (${price}/mo).",
    "paywall_channel": "More channels — on {plan} (${price}/mo).",

    # ── Payment error (T2.2) ──
    "pay_error_body": (
        "❌ <b>Payment failed</b>\n\n"
        "The payment didn't go through. Try again or choose another payment method."
    ),
    "pay_error_expired": (
        "⌛️ <b>Invoice expired</b>\n\n"
        "Payment wasn't received in time. Tap “Retry” to create a new invoice."
    ),
    "pay_err_retry": "🔄 Retry",
    "pay_err_other": "💱 Another method",
    "reminder_trial_ending_2": "⏳ Your trial ends in 2 days.\nClient contacts will then be hidden. Keep access with Start from ${start}/mo.",
    "reminder_trial_ending_1": "⏳ Your trial ends tomorrow.\nLeads will remain visible without contacts. Start (${start}/mo) keeps them open.",
    "reminder_subscription_ending_5": "⏳ Your subscription ends in 5 days.\nRenew to keep receiving leads without interruption.",
    "reminder_btn_plans": "🎯 Plans — from ${price}/mo",
    "reminder_btn_search": "🔍 Find clients",
    "reminder_btn_renew": "🔄 Renew",
    "reminder_btn_other_plans": "📋 Other plans",
    "winback_offer": ("🎁 <b>Personal 25% discount on a 3-month plan</b>\n\n"
        "Leads found in your niche over 30 days: {missed}.\n"
        "Choose a 3-month plan — the discount is applied automatically.\n\n"
        "This is a one-time offer valid for 12 hours, until {expires}."),
    "winback_btn_start": "🎯 Start for 3 months — ${total}",
    "winback_btn_pro": "🚀 Pro for 3 months — ${total}",
    "winback_btn_business": "🏆 Business for 3 months — ${total}",
    "winback_expired": "⌛️ Your personal offer has expired. Choose a plan at the regular price.",
    "winback_payment_title": "🎁 25% discount applied\n\nPlan: {plan}\nTerm: 3 months\nTotal: ${total}\nOffer valid until {expires}.\n\nChoose a payment method:",
    "list_count": "Added: {current}/{limit}",
    "list_empty_keywords": "No custom keywords yet. Add a phrase to receive matches from Telegram chats.\n\nAvailable: {current}/{limit} ({plan})",
    "list_empty_channels": "No custom channels yet. Add a channel to track it using your keywords.\n\nAvailable: {current}/{limit} ({plan})",
    "keywords_title": "Your custom keywords ({current}/{limit}):",
    "channels_title": "Your channels ({current}/{limit}):",
    "keywords_prompt": "Send a keyword or phrase, for example: “looking for a chef”.\n\nAvailable: {remaining}/{limit} ({plan})\n\n/cancel — cancel.",
    "channels_prompt": "Send a channel , for example: .\n\nAvailable: {remaining}/{limit} ({plan})\n\n/cancel — cancel.",
    "input_too_short": "That value is too short. Try again or send /cancel.",
    "channel_invalid": "Invalid . Try again or send /cancel.",
    "item_added": "✅ Added: {item}",
    "item_delete_confirm": "Delete {item}?",
    "btn_delete": "🗑 Delete",
    "item_deleted": "Deleted",
    "item_not_found": "Not found",
    "btn_add_keyword": "➕ Add keyword",
    "btn_add_channel": "➕ Add channel",
    "channel_private_pending": "⏳ @{channel} appears to be private. It was sent to an administrator for manual review.",
    "more_items": "… and {count} more",
    "catalog_categories": "Choose services ({current}/{limit}):\n\nSelect a category to choose services.",
    "catalog_done": "✅ Done ({count} selected)",
    "catalog_missing": "💬 Don’t see your service? Contact support",
    "catalog_services": "{category} — choose services ({current}/{limit}):",
    "catalog_continue": "✅ Continue ({count})",
    "catalog_select_service": "Select at least one service",
    "catalog_country": "Which country should we search in?",
    "catalog_geo": "Where should we look?",
    "catalog_all_country": "🌍 Entire country",
    "catalog_select_cities": "🏙 Select cities",
    "catalog_cities": "Select cities (selected: {count}):",
    "catalog_select_city": "Select at least one city",
    "catalog_confirm": "Confirm your search:",
    "catalog_new_services": "📌 New services: {count}",
    "catalog_skipped": "📎 Already added: {count} (skipped)",
    "catalog_country_line": "🌍 Country: {country}",
    "catalog_cities_line": "🏙 Cities: {cities}",
    "catalog_activate_hint": "Tap “Start search” to activate it.",
    "catalog_activate": "✅ Start search",
    "catalog_error_country": "No country selected. Start the setup again.",
    "instructions_body": ("📖 <b>How to use LeadHunter</b>\n\n"
        "1. Set up a search: choose services, a country, and cities.\n"
        "2. Add custom keywords and channels in Settings.\n"
        "3. Relevant new messages will arrive automatically.\n"
        "4. Paid plans include available contacts and chat links.\n\n"
        "Payment: Plan & payment → plan → period → Telegram Stars or CryptoBot. Your plan activates automatically after confirmation."),
    "about_body": ("ℹ️ <b>LeadHunter</b>\n\n"
        "Automatically monitors new messages in Telegram sources and selects requests matching your services and locations.\n\n"
        "📊 Sources in the catalog: {channels}\n"
        "🌍 Countries: {countries}\n"
        "🤖 Irrelevant-message filtering\n"
        "📬 Unlimited notifications on every plan\n"
        "🔒 Available contacts and chat links are included with paid plans\n"
        "🆓 Your first search starts a free 3-day Business trial"),
    "referral_share": "LeadHunter automatically finds client requests in Telegram chats by service and location. My link gives you {trial_days} free days of Business.\n\n{link}",
    "referral_body": ("🎁 <b>Invite a friend</b>\n\n"
        "Your friend gets +{referral_bonus} trial days — {trial_days} days of Business in total.\n"
        "After their first payment, you get +{bonus} days on your current or previous plan.\n"
        "If you have never had a plan, we activate Start.\n\n"
        "🔗 {link}\n\n📊 Invited: {invited} · paid: {activated} · credited: {bonus_days} days."),
    "referral_reward": "🎁 Your friend subscribed!\n\n{days} days were added to your {plan} plan.\n📅 Valid until: {date}",
    "referral_share_btn": "📤 Share with a friend",

    "settings_title": "⚙️ Settings",
    "btn_instructions": "📖 Instructions",
    "support_sent": "📩 Your message was sent to support. We will reply as soon as possible.",
    "search_scope_services": "📌 Services:",
    "search_scope_country": "🌍 {country}",
    "search_scope_cities": "🏙 {cities}",
    "searches_title": "🎯 My searches ({current}/{limit})",
    "searches_empty": "You do not have any searches yet. Set up your first client search.",
    "searches_countries": "🌍 Countries used: {current}/{limit}",
    "search_created": "✅ Searches created: {count}",
    "search_added": "✅ Searches added: {count}",
    "search_delivery": "Relevant leads will arrive after new messages are processed.",
    "trial_started": "🎉 Search started! Your Business trial is active until {date}.",
    "trial_after": "After the trial, contacts will be hidden. Start unlocks them from ${price}/mo.",
    "free_after_search": "🔒 Free hides contacts. A paid plan unlocks available contacts and links.",
    "catalog_error_services": "No services selected. Start the setup again.",
    "btn_main_menu": "🏠 Main menu",
    "period_1m": "1 month",
    "period_3m": "3 months (−10%)",
    "period_1y": "1 year (−20%)",
    "payment_period_title": "💳 {plan} — choose a billing period:",
    "payment_period_line": "• {period}: ${total} (${monthly}/mo), save ${savings}",
    "payment_period_line_regular": "• {period}: ${total}",
    "payment_period_recommended": "🔥 3 months — best value",
    "payment_period_button": "{period} — ${total}",
    "payment_method_title": "💳 Pay for {plan}\n\nPeriod: {period}\nTotal: ${total}\n\nChoose a payment method:",
    "payment_crypto_unavailable": "CryptoBot is temporarily unavailable.",
    "payment_invoice_created": "💳 Invoice created!\n\nTotal: ${total}\n\nPay using the button below — your plan will activate automatically.",
    "payment_btn_pay": "💳 Pay",
    "annual_offer": "💡 Monthly payments for a year: ${monthly_total}.\nAnnual {plan}: ${year_total} (−20%).",
    "annual_offer_btn": "💳 Annual — ${total}",
    "feedback_thanks": "👍 Thank you!",
    "feedback_not_relevant": "👎 Thank you, your feedback was saved — we are improving accuracy.",
    "error_generic": "⚠️ Something went wrong. Please try again.",
    "error_user_not_found": "⚠️ User not found. Tap /start.",
    "payment_success": "✅ Payment successful!\n\nPlan: {plan}\nPeriod: {period}\nValid until: {date}",
    "lead_title": "🎯 <b>I found a new client! | Lead Hunter AI</b>",
    "lead_chat": "💬 {chat}",
    "lead_sender": " from <a href='https://t.me/{sender}'>@{sender}</a>",
    "lead_hidden": "🔒 Contacts are hidden. The author and link are available on a paid plan.",
    "lead_tags": "🏷 {labels}",
    "lead_paywall_title": "🔒 Unlock contacts for this lead",
    "lead_paywall_preview": "Lead: “{preview}”",
    "lead_paywall_access": "Start unlocks available contacts and links in new notifications.",
    "lead_btn_unlock": "🎯 Unlock contacts — from ${price}/mo",
    "lead_btn_chat": "💬 Chat",
    "lead_btn_sender": "💬 Message",
}