from __future__ import annotations

import pytest
from pydantic import SecretStr, ValidationError

from empirical_platform.shared.config.settings import (
    PostgreSQLConfigSnapshot,
    resolve_foundation_config,
)
from empirical_platform.shared.errors import FoundationError


def test_postgresql_config_resolves_safe_connectivity_settings() -> None:
    secret_value = "-".join(("local", "compose", "placeholder"))

    snapshot = resolve_foundation_config(
        {
            "EMPIRICAL_PLATFORM_POSTGRES_HOST": "127.0.0.1",
            "EMPIRICAL_PLATFORM_POSTGRES_PORT": "5432",
            "EMPIRICAL_PLATFORM_POSTGRES_DATABASE": "empirical_platform",
            "EMPIRICAL_PLATFORM_POSTGRES_USER": "empirical",
            "EMPIRICAL_PLATFORM_POSTGRES_PASSWORD": secret_value,
            "EMPIRICAL_PLATFORM_POSTGRES_POOL_SIZE": "2",
            "EMPIRICAL_PLATFORM_POSTGRES_MAX_OVERFLOW": "1",
            "EMPIRICAL_PLATFORM_POSTGRES_CONNECT_TIMEOUT_SECONDS": "3",
        }
    )

    assert snapshot.postgresql.host == "127.0.0.1"
    assert snapshot.postgresql.password is not None
    assert secret_value not in str(snapshot.postgresql.safe_context())
    assert "postgresql+psycopg" in str(snapshot.postgresql.sqlalchemy_url())


def test_postgresql_config_requires_valid_port_and_pool_bounds() -> None:
    with pytest.raises(FoundationError):
        resolve_foundation_config({"EMPIRICAL_PLATFORM_POSTGRES_PORT": "70000"})

    with pytest.raises(ValidationError):
        PostgreSQLConfigSnapshot(pool_size=0)


def test_postgresql_url_requires_password_without_leaking_details() -> None:
    snapshot = PostgreSQLConfigSnapshot(password=None)

    with pytest.raises(FoundationError) as exc_info:
        snapshot.sqlalchemy_url()

    payload = exc_info.value.as_dict()
    assert payload["category"] == "configuration_error"
    assert "password" not in str(payload).lower() or "[REDACTED]" in str(payload)


def test_postgresql_config_snapshot_is_immutable() -> None:
    snapshot = PostgreSQLConfigSnapshot(password=SecretStr("local-compose-placeholder"))

    with pytest.raises(ValidationError):
        snapshot.host = "elsewhere"  # type: ignore[misc]
