"""Typed settings foundation with safe defaults and secret separation."""

from __future__ import annotations

import os
from collections.abc import Mapping
from enum import StrEnum
from functools import lru_cache

from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL

from empirical_platform.shared.config.redaction import redact_mapping
from empirical_platform.shared.errors import FoundationError, FoundationErrorCategory


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


class AppConfigSnapshot(BaseModel):
    """Immutable application configuration snapshot."""

    model_config = ConfigDict(frozen=True)

    environment: Environment = Environment.DEVELOPMENT
    correlation_id_header: str = "x-correlation-id"


class LoggingConfigSnapshot(BaseModel):
    """Immutable logging configuration snapshot."""

    model_config = ConfigDict(frozen=True)

    log_level: str = Field(default="INFO", pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$")


class PostgreSQLConfigSnapshot(BaseModel):
    """Immutable PostgreSQL connectivity configuration snapshot."""

    model_config = ConfigDict(frozen=True)

    host: str = "localhost"
    port: int = Field(default=5432, ge=1, le=65535)
    database: str = "empirical_platform"
    user: str = "empirical"
    password: SecretStr | None = None
    pool_size: int = Field(default=5, ge=1, le=50)
    max_overflow: int = Field(default=0, ge=0, le=50)
    connection_timeout_seconds: int = Field(default=5, ge=1, le=60)
    application_name: str = "empirical-platform"

    def sqlalchemy_url(self) -> URL:
        """Build a SQLAlchemy PostgreSQL URL without exposing it in diagnostics."""
        if self.password is None:
            raise FoundationError(
                category=FoundationErrorCategory.CONFIGURATION,
                message="PostgreSQL password is required for connectivity",
                layer="configuration",
                operation="postgresql_url",
                context=self.safe_context(),
            )
        return URL.create(
            "postgresql+psycopg",
            username=self.user,
            password=self.password.get_secret_value(),
            host=self.host,
            port=self.port,
            database=self.database,
        )

    def safe_context(self) -> dict[str, object]:
        """Return redacted PostgreSQL connectivity diagnostics."""
        return {
            "host": self.host,
            "port": self.port,
            "database": self.database,
            "user": self.user,
            "password_configured": self.password is not None,
            "pool_size": self.pool_size,
            "max_overflow": self.max_overflow,
            "connection_timeout_seconds": self.connection_timeout_seconds,
            "application_name": self.application_name,
        }


class FoundationConfigSnapshot(BaseModel):
    """Canonical immutable process-local configuration snapshot."""

    model_config = ConfigDict(frozen=True)

    app: AppConfigSnapshot = Field(default_factory=AppConfigSnapshot)
    logging: LoggingConfigSnapshot = Field(default_factory=LoggingConfigSnapshot)
    postgresql: PostgreSQLConfigSnapshot = Field(default_factory=PostgreSQLConfigSnapshot)

    def safe_context(self) -> dict[str, object]:
        """Return a redacted context representation."""
        return redact_mapping(self.model_dump(mode="json"))


def resolve_foundation_config(
    environ: Mapping[str, str] | None = None,
) -> FoundationConfigSnapshot:
    """Resolve the process-local foundation configuration once."""
    source = os.environ if environ is None else environ
    try:
        return FoundationConfigSnapshot(
            app=AppConfigSnapshot(
                environment=Environment(
                    source.get("EMPIRICAL_PLATFORM_ENVIRONMENT", Environment.DEVELOPMENT)
                ),
                correlation_id_header=source.get(
                    "EMPIRICAL_PLATFORM_CORRELATION_ID_HEADER", "x-correlation-id"
                ),
            ),
            logging=LoggingConfigSnapshot(
                log_level=source.get("EMPIRICAL_PLATFORM_LOG_LEVEL", "INFO")
            ),
            postgresql=PostgreSQLConfigSnapshot(
                host=source.get("EMPIRICAL_PLATFORM_POSTGRES_HOST", "localhost"),
                port=int(source.get("EMPIRICAL_PLATFORM_POSTGRES_PORT", "5432")),
                database=source.get("EMPIRICAL_PLATFORM_POSTGRES_DATABASE", "empirical_platform"),
                user=source.get("EMPIRICAL_PLATFORM_POSTGRES_USER", "empirical"),
                password=(
                    SecretStr(source["EMPIRICAL_PLATFORM_POSTGRES_PASSWORD"])
                    if "EMPIRICAL_PLATFORM_POSTGRES_PASSWORD" in source
                    else None
                ),
                pool_size=int(source.get("EMPIRICAL_PLATFORM_POSTGRES_POOL_SIZE", "5")),
                max_overflow=int(source.get("EMPIRICAL_PLATFORM_POSTGRES_MAX_OVERFLOW", "0")),
                connection_timeout_seconds=int(
                    source.get("EMPIRICAL_PLATFORM_POSTGRES_CONNECT_TIMEOUT_SECONDS", "5")
                ),
                application_name=source.get(
                    "EMPIRICAL_PLATFORM_POSTGRES_APPLICATION_NAME",
                    "empirical-platform",
                ),
            ),
        )
    except (ValueError, ValidationError) as exc:
        raise FoundationError.wrap(
            exc,
            category=FoundationErrorCategory.CONFIGURATION,
            message="Foundation configuration resolution failed",
            layer="configuration",
            operation="resolve_foundation_config",
            context={"environment_keys": sorted(source.keys())},
        ) from exc


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
