from __future__ import annotations

from collections.abc import Mapping

import pytest

from empirical_platform.shared.bootstrap import (
    RuntimeLifecycleState,
    initialize_infrastructure_runtime,
)
from empirical_platform.shared.errors import FoundationError, FoundationErrorCategory
from empirical_platform.shared.health import HealthReport, LayerHealth, ProcessHealth
from empirical_platform.shared.object_storage.fake import FakeObjectStorageService
from empirical_platform.shared.persistence.fake import FakePersistenceService


class RecordingPersistence(FakePersistenceService):
    def __init__(
        self,
        *,
        events: list[str],
        reachable: bool = True,
        check_result: bool = True,
        close_fails: bool = False,
    ) -> None:
        super().__init__(reachable=reachable)
        self.events = events
        self.check_result = check_result
        self.close_fails = close_fails

    def initialize(self) -> None:
        self.events.append("persistence.initialize")
        super().initialize()

    def check(self) -> bool:
        self.events.append("persistence.check")
        return super().check() and self.check_result

    def close(self) -> None:
        self.events.append("persistence.close")
        super().close()
        if self.close_fails:
            raise FoundationError(
                category=FoundationErrorCategory.PERSISTENCE,
                message="Persistence close failed",
                layer="persistence",
                operation="close",
            )


class RecordingObjectStorage(FakeObjectStorageService):
    def __init__(
        self,
        *,
        events: list[str],
        reachable: bool = True,
        fail_operations: set[str] | None = None,
        check_result: bool = True,
        close_fails: bool = False,
    ) -> None:
        super().__init__(reachable=reachable, fail_operations=fail_operations)
        self.events = events
        self.check_result = check_result
        self.close_fails = close_fails

    def initialize(self) -> None:
        self.events.append("object_storage.initialize")
        super().initialize()

    def check(self) -> bool:
        self.events.append("object_storage.check")
        return super().check() and self.check_result

    def close(self) -> None:
        self.events.append("object_storage.close")
        super().close()
        if self.close_fails:
            raise FoundationError(
                category=FoundationErrorCategory.OBJECT_STORAGE,
                message="Object-storage close failed",
                layer="object_storage",
                operation="close",
            )


def _env() -> Mapping[str, str]:
    storage_access_key = "-".join(("local", "minio", "access"))
    storage_private_key = "-".join(("local", "minio", "value"))
    pg_credential_name = "_".join(("EMPIRICAL_PLATFORM_POSTGRES", "PASSWORD"))
    object_storage_access_name = "_".join(("EMPIRICAL_PLATFORM_OBJECT_STORAGE", "ACCESS_KEY"))
    object_storage_private_name = "_".join(("EMPIRICAL_PLATFORM_OBJECT_STORAGE", "SECRET_KEY"))
    return {
        "EMPIRICAL_PLATFORM_ENVIRONMENT": "test",
        pg_credential_name: "-".join(("local", "postgres", "value")),
        object_storage_access_name: storage_access_key,
        object_storage_private_name: storage_private_key,
    }


def test_unified_runtime_initializes_all_dependencies_with_one_config_snapshot() -> None:
    events: list[str] = []
    persistence = RecordingPersistence(events=events)
    object_storage = RecordingObjectStorage(events=events)

    runtime = initialize_infrastructure_runtime(
        _env(),
        persistence=persistence,
        object_storage=object_storage,
    )

    assert runtime.lifecycle_state is RuntimeLifecycleState.READY
    assert runtime.lifecycle_events == (
        RuntimeLifecycleState.NEW,
        RuntimeLifecycleState.STARTING,
        RuntimeLifecycleState.READY,
    )
    assert runtime.persistence is persistence
    assert runtime.object_storage is object_storage
    assert runtime.config.postgresql.password is not None
    assert runtime.config.object_storage.secret_key is not None
    assert runtime.health.status is ProcessHealth.PASS
    assert events[:4] == [
        "persistence.initialize",
        "persistence.check",
        "object_storage.initialize",
        "object_storage.check",
    ]


def test_persistence_initialize_failure_returns_no_runtime_and_does_not_start_storage() -> None:
    events: list[str] = []

    with pytest.raises(FoundationError) as exc_info:
        initialize_infrastructure_runtime(
            _env(),
            persistence=RecordingPersistence(events=events, reachable=False),
            object_storage=RecordingObjectStorage(events=events),
        )

    assert exc_info.value.layer == "persistence"
    assert exc_info.value.context["lifecycle_state"] == RuntimeLifecycleState.FAILED.value
    assert events == ["persistence.initialize"]


def test_persistence_probe_failure_closes_persistence_and_does_not_start_storage() -> None:
    events: list[str] = []

    with pytest.raises(FoundationError) as exc_info:
        initialize_infrastructure_runtime(
            _env(),
            persistence=RecordingPersistence(events=events, check_result=False),
            object_storage=RecordingObjectStorage(events=events),
        )

    assert exc_info.value.layer == "persistence"
    assert events == ["persistence.initialize", "persistence.check", "persistence.close"]


