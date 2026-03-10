"""
Application configuration loaded from environment variables.
"""
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # App
    app_name: str = "AI Personal Assistant"
    app_env: str = "development"
    app_debug: bool = True
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_secret_key: str = "change-this-to-a-random-secret-key"

    # Database
    database_url: str = "postgresql+asyncpg://assistant:password@localhost:5432/ai_assistant"
    database_echo: bool = False

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Telegram
    telegram_bot_token: str = ""
    admin_telegram_id: str = ""
    webhook_url: str = ""

    # Claude AI
    anthropic_api_key: str = ""
    ai_model: str = "claude-sonnet-4-5-20250929"
    ai_max_tokens: int = 2048

    # Google Calendar (Phase 2)
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = ""

    # Dashboard Auth — comma-separated list of allowed Google emails
    dashboard_allowed_emails: str = "mvsotso@gmail.com"

    # Web Push (VAPID)
    vapid_public_key: str = ""
    vapid_private_key: str = ""
    vapid_email: str = "mailto:mvsotso@gmail.com"

    # Email (SMTP)
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""
    smtp_from_name: str = "AI Assistant"
    smtp_use_tls: bool = True

    # Celery
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
