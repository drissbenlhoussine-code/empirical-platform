from __future__ import annotations

import os
import uuid

import pytest
from pydantic import SecretStr

from empirical_platform.shared.config.settings import ObjectStorageConfigSnapshot
from empirical_platform.shared.errors import FoundationError
from empirical_platform.shared.health import HealthState
from empirical_platform.shared.object_storage.s3 import S3ObjectStorageService

pytestmark = pytest.mark.integration


def _integration_enabled() -> bool:
    return os.environ.get("EMPIRICAL_PLATFORM_RUN_OBJECT_STORAGE_TESTS") == "1"


def _config(
    *, bucket: str, access_key: str | None = None, secret_key: str | None = None
) -> ObjectStorageConfigSnapshot:
    return ObjectStorageConfigSnapshot(
        endpoint_url=os.environ.get(
            "EMPIRICAL_PLATFORM_OBJECT_STORAGE_ENDPOINT_URL", "http://localhost:9000"
        ),
        region=os.environ.get("EMPIRICAL_PLATFORM_OBJECT_STORAGE_REGION", "us-east-1"),
        foundation_bucket=bucket,
        access_key=SecretStr(
            access_key or os.environ["EMPIRICAL_PLATFORM_OBJECT_STORAGE_ACCESS_KEY"]
        ),
        secret_key=SecretStr(
            secret_key or os.environ["EMPIRICAL_PLATFORM_OBJECT_STORAGE_SECRET_KEY"]
        ),
        secure=False,
        path_style=True,
        connection_timeout_seconds=5,
        operation_timeout_seconds=5,
        create_bucket_if_missing=True,
    )


@pytest.fixture
def object_storage_service() -> S3ObjectStorageService:
    if not _integration_enabled():
        pytest.skip("Object-storage integration tests require explicit opt-in")
    bucket = f"foundation-m009-{uuid.uuid4().hex}"
    service = S3ObjectStorageService(_config(bucket=bucket))
    service.initialize()
    try:
        yield service
    finally:
        try:
            for item in service.list_objects(prefix=""):
                service.delete_object(item.key)
            service.client.delete_bucket(Bucket=bucket)
        finally:
            service.close()


def test_minio_connectivity_probe_and_health(
    object_storage_service: S3ObjectStorageService,
) -> None:
    assert object_storage_service.check()
    assert object_storage_service.health().dependency_health is HealthState.PASS


def test_minio_generic_object_operations(object_storage_service: S3ObjectStorageService) -> None:
    key = f"generic-{uuid.uuid4().hex}"
    payload = b"exact bytes"

    metadata = object_storage_service.put_object(
        key=key,
        payload=payload,
        content_type="application/octet-stream",
        metadata={"kind": "generic"},
    )

    assert metadata.size_bytes == len(payload)
    stored = object_storage_service.get_object(key)
    assert stored is not None
    assert stored.payload == payload
    assert stored.metadata.metadata == {"kind": "generic"}
    assert object_storage_service.head_object(key) is not None
    assert object_storage_service.object_exists(key)
    assert key in {item.key for item in object_storage_service.list_objects(prefix="generic-")}

    object_storage_service.put_object(key=key, payload=b"overwrite")
    overwritten = object_storage_service.get_object(key)
    assert overwritten is not None
    assert overwritten.payload == b"overwrite"

    assert object_storage_service.delete_object(key) is True
    assert object_storage_service.get_object(key) is None
    assert object_storage_service.head_object(key) is None
    assert object_storage_service.delete_object(key) is False


def test_minio_invalid_credentials_are_translated_safely() -> None:
    if not _integration_enabled():
        pytest.skip("Object-storage integration tests require explicit opt-in")
    bucket = f"foundation-m009-{uuid.uuid4().hex}"
    service = S3ObjectStorageService(
        _config(
            bucket=bucket,
            access_key="-".join(("invalid", "local", "user")),
            secret_key="-".join(("invalid", "local", "secret")),
        )
    )

    with pytest.raises(FoundationError) as exc_info:
        service.initialize()

    payload = exc_info.value.as_dict()
    assert payload["category"] == "object_storage_error"
    assert "invalid-local-secret" not in str(payload)
    assert "SignatureDoesNotMatch" not in str(payload)


def test_minio_shutdown_is_idempotent() -> None:
    if not _integration_enabled():
        pytest.skip("Object-storage integration tests require explicit opt-in")
    bucket = f"foundation-m009-{uuid.uuid4().hex}"
    service = S3ObjectStorageService(_config(bucket=bucket))
    service.initialize()
    service.client.delete_bucket(Bucket=bucket)

    service.close()
    service.close()

    with pytest.raises(FoundationError):
        service.put_object(key="after-close", payload=b"nope")
