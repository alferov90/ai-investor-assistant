from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://investor:investor@localhost:5432/investor"
    redis_url: str = "redis://localhost:6379/0"
    secret_key: str = "change-me-in-production-use-openssl-rand-hex-32"
    access_token_expire_minutes: int = 60 * 24 * 7
    algorithm: str = "HS256"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    yandex_cloud_api_key: str = ""
    yandex_cloud_folder_id: str = ""
    yandex_gpt_model: str = "yandexgpt/latest"
    stock_cache_ttl_seconds: int = 300
    twelve_data_api_key: str = ""
    yahoo_proxy_url: str = ""
    yahoo_fetch_timeout_seconds: int = 10
    finnhub_api_key: str = ""
    telegram_bot_token: str = ""
    telegram_bot_username: str = ""
    telegram_proxy_url: str = ""
    telegram_digest_hour: int = 6  # UTC; 6 = 09:00 MSK
    telegram_digest_minute: int = 0


settings = Settings()
