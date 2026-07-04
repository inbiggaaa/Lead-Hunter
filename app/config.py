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

    # Limits
    max_segments_free: int = 1
    max_segments_pro: int = 3
    max_channels_free: int = 1
    max_channels_pro: int = 15
    max_keywords_free: int = 1
    max_keywords_pro: int = 50
    notifications_per_day_free: int = 50
    notifications_per_day_pro: int = 150
    trial_days: int = 5
    referral_trial_bonus: int = 3
    referral_bonus_days: int = 7
    max_referrals_per_month: int = 10
    heartbeat_interval_minutes: int = 15
    sender_throttle_per_second: int = 25

    # Userbot rate limiter (per-account)
    userbot_min_interval: float = 1.5   # seconds between API calls per account
    daily_request_budget: int = 10000    # max API calls per account per day
    flood_sleep_threshold: int = 60       # Telethon auto-sleep short FloodWait; longer → exception
    poll_parked_countries: bool = False  # poll channels from countries with no subscriptions
    message_max_age_days: int = 7        # skip messages older than N days (0 = disabled)

    # Tier intervals (Task 1.3 — all configurable, no hardcoded constants)
    hot_interval_base: int = 300          # seconds, Hot base (2 healthy accounts)
    hot_interval_3plus: int = 420         # seconds, Hot for 3+ accounts (7 min)
    warm_interval: int = 3000             # seconds, Warm tier (50 min)
    cold_interval: int = 9000             # seconds, Cold tier (2.5 h)
    dormant_interval: int = 43200         # seconds, Dormant tier (12 h)
    hot_degraded_multiplier: float = 2.0  # ×2 when only 1 healthy account
    post_ban_interval_multiplier: float = 1.5  # ×1.5 during post-ban mode
    hot_interval_cap: int = 1200          # seconds, effective interval ceiling (20 min)
    daily_report_hour: int = 19
    business_hidden_cap_channels: int = 60
    business_hidden_cap_keywords: int = 60
    business_hidden_cap_segments: int = 60
    stars_per_usd: int = 100
    admin_channel_id: int = 0

    # Session backup (used by backup.sh, not Python)
    session_backup_passphrase: str = ""

    # Prices
    price_pro_monthly_usd: int = 5
    price_business_monthly_usd: int = 15

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
