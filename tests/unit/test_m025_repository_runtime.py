"""MILESTONE-025 unit tests for `PostgresRepositoryRuntime`.

Exercises construction, validation, stable identity, lifecycle, and
independent-root behavior against a fast, dependency-free SQLite backend,
mirroring the existing `tests/unit/test_m024_composed_unit_of_work.py`
pattern. Real-PostgreSQL evidence (repository-level get/add/save,
cross-aggregate `run_composed` through the runtime, cross-root rejection)
lives in `tests/integration/test_m025_postgres_repository_runtime.py`.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from pydantic import SecretStr
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.shared.errors import FoundationError
from empirical_platform.shared.persistence.postgres import PostgresPersistenceService
from empirical_platform.shared.persistence.postgres_repositories.campaign_repository import (
    PostgresCampaignRepository,
)
from empirical_platform.shared.persistence.postgres_repositories.evidence_package_repository import (  # noqa: E501
    PostgresEvidencePackageRepository,
)
from empirical_platform.shared.persistence.postgres_repositories.review_repository import (
    PostgresReviewRepository,
)
from empirical_platform.shared.persistence.postgres_repositories.run_repository import (
    PostgresRunRepository,
)
from empirical_platform.shared.persistence.postgres_repositories.runtime import (
    PostgresRepositoryRuntime,
)


def _sqlite_engine() -> object:
    return create_engine(
        "sqlite+pysqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )


def _config() -> PostgreSQLConfigSnapshot:
    return PostgreSQLConfigSnapshot(password=SecretStr("local-compose-placeholder"))


@pytest.fixture
def service() -> Iterator[PostgresPersistenceService]:
    svc = PostgresPersistenceService(_config(), engine=_sqlite_engine())
    svc.initialize()
    try:
        yield svc
    finally:
        svc.close()


# --- Constructor validation ----------------------------------------------------


def test_constructor_rejects_none_with_type_error() -> None:
    with pytest.raises(TypeError, match="PostgresPersistenceService instance"):
        PostgresRepositoryRuntime(None)  # type: ignore[arg-type]


def test_constructor_rejects_incompatible_object_with_type_error() -> None:
    with pytest.raises(TypeError, match="PostgresPersistenceService instance"):
        PostgresRepositoryRuntime("not a service")  # type: ignore[arg-type]


def test_constructor_accepts_valid_service(service: PostgresPersistenceService) -> None:
    runtime = PostgresRepositoryRuntime(service)
    assert isinstance(runtime, PostgresRepositoryRuntime)


def test_constructor_validation_happens_before_repository_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []
    original_init = PostgresCampaignRepository.__init__

    def _counting_init(self: PostgresCampaignRepository, *args: object, **kwargs: object) -> None:
        calls.append(True)
        original_init(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(PostgresCampaignRepository, "__init__", _counting_init)

    with pytest.raises(TypeError):
        PostgresRepositoryRuntime(None)  # type: ignore[arg-type]

    assert calls == [], "no repository must be constructed when validation rejects service"


# --- Construction graph: eager, once, correct types and mapper defaults --------


def test_all_four_repositories_are_exposed_with_correct_concrete_types(
    service: PostgresPersistenceService,
) -> None:
    runtime = PostgresRepositoryRuntime(service)
    assert isinstance(runtime.campaigns, PostgresCampaignRepository)
    assert isinstance(runtime.runs, PostgresRunRepository)
    assert isinstance(runtime.evidence_packages, PostgresEvidencePackageRepository)
    assert isinstance(runtime.reviews, PostgresReviewRepository)


def test_each_repository_is_constructed_exactly_once(
    service: PostgresPersistenceService, monkeypatch: pytest.MonkeyPatch
) -> None:
    call_counts = {"campaign": 0, "run": 0, "evidence": 0, "review": 0}
    originals = {
        "campaign": PostgresCampaignRepository.__init__,
        "run": PostgresRunRepository.__init__,
        "evidence": PostgresEvidencePackageRepository.__init__,
        "review": PostgresReviewRepository.__init__,
    }

    def _make_counter(key: str, original: object) -> object:
        def _counted(self: object, *args: object, **kwargs: object) -> None:
            call_counts[key] += 1
            original(self, *args, **kwargs)  # type: ignore[operator]

        return _counted

    monkeypatch.setattr(
        PostgresCampaignRepository, "__init__", _make_counter("campaign", originals["campaign"])
    )
    monkeypatch.setattr(PostgresRunRepository, "__init__", _make_counter("run", originals["run"]))
    monkeypatch.setattr(
        PostgresEvidencePackageRepository,
        "__init__",
        _make_counter("evidence", originals["evidence"]),
    )
    monkeypatch.setattr(
        PostgresReviewRepository, "__init__", _make_counter("review", originals["review"])
    )

    runtime = PostgresRepositoryRuntime(service)
    # Access every property multiple times -- construction must not repeat.
    _ = runtime.campaigns, runtime.campaigns, runtime.runs, runtime.runs
    _ = runtime.evidence_packages, runtime.evidence_packages
    _ = runtime.reviews, runtime.reviews

    assert call_counts == {"campaign": 1, "run": 1, "evidence": 1, "review": 1}


def test_repository_mapper_defaults_match_frozen_m023_concrete_mappers(
    service: PostgresPersistenceService,
) -> None:
    from empirical_platform.campaign.mapper import ConcreteCampaignMapper
    from empirical_platform.evidence.mapper import ConcreteEvidencePackageMapper
    from empirical_platform.review.mapper import ConcreteReviewMapper
    from empirical_platform.run.mapper import ConcreteRunMapper

    runtime = PostgresRepositoryRuntime(service)
    assert isinstance(runtime.campaigns._mapper, ConcreteCampaignMapper)
    assert isinstance(runtime.runs._mapper, ConcreteRunMapper)
    assert isinstance(runtime.evidence_packages._mapper, ConcreteEvidencePackageMapper)
    assert isinstance(runtime.reviews._mapper, ConcreteReviewMapper)


def test_all_four_repositories_share_the_exact_same_service_identity(
    service: PostgresPersistenceService,
) -> None:
    runtime = PostgresRepositoryRuntime(service)
    assert runtime.campaigns._service is service
    assert runtime.runs._service is service
    assert runtime.evidence_packages._service is service
    assert runtime.reviews._service is service


# --- Stable identity ------------------------------------------------------------


def test_repeated_property_access_returns_identical_object(
    service: PostgresPersistenceService,
) -> None:
    runtime = PostgresRepositoryRuntime(service)
    assert runtime.campaigns is runtime.campaigns
    assert runtime.runs is runtime.runs
    assert runtime.evidence_packages is runtime.evidence_packages
    assert runtime.reviews is runtime.reviews


def test_identity_remains_stable_after_close(service: PostgresPersistenceService) -> None:
    runtime = PostgresRepositoryRuntime(service)
    campaigns_before = runtime.campaigns
    runtime.close()
    assert runtime.campaigns is campaigns_before


# --- Public API surface ---------------------------------------------------------


def test_runtime_has_no_context_manager_protocol(service: PostgresPersistenceService) -> None:
    runtime = PostgresRepositoryRuntime(service)
    assert not hasattr(runtime, "__enter__")
    assert not hasattr(runtime, "__exit__")


def test_runtime_has_no_generic_repository_lookup_or_public_service_locator(
    service: PostgresPersistenceService,
) -> None:
    runtime = PostgresRepositoryRuntime(service)
    assert not hasattr(runtime, "get_repository")
    assert not hasattr(runtime, "service")
    assert not hasattr(runtime, "persistence_service")


def test_run_composed_delegates_exactly_once_and_returns_result_tuple(
    service: PostgresPersistenceService, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = []
    original = PostgresPersistenceService.run_composed

    def _counting_run_composed(self: PostgresPersistenceService, operations: object) -> object:
        calls.append(operations)
        return original(self, operations)  # type: ignore[arg-type]

    monkeypatch.setattr(PostgresPersistenceService, "run_composed", _counting_run_composed)

    runtime = PostgresRepositoryRuntime(service)
    result = runtime.run_composed([lambda: "a", lambda: "b"])

    assert result == ("a", "b")
    assert len(calls) == 1


def test_close_delegates_to_service_close(
    service: PostgresPersistenceService, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = []
    original = PostgresPersistenceService.close

    def _counting_close(self: PostgresPersistenceService) -> None:
        calls.append(True)
        original(self)

    monkeypatch.setattr(PostgresPersistenceService, "close", _counting_close)

    runtime = PostgresRepositoryRuntime(service)
    runtime.close()

    assert calls == [True]


# --- Readiness precondition (no probe, no initialize, existing guard fires) ----


def test_construction_does_not_initialize_an_uninitialized_service() -> None:
    svc = PostgresPersistenceService(_config(), engine=_sqlite_engine())
    # Deliberately never call svc.initialize().
    runtime = PostgresRepositoryRuntime(svc)  # must not raise
    assert isinstance(runtime, PostgresRepositoryRuntime)


def test_uninitialized_service_fails_on_first_repository_operation() -> None:
    svc = PostgresPersistenceService(_config(), engine=_sqlite_engine())
    runtime = PostgresRepositoryRuntime(svc)
    with pytest.raises(FoundationError, match="not initialized"):
        with runtime.campaigns._service.unit_of_work():
            pass


def test_uninitialized_service_fails_on_run_composed() -> None:
    svc = PostgresPersistenceService(_config(), engine=_sqlite_engine())
    runtime = PostgresRepositoryRuntime(svc)
    with pytest.raises(FoundationError, match="not initialized"):
        runtime.run_composed([lambda: None])


def test_closed_service_fails_on_first_repository_operation(
    service: PostgresPersistenceService,
) -> None:
    runtime = PostgresRepositoryRuntime(service)
    runtime.close()
    with pytest.raises(FoundationError, match="closed"):
        with runtime.campaigns._service.unit_of_work():
            pass


def test_closed_service_fails_on_run_composed(service: PostgresPersistenceService) -> None:
    runtime = PostgresRepositoryRuntime(service)
    runtime.close()
    with pytest.raises(FoundationError, match="closed"):
        runtime.run_composed([lambda: None])


def test_repeated_close_is_idempotent(service: PostgresPersistenceService) -> None:
    runtime = PostgresRepositoryRuntime(service)
    runtime.close()
    runtime.close()  # must not raise


# --- Independent roots -----------------------------------------------------------


def test_two_independent_roots_coexist_with_distinct_services() -> None:
    service_a = PostgresPersistenceService(_config(), engine=_sqlite_engine())
    service_a.initialize()
    service_b = PostgresPersistenceService(_config(), engine=_sqlite_engine())
    service_b.initialize()
    try:
        runtime_a = PostgresRepositoryRuntime(service_a)
        runtime_b = PostgresRepositoryRuntime(service_b)

        assert runtime_a.campaigns is not runtime_b.campaigns
        assert runtime_a.campaigns._service is not runtime_b.campaigns._service
        assert runtime_a.campaigns._service is service_a
        assert runtime_b.campaigns._service is service_b
    finally:
        service_a.close()
        service_b.close()


def test_closing_one_root_leaves_the_other_independent_root_usable() -> None:
    service_a = PostgresPersistenceService(_config(), engine=_sqlite_engine())
    service_a.initialize()
    service_b = PostgresPersistenceService(_config(), engine=_sqlite_engine())
    service_b.initialize()
    try:
        runtime_a = PostgresRepositoryRuntime(service_a)
        runtime_b = PostgresRepositoryRuntime(service_b)

        runtime_a.close()

        with pytest.raises(FoundationError, match="closed"):
            runtime_a.run_composed([lambda: None])

        # runtime_b's own, distinct service is entirely unaffected.
        result = runtime_b.run_composed([lambda: "still-usable"])
        assert result == ("still-usable",)
    finally:
        service_a.close()
        service_b.close()


def test_cross_root_repository_rejected_from_joining_a_different_roots_composed_scope() -> None:
    service_a = PostgresPersistenceService(_config(), engine=_sqlite_engine())
    service_a.initialize()
    service_b = PostgresPersistenceService(_config(), engine=_sqlite_engine())
    service_b.initialize()
    try:
        runtime_a = PostgresRepositoryRuntime(service_a)
        runtime_b = PostgresRepositoryRuntime(service_b)

        def op_first() -> str:
            return "a-result"

        def op_cross_root() -> None:
            # Attempting to use runtime_b's service while runtime_a's
            # composed scope is active must be rejected by the existing,
            # unmodified M024 same-service-identity rule -- before any SQL.
            with runtime_b.campaigns._service.unit_of_work():
                pass

        with pytest.raises(FoundationError, match="Nested persistence units of work"):
            runtime_a.run_composed([op_first, op_cross_root])
    finally:
        service_a.close()
        service_b.close()
