# EN locale — all UI texts

TEXTS = {
    # ── Welcome screen ──
    "welcome_title": "🎯 LeadHunter",
    "welcome_body": (
        "<b>Lead Hunter AI — client request monitoring on Telegram</b>\n\n"
        "The service tracks public Telegram channels in real time "
        "and identifies messages from potential clients in your "
        "line of business. Relevant leads are delivered to you as notifications.\n\n"
        "<b>What you get:</b>\n\n"
        "✔️ A steady flow of inbound leads — no manual searching\n"
        "✔️ Setup by category, geography, and keywords\n"
        "✔️ Unlimited notifications on every plan\n"
        "✔️ First-contact advantage over competitors\n"
        "✔️ 24/7 automated operation\n\n"
        "Lead Hunter AI handles client discovery — "
        "so you can focus on working with them.\n\n"
        "A free trial is available — 5 days of the Business plan.\n\n"
        "Tap the button below to get started. 👇"
    ),
    "welcome_lang_prompt": "Выбери язык / Choose language:",

    # ── Onboarding wizard ──
    "onb_step1_title": "What do you do? Choose a category:",
    "onb_step1_placeholder": "Category selection coming in Phase 3",
    "onb_step2_title": "Which country are you looking for clients in?",
    "onb_step2_placeholder": "Country selection coming in Phase 3",
    "onb_step3_title": (
        "🎉 Done! You got 5 days of Business plan.\n"
        "Here are your first leads:"
    ),
    "onb_step3_placeholder": "Leads coming in Phase 5",
    "onb_skip": "⏭ Skip",
    "onb_next": "▶️ Next",

    # ── Main menu ──
    "menu_header": "🎯 LeadHunter",
    "menu_plan": "Your plan: {plan}",
    "menu_notifications": "📬 Leads today: {matched}",
    "menu_free_hidden": "🔒 Contacts hidden — unlock them on a paid plan",
    "btn_search": "🔍 Find clients",
    "btn_keywords": "⚙️ My keywords",
    "btn_channels": "📢 My channels",
    "btn_subscriptions": "📋 My subscriptions",
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
        "• 1 service · 1 country · 1 city\n"
        "• 3 keywords · 1 channel · full contacts"
    ),
    "plan_card_pro": (
        "🚀 Pro — ${price}/mo\n"
        "• 3 services · 3 countries · up to 9 cities\n"
        "• 20 keywords · 10 channels · regex · stats"
    ),
    "plan_card_business": (
        "🏆 Business — ${price}/mo\n"
        "• 12 services · 9 countries · unlimited cities\n"
        "• 50 keywords · 50 channels · CSV · full stats"
    ),
    "plan_discounts": "3 mo −10% · year −20%",
    "plan_btn_start": "🎯 Start — ${price}",
    "plan_btn_pro": "🚀 Pro — ${price}",
    "plan_btn_business": "🏆 Business — ${price}",
    "plan_btn_current": "✅ {name} · yours",

    # ── End-of-day report for Free (T4.2) ──
    "eod_body": (
        "📊 <b>Your day</b>\n\n"
        "New leads today: {count}.\n"
        "Contacts are hidden — Free shows only the text.\n\n"
        "Each hidden contact goes to whoever replies first."
    ),
    "eod_btn": "🎯 Unlock contacts — from ${price}/mo",

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
    "reminder_trial_expired_1": "⏰ Your trial has ended. Leads still arrive, but contacts are hidden.\nUnlock them again with Start from ${start}/mo.",
    "reminder_trial_expired_3": "🔒 Three days without contacts. Restore access from ${start}/mo.",
    "reminder_trial_expired_7": "📊 One week on Free. Leads are visible, but authors are hidden.\nUnlock contacts with Start from ${start}/mo.",
    "reminder_subscription_ending_5": "⏳ Your subscription ends in 5 days.\nRenew to keep receiving leads without interruption.",
    "reminder_subscription_expired_1": "⏰ Your subscription term has ended. The grace period is now active.\nRenew to keep uninterrupted access.",
    "reminder_subscription_expired_3": "⏳ Your grace period is active. Renew to keep access.",
    "reminder_subscription_expired_7": "⏳ This is the final day of your grace period. Renew to keep access.",
    "reminder_inactive_14": "👋 Open LeadHunter and review your searches.",
    "reminder_inactive_28": "📊 Review your active searches and LeadHunter settings.",
    "reminder_winback_missed_14": "📊 Leads found in your niche over two weeks: {missed}. Contacts were hidden.\nRestore access with Start from ${start}/mo.",
    "reminder_winback_missed_28": "📊 Leads found in your niche this month: {missed}. Contacts were hidden.\nRestore access from ${start}/mo.",
    "reminder_btn_plans": "🎯 Plans — from ${price}/mo",
    "reminder_btn_search": "🔍 Find clients",
    "reminder_btn_renew": "🔄 Renew",
    "reminder_btn_other_plans": "📋 Other plans",
    "periodic_weekly_digest": "📊 Review your weekly results in LeadHunter.",
    "periodic_niche_growth": "🌱 Review current sources and search settings.",
    "periodic_monthly_summary": "📈 Review your monthly results in LeadHunter.",
    "periodic_upgrade": "🔒 Author contacts are available on a paid plan — Start from ${price}/mo.",
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
    "lead_btn_unlock": "🎯 Unlock contacts — from ${price}/mo",
    "lead_btn_chat": "💬 Chat",
    "lead_btn_sender": "💬 Message",
}