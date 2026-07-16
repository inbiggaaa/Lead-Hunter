from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Telegram
    bot_token: str
    owner_telegram_id: int

    # Userbot
    userbot_api_id: int
    userbot_api_hash: str
    userbot_phone: str = ""

    # Userbot account 2 (optional — separate API credentials for second phone number)
    userbot_2_api_id: int = 0
    userbot_2_api_hash: str = ""
    userbot_2_phone: str = ""

    def get_userbot_creds(self, account_id: int) -> tuple[int, str, str]:
        """Return (api_id, api_hash, phone) for a given account_id (1-based)."""
        if account_id == 1:
            return (self.userbot_api_id, self.userbot_api_hash, self.userbot_phone)
        if account_id == 2:
            api_id = self.userbot_2_api_id or self.userbot_api_id
            api_hash = self.userbot_2_api_hash or self.userbot_api_hash
            return (api_id, api_hash, self.userbot_2_phone)
        raise ValueError(f"No credentials configured for account {account_id}")

    # Explicit account identity: "id:session_name" pairs, comma-separated.
    # Account IDs are baked into Redis keys (budget:used:{id}, circuit:*:{id},
    # ban_count:{id}, session:*:{id}) — they must stay stable no matter what
    # session files appear on disk. NEVER renumber existing accounts.
    userbot_session_map: str = "1:userbot,2:userbot2"

    @property
    def userbot_sessions(self) -> dict[int, str]:
        """Parse userbot_session_map into {account_id: session_name}."""
        mapping: dict[int, str] = {}
        for pair in self.userbot_session_map.split(","):
            pair = pair.strip()
            if not pair:
                continue
            account_id_raw, _, name = pair.partition(":")
            account_id = int(account_id_raw)
            name = name.strip()
            if not name:
                raise ValueError(f"Empty session name in userbot_session_map: {pair!r}")
            if account_id in mapping:
                raise ValueError(f"Duplicate account_id in userbot_session_map: {account_id}")
            mapping[account_id] = name
        return mapping

    # Database
    postgres_host: str = "db"
    postgres_port: int = 5432
    postgres_user: str = "leadhunter"
    postgres_password: str
    postgres_db: str = "leadhunter"

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def database_url_sync(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    # Redis
    redis_host: str = "redis"
    redis_port: int = 6379
    redis_db: int = 0

    # Admin
    admin_password: str
    admin_secret: str = ""
    admin_public_port: int = 17421

    # Payments
    cryptobot_api_token: str = ""
    cryptobot_testnet: bool = False

    # LLM
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-chat"
    llm_enabled: bool = False           # master switch for LLM validator
    llm_mode: str = "shadow"            # "shadow" (log only) | "blocking" (filter)
    exclude_broadcast_channels: bool = True  # skip broadcast-only channels (not chats)

    # Monitoring
    sentry_dsn: str = ""

    # Limits (тарифы v2, #81 — метрика ценности = широта покрытия)
    max_segments_free: int = 1
    max_segments_start: int = 1
    max_segments_pro: int = 3
    max_segments_business: int = 12
    max_channels_free: int = 1
    max_channels_start: int = 1
    max_channels_pro: int = 10
    max_channels_business: int = 50
    max_keywords_free: int = 1
    max_keywords_start: int = 3
    max_keywords_pro: int = 20
    max_keywords_business: int = 50
    # Гео-лимиты: Free/Start — одна страна и один город; Pro — до 3 стран
    # и 9 distinct-городов суммарно; Business/Trial — до 9 стран, города без лимита.
    max_cities_free: int = 1
    max_countries_start: int = 1
    max_cities_start: int = 1
    max_countries_pro: int = 3
    max_cities_pro: int = 9
    max_countries_business: int = 9
    # Deprecated env compatibility; runtime matrix does not read these fields.
    business_hidden_cap_channels: int = 60
    business_hidden_cap_keywords: int = 60
    business_hidden_cap_segments: int = 60
    trial_days: int = 3
    referral_trial_bonus: int = 4
    referral_bonus_days: int = 10
    max_referrals_per_month: int = 10
    heartbeat_interval_minutes: int = 15
    sender_throttle_per_second: int = 25

    # Userbot rate limiter (per-account)
    userbot_min_interval: float = 1.5   # seconds between API calls per account
    daily_request_budget: int = 10000    # max API calls per account per day
    flood_sleep_threshold: int = 60       # Telethon auto-sleep short FloodWait; longer → exception
    poll_parked_countries: bool = False  # only poll channels from countries with active subscribers
    message_max_age_days: int = 7        # skip messages older than N days (0 = disabled)
    keyword_match_window: int = 20       # C2: multi-word phrase words must fit in N tokens

    # Discovery v2
    discovery_enabled: bool = False       # ENV: DISCOVERY_ENABLED=true
    discovery_api_id: int = 0
    discovery_api_hash: str = ""
    discovery_phone: str = ""
    discovery_session_name: str = "discovery"
    discovery_account_id: int = 3          # 3 = dedicated, other = manual/test mode
    discovery_daily_limit: int = 500       # max SearchRequests per day (dedicated mode)
    discovery_manual_daily_limit: int = 100  # max per day in manual/test mode
    discovery_flood_sleep_threshold: int = 120

    # Tier intervals (Task 1.3 — all configurable, no hardcoded constants)
    hot_interval_base: int = 300          # seconds, Hot base (2 healthy accounts)
    hot_interval_3plus: int = 420         # seconds, Hot for 3+ accounts (7 min)
    warm_interval: int = 3000             # seconds, Warm tier (50 min)
    cold_interval: int = 9000             # seconds, Cold tier (2.5 h)
    dormant_interval: int = 43200         # seconds, Dormant tier (12 h)
    hot_degraded_multiplier: float = 2.0  # ×2 when only 1 healthy account
    post_ban_interval_multiplier: float = 1.5  # ×1.5 during post-ban mode
    review_score_threshold: float = 0.90  # ниже → канал в needs_review (карантин)
    hot_interval_cap: int = 1200          # seconds, effective interval ceiling (20 min)
    daily_report_hour: int = 19
    stars_per_usd: int = 100
    admin_channel_id: int = 0

    # Session backup (used by backup.sh, not Python)
    session_backup_passphrase: str = ""

    # Prices (тарифы v2, #81)
    price_start_monthly_usd: int = 9
    price_pro_monthly_usd: int = 19
    price_business_monthly_usd: int = 39

    # extra="ignore": tolerate stale/unknown env keys (e.g. obsolete
    # NOTIFICATIONS_PER_DAY_* left in an old baked .env after tariffs v2) so a
    # dropped setting never crashes a service on restart.
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
