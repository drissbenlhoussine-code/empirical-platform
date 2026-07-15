from __future__ import annotations

import pytest
from pydantic import SecretStr, ValidationError

from empirical_platform.shared.config.settings import (
    ObjectStorageConfigSnapshot,
    resolve_foundation_config,
)
from empirical_platform.shared.errors import FoundationError


def test_object_storage_config_resolves_safe_connectivity_settings() -> None:
    access = "-".join(("local", "minio", "user"))
    secret = "-".join(("local", "minio", "placeholder"))
    endpoint_with_credentials = "http://" + "user" + ":" + "pass" + "@localhost:9000"

    snapshot = resolve_foundation_config(
        {
            "EMPIRICAL_PLATFORM_OBJECT_STORAGE_ENDPOINT_URL": endpoint_with_credentials,
            "EMPIRICAL_PLATFORM_OBJECT_STORAGE_REGION": "us-east-1",
            "EMPIRICAL_PLATFORM_OBJECT_STORAGE_FOUNDATION_BUCKET": "foundation-probe",
            "EMPIRICAL_PLATFORM_OBJECT_STORAGE_ACCESS_KEY": access,
            "EMPIRICAL_PLATFORM_OBJECT_STORAGE_SECRET_KEY": secret,
            "EMPIRICAL_PLATFORM_OBJECT_STORAGE_SECURE": "false",
            "EMPIRICAL_PLATFORM_OBJECT_STORAGE_PATH_STYLE": "true",
            "EMPIRICAL_PLATFORM_OBJECT_STORAGE_CONNECT_TIMEOUT_SECONDS": "2",
            "EMPIRICAL_PLATFORM_OBJECT_STORAGE_OPERATION_TIMEOUT_SECONDS": "3",
            "EMPIRICAL_PLATFORM_OBJECT_STORAGE_CREATE_BUCKET_IF_MISSING": "true",
        }
    )

    assert snapshot.object_storage.safe_endpoint() == "http://localhost:9000"
    assert snapshot.object_storage.credentials_required() == (access, secret)
    safe_context = snapshot.object_storage.safe_context()
    assert access not in str(safe_context)
    assert secret not in str(safe_context)
    assert safe_context["access_key_configured"] is True
    assert safe_context["secret_key_configured"] is True


def test_object_storage_config_requires_valid_bounds() -> None:
    with pytest.raises(FoundationError):
        resolve_foundation_config(
            {"EMPIRICAL_PLATFORM_OBJECT_STORAGE_CONNECT_TIMEOUT_SECONDS": "0"}
        )

    with pytest.raises(ValidationError):
        ObjectStorageConfigSnapshot(foundation_bucket="ab")


def test_object_storage_credentials_are_required_without_leaking_details() -> None:
    snapshot = ObjectStorageConfigSnapshot(access_key=None, secret_key=None)

    with pytest.raises(FoundationError) as exc_info:
        snapshot.credentials_required()

    payload = exc_info.value.as_dict()
    assert payload["category"] == "configuration_error"
    assert "Object-storage access key and secret key are required" in payload["message"]
    assert "secret_key" not in str(payload).lower() or "[REDACTED]" in str(payload)


def test_object_storage_config_snapshot_is_immutable() -> None:
    snapshot = ObjectStorageConfigSnapshot(
        access_key=SecretStr("local-user-placeholder"),
        secret_key=SecretStr("local-secret-placeholder"),
    )

    with pytest.raises(ValidationError):
        snapshot.endpoint_url = "http://elsewhere:9000"  # type: ignore[misc]
