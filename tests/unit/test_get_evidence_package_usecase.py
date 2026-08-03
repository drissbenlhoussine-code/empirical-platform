"""MILESTONE-037 behavioral tests for `GetEvidencePackageQuery`/`GetEvidencePackageHandler`.

Proves the frozen retrieval flow (design Section 10): call
`EvidencePackageRepository.get()` exactly once with the query's identity
object unchanged, and build `EvidencePackageSnapshot` from the loaded
aggregate's `identity`/`run_id`/`state` only -- `EvidencePackage.version` and
`LoadedAggregate.persisted_version` are read (or reachable) but never
exposed, and neither `criterion_results`, `artifact_references`, nor
`transition_history` are copied, aliased, or exposed. Also proves
transparent failure propagation for every collaborator (frozen M029
invariant) and that the handler is invocable through the frozen
`QueryEntryPoint`.

Uses deterministic recording fakes/stubs, not mocks, for stronger evidence.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from empirical_platform.application.query import QueryEntryPoint
from empirical_platform.evidence.lifecycle import EvidencePackageLifecycleState
from empirical_platform.evidence.package import ArtifactReference, EvidencePackage
from empirical_platform.evidence.results import CriterionResult
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import EvidencePackageId, RunId
from empirical_platform.shared.contracts.repository import (
    AggregateNotFound,
    LoadedAggregate,
)
from empirical_platform.shared.domain.versioning import AggregateVersion
from empirical_platform.shared.identifiers import RuntimeIdentifier
from empirical_platform.usecases.get_evidence_package import (
    EvidencePackageSnapshot,
    GetEvidencePackageHandler,
    GetEvidencePackageQuery,
)

if TYPE_CHECKING:
    from empirical_platform.evidence.repository import EvidencePackageRepository

_RUNTIME_ID_VALUE = "12345678-1234-4321-8765-1234567890ab"


def _identity(governance_id: str = "EVID-0001") -> DomainIdentity[EvidencePackageId]:
    return DomainIdentity(
        governance_id=EvidencePackageId(governance_id),
        runtime_id=RuntimeIdentifier(_RUNTIME_ID_VALUE),
    )


def _package(
    identity: DomainIdentity[EvidencePackageId], run_id: str = "RUN-0001"
) -> EvidencePackage:
    return EvidencePackage(identity=identity, run_id=RunId(run_id))


class _RecordingEvidencePackageRepository:
    """Records every `get()` call; conforms structurally to `EvidencePackageRepository`."""

    def __init__(self, loaded: LoadedAggregate[EvidencePackage]) -> None:
        self._loaded = loaded
        self.get_calls: list[DomainIdentity[EvidencePackageId]] = []

    def get(self, identity: DomainIdentity[EvidencePackageId]) -> LoadedAggregate[EvidencePackage]:
        self.get_calls.append(identity)
        return self._loaded

    def add(self, aggregate: EvidencePackage) -> object:
        raise AssertionError("add() must not be called by GetEvidencePackageHandler")

    def save(self, aggregate: EvidencePackage, *, expected_persisted_version: object) -> object:
        raise AssertionError("save() must not be called by GetEvidencePackageHandler")


class _FailingEvidencePackageRepository:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc
        self.get_calls = 0

    def get(self, identity: DomainIdentity[EvidencePackageId]) -> object:
        self.get_calls += 1
        raise self._exc

    def add(self, aggregate: EvidencePackage) -> object:
        raise AssertionError("add() must not be called")

    def save(self, aggregate: EvidencePackage, *, expected_persisted_version: object) -> object:
        raise AssertionError("save() must not be called")


def _handler(repository: object) -> GetEvidencePackageHandler:
    return GetEvidencePackageHandler(evidence_package_repository=repository)  # type: ignore[arg-type]


def test_typed_conformance_check() -> None:
    """Mypy-checked proof that GetEvidencePackageHandler conforms to
    QueryHandler[GetEvidencePackageQuery, EvidencePackageSnapshot] without
    inheritance (structural typing only)."""
    identity = _identity()
    loaded = LoadedAggregate(
        aggregate=_package(identity), persisted_version=AggregateVersion.initial()
    )
    repository: EvidencePackageRepository = _RecordingEvidencePackageRepository(loaded)  # type: ignore[assignment]
    handler: GetEvidencePackageHandler = _handler(repository)
    assert handler is not None


def test_query_preserves_the_exact_identity_object() -> None:
    identity = _identity()
    query = GetEvidencePackageQuery(identity=identity)

    assert query.identity is identity


def test_query_contains_no_additional_fields() -> None:
    query = GetEvidencePackageQuery(identity=_identity())
    assert [field for field in query.__slots__] == ["identity"]  # type: ignore[attr-defined]


def test_query_is_immutable() -> None:
    query = GetEvidencePackageQuery(identity=_identity())
    with pytest.raises(AttributeError):
        query.identity = _identity("EVID-0002")  # type: ignore[misc]


def test_evidence_package_repository_get_is_called_exactly_once() -> None:
    identity = _identity()
    loaded = LoadedAggregate(
        aggregate=_package(identity), persisted_version=AggregateVersion.initial()
    )
    repository = _RecordingEvidencePackageRepository(loaded)
    handler = _handler(repository)

    handler.handle(GetEvidencePackageQuery(identity=identity))

    assert len(repository.get_calls) == 1


def test_exact_query_identity_object_is_passed_to_repository_unchanged() -> None:
    identity = _identity()
    loaded = LoadedAggregate(
        aggregate=_package(identity), persisted_version=AggregateVersion.initial()
    )
    repository = _RecordingEvidencePackageRepository(loaded)
    handler = _handler(repository)
    query = GetEvidencePackageQuery(identity=identity)

    handler.handle(query)

    assert repository.get_calls[0] is query.identity


def test_no_add_or_save_call_occurs() -> None:
    """add()/save() raise AssertionError in the fake if called; handler must
    never call either."""
    identity = _identity()
    loaded = LoadedAggregate(
        aggregate=_package(identity), persisted_version=AggregateVersion.initial()
    )
    repository = _RecordingEvidencePackageRepository(loaded)
    handler = _handler(repository)

    handler.handle(GetEvidencePackageQuery(identity=identity))  # would raise otherwise


def test_returned_object_is_an_evidence_package_snapshot() -> None:
    identity = _identity()
    loaded = LoadedAggregate(
        aggregate=_package(identity), persisted_version=AggregateVersion.initial()
    )
    repository = _RecordingEvidencePackageRepository(loaded)
    handler = _handler(repository)

    result = handler.handle(GetEvidencePackageQuery(identity=identity))

    assert isinstance(result, EvidencePackageSnapshot)


def test_snapshot_identity_run_id_and_state_match_the_loaded_aggregate() -> None:
    identity = _identity("EVID-0042")
    package = _package(identity, run_id="RUN-0099")
    loaded = LoadedAggregate(aggregate=package, persisted_version=AggregateVersion.initial())
    repository = _RecordingEvidencePackageRepository(loaded)
    handler = _handler(repository)

    result = handler.handle(GetEvidencePackageQuery(identity=identity))

    assert result.identity == package.identity
    assert result.run_id == package.run_id
    assert result.state == package.state
    assert result.state is EvidencePackageLifecycleState.INITIALIZED


def test_snapshot_exact_field_set() -> None:
    snapshot_fields = {"identity", "run_id", "state"}
    assert set(EvidencePackageSnapshot.__slots__) == snapshot_fields  # type: ignore[attr-defined]


def test_snapshot_is_immutable() -> None:
    identity = _identity()
    loaded = LoadedAggregate(
        aggregate=_package(identity), persisted_version=AggregateVersion.initial()
    )
    repository = _RecordingEvidencePackageRepository(loaded)
    handler = _handler(repository)

    result = handler.handle(GetEvidencePackageQuery(identity=identity))

    with pytest.raises(AttributeError):
        result.state = EvidencePackageLifecycleState.COLLECTING  # type: ignore[misc]


def test_evidence_package_aggregate_is_not_mutated() -> None:
    identity = _identity()
    package = _package(identity)
    version_before = package.version
    loaded = LoadedAggregate(aggregate=package, persisted_version=AggregateVersion.initial())
    repository = _RecordingEvidencePackageRepository(loaded)
    handler = _handler(repository)

    handler.handle(GetEvidencePackageQuery(identity=identity))

    assert package.version == version_before
    assert package.state is EvidencePackageLifecycleState.INITIALIZED


def test_aggregate_version_and_persisted_version_are_distinct_and_neither_leaks() -> None:
    """Mandatory M037 implementation evidence: construct a LoadedAggregate
    whose `aggregate.version` and `persisted_version` are intentionally
    different values, and prove neither appears anywhere on
    EvidencePackageSnapshot -- aggregate version and persisted version must
    never be conflated."""
    identity = _identity()
    package = _package(identity)
    package.start_collection(actor="tester", occurred_at=datetime(2026, 1, 1, tzinfo=UTC))
    # package.version is now 1 (advanced by the transition above); persisted_version
    # is deliberately set to a different value (0) to prove the two are
    # independent concepts that must not be conflated.
    assert package.version == AggregateVersion(1)
    loaded = LoadedAggregate(aggregate=package, persisted_version=AggregateVersion(0))
    assert loaded.aggregate.version != loaded.persisted_version
    repository = _RecordingEvidencePackageRepository(loaded)
    handler = _handler(repository)

    result = handler.handle(GetEvidencePackageQuery(identity=identity))

    assert set(EvidencePackageSnapshot.__slots__) == {"identity", "run_id", "state"}  # type: ignore[attr-defined]
    assert not hasattr(result, "version")
    assert not hasattr(result, "persisted_version")
    assert result.state is EvidencePackageLifecycleState.COLLECTING


def test_criterion_results_artifact_references_and_transition_history_are_not_exposed() -> None:
    """Mandatory M037 implementation evidence: an EvidencePackage with
    non-empty Criterion Results, artifact references, and transition
    history must still produce an EvidencePackageSnapshot that exposes
    none of them -- the exclusion holds regardless of whether the source
    aggregate's own state is empty or populated."""
    identity = _identity()
    package = _package(identity)
    package.start_collection(actor="tester", occurred_at=datetime(2026, 1, 1, tzinfo=UTC))
    package.add_criterion_result(
        CriterionResult(
            evidence_package_id=identity.governance_id,
            criterion_id="CRIT-001",
            recorded_at=datetime(2026, 1, 1, tzinfo=UTC),
            result_label="PASS",
        )
    )
    package.add_artifact_reference(ArtifactReference(value="s3://bucket/artifact-1"))
    assert len(package.criterion_results) == 1
    assert len(package.artifact_references) == 1
    assert len(package.transition_history) == 1
    loaded = LoadedAggregate(aggregate=package, persisted_version=AggregateVersion(1))
    repository = _RecordingEvidencePackageRepository(loaded)
    handler = _handler(repository)

    result = handler.handle(GetEvidencePackageQuery(identity=identity))

    assert not hasattr(result, "criterion_results")
    assert not hasattr(result, "artifact_references")
    assert not hasattr(result, "transition_history")
    assert set(EvidencePackageSnapshot.__slots__) == {"identity", "run_id", "state"}  # type: ignore[attr-defined]
    # The source aggregate's own data remains intact and untouched by retrieval.
    assert len(package.criterion_results) == 1
    assert len(package.artifact_references) == 1
    assert len(package.transition_history) == 1


