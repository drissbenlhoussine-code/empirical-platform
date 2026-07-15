"""Deterministic in-memory object-storage substitute."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime

from empirical_platform.shared.errors import FoundationError, FoundationErrorCategory
from empirical_platform.shared.health import HealthState, LayerHealth
from empirical_platform.shared.interfaces.object_storage import (
    ObjectMetadata,
    ObjectStorageConsistency,
    StoredObject,
)


@dataclass(frozen=True, slots=True)
class _ObjectRecord:
    payload: bytes
    content_type: str | None
    metadata: Mapping[str, str] | None
    last_modified: datetime
    version: int


class FakeObjectStorageService:
    """In-memory object-storage fake with production-like lifecycle checks."""

    def __init__(
        self,
        *,
        reachable: bool = True,
        fail_operations: set[str] | None = None,
    ) -> None:
        self._reachable = reachable
        self._fail_operations = fail_operations or set()
        self._objects: dict[str, _ObjectRecord] = {}
        self._initialized = False
        self._closed = False
        self._clock_tick = 0
        self._last_health = LayerHealth(
            "object_storage",
            liveness=HealthState.PASS,
            readiness=HealthState.UNKNOWN,
            dependency_health=HealthState.UNKNOWN,
        )

    @property
    def consistency(self) -> ObjectStorageConsistency:
        """Return deterministic fake consistency semantics."""
        return ObjectStorageConsistency.FAKE_STRONG_READ_AFTER_WRITE

    def initialize(self) -> None:
        """Initialize the fake dependency."""
        self._ensure_not_closed("initialize")
        self._maybe_fail("initialize")
        if not self._reachable:
            self._last_health = LayerHealth(
                "object_storage",
                liveness=HealthState.PASS,
                readiness=HealthState.FAIL,
                dependency_health=HealthState.FAIL,
            )
            raise self._error("initialize", "Object-storage dependency is unreachable")
        self._initialized = True
        self._last_health = LayerHealth(
            "object_storage",
            liveness=HealthState.PASS,
            readiness=HealthState.PASS,
            dependency_health=HealthState.PASS,
        )

    def check(self) -> bool:
        """Return fake dependency reachability."""
        if not self._initialized or self._closed:
            self._last_health = LayerHealth(
                "object_storage",
                liveness=HealthState.PASS,
                readiness=HealthState.UNKNOWN if not self._closed else HealthState.FAIL,
                dependency_health=HealthState.UNKNOWN,
            )
            return False
        if not self._reachable:
            self._last_health = LayerHealth(
                "object_storage",
                liveness=HealthState.PASS,
                readiness=HealthState.FAIL,
                dependency_health=HealthState.FAIL,
            )
            return False
        self._last_health = LayerHealth(
            "object_storage",
            liveness=HealthState.PASS,
            readiness=HealthState.PASS,
            dependency_health=HealthState.PASS,
        )
        return True

    def health(self) -> LayerHealth:
        """Return latest fake object-storage health."""
        return self._last_health

    def close(self) -> None:
        """Close idempotently and reject future work."""
        if self._closed:
            return
        self._closed = True
        self._initialized = False
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
        """Store a complete object."""
        self._ensure_ready("put_object")
        self._maybe_fail("put_object")
        self._validate_key(key, "put_object")
        self._clock_tick += 1
        record = _ObjectRecord(
            payload=bytes(payload),
            content_type=content_type,
            metadata=dict(metadata or {}),
            last_modified=datetime(2026, 1, 1, tzinfo=UTC).replace(microsecond=self._clock_tick),
            version=self._clock_tick,
        )
        self._objects[key] = record
        return self._metadata_for(key, record)

    def get_object(self, key: str) -> StoredObject | None:
        """Return an object or None when absent."""
        self._ensure_ready("get_object")
        self._maybe_fail("get_object")
        self._validate_key(key, "get_object")
        record = self._objects.get(key)
        if record is None:
            return None
        return StoredObject(metadata=self._metadata_for(key, record), payload=record.payload)

    def head_object(self, key: str) -> ObjectMetadata | None:
        """Return metadata or None when absent."""
        self._ensure_ready("head_object")
        self._maybe_fail("head_object")
        self._validate_key(key, "head_object")
        record = self._objects.get(key)
        return None if record is None else self._metadata_for(key, record)

    def object_exists(self, key: str) -> bool:
        """Return whether a key exists."""
        return self.head_object(key) is not None

    def list_objects(self, *, prefix: str = "") -> tuple[ObjectMetadata, ...]:
        """List metadata for objects with a matching opaque prefix."""
        self._ensure_ready("list_objects")
        self._maybe_fail("list_objects")
        return tuple(
            self._metadata_for(key, record)
            for key, record in sorted(self._objects.items())
            if key.startswith(prefix)
        )

    def delete_object(self, key: str) -> bool:
        """Delete an object and distinguish not-found."""
        self._ensure_ready("delete_object")
        self._maybe_fail("delete_object")
        self._validate_key(key, "delete_object")
        return self._objects.pop(key, None) is not None

    def _metadata_for(self, key: str, record: _ObjectRecord) -> ObjectMetadata:
        return ObjectMetadata(
            key=key,
            size_bytes=len(record.payload),
            content_type=record.content_type,
            provider_checksum=f"fake-etag-{record.version}",
            last_modified=record.last_modified,
            metadata=dict(record.metadata or {}),
        )

    def _ensure_not_closed(self, operation: str) -> None:
        if self._closed:
            raise self._error(operation, "Object-storage service is closed")

    def _ensure_ready(self, operation: str) -> None:
        self._ensure_not_closed(operation)
        if not self._initialized:
            raise self._error(operation, "Object-storage service is not initialized")

    def _maybe_fail(self, operation: str) -> None:
        if operation in self._fail_operations:
            raise self._error(operation, f"Object-storage {operation} failed")

    def _validate_key(self, key: str, operation: str) -> None:
        if key == "" or "\x00" in key:
            raise self._error(operation, "Object-storage key is invalid")

    def _error(self, operation: str, message: str) -> FoundationError:
        return FoundationError(
            category=FoundationErrorCategory.OBJECT_STORAGE,
            message=message,
            layer="object_storage",
            operation=operation,
        )
