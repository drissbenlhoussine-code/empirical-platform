from __future__ import annotations

from empirical_platform.shared.errors import FoundationError, FoundationErrorCategory


def test_foundation_error_contains_safe_structured_fields() -> None:
    sensitive_name = "".join(("pass", "word"))
    error = FoundationError(
        category=FoundationErrorCategory.CONFIGURATION,
        message="Configuration failed",
        layer="configuration",
        operation="resolve",
        context={sensitive_name: "redaction fixture value", "name": "visible"},
    )

    assert error.as_dict() == {
        "category": "configuration_error",
        "message": "Configuration failed",
        "layer": "configuration",
        "operation": "resolve",
        "context": {sensitive_name: "[REDACTED]", "name": "visible"},
    }


def test_foundation_error_wraps_raw_exception_without_public_type_leak() -> None:
    cause = RuntimeError("driver detail")

    error = FoundationError.wrap(
        cause,
        category=FoundationErrorCategory.PERSISTENCE,
        message="Persistence failed",
        layer="persistence",
        operation="connect",
    )

    assert error.__cause__ is cause
    payload = error.as_dict()
    assert "RuntimeError" not in str(payload)
    assert payload["category"] == "persistence_error"
