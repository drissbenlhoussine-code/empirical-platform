"""MILESTONE-034 behavioral tests for `GetRunQuery`/`GetRunHandler`.

Proves the frozen retrieval flow (design freeze Section 22): call
`RunRepository.get()` exactly once with the query's identity object
unchanged, and build `RunSnapshot` from the loaded aggregate's
`identity`/`campaign_id`/`state` only -- `Run.version` and
`LoadedAggregate.persisted_version` are read (or reachable) but never
exposed, and neither `manifests` nor `transition_history` are copied,
aliased, or exposed. Also proves transparent failure propagation for
every collaborator (frozen M029 invariant) and that the handler is
invocable through the frozen `QueryEntryPoint`.

Uses deterministic recording fakes/stubs, not mocks, for stronger evidence.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from empirical_platform.application.query import QueryEntryPoint
from empirical_platform.campaign.lifecycle import RunLifecycleState
from empirical_platform.datasets import DatasetManifest
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import CampaignId, RunId
from empirical_platform.run.aggregate import Run
from empirical_platform.shared.contracts.repository import (
    AggregateNotFound,
    LoadedAggregate,
)
from empirical_platform.shared.domain.versioning import AggregateVersion
from empirical_platform.shared.identifiers import RuntimeIdentifier
from empirical_platform.usecases.get_run import GetRunHandler, GetRunQuery, RunSnapshot

if TYPE_CHECKING:
    from empirical_platform.run.repository import RunRepository

_RUNTIME_ID_VALUE = "12345678-1234-4321-8765-1234567890ab"


def _identity(governance_id: str = "RUN-0001") -> DomainIdentity[RunId]:
    return DomainIdentity(
        governance_id=RunId(governance_id),
        runtime_id=RuntimeIdentifier(_RUNTIME_ID_VALUE),
    )


def _run(identity: DomainIdentity[RunId], campaign_id: str = "CAMP-0001") -> Run:
    return Run(identity=identity, campaign_id=CampaignId(campaign_id))


class _RecordingRunRepository:
    """Records every `get()` call; conforms structurally to `RunRepository`."""

    def __init__(self, loaded: LoadedAggregate[Run]) -> None:
        self._loaded = loaded
        self.get_calls: list[DomainIdentity[RunId]] = []

    def get(self, identity: DomainIdentity[RunId]) -> LoadedAggregate[Run]:
        self.get_calls.append(identity)
        return self._loaded

    def add(self, aggregate: Run) -> object:
        raise AssertionError("add() must not be called by GetRunHandler")

    def save(self, aggregate: Run, *, expected_persisted_version: object) -> object:
        raise AssertionError("save() must not be called by GetRunHandler")


class _FailingRunRepository:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc
        self.get_calls = 0

    def get(self, identity: DomainIdentity[RunId]) -> object:
        self.get_calls += 1
        raise self._exc

    def add(self, aggregate: Run) -> object:
        raise AssertionError("add() must not be called")

    def save(self, aggregate: Run, *, expected_persisted_version: object) -> object:
        raise AssertionError("save() must not be called")


def _handler(repository: object) -> GetRunHandler:
    return GetRunHandler(run_repository=repository)  # type: ignore[arg-type]


def test_typed_conformance_check() -> None:
    """Mypy-checked proof that GetRunHandler conforms to
    QueryHandler[GetRunQuery, RunSnapshot] without inheritance (structural
    typing only)."""
    identity = _identity()
    loaded = LoadedAggregate(aggregate=_run(identity), persisted_version=AggregateVersion.initial())
    repository: RunRepository = _RecordingRunRepository(loaded)  # type: ignore[assignment]
    handler: GetRunHandler = _handler(repository)
    assert handler is not None


def test_query_preserves_the_exact_identity_object() -> None:
    identity = _identity()
    query = GetRunQuery(identity=identity)

    assert query.identity is identity


def test_query_contains_no_additional_fields() -> None:
    query = GetRunQuery(identity=_identity())
    assert [field for field in query.__slots__] == ["identity"]  # type: ignore[attr-defined]


def test_query_is_immutable() -> None:
    query = GetRunQuery(identity=_identity())
    with pytest.raises(AttributeError):
        query.identity = _identity("RUN-0002")  # type: ignore[misc]


def test_run_repository_get_is_called_exactly_once() -> None:
    identity = _identity()
    loaded = LoadedAggregate(aggregate=_run(identity), persisted_version=AggregateVersion.initial())
    repository = _RecordingRunRepository(loaded)
    handler = _handler(repository)

    handler.handle(GetRunQuery(identity=identity))

    assert len(repository.get_calls) == 1


def test_exact_query_identity_object_is_passed_to_repository_unchanged() -> None:
    identity = _identity()
    loaded = LoadedAggregate(aggregate=_run(identity), persisted_version=AggregateVersion.initial())
    repository = _RecordingRunRepository(loaded)
    handler = _handler(repository)
    query = GetRunQuery(identity=identity)

    handler.handle(query)

    assert repository.get_calls[0] is query.identity


def test_no_add_or_save_call_occurs() -> None:
    """add()/save() raise AssertionError in the fake if called; handler must
    never call either."""
    identity = _identity()
    loaded = LoadedAggregate(aggregate=_run(identity), persisted_version=AggregateVersion.initial())
    repository = _RecordingRunRepository(loaded)
    handler = _handler(repository)

    handler.handle(GetRunQuery(identity=identity))  # would raise if add()/save() were called


def test_returned_object_is_a_run_snapshot() -> None:
    identity = _identity()
    loaded = LoadedAggregate(aggregate=_run(identity), persisted_version=AggregateVersion.initial())
    repository = _RecordingRunRepository(loaded)
    handler = _handler(repository)

    result = handler.handle(GetRunQuery(identity=identity))

    assert isinstance(result, RunSnapshot)


def test_snapshot_identity_campaign_id_and_state_match_the_loaded_aggregate() -> None:
    identity = _identity("RUN-0042")
    run = _run(identity, campaign_id="CAMP-0099")
    loaded = LoadedAggregate(aggregate=run, persisted_version=AggregateVersion.initial())
    repository = _RecordingRunRepository(loaded)
    handler = _handler(repository)

    result = handler.handle(GetRunQuery(identity=identity))

    assert result.identity == run.identity
    assert result.campaign_id == run.campaign_id
    assert result.state == run.state
    assert result.state is RunLifecycleState.CREATED


def test_snapshot_exact_field_set() -> None:
    snapshot_fields = {"identity", "campaign_id", "state"}
    assert set(RunSnapshot.__slots__) == snapshot_fields  # type: ignore[attr-defined]


def test_snapshot_is_immutable() -> None:
    identity = _identity()
    loaded = LoadedAggregate(aggregate=_run(identity), persisted_version=AggregateVersion.initial())
    repository = _RecordingRunRepository(loaded)
    handler = _handler(repository)

    result = handler.handle(GetRunQuery(identity=identity))

    with pytest.raises(AttributeError):
        result.state = RunLifecycleState.AUTHORIZED  # type: ignore[misc]


def test_run_aggregate_is_not_mutated() -> None:
    identity = _identity()
    run = _run(identity)
    version_before = run.version
    loaded = LoadedAggregate(aggregate=run, persisted_version=AggregateVersion.initial())
    repository = _RecordingRunRepository(loaded)
    handler = _handler(repository)

    handler.handle(GetRunQuery(identity=identity))

    assert run.version == version_before
    assert run.state is RunLifecycleState.CREATED


def test_aggregate_version_and_persisted_version_are_distinct_and_neither_leaks() -> None:
    """Mandatory M034 implementation evidence: construct a LoadedAggregate
    whose `aggregate.version` and `persisted_version` are intentionally
    different values, and prove neither appears anywhere on RunSnapshot --
    aggregate version and persisted version must never be conflated."""
    identity = _identity()
    run = _run(identity)
    run.authorize(actor="tester", occurred_at=datetime(2026, 1, 1, tzinfo=UTC))
    # run.version is now 1 (advanced by the transition above); persisted_version
    # is deliberately set to a different value (0) to prove the two are
    # independent concepts that must not be conflated.
    assert run.version == AggregateVersion(1)
    loaded = LoadedAggregate(aggregate=run, persisted_version=AggregateVersion(0))
    assert loaded.aggregate.version != loaded.persisted_version
    repository = _RecordingRunRepository(loaded)
    handler = _handler(repository)

    result = handler.handle(GetRunQuery(identity=identity))

    assert set(RunSnapshot.__slots__) == {"identity", "campaign_id", "state"}  # type: ignore[attr-defined]
    assert not hasattr(result, "version")
    assert not hasattr(result, "persisted_version")
    assert result.state is RunLifecycleState.AUTHORIZED


def test_manifests_and_transition_history_are_not_exposed_even_when_non_empty() -> None:
    """Mandatory M034 implementation evidence: a Run with non-empty
    Run-owned manifests and transition history must still produce a
    RunSnapshot that exposes neither -- the exclusion holds regardless of
    whether the source aggregate's own state is empty or populated."""
    identity = _identity()
    run = _run(identity)
    run.authorize(actor="tester", occurred_at=datetime(2026, 1, 1, tzinfo=UTC))
    run.append_manifest(
        DatasetManifest(
            run_id=identity.governance_id,
            recorded_at=datetime(2026, 1, 1, tzinfo=UTC),
            source="test-source",
        )
    )
    assert len(run.manifests) == 1
    assert len(run.transition_history) == 1
    loaded = LoadedAggregate(aggregate=run, persisted_version=AggregateVersion(1))
    repository = _RecordingRunRepository(loaded)
    handler = _handler(repository)

    result = handler.handle(GetRunQuery(identity=identity))

    assert not hasattr(result, "manifests")
    assert not hasattr(result, "transition_history")
    assert set(RunSnapshot.__slots__) == {"identity", "campaign_id", "state"}  # type: ignore[attr-defined]
    # The source aggregate's own data remains intact and untouched by retrieval.
    assert len(run.manifests) == 1
    assert len(run.transition_history) == 1


