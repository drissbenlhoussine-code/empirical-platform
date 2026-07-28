"""MILESTONE-026 unit tests for Foundation Runtime Repository Composition.

Exercises the new `FoundationRuntime.repository_runtime` field and its
conditional construction inside `initialize_infrastructure_runtime` and
`initialize_foundation_runtime_with_postgresql`, against a fast,
dependency-free SQLite-backed `PostgresPersistenceService`, mirroring the
existing `tests/unit/test_m025_repository_runtime.py` pattern. Real-PostgreSQL
evidence lives in
`tests/integration/test_m026_foundation_runtime_repository_composition.py`.
"""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import patch

import pytest
from pydantic import SecretStr
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

import empirical_platform.shared.bootstrap as bootstrap
from empirical_platform.shared.bootstrap import (
    FoundationRuntime,
    RuntimeLifecycleState,
    initialize_foundation_runtime,
    initialize_foundation_runtime_with_object_storage,
    initialize_foundation_runtime_with_postgresql,
    initialize_infrastructure_runtime,
)
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.shared.errors import FoundationError, FoundationErrorCategory
from empirical_platform.shared.health import HealthReport, LayerHealth
from empirical_platform.shared.object_storage.fake import FakeObjectStorageService
from empirical_platform.shared.persistence.fake import FakePersistenceService
from empirical_platform.shared.persistence.postgres import PostgresPersistenceService
from empirical_platform.shared.persistence.postgres_repositories.runtime import (
    PostgresRepositoryRuntime,
)


