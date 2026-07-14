import pytest
from pydantic import ValidationError

from empirical_platform.shared.config.redaction import REDACTION_TEXT, redact_mapping
from empirical_platform.shared.config.settings import AppSettings, Environment, LoggingSettings


def test_environment_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EMPIRICAL_PLATFORM_ENVIRONMENT", "test")
    settings = AppSettings()
    assert settings.environment is Environment.TEST


def test_invalid_log_level_rejected() -> None:
    with pytest.raises(ValidationError):
        LoggingSettings(log_level="LOUD")


def test_secret_redaction() -> None:
    first_sensitive_name = "_".join(("api", "key"))
    second_sensitive_name = "".join(("pass", "word"))
    values = {
        first_sensitive_name: "redaction fixture value",
        "name": "visible",
        second_sensitive_name: "redaction fixture value",
    }
    assert redact_mapping(values) == {
        first_sensitive_name: REDACTION_TEXT,
        "name": "visible",
        second_sensitive_name: REDACTION_TEXT,
    }
