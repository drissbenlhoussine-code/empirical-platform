"""Generic object-storage interfaces without domain key semantics."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from empirical_platform.shared.health import LayerHealth


class ObjectStorageConsistency(StrEnum):
    """Declared object-storage visibility semantics."""

    MINIO_STRONG_READ_AFTER_WRITE = "minio_strong_read_after_write"
    FAKE_STRONG_READ_AFTER_WRITE = "fake_strong_read_after_write"


@dataclass(frozen=True, slots=True)
class ObjectMetadata:
    """Provider metadata for one opaque object key."""

    key: str
    size_bytes: int
    content_type: str | None = None
    provider_checksum: str | None = None
    last_modified: datetime | None = None
    metadata: Mapping[str, str] | None = None


@dataclass(frozen=True, slots=True)
class StoredObject:
    """Bounded in-memory object payload returned by the foundation adapter."""

    metadata: ObjectMetadata
    payload: bytes


class ObjectStorageService(Protocol):
    """Generic object-storage operations over opaque string keys."""

    @property
    def consistency(self) -> ObjectStorageConsistency:
        """Return the implementation's declared consistency semantics."""
        ...

    def initialize(self) -> None:
        """Initialize the client and verify dependency reachability."""
        ...

    def check(self) -> bool:
        """Return whether the object-storage dependency is reachable."""
        ...

    def health(self) -> LayerHealth:
        """Return the latest health signal."""
        ...

    def close(self) -> None:
        """Close client resources idempotently."""
        ...

    def put_object(
        self,
        *,
        key: str,
        payload: bytes,
        content_type: str | None = None,
        metadata: Mapping[str, str] | None = None,
    ) -> ObjectMetadata:
        """Write a complete object or fail without reporting success."""
        ...

    def get_object(self, key: str) -> StoredObject | None:
        """Return an object or None when the key is not found."""
        ...

    def head_object(self, key: str) -> ObjectMetadata | None:
        """Return object metadata or None when the key is not found."""
        ...

    def object_exists(self, key: str) -> bool:
        """Return whether a key exists."""
        ...

    def list_objects(self, *, prefix: str = "") -> tuple[ObjectMetadata, ...]:
        """List object metadata by opaque prefix."""
        ...

    def delete_object(self, key: str) -> bool:
        """Delete an object and return False when the key was not found."""
        ...