def test_object_storage_initialize_failure_closes_persistence() -> None:
    events: list[str] = []
    persistence = RecordingPersistence(events=events)

    with pytest.raises(FoundationError) as exc_info:
        initialize_infrastructure_runtime(
            _env(),
            persistence=persistence,
            object_storage=RecordingObjectStorage(events=events, reachable=False),
        )

    assert exc_info.value.layer == "object_storage"
    assert persistence.closed is True
    assert events == [
        "persistence.initialize",
        "persistence.check",
        "object_storage.initialize",
        "persistence.close",
    ]


def test_object_storage_probe_failure_closes_storage_then_persistence() -> None:
    events: list[str] = []

    with pytest.raises(FoundationError) as exc_info:
        initialize_infrastructure_runtime(
            _env(),
            persistence=RecordingPersistence(events=events),
            object_storage=RecordingObjectStorage(events=events, check_result=False),
        )

    assert exc_info.value.layer == "object_storage"
    assert events == [
        "persistence.initialize",
        "persistence.check",
        "object_storage.initialize",
        "object_storage.check",
        "object_storage.close",
        "persistence.close",
    ]


def test_combined_health_failure_closes_storage_then_persistence() -> None:
    events: list[str] = []

    def failing_health(_: list[LayerHealth]) -> HealthReport:
        raise RuntimeError("aggregate exploded")

    with pytest.raises(FoundationError) as exc_info:
        initialize_infrastructure_runtime(
            _env(),
            persistence=RecordingPersistence(events=events),
            object_storage=RecordingObjectStorage(events=events),
            health_report_factory=failing_health,
        )

    assert exc_info.value.layer == "runtime"
    assert exc_info.value.operation == "startup"
    assert events.index("object_storage.close") < events.index("persistence.close")


def test_cleanup_failure_does_not_mask_primary_failure() -> None:
    events: list[str] = []

    with pytest.raises(FoundationError) as exc_info:
        initialize_infrastructure_runtime(
            _env(),
            persistence=RecordingPersistence(events=events, close_fails=True),
            object_storage=RecordingObjectStorage(events=events, reachable=False),
        )

    assert exc_info.value.layer == "object_storage"
    failures = exc_info.value.context["cleanup_failures"]
    assert isinstance(failures, list)
    assert failures[0]["layer"] == "persistence"


def test_shutdown_is_ordered_idempotent_and_blocks_later_work() -> None:
    events: list[str] = []
    runtime = initialize_infrastructure_runtime(
        _env(),
        persistence=RecordingPersistence(events=events),
        object_storage=RecordingObjectStorage(events=events),
    )

    runtime.close()
    runtime.close()

    assert runtime.lifecycle_events[-2:] == (
        RuntimeLifecycleState.STOPPING,
        RuntimeLifecycleState.STOPPED,
    )
    assert runtime.lifecycle_state is RuntimeLifecycleState.STOPPED
    assert events.index("object_storage.close") < events.index("persistence.close")
    assert events.count("object_storage.close") == 1
    assert events.count("persistence.close") == 1
    with pytest.raises(FoundationError):
        runtime.ensure_ready("after_shutdown")
    assert runtime.refresh_health().status is ProcessHealth.FAIL


def test_shutdown_before_ready_fails_safely() -> None:
    runtime = initialize_infrastructure_runtime(
        _env(),
        persistence=RecordingPersistence(events=[]),
        object_storage=RecordingObjectStorage(events=[]),
    )
    runtime._state = RuntimeLifecycleState.NEW

    with pytest.raises(FoundationError) as exc_info:
        runtime.close()

    assert exc_info.value.layer == "runtime"
    assert exc_info.value.operation == "shutdown"


def test_shutdown_failure_is_reported_after_reverse_cleanup() -> None:
    events: list[str] = []
    runtime = initialize_infrastructure_runtime(
        _env(),
        persistence=RecordingPersistence(events=events),
        object_storage=RecordingObjectStorage(events=events, close_fails=True),
    )

    with pytest.raises(FoundationError) as exc_info:
        runtime.close()

    assert runtime.lifecycle_state is RuntimeLifecycleState.STOPPED
    assert exc_info.value.operation == "shutdown"
    assert exc_info.value.context["cleanup_failures"][0]["layer"] == "object_storage"


def test_unified_runtime_rejects_invalid_shared_configuration() -> None:
    with pytest.raises(FoundationError) as exc_info:
        initialize_infrastructure_runtime({"EMPIRICAL_PLATFORM_LOG_LEVEL": "NOPE"})

    assert exc_info.value.category is FoundationErrorCategory.CONFIGURATION
    assert exc_info.value.context["lifecycle_state"] == RuntimeLifecycleState.FAILED.value