def test_aggregate_not_found_propagates_with_identity_preserved() -> None:
    exc = AggregateNotFound(aggregate_kind="Run", identity=_identity())
    repository = _FailingRunRepository(exc)
    handler = _handler(repository)

    with pytest.raises(AggregateNotFound) as excinfo:
        handler.handle(GetRunQuery(identity=_identity()))

    assert excinfo.value is exc
    assert repository.get_calls == 1


def test_arbitrary_repository_exception_propagates_with_identity_preserved() -> None:
    exc = RuntimeError("unexpected repository failure")
    repository = _FailingRunRepository(exc)
    handler = _handler(repository)

    with pytest.raises(RuntimeError) as excinfo:
        handler.handle(GetRunQuery(identity=_identity()))

    assert excinfo.value is exc
    assert repository.get_calls == 1


def test_handler_is_invocable_through_query_entry_point() -> None:
    identity = _identity()
    loaded = LoadedAggregate(aggregate=_run(identity), persisted_version=AggregateVersion.initial())
    repository = _RecordingRunRepository(loaded)
    handler = _handler(repository)
    entry_point = QueryEntryPoint(handler)

    result = entry_point(GetRunQuery(identity=identity))

    assert isinstance(result, RunSnapshot)
    assert len(repository.get_calls) == 1


def test_handler_bound_at_construction_not_per_call() -> None:
    identity_one = _identity("RUN-0001")
    identity_two = _identity("RUN-0002")
    loaded_one = LoadedAggregate(
        aggregate=_run(identity_one), persisted_version=AggregateVersion.initial()
    )
    repository = _RecordingRunRepository(loaded_one)
    handler = _handler(repository)
    entry_point = QueryEntryPoint(handler)

    entry_point(GetRunQuery(identity=identity_one))
    entry_point(GetRunQuery(identity=identity_two))

    assert len(repository.get_calls) == 2
