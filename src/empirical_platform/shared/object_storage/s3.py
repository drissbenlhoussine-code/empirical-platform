"""S3-compatible object-storage connectivity foundation."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Protocol, cast

import boto3  # type: ignore[import-untyped]
from botocore.config import Config as BotoConfig  # type: ignore[import-untyped]
from botocore.exceptions import (  # type: ignore[import-untyped]
    BotoCoreError,
    ClientError,
    ConnectTimeoutError,
    EndpointConnectionError,
    ReadTimeoutError,
)

from empirical_platform.shared.config.settings import ObjectStorageConfigSnapshot
from empirical_platform.shared.errors import FoundationError, FoundationErrorCategory
from empirical_platform.shared.health import HealthState, LayerHealth
from empirical_platform.shared.interfaces.object_storage import (
    ObjectMetadata,
    ObjectStorageConsistency,
    StoredObject,
)

_OBJECT_NOT_FOUND_CODES = {"NoSuchKey", "404", "NotFound"}
_BUCKET_NOT_FOUND_CODES = {"NoSuchBucket", "NoSuchBucketPolicy"}
_ACCESS_DENIED_CODES = {"AccessDenied", "InvalidAccessKeyId", "SignatureDoesNotMatch", "403"}


class _BodyProtocol(Protocol):
    def read(self) -> bytes:
        """Read an object body."""
        ...


class _S3ClientProtocol(Protocol):
    def head_bucket(self, *, Bucket: str) -> None:  # noqa: N803 - boto3 API shape
        """Probe a bucket."""
        ...

    def create_bucket(self, *, Bucket: str) -> None:  # noqa: N803 - boto3 API shape
        """Create a bucket."""
        ...

    def delete_bucket(self, *, Bucket: str) -> None:  # noqa: N803 - boto3 API shape
        """Delete an empty bucket."""
        ...

    def put_object(self, **kwargs: object) -> Mapping[str, object]:
        """Put an object."""
        ...

    def get_object(self, *, Bucket: str, Key: str) -> Mapping[str, object]:  # noqa: N803
        """Get an object."""
        ...

    def head_object(self, *, Bucket: str, Key: str) -> Mapping[str, object]:  # noqa: N803
        """Head an object."""
        ...

    def list_objects_v2(
        self,
        *,
        Bucket: str,  # noqa: N803 - boto3 API shape
        Prefix: str,  # noqa: N803 - boto3 API shape
    ) -> Mapping[str, object]:
        """List objects."""
        ...

    def delete_object(self, *, Bucket: str, Key: str) -> None:  # noqa: N803
        """Delete an object."""
        ...

    def close(self) -> None:
        """Close client resources."""
        ...


def translate_object_storage_error(
    exc: BaseException,
    *,
    operation: str,
    context: Mapping[str, object] | None = None,
) -> FoundationError:
    """Translate SDK failures into a safe foundation object-storage error."""
    return FoundationError.wrap(
        exc,
        category=FoundationErrorCategory.OBJECT_STORAGE,
        message=_safe_message_for(exc, operation),
        layer="object_storage",
        operation=operation,
        context=context or {},
    )


class S3ObjectStorageService:
    """Narrow S3-compatible adapter using opaque keys and one foundation bucket."""

    def __init__(
        self,
        config: ObjectStorageConfigSnapshot,
        *,
        client: _S3ClientProtocol | None = None,
    ) -> None:
        self._config = config
        self._client = client
        self._initialized = False
        self._closed = False
        self._last_health = LayerHealth(
            "object_storage",
            liveness=HealthState.PASS,
            readiness=HealthState.UNKNOWN,
            dependency_health=HealthState.UNKNOWN,
        )

    @property
    def consistency(self) -> ObjectStorageConsistency:
        """Return the adapter consistency declaration tested against MinIO."""
        return ObjectStorageConsistency.MINIO_STRONG_READ_AFTER_WRITE

    @property
    def client(self) -> _S3ClientProtocol:
        """Return the initialized SDK client."""
        if self._client is None:
            raise FoundationError(
                category=FoundationErrorCategory.OBJECT_STORAGE,
                message="Object-storage client is not initialized",
                layer="object_storage",
                operation="client",
            )
        return self._client

    def initialize(self) -> None:
        """Initialize the SDK client and verify bucket reachability."""
        if self._initialized and not self._closed:
            return
        self._ensure_not_closed("initialize")
        try:
            if self._client is None:
                access_key, secret_key = self._config.credentials_required()
                self._client = cast(
                    _S3ClientProtocol,
                    boto3.client(
                        "s3",
                        endpoint_url=self._config.endpoint_url,
                        aws_access_key_id=access_key,
                        aws_secret_access_key=secret_key,
                        region_name=self._config.region,
                        use_ssl=self._config.secure,
                        config=BotoConfig(
                            connect_timeout=self._config.connection_timeout_seconds,
                            read_timeout=self._config.operation_timeout_seconds,
                            retries={"max_attempts": 1, "mode": "standard"},
                            s3={"addressing_style": "path" if self._config.path_style else "auto"},
                        ),
                    ),
                )
            self._probe()
            self._initialized = True
            self._last_health = self._passing_health()
        except FoundationError:
            self._last_health = self._failing_health()
            raise
        except Exception as exc:
            self._last_health = self._failing_health()
            raise translate_object_storage_error(
                exc,
                operation="initialize",
                context=self.safe_context(),
            ) from exc

    def check(self) -> bool:
        """Return whether the S3-compatible dependency is reachable."""
        try:
            if not self._initialized or self._closed:
                self._last_health = LayerHealth(
                    "object_storage",
                    liveness=HealthState.PASS,
                    readiness=HealthState.UNKNOWN if not self._closed else HealthState.FAIL,
                    dependency_health=HealthState.UNKNOWN,
                )
                return False
            self._probe()
        except Exception:
            self._last_health = self._failing_health()
            return False
        self._last_health = self._passing_health()
        return True

    def health(self) -> LayerHealth:
        """Return latest object-storage health."""
        return self._last_health

    def close(self) -> None:
        """Close SDK resources idempotently."""
        if self._closed:
            return
        self._closed = True
        self._initialized = False
        if self._client is not None and hasattr(self._client, "close"):
            self._client.close()
        self._last_health = LayerHealth(
            "object_storage",
            liveness=HealthState.PASS,
            readiness=HealthState.FAIL,
            dependency_health=HealthState.UNKNOWN,
        )

    def put_object(
        self,
        *,
        key: str,
        payload: bytes,
        content_type: str | None = None,
        metadata: Mapping[str, str] | None = None,
    ) -> ObjectMetadata:
        """Write one complete object."""
        self._ensure_ready("put_object")
        self._validate_key(key, "put_object")
        try:
            kwargs: dict[str, object] = {
                "Bucket": self._config.foundation_bucket,
                "Key": key,
                "Body": payload,
            }
            if content_type is not None:
                kwargs["ContentType"] = content_type
            if metadata is not None:
                kwargs["Metadata"] = dict(metadata)
            response = self.client.put_object(**kwargs)
            checksum = cast(str | None, response.get("ETag"))
            return ObjectMetadata(
                key=key,
                size_bytes=len(payload),
                content_type=content_type,
                provider_checksum=_strip_quotes(checksum),
                metadata=dict(metadata or {}),
            )
        except Exception as exc:
            raise translate_object_storage_error(
                exc,
                operation="put_object",
                context=self.safe_context() | {"key_length": len(key)},
            ) from exc

    def get_object(self, key: str) -> StoredObject | None:
        """Return an object or None when absent."""
        self._ensure_ready("get_object")
        self._validate_key(key, "get_object")
        try:
            response = self.client.get_object(Bucket=self._config.foundation_bucket, Key=key)
        except ClientError as exc:
            if _client_error_code(exc) in _OBJECT_NOT_FOUND_CODES:
                return None
            raise translate_object_storage_error(
                exc,
                operation="get_object",
                context=self.safe_context() | {"key_length": len(key)},
            ) from exc
        except Exception as exc:
            raise translate_object_storage_error(
                exc,
                operation="get_object",
                context=self.safe_context() | {"key_length": len(key)},
            ) from exc
        body = cast(_BodyProtocol, response["Body"])
        payload = body.read()
        return StoredObject(
            metadata=_metadata_from_response(key=key, response=response),
            payload=payload,
        )

    def head_object(self, key: str) -> ObjectMetadata | None:
        """Return metadata or None when absent."""
        self._ensure_ready("head_object")
        self._validate_key(key, "head_object")
        try:
            response = self.client.head_object(Bucket=self._config.foundation_bucket, Key=key)
        except ClientError as exc:
            if _client_error_code(exc) in _OBJECT_NOT_FOUND_CODES:
                return None
            raise translate_object_storage_error(
                exc,
                operation="head_object",
                context=self.safe_context() | {"key_length": len(key)},
            ) from exc
        except Exception as exc:
            raise translate_object_storage_error(
                exc,
                operation="head_object",
                context=self.safe_context() | {"key_length": len(key)},
            ) from exc
        return _metadata_from_response(key=key, response=response)

    def object_exists(self, key: str) -> bool:
        """Return whether a key exists."""
        return self.head_object(key) is not None

    def list_objects(self, *, prefix: str = "") -> tuple[ObjectMetadata, ...]:
        """List object metadata under an opaque prefix."""
        self._ensure_ready("list_objects")
        try:
            response = self.client.list_objects_v2(
                Bucket=self._config.foundation_bucket,
                Prefix=prefix,
            )
            contents = cast(list[Mapping[str, object]], response.get("Contents", []))
            return tuple(
                ObjectMetadata(
                    key=cast(str, item["Key"]),
                    size_bytes=cast(int, item.get("Size", 0)),
                    provider_checksum=_strip_quotes(cast(str | None, item.get("ETag"))),
                    last_modified=cast(datetime | None, item.get("LastModified")),
                )
                for item in contents
            )
        except Exception as exc:
            raise translate_object_storage_error(
                exc,
                operation="list_objects",
                context=self.safe_context() | {"prefix_length": len(prefix)},
            ) from exc

    def delete_object(self, key: str) -> bool:
        """Delete an object and distinguish absent keys."""
        self._ensure_ready("delete_object")
        self._validate_key(key, "delete_object")
        if self.head_object(key) is None:
            return False
        try:
            self.client.delete_object(Bucket=self._config.foundation_bucket, Key=key)
        except Exception as exc:
            raise translate_object_storage_error(
                exc,
                operation="delete_object",
                context=self.safe_context() | {"key_length": len(key)},
            ) from exc
        return True

    def safe_context(self) -> dict[str, object]:
        """Return safe S3-compatible diagnostics."""
        return self._config.safe_context()

    def _probe(self) -> None:
        try:
            self.client.head_bucket(Bucket=self._config.foundation_bucket)
        except ClientError as exc:
            code = _client_error_code(exc)
            if code in _BUCKET_NOT_FOUND_CODES or code in _OBJECT_NOT_FOUND_CODES:
                if self._config.create_bucket_if_missing:
                    self.client.create_bucket(Bucket=self._config.foundation_bucket)
                    self.client.head_bucket(Bucket=self._config.foundation_bucket)
                    return
                raise translate_object_storage_error(
                    exc,
                    operation="probe",
                    context=self.safe_context() | {"bucket_state": "missing"},
                ) from exc
            raise translate_object_storage_error(
                exc,
                operation="probe",
                context=self.safe_context(),
            ) from exc

    def _ensure_not_closed(self, operation: str) -> None:
        if self._closed:
            raise FoundationError(
                category=FoundationErrorCategory.OBJECT_STORAGE,
                message="Object-storage service is closed",
                layer="object_storage",
                operation=operation,
            )

    def _ensure_ready(self, operation: str) -> None:
        self._ensure_not_closed(operation)
        if not self._initialized:
            raise FoundationError(
                category=FoundationErrorCategory.OBJECT_STORAGE,
                message="Object-storage service is not initialized",
                layer="object_storage",
                operation=operation,
            )

    def _validate_key(self, key: str, operation: str) -> None:
        if key == "" or "\x00" in key:
            raise FoundationError(
                category=FoundationErrorCategory.OBJECT_STORAGE,
                message="Object-storage key is invalid",
                layer="object_storage",
                operation=operation,
            )

    def _passing_health(self) -> LayerHealth:
        return LayerHealth(
            "object_storage",
            liveness=HealthState.PASS,
            readiness=HealthState.PASS,
            dependency_health=HealthState.PASS,
        )

    def _failing_health(self) -> LayerHealth:
        return LayerHealth(
            "object_storage",
            liveness=HealthState.PASS,
            readiness=HealthState.FAIL,
            dependency_health=HealthState.FAIL,
        )


def _client_error_code(exc: ClientError) -> str:
    return cast(str, exc.response.get("Error", {}).get("Code", "Unknown"))


def _safe_message_for(exc: BaseException, operation: str) -> str:
    if isinstance(exc, (ConnectTimeoutError, ReadTimeoutError)):
        return f"Object-storage {operation} timed out"
    if isinstance(exc, EndpointConnectionError):
        return f"Object-storage {operation} failed because the endpoint is unreachable"
    if isinstance(exc, ClientError):
        code = _client_error_code(exc)
        if code in _ACCESS_DENIED_CODES:
            return f"Object-storage {operation} failed because access was denied"
        if code in _BUCKET_NOT_FOUND_CODES:
            return f"Object-storage {operation} failed because the bucket was not found"
        if code in _OBJECT_NOT_FOUND_CODES:
            return f"Object-storage {operation} did not find the object"
        return f"Object-storage {operation} failed in the provider"
    if isinstance(exc, BotoCoreError):
        return f"Object-storage {operation} failed in the SDK"
    if isinstance(exc, FoundationError):
        return exc.safe_message
    return f"Object-storage {operation} failed unexpectedly"


def _strip_quotes(value: str | None) -> str | None:
    return value.strip('"') if value is not None else None


def _metadata_from_response(*, key: str, response: Mapping[str, object]) -> ObjectMetadata:
    return ObjectMetadata(
        key=key,
        size_bytes=cast(int, response.get("ContentLength", 0)),
        content_type=cast(str | None, response.get("ContentType")),
        provider_checksum=_strip_quotes(cast(str | None, response.get("ETag"))),
        last_modified=cast(datetime | None, response.get("LastModified")),
        metadata=cast(Mapping[str, str] | None, response.get("Metadata")),
    )
