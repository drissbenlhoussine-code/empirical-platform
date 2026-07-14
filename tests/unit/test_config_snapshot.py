from __future__ import annotations

import pytest
from pydantic import ValidationError

from empirical_platform.shared.config.settings import (
    Environment,
    FoundationConfigSnapshot,
    resolve_foundation_config,
)
from empirical_platform.shared.errors import FoundationError


def test_resolve_foundation_config_uses_defaults_and_supplied_environment() -> None:
    snapshot = resolve_foundation_config(
        {
            "EMPIRICAL_PLATFORM_ENVIRONMENT": "test",
            "EMPIRICAL_PLATFORM_LOG_LEVEL": "DEBUG",
        }
    )

    assert snapshot.app.environment is Environment.TEST
    assert snapshot.logging.log_level == "DEBUG"


def test_resolve_foundation_config_rejects_invalid_values_without_partial_snapshot() -> None:
    with pytest.raises(FoundationError) as exc_info:
        resolve_foundation_config({"EMPIRICAL_PLATFORM_LOG_LEVEL": "LOUD"})

    assert exc_info.value.category == "configuration_error"
    assert "LOUD" not in str(exc_info.value.as_dict())


def test_foundation_config_snapshot_is_immutable() -> None:
    snapshot = FoundationConfigSnapshot()

    with pytest.raises(ValidationError):
        snapshot.logging.log_level = "DEBUG"  # type: ignore[misc]


def test_foundation_config_safe_context_redacts_sensitive_values() -> None:
    snapshot = FoundationConfigSnapshot()

    assert "app" in snapshot.safe_context()
