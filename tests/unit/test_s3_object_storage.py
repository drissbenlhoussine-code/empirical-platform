from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from botocore.exceptions import ClientError, EndpointConnectionError
from pydantic import SecretStr

from empirical_platform.shared.config.settings import ObjectStorageConfigSnapshot
from empirical_platform.shared.errors import FoundationError
from empirical_platform.shared.health import HealthState, ProcessHealth
from empirical_platform.shared.interfaces.object_storage import ObjectStorageConsistency
from empirical_platform.shared.object_storage.s3 import (
    S3ObjectStorageService,
    translate_object_storage_error,
)


class Body:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def read(self) -> bytes:
        return self.payload


class FakeS3Client:
    def __init__(self, *, fail_head_bucket: bool = False) -> None:
        self.fail_head_bucket = fail_head_bucket
        self.objects: dict[str, tuple[bytes, dict[str, str], str | None]] = {}
        self.closed = False
        self.bucket_created = False

    def head_bucket(self, Bucket: str) -> None:  # noqa: N803 - boto3 API shape
        if self.fail_head_bucket and not self.bucket_created:
            raise _client_error("NoSuchBucket")

    def create_bucket(self, Bucket: str) -> None:  # noqa: N803 - boto3 API shape
        self.bucket_created = True

    def put_object(self, **kwargs: object) -> dict[str, str]:
        key = str(kwargs["Key"])
        self.objects[key] = (
            bytes(kwargs["Body"]),
            dict(kwargs.get("Metadata", {})),
            kwargs.get("ContentType") if isinstance(kwargs.get("ContentType"), str) else None,
        )
        return {"ETag": '"fake-etag"'}

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, object]:  # noqa: N803
        if Key not in self.objects:
            raise _client_error("NoSuchKey")
        payload, metadata, content_type = self.objects[Key]
        return {
            "Body": Body(payload),
            "ContentLength": len(payload),
            "ContentType": content_type,
            "ETag": '"fake-etag"',
            "LastModified": datetime(2026, 1, 1, tzinfo=UTC),
            "Metadata": metadata,
        }

    def head_object(self, *, Bucket: str, Key: str) -> dict[str, object]:  # noqa: N803
        if Key not in self.objects:
            raise _client_error("NoSuchKey")
        payload, metadata, content_type = self.objects[Key]
        return {
            "ContentLength": len(payload),
            "ContentType": content_type,
            "ETag": '"fake-etag"',
            "LastModified": datetime(2026, 1, 1, tzinfo=UTC),
            "Metadata": metadata,
        }

    def list_objects_v2(self, *, Bucket: str, Prefix: str) -> dict[str, object]:  # noqa: N803
        return {
            "Contents": [
                {"Key": key, "Size": len(payload), "ETag": '"fake-etag"'}
                for key, (payload, _metadata, _content_type) in sorted(self.objects.items())
                if key.startswith(Prefix)
            ]
        }

    def delete_object(self, *, Bucket: str, Key: str) -> None:  # noqa: N803
        self.objects.pop(Key, None)

    def close(self) -> None:
        self.closed = True


def _client_error(code: str) -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": "provider detail"}}, "operation")


def _config(*, create_bucket: bool = False) -> ObjectStorageConfigSnapshot:
    endpoint_with_credentials = "http://" + "user" + ":" + "pass" + "@localhost:9000"
    return ObjectStorageConfigSnapshot(
        endpoint_url=endpoint_with_credentials,
        foundation_bucket="foundation-unit-test",
        access_key=SecretStr("local-user-placeholder"),
        secret_key=SecretStr("local-secret-placeholder"),
        create_bucket_if_missing=create_bucket,
    )


def test_s3_service_lifecycle_and_generic_operations() -> None:
    client = FakeS3Client()
    service = S3ObjectStorageService(_config(), client=client)

    assert service.consistency is ObjectStorageConsistency.MINIO_STRONG_READ_AFTER_WRITE
    with pytest.raises(FoundationError):
        service.get_object("before-init")

    service.initialize()
    assert service.check()
    assert service.health().dependency_health is HealthState.PASS

    written = service.put_object(
        key="opaque/key",
        payload=b"payload",
        content_type="application/octet-stream",
        metadata={"shape": "generic"},
    )
    assert written.provider_checksum == "fake-etag"

    stored = service.get_object("opaque/key")
    assert stored is not None
    assert stored.payload == b"payload"
    assert stored.metadata.metadata == {"shape": "generic"}
    assert service.object_exists("opaque/key")
    assert service.head_object("missing") is None
    assert service.get_object("missing") is None
    assert [item.key for item in service.list_objects(prefix="opaque/")] == ["opaque/key"]
    assert service.delete_object("opaque/key")
    assert not service.delete_object("opaque/key")

    service.close()
    service.close()
    assert client.closed
    with pytest.raises(FoundationError):
        service.list_objects()


def test_s3_service_can_create_infrastructure_only_bucket_when_explicitly_configured() -> None:
    client = FakeS3Client(fail_head_bucket=True)
    service = S3ObjectStorageService(_config(create_bucket=True), client=client)

    service.initialize()

    assert client.bucket_created


def test_s3_service_missing_bucket_blocks_when_creation_not_enabled() -> None:
    service = S3ObjectStorageService(_config(), client=FakeS3Client(fail_head_bucket=True))

    with pytest.raises(FoundationError) as exc_info:
        service.initialize()

    payload = exc_info.value.as_dict()
    assert payload["category"] == "object_storage_error"
    assert payload["context"]["bucket_state"] == "missing"


def test_s3_translation_is_secret_safe_and_does_not_leak_sdk_type() -> None:
    endpoint_with_credentials = "http://" + "user" + ":" + "pass" + "@localhost:9000"
    error = translate_object_storage_error(
        EndpointConnectionError(endpoint_url=endpoint_with_credentials),
        operation="probe",
        context=_config().safe_context(),
    )

    payload = error.as_dict()
    assert payload["category"] == "object_storage_error"
    assert payload["layer"] == "object_storage"
    assert "EndpointConnectionError" not in str(payload)
    assert "user:pass" not in str(payload)


def test_failed_object_operation_does_not_force_liveness_failure() -> None:
    service = S3ObjectStorageService(_config(), client=FakeS3Client())
    service.initialize()

    with pytest.raises(FoundationError):
        service.put_object(key="", payload=b"value")

    assert service.health().liveness is HealthState.PASS
    assert ProcessHealth.PASS.value == "PASS"


def test_raw_client_error_is_translated_without_exposing_provider_message() -> None:
    service = S3ObjectStorageService(_config(), client=FakeS3Client())
    service.initialize()

    class BrokenClient(FakeS3Client):
        def list_objects_v2(self, *, Bucket: str, Prefix: str) -> dict[str, Any]:  # noqa: N803
            raise _client_error("AccessDenied")

    broken = S3ObjectStorageService(_config(), client=BrokenClient())
    broken.initialize()
    with pytest.raises(FoundationError) as exc_info:
        broken.list_objects(prefix="anything")

    payload = exc_info.value.as_dict()
    assert "provider detail" not in str(payload)
    assert "access was denied" in payload["message"]
