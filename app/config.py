from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Telegram
    bot_token: str
    owner_telegram_id: int

    # Userbot
    userbot_api_id: int
    userbot_api_hash: str
    userbot_phone: str = ""

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

    # Payments
    cryptobot_api_token: str = ""
    cryptobot_testnet: bool = False

    # LLM
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-chat"

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
    daily_report_hour: int = 19
    business_hidden_cap_channels: int = 60
    business_hidden_cap_keywords: int = 60
    business_hidden_cap_segments: int = 60

    # Prices
    price_pro_monthly_usd: int = 5
    price_business_monthly_usd: int = 15

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