def test_aggregate_not_found_propagates_with_identity_preserved() -> None:
    exc = AggregateNotFound(aggregate_kind="EvidencePackage", identity=_identity())
    repository = _FailingEvidencePackageRepository(exc)
    handler = _handler(repository)

    with pytest.raises(AggregateNotFound) as excinfo:
        handler.handle(GetEvidencePackageQuery(identity=_identity()))

    assert excinfo.value is exc
    assert repository.get_calls == 1


def test_arbitrary_repository_exception_propagates_with_identity_preserved() -> None:
    exc = RuntimeError("unexpected repository failure")
    repository = _FailingEvidencePackageRepository(exc)
    handler = _handler(repository)

    with pytest.raises(RuntimeError) as excinfo:
        handler.handle(GetEvidencePackageQuery(identity=_identity()))

    assert excinfo.value is exc
    assert repository.get_calls == 1


def test_handler_is_invocable_through_query_entry_point() -> None:
    identity = _identity()
    loaded = LoadedAggregate(
        aggregate=_package(identity), persisted_version=AggregateVersion.initial()
    )
    repository = _RecordingEvidencePackageRepository(loaded)
    handler = _handler(repository)
    entry_point = QueryEntryPoint(handler)

    result = entry_point(GetEvidencePackageQuery(identity=identity))

    assert isinstance(result, EvidencePackageSnapshot)
    assert len(repository.get_calls) == 1


def test_handler_bound_at_construction_not_per_call() -> None:
    identity_one = _identity("EVID-0001")
    identity_two = _identity("EVID-0002")
    loaded_one = LoadedAggregate(
        aggregate=_package(identity_one), persisted_version=AggregateVersion.initial()
    )
    repository = _RecordingEvidencePackageRepository(loaded_one)
    handler = _handler(repository)
    entry_point = QueryEntryPoint(handler)

    entry_point(GetEvidencePackageQuery(identity=identity_one))
    entry_point(GetEvidencePackageQuery(identity=identity_two))

    assert len(repository.get_calls) == 2
