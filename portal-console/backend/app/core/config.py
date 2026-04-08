from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Portal Console"
    api_v1_prefix: str = "/api"
    secret_key: str = Field(default="change-me-in-production", alias="SECRET_KEY")
    access_token_expire_minutes: int = 60 * 12
    database_url: str = Field(
        default="sqlite:///./portal_console.db",
        alias="DATABASE_URL",
    )

    first_superuser: str = Field(default="admin", alias="FIRST_SUPERUSER")
    first_superuser_password: str = Field(default="admin123", alias="FIRST_SUPERUSER_PASSWORD")

    ssh_key_storage_dir: str = Field(default="./data/ssh_keys", alias="SSH_KEY_STORAGE_DIR")
    ssh_key_encryption_secret: str = Field(
        default="change-this-key-encryption-secret",
        alias="SSH_KEY_ENCRYPTION_SECRET",
    )

    rundeck_url: str | None = Field(default=None, alias="RUNDECK_URL")
    rundeck_token: str | None = Field(default=None, alias="RUNDECK_TOKEN")
    rundeck_api_version: int = Field(default=57, alias="RUNDECK_API_VERSION")
    rundeck_poll_attempts: int = Field(default=3, alias="RUNDECK_POLL_ATTEMPTS")
    rundeck_poll_interval_seconds: float = Field(default=2.0, alias="RUNDECK_POLL_INTERVAL_SECONDS")

    kuma_url: str | None = Field(default=None, alias="KUMA_URL")
    kuma_token: str | None = Field(default=None, alias="KUMA_TOKEN")

    cors_origins: list[str] = Field(
        default=["http://localhost:5173", "http://127.0.0.1:5173"],
        alias="CORS_ORIGINS",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
