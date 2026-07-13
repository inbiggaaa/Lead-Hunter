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
        "• 1 category · 1 country / 3 cities\n"
        "• 10 keywords · 1 channel · contacts shown"
    ),
    "plan_card_pro": (
        "🚀 Pro — ${price}/mo\n"
        "• 5 categories · 5 countries\n"
        "• 50 keywords · 10 channels · regex · stats"
    ),
    "plan_card_business": (
        "🏆 Business — ${price}/mo\n"
        "• No limits · CSV · full stats"
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

    # ── Contextual paywalls (T4.1) ──
    "paywall_title": "🔒 Current plan limit",
    "paywall_keyword": "More keywords — on {plan} (${price}/mo).",
    "paywall_direction": "More categories and countries — on {plan} (${price}/mo).",
    "paywall_country": "Multiple countries — on {plan} (${price}/mo).",
    "paywall_city": "Unlimited cities — on {plan} (${price}/mo).",
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
}
