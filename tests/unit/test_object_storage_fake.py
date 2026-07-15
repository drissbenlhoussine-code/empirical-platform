from __future__ import annotations

import pytest

from empirical_platform.shared.errors import FoundationError
from empirical_platform.shared.health import HealthState
from empirical_platform.shared.interfaces.object_storage import ObjectStorageConsistency
from empirical_platform.shared.object_storage.fake import FakeObjectStorageService


def test_fake_object_storage_lifecycle_and_operations() -> None:
    service = FakeObjectStorageService()

    assert service.health().readiness is HealthState.UNKNOWN
    with pytest.raises(FoundationError):
        service.put_object(key="alpha", payload=b"before-init")

    service.initialize()
    assert service.consistency is ObjectStorageConsistency.FAKE_STRONG_READ_AFTER_WRITE
    assert service.check()

    metadata = service.put_object(
        key="prefix/alpha",
        payload=b"hello",
        content_type="text/plain",
        metadata={"purpose": "unit-test"},
    )
    assert metadata.size_bytes == 5
    assert service.object_exists("prefix/alpha")

    stored = service.get_object("prefix/alpha")
    assert stored is not None
    assert stored.payload == b"hello"
    assert stored.metadata.metadata == {"purpose": "unit-test"}
    assert service.head_object("missing") is None
    assert service.get_object("missing") is None

    assert [item.key for item in service.list_objects(prefix="prefix/")] == ["prefix/alpha"]
    assert service.delete_object("prefix/alpha") is True
    assert service.delete_object("prefix/alpha") is False

    service.close()
    service.close()
    with pytest.raises(FoundationError):
        service.get_object("prefix/alpha")


def test_fake_object_storage_overwrite_and_empty_payload() -> None:
    service = FakeObjectStorageService()
    service.initialize()

    first = service.put_object(key="opaque-key", payload=b"first")
    second = service.put_object(key="opaque-key", payload=b"")

    assert first.provider_checksum != second.provider_checksum
    stored = service.get_object("opaque-key")
    assert stored is not None
    assert stored.payload == b""
    assert stored.metadata.size_bytes == 0


def test_fake_object_storage_failure_injection_and_unreachable_health() -> None:
    service = FakeObjectStorageService(reachable=False)

    with pytest.raises(FoundationError):
        service.initialize()
    assert service.health().dependency_health is HealthState.FAIL

    failing = FakeObjectStorageService(fail_operations={"put_object"})
    failing.initialize()
    with pytest.raises(FoundationError) as exc_info:
        failing.put_object(key="key", payload=b"value")
    assert exc_info.value.as_dict()["category"] == "object_storage_error"


def test_fake_object_storage_rejects_invalid_key() -> None:
    service = FakeObjectStorageService()
    service.initialize()

    with pytest.raises(FoundationError):
        service.put_object(key="", payload=b"value")
    with pytest.raises(FoundationError):
        service.get_object("bad\x00key")