def _sqlite_engine() -> object:
    return create_engine(
        "sqlite+pysqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )


def _config(secret_value: str) -> PostgreSQLConfigSnapshot:
    return PostgreSQLConfigSnapshot(password=SecretStr(secret_value))


def _env() -> dict[str, str]:
    return {
        "EMPIRICAL_PLATFORM_ENVIRONMENT": "test",
        "EMPIRICAL_PLATFORM_POSTGRES_PASSWORD": "-".join(("m026", "placeholder")),
        "EMPIRICAL_PLATFORM_OBJECT_STORAGE_ACCESS_KEY": "-".join(("local", "access")),
        "EMPIRICAL_PLATFORM_OBJECT_STORAGE_SECRET_KEY": "-".join(("local", "secret")),
    }


class RecordingPostgresPersistenceService(PostgresPersistenceService):
    """Real `PostgresPersistenceService` subclass recording lifecycle events."""

    def __init__(
        self, *, events: list[str], config: PostgreSQLConfigSnapshot | None = None
    ) -> None:
        super().__init__(config or _config("m026-placeholder"), engine=_sqlite_engine())
        self.events = events

    def initialize(self) -> None:
        self.events.append("persistence.initialize")
        super().initialize()

    def check(self) -> bool:
        self.events.append("persistence.check")
        return super().check()

    def close(self) -> None:
        self.events.append("persistence.close")
        super().close()


@pytest.fixture
def sqlite_service() -> Iterator[PostgresPersistenceService]:
    svc = PostgresPersistenceService(_config("m026-placeholder"), engine=_sqlite_engine())
    svc.initialize()
    try:
        yield svc
    finally:
        svc.close()


# --- Foundation field ---------------------------------------------------


def test_field_defaults_to_none_on_manual_construction() -> None:
    runtime = initialize_foundation_runtime({"EMPIRICAL_PLATFORM_ENVIRONMENT": "test"})
    assert runtime.repository_runtime is None


def test_field_accepts_explicit_postgres_repository_runtime(
    sqlite_service: PostgresPersistenceService,
) -> None:
    base = initialize_foundation_runtime({"EMPIRICAL_PLATFORM_ENVIRONMENT": "test"})
    manual = FoundationRuntime(
        config=base.config,
        wall_clock=base.wall_clock,
        monotonic_clock=base.monotonic_clock,
        identifiers=base.identifiers,
        logger=base.logger,
        health=base.health,
        persistence=sqlite_service,
        repository_runtime=PostgresRepositoryRuntime(sqlite_service),
    )
    assert manual.repository_runtime is not None
    assert manual.repository_runtime.campaigns is not None


# --- Real (SQLite-backed) PostgresPersistenceService construction paths --


def test_infrastructure_runtime_constructs_repository_runtime_for_real_service() -> None:
    events: list[str] = []
    persistence = RecordingPostgresPersistenceService(events=events)
    object_storage = FakeObjectStorageService()

    runtime = initialize_infrastructure_runtime(
        _env(), persistence=persistence, object_storage=object_storage
    )
    try:
        assert runtime.repository_runtime is not None
        assert isinstance(runtime.repository_runtime, PostgresRepositoryRuntime)
        assert runtime.repository_runtime._service is runtime.persistence
        assert runtime.persistence is persistence
        # construction happens strictly after persistence initialize + readiness check
        assert events[:2] == ["persistence.initialize", "persistence.check"]
    finally:
        runtime.close()


def test_foundation_runtime_with_postgresql_constructs_repository_runtime_for_real_service() -> (
    None
):
    events: list[str] = []
    persistence = RecordingPostgresPersistenceService(events=events)

    runtime = initialize_foundation_runtime_with_postgresql(
        {"EMPIRICAL_PLATFORM_ENVIRONMENT": "test"}, persistence=persistence
    )
    try:
        assert runtime.repository_runtime is not None
        assert runtime.repository_runtime._service is runtime.persistence
        assert runtime.persistence is persistence
        assert events == ["persistence.initialize"]
    finally:
        persistence.close()


def test_repository_runtime_constructed_exactly_once_per_call() -> None:
    persistence = RecordingPostgresPersistenceService(events=[])
    object_storage = FakeObjectStorageService()

    with patch.object(
        bootstrap, "PostgresRepositoryRuntime", wraps=PostgresRepositoryRuntime
    ) as spy:
        runtime = initialize_infrastructure_runtime(
            _env(), persistence=persistence, object_storage=object_storage
        )
        try:
            assert spy.call_count == 1
        finally:
            runtime.close()


# --- Fake / non-PostgreSQL persistence paths -----------------------------


def test_infrastructure_runtime_leaves_repository_runtime_none_for_fake_persistence() -> None:
    with patch.object(
        bootstrap, "PostgresRepositoryRuntime", wraps=PostgresRepositoryRuntime
    ) as spy:
        runtime = initialize_infrastructure_runtime(
            _env(),
            persistence=FakePersistenceService(),
            object_storage=FakeObjectStorageService(),
        )
        assert runtime.repository_runtime is None
        assert spy.call_count == 0


def test_foundation_runtime_with_postgresql_leaves_repository_runtime_none_for_fake() -> None:
    with patch.object(
        bootstrap, "PostgresRepositoryRuntime", wraps=PostgresRepositoryRuntime
    ) as spy:
        runtime = initialize_foundation_runtime_with_postgresql(
            {"EMPIRICAL_PLATFORM_ENVIRONMENT": "test"},
            persistence=FakePersistenceService(),
        )
        assert runtime.repository_runtime is None
        assert spy.call_count == 0


def test_bare_foundation_runtime_leaves_repository_runtime_none() -> None:
    runtime = initialize_foundation_runtime({"EMPIRICAL_PLATFORM_ENVIRONMENT": "test"})
    assert runtime.repository_runtime is None


def test_object_storage_runtime_leaves_repository_runtime_none() -> None:
    runtime = initialize_foundation_runtime_with_object_storage(
        {"EMPIRICAL_PLATFORM_ENVIRONMENT": "test"},
        object_storage=FakeObjectStorageService(),
    )
    assert runtime.repository_runtime is None


# --- Failure paths --------------------------------------------------------


def test_persistence_initialize_failure_means_repository_runtime_never_constructed() -> None:
    class FailingPersistence(FakePersistenceService):
        def initialize(self) -> None:
            raise FoundationError(
                category=FoundationErrorCategory.PERSISTENCE,
                message="boom",
                layer="persistence",
                operation="initialize",
            )

    with patch.object(
        bootstrap, "PostgresRepositoryRuntime", wraps=PostgresRepositoryRuntime
    ) as spy:
        with pytest.raises(FoundationError):
            initialize_infrastructure_runtime(
                _env(),
                persistence=FailingPersistence(),
                object_storage=FakeObjectStorageService(),
            )
        assert spy.call_count == 0


def test_persistence_readiness_failure_means_repository_runtime_never_constructed() -> None:
    with patch.object(
        bootstrap, "PostgresRepositoryRuntime", wraps=PostgresRepositoryRuntime
    ) as spy:
        with pytest.raises(FoundationError):
            initialize_infrastructure_runtime(
                _env(),
                persistence=FakePersistenceService(reachable=False),
                object_storage=FakeObjectStorageService(),
            )
        assert spy.call_count == 0


def test_injected_repository_runtime_constructor_failure_returns_no_runtime_and_cleans_up() -> None:
    events: list[str] = []
    persistence = RecordingPostgresPersistenceService(events=events)

    def _boom(_service: object) -> None:
        raise RuntimeError("injected repository-runtime construction failure")

    with patch.object(bootstrap, "PostgresRepositoryRuntime", side_effect=_boom):
        with pytest.raises(Exception):  # noqa: B017,PT011 - wrapped FoundationError expected
            initialize_infrastructure_runtime(
                _env(),
                persistence=persistence,
                object_storage=FakeObjectStorageService(),
            )

    assert events == ["persistence.initialize", "persistence.check", "persistence.close"]


def test_object_storage_failure_after_repository_runtime_construction_returns_no_runtime() -> None:
    events: list[str] = []
    persistence = RecordingPostgresPersistenceService(events=events)

    with pytest.raises(FoundationError) as exc_info:
        initialize_infrastructure_runtime(
            _env(),
            persistence=persistence,
            object_storage=FakeObjectStorageService(reachable=False),
        )

    assert exc_info.value.layer == "object_storage"
    assert events == ["persistence.initialize", "persistence.check", "persistence.close"]


def test_health_aggregation_failure_after_repository_runtime_construction_returns_no_runtime() -> (
    None
):
    events: list[str] = []
    persistence = RecordingPostgresPersistenceService(events=events)

    def failing_health(_: list[LayerHealth]) -> HealthReport:
        raise RuntimeError("aggregate exploded")

    with pytest.raises(FoundationError) as exc_info:
        initialize_infrastructure_runtime(
            _env(),
            persistence=persistence,
            object_storage=FakeObjectStorageService(),
            health_report_factory=failing_health,
        )

    assert exc_info.value.layer == "runtime"
    assert exc_info.value.operation == "startup"
    assert events == ["persistence.initialize", "persistence.check", "persistence.close"]


# --- Close / post-close behavior ------------------------------------------


def test_close_does_not_separately_close_repository_runtime() -> None:
    persistence = RecordingPostgresPersistenceService(events=[])
    object_storage = FakeObjectStorageService()

    runtime = initialize_infrastructure_runtime(
        _env(), persistence=persistence, object_storage=object_storage
    )
    repository_runtime = runtime.repository_runtime
    assert repository_runtime is not None

    with patch.object(PostgresRepositoryRuntime, "close") as repo_close_spy:
        runtime.close()
        repo_close_spy.assert_not_called()

    assert runtime.repository_runtime is repository_runtime
    assert runtime.lifecycle_state is RuntimeLifecycleState.STOPPED


def test_repository_runtime_operations_fail_after_close() -> None:
    persistence = RecordingPostgresPersistenceService(events=[])
    object_storage = FakeObjectStorageService()

    runtime = initialize_infrastructure_runtime(
        _env(), persistence=persistence, object_storage=object_storage
    )
    runtime.close()

    assert runtime.repository_runtime is not None
    with pytest.raises(FoundationError):
        runtime.repository_runtime.run_composed([])


# --- Repr / credential safety ----------------------------------------------


def test_repr_does_not_expose_secret_marker() -> None:
    marker = "m026-unique-secret-marker-7f3a9c"
    config = _config(marker)
    service = PostgresPersistenceService(config, engine=_sqlite_engine())
    repository_runtime = PostgresRepositoryRuntime(service)

    base = initialize_foundation_runtime({"EMPIRICAL_PLATFORM_ENVIRONMENT": "test"})
    runtime = FoundationRuntime(
        config=base.config,
        wall_clock=base.wall_clock,
        monotonic_clock=base.monotonic_clock,
        identifiers=base.identifiers,
        logger=base.logger,
        health=base.health,
        persistence=service,
        repository_runtime=repository_runtime,
    )

    reprs = [
        repr(runtime),
        repr(runtime.repository_runtime),
        repr(runtime.repository_runtime.campaigns),
        repr(runtime.repository_runtime.runs),
        repr(runtime.repository_runtime.evidence_packages),
        repr(runtime.repository_runtime.reviews),
    ]

    for value in reprs:
        assert marker not in value
        assert "postgresql://" not in value
        assert config.sqlalchemy_url().render_as_string(hide_password=False) not in value

    service.close()
