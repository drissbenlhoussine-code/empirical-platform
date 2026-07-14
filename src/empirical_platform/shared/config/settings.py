"""Typed settings foundation with safe defaults and secret separation."""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    """Supported runtime environments."""

    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class AppSettings(BaseSettings):
    """Application-level settings."""

    model_config = SettingsConfigDict(
        env_prefix="EMPIRICAL_PLATFORM_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: Environment = Environment.DEVELOPMENT
    correlation_id_header: str = "x-correlation-id"


class DatabaseSettings(BaseSettings):
    """Database settings without schema or business entities."""

    model_config = SettingsConfigDict(
        env_prefix="EMPIRICAL_PLATFORM_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "postgresql://localhost:5432/empirical_platform"


class ObjectStorageSettings(BaseSettings):
    """Object-storage settings without concrete read/write behavior."""

    model_config = SettingsConfigDict(
        env_prefix="EMPIRICAL_PLATFORM_OBJECT_STORAGE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    endpoint: str = "http://localhost:9000"
    region: str = "us-east-1"
    bucket_prefix: str = "empirical-platform-dev"
    access_key: SecretStr | None = None
    secret_key: SecretStr | None = None


class LoggingSettings(BaseSettings):
    """Structured logging settings."""

    model_config = SettingsConfigDict(
        env_prefix="EMPIRICAL_PLATFORM_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    log_level: str = Field(default="INFO", pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$")


class Settings:
    """Aggregated settings object."""

    def __init__(
        self,
        app: AppSettings | None = None,
        database: DatabaseSettings | None = None,
        object_storage: ObjectStorageSettings | None = None,
        logging: LoggingSettings | None = None,
    ) -> None:
        self.app = app or AppSettings()
        self.database = database or DatabaseSettings()
        self.object_storage = object_storage or ObjectStorageSettings()
        self.logging = logging or LoggingSettings()


@lru_cache
def load_settings() -> Settings:
    """Load settings using environment, .env, and safe defaults."""
    return Settings()
