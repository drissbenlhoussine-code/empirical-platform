from __future__ import annotations

import pytest

from empirical_platform.shared.bootstrap import initialize_foundation_runtime_with_object_storage
from empirical_platform.shared.errors import FoundationError
from empirical_platform.shared.health import ProcessHealth
from empirical_platform.shared.object_storage.fake import FakeObjectStorageService


def test_bootstrap_with_object_storage_initializes_ready_runtime() -> None:
    object_storage = FakeObjectStorageService()

    runtime = initialize_foundation_runtime_with_object_storage(
        {"EMPIRICAL_PLATFORM_ENVIRONMENT": "test"},
        object_storage=object_storage,
    )

    assert runtime.object_storage is object_storage
    assert runtime.persistence is None
    assert runtime.health.status is ProcessHealth.PASS


def test_bootstrap_with_unreachable_object_storage_fails_before_ready_runtime() -> None:
    with pytest.raises(FoundationError):
        initialize_foundation_runtime_with_object_storage(
            {"EMPIRICAL_PLATFORM_ENVIRONMENT": "test"},
            object_storage=FakeObjectStorageService(reachable=False),
        )


def test_bootstrap_with_unreachable_object_storage_closes_service_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression test: `object_storage_service.close()` must be attempted
    even when `object_storage_service.initialize()` itself raises, mirroring
    the M050-Y-1 resource-lifecycle correction applied to the entrypoint
    composition roots."""
    object_storage = FakeObjectStorageService(reachable=False)
    close_calls: list[None] = []
    original_close = object_storage.close

    def _tracking_close() -> None:
        close_calls.append(None)
        original_close()

    monkeypatch.setattr(object_storage, "close", _tracking_close)

    with pytest.raises(FoundationError):
        initialize_foundation_runtime_with_object_storage(
            {"EMPIRICAL_PLATFORM_ENVIRONMENT": "test"},
            object_storage=object_storage,
        )

    assert close_calls == [None]
