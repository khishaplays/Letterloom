"""Typed application configuration loaded from environment variables."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Settings sourced from the environment or a local .env file."""

    app_name: str = "Letterloom"
    app_version: str = "0.1.0"
    database_url: str = "postgresql+psycopg://localhost:5432/letterloom"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Return cached settings so the app and migration tooling agree."""

    return Settings()
