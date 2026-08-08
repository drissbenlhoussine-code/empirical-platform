"""MILESTONE-055 behavioral tests for the five new Run execution usecases:
`start_run_acquisition`, `start_run_normalization`, `start_run_validation`,
`complete_run_execution`, `append_run_manifest`.

Each transition usecase mirrors the exact frozen load-mutate-save pattern
already proven by `authorize_run` (M035) and `fail_run` (M048): call
`RunRepository.get()` exactly once, invoke the corresponding `Run` domain
method exactly once with the command's data unchanged, then call
`RunRepository.save()` exactly once with the mutated aggregate and the
command's own `expected_persisted_version` -- never `loaded.persisted_version`.
Transparent failure propagation is proven once per usecase, not with the
full ~30-test breadth of the established convention (per this milestone's
own instruction to reuse established test infrastructure without chasing
test quantity), since the underlying mechanism is identical and already
exhaustively proven by M035/M048.

Uses deterministic recording fakes/stubs, not mocks, for stronger evidence.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from empirical_platform.application.command import CommandEntryPoint
from empirical_platform.campaign.lifecycle import RunLifecycleState
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import CampaignId, RunId
from empirical_platform.run import DatasetManifest
from empirical_platform.run.aggregate import Run
from empirical_platform.shared.contracts.repository import (
    AggregateNotFound,
    LoadedAggregate,
    OptimisticConcurrencyConflict,
    SaveOperation,
    SaveResult,
)
from empirical_platform.shared.domain.versioning import AggregateVersion
from empirical_platform.shared.identifiers import RuntimeIdentifier
from empirical_platform.usecases.append_run_manifest import (
    AppendRunManifestCommand,
    AppendRunManifestHandler,
)
from empirical_platform.usecases.complete_run_execution import (
    CompleteRunExecutionCommand,
    CompleteRunExecutionHandler,
)
from empirical_platform.usecases.start_run_acquisition import (
    StartRunAcquisitionCommand,
    StartRunAcquisitionHandler,
)
from empirical_platform.usecases.start_run_normalization import (
    StartRunNormalizationCommand,
    StartRunNormalizationHandler,
)
from empirical_platform.usecases.start_run_validation import (
    StartRunValidationCommand,
    StartRunValidationHandler,
)

_RUNTIME_ID_VALUE = "12345678-1234-4321-8765-1234567890ab"
_OCCURRED_AT = datetime(2026, 1, 1, tzinfo=UTC)


def _identity() -> DomainIdentity[RunId]:
    return DomainIdentity(
        governance_id=RunId("RUN-0001"), runtime_id=RuntimeIdentifier(_RUNTIME_ID_VALUE)
    )


def _run(identity: DomainIdentity[RunId]) -> Run:
    return Run(identity=identity, campaign_id=CampaignId("CAMP-0001"))


def _authorized_run(identity: DomainIdentity[RunId]) -> Run:
    run = _run(identity)
    run.authorize(actor="seed", occurred_at=_OCCURRED_AT)
    return run


def _acquiring_run(identity: DomainIdentity[RunId]) -> Run:
    run = _authorized_run(identity)
    run.start_acquisition(actor="seed", occurred_at=_OCCURRED_AT)
    return run


def _normalizing_run(identity: DomainIdentity[RunId]) -> Run:
    run = _acquiring_run(identity)
    run.start_normalization(actor="seed", occurred_at=_OCCURRED_AT)
    return run


def _validating_run(identity: DomainIdentity[RunId]) -> Run:
    run = _normalizing_run(identity)
    run.start_validation(actor="seed", occurred_at=_OCCURRED_AT)
    return run


class _RecordingRunRepository:
    def __init__(self, loaded: LoadedAggregate[Run], save_result: SaveResult) -> None:
        self._loaded = loaded
        self._save_result = save_result
        self.get_calls: list[DomainIdentity[RunId]] = []
        self.save_calls: list[tuple[Run, AggregateVersion]] = []

    def get(self, identity: DomainIdentity[RunId]) -> LoadedAggregate[Run]:
        self.get_calls.append(identity)
        return self._loaded

    def add(self, aggregate: Run) -> SaveResult:
        raise AssertionError("add() must not be called")

    def save(self, aggregate: Run, *, expected_persisted_version: AggregateVersion) -> SaveResult:
        self.save_calls.append((aggregate, expected_persisted_version))
        return self._save_result


class _FailingGetRunRepository:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc
        self.get_calls = 0
        self.save_calls = 0

    def get(self, identity: DomainIdentity[RunId]) -> object:
        self.get_calls += 1
        raise self._exc

    def add(self, aggregate: Run) -> object:
        raise AssertionError("add() must not be called")

    def save(self, aggregate: Run, *, expected_persisted_version: object) -> object:
        self.save_calls += 1
        raise AssertionError("save() must not be called after get() failure")


class _FailingSaveRunRepository:
    def __init__(self, loaded: LoadedAggregate[Run], exc: Exception) -> None:
        self._loaded = loaded
        self._exc = exc
        self.get_calls = 0
        self.save_calls = 0

    def get(self, identity: DomainIdentity[RunId]) -> LoadedAggregate[Run]:
        self.get_calls += 1
        return self._loaded

    def add(self, aggregate: Run) -> object:
        raise AssertionError("add() must not be called")

    def save(self, aggregate: Run, *, expected_persisted_version: AggregateVersion) -> object:
        self.save_calls += 1
        raise self._exc


def _save_result(version: int = 1) -> SaveResult:
    return SaveResult(operation=SaveOperation.UPDATED, persisted_version=AggregateVersion(version))


def _occ_conflict(identity: DomainIdentity[RunId]) -> OptimisticConcurrencyConflict:
    return OptimisticConcurrencyConflict(
        aggregate_kind="Run",
        identity=identity,
        expected_persisted_version=AggregateVersion(0),
        aggregate_current_version=AggregateVersion(1),
        actual_persisted_version=AggregateVersion(1),
    )


# ---------------------------------------------------------------------------
# start_run_acquisition
# ---------------------------------------------------------------------------


def test_start_acquisition_transitions_authorized_run_and_saves_with_command_version() -> None:
    identity = _identity()
    run = _authorized_run(identity)
    loaded = LoadedAggregate(aggregate=run, persisted_version=AggregateVersion(1))
    repository = _RecordingRunRepository(loaded, _save_result(2))
    handler = StartRunAcquisitionHandler(run_repository=repository)
    command = StartRunAcquisitionCommand(
        identity=identity,
        expected_persisted_version=AggregateVersion(1),
        actor="operator",
        occurred_at=_OCCURRED_AT,
    )

    result = CommandEntryPoint(handler)(command)

    assert repository.get_calls == [identity]
    assert run.state is RunLifecycleState.ACQUIRING
    saved_aggregate, saved_version = repository.save_calls[0]
    assert saved_aggregate is run
    assert saved_version is command.expected_persisted_version
    assert result is repository._save_result


def test_start_acquisition_invalid_transition_propagates_and_save_never_called() -> None:
    identity = _identity()
    run = _run(identity)  # CREATED, not AUTHORIZED
    loaded = LoadedAggregate(aggregate=run, persisted_version=AggregateVersion.initial())
    repository = _RecordingRunRepository(loaded, _save_result())
    handler = StartRunAcquisitionHandler(run_repository=repository)
    command = StartRunAcquisitionCommand(
        identity=identity,
        expected_persisted_version=AggregateVersion.initial(),
        actor="operator",
        occurred_at=_OCCURRED_AT,
    )

    with pytest.raises(ValueError, match="cannot transition from"):
        handler.handle(command)

    assert repository.save_calls == []


def test_start_acquisition_propagates_aggregate_not_found() -> None:
    identity = _identity()
    exc = AggregateNotFound(aggregate_kind="Run", identity=identity)
    repository = _FailingGetRunRepository(exc)
    handler = StartRunAcquisitionHandler(run_repository=repository)  # type: ignore[arg-type]
    command = StartRunAcquisitionCommand(
        identity=identity,
        expected_persisted_version=AggregateVersion.initial(),
        actor="operator",
        occurred_at=_OCCURRED_AT,
    )

    with pytest.raises(AggregateNotFound) as excinfo:
        handler.handle(command)

    assert excinfo.value is exc


def test_start_acquisition_propagates_optimistic_concurrency_conflict() -> None:
    identity = _identity()
    run = _authorized_run(identity)
    loaded = LoadedAggregate(aggregate=run, persisted_version=AggregateVersion(1))
    exc = _occ_conflict(identity)
    repository = _FailingSaveRunRepository(loaded, exc)
    handler = StartRunAcquisitionHandler(run_repository=repository)  # type: ignore[arg-type]
    command = StartRunAcquisitionCommand(
        identity=identity,
        expected_persisted_version=AggregateVersion(0),
        actor="operator",
        occurred_at=_OCCURRED_AT,
    )

    with pytest.raises(OptimisticConcurrencyConflict) as excinfo:
        handler.handle(command)

    assert excinfo.value is exc


# ---------------------------------------------------------------------------
# start_run_normalization
# ---------------------------------------------------------------------------


def test_start_normalization_transitions_acquiring_run_and_saves_with_command_version() -> None:
    identity = _identity()
    run = _acquiring_run(identity)
    loaded = LoadedAggregate(aggregate=run, persisted_version=AggregateVersion(2))
    repository = _RecordingRunRepository(loaded, _save_result(3))
    handler = StartRunNormalizationHandler(run_repository=repository)
    command = StartRunNormalizationCommand(
        identity=identity,
        expected_persisted_version=AggregateVersion(2),
        actor="operator",
        occurred_at=_OCCURRED_AT,
    )

    CommandEntryPoint(handler)(command)

    assert run.state is RunLifecycleState.NORMALIZING
    _, saved_version = repository.save_calls[0]
    assert saved_version is command.expected_persisted_version


def test_start_normalization_invalid_transition_propagates_and_save_never_called() -> None:
    identity = _identity()
    run = _authorized_run(identity)  # AUTHORIZED, not ACQUIRING
    loaded = LoadedAggregate(aggregate=run, persisted_version=AggregateVersion(1))
    repository = _RecordingRunRepository(loaded, _save_result())
    handler = StartRunNormalizationHandler(run_repository=repository)
    command = StartRunNormalizationCommand(
        identity=identity,
        expected_persisted_version=AggregateVersion(1),
        actor="operator",
        occurred_at=_OCCURRED_AT,
    )

    with pytest.raises(ValueError, match="cannot transition from"):
        handler.handle(command)

    assert repository.save_calls == []


def test_start_normalization_propagates_optimistic_concurrency_conflict() -> None:
    identity = _identity()
    run = _acquiring_run(identity)
    loaded = LoadedAggregate(aggregate=run, persisted_version=AggregateVersion(2))
    exc = _occ_conflict(identity)
    repository = _FailingSaveRunRepository(loaded, exc)
    handler = StartRunNormalizationHandler(run_repository=repository)  # type: ignore[arg-type]
    command = StartRunNormalizationCommand(
        identity=identity,
        expected_persisted_version=AggregateVersion(1),
        actor="operator",
        occurred_at=_OCCURRED_AT,
    )

    with pytest.raises(OptimisticConcurrencyConflict) as excinfo:
        handler.handle(command)

    assert excinfo.value is exc


# ---------------------------------------------------------------------------
# start_run_validation
# ---------------------------------------------------------------------------


def test_start_validation_transitions_normalizing_run_and_saves_with_command_version() -> None:
    identity = _identity()
    run = _normalizing_run(identity)
    loaded = LoadedAggregate(aggregate=run, persisted_version=AggregateVersion(3))
    repository = _RecordingRunRepository(loaded, _save_result(4))
    handler = StartRunValidationHandler(run_repository=repository)
    command = StartRunValidationCommand(
        identity=identity,
        expected_persisted_version=AggregateVersion(3),
        actor="operator",
        occurred_at=_OCCURRED_AT,
    )

    CommandEntryPoint(handler)(command)

    assert run.state is RunLifecycleState.VALIDATING
    _, saved_version = repository.save_calls[0]
    assert saved_version is command.expected_persisted_version


def test_start_validation_invalid_transition_propagates_and_save_never_called() -> None:
    identity = _identity()
    run = _acquiring_run(identity)  # ACQUIRING, not NORMALIZING
    loaded = LoadedAggregate(aggregate=run, persisted_version=AggregateVersion(2))
    repository = _RecordingRunRepository(loaded, _save_result())
    handler = StartRunValidationHandler(run_repository=repository)
    command = StartRunValidationCommand(
        identity=identity,
        expected_persisted_version=AggregateVersion(2),
        actor="operator",
        occurred_at=_OCCURRED_AT,
    )

    with pytest.raises(ValueError, match="cannot transition from"):
        handler.handle(command)

    assert repository.save_calls == []


def test_start_validation_propagates_optimistic_concurrency_conflict() -> None:
    identity = _identity()
    run = _normalizing_run(identity)
    loaded = LoadedAggregate(aggregate=run, persisted_version=AggregateVersion(3))
    exc = _occ_conflict(identity)
    repository = _FailingSaveRunRepository(loaded, exc)
    handler = StartRunValidationHandler(run_repository=repository)  # type: ignore[arg-type]
    command = StartRunValidationCommand(
        identity=identity,
        expected_persisted_version=AggregateVersion(2),
        actor="operator",
        occurred_at=_OCCURRED_AT,
    )

    with pytest.raises(OptimisticConcurrencyConflict) as excinfo:
        handler.handle(command)

    assert excinfo.value is exc


# ---------------------------------------------------------------------------
# complete_run_execution
# ---------------------------------------------------------------------------


def test_complete_execution_transitions_validating_run_and_saves_with_command_version() -> None:
    identity = _identity()
    run = _validating_run(identity)
    loaded = LoadedAggregate(aggregate=run, persisted_version=AggregateVersion(4))
    repository = _RecordingRunRepository(loaded, _save_result(5))
    handler = CompleteRunExecutionHandler(run_repository=repository)
    command = CompleteRunExecutionCommand(
        identity=identity,
        expected_persisted_version=AggregateVersion(4),
        actor="operator",
        occurred_at=_OCCURRED_AT,
    )

    CommandEntryPoint(handler)(command)

    assert run.state is RunLifecycleState.EXECUTION_COMPLETED
    _, saved_version = repository.save_calls[0]
    assert saved_version is command.expected_persisted_version


def test_complete_execution_invalid_transition_propagates_and_save_never_called() -> None:
    identity = _identity()
    run = _normalizing_run(identity)  # NORMALIZING, not VALIDATING
    loaded = LoadedAggregate(aggregate=run, persisted_version=AggregateVersion(3))
    repository = _RecordingRunRepository(loaded, _save_result())
    handler = CompleteRunExecutionHandler(run_repository=repository)
    command = CompleteRunExecutionCommand(
        identity=identity,
        expected_persisted_version=AggregateVersion(3),
        actor="operator",
        occurred_at=_OCCURRED_AT,
    )

    with pytest.raises(ValueError, match="cannot transition from"):
        handler.handle(command)

    assert repository.save_calls == []


def test_complete_execution_propagates_optimistic_concurrency_conflict() -> None:
    identity = _identity()
    run = _validating_run(identity)
    loaded = LoadedAggregate(aggregate=run, persisted_version=AggregateVersion(4))
    exc = _occ_conflict(identity)
    repository = _FailingSaveRunRepository(loaded, exc)
    handler = CompleteRunExecutionHandler(run_repository=repository)  # type: ignore[arg-type]
    command = CompleteRunExecutionCommand(
        identity=identity,
        expected_persisted_version=AggregateVersion(3),
        actor="operator",
        occurred_at=_OCCURRED_AT,
    )

    with pytest.raises(OptimisticConcurrencyConflict) as excinfo:
        handler.handle(command)

    assert excinfo.value is exc


# ---------------------------------------------------------------------------
# append_run_manifest
# ---------------------------------------------------------------------------


def test_append_manifest_appends_to_acquiring_run_and_saves_with_command_version() -> None:
    identity = _identity()
    run = _acquiring_run(identity)
    loaded = LoadedAggregate(aggregate=run, persisted_version=AggregateVersion(2))
    repository = _RecordingRunRepository(loaded, _save_result(3))
    handler = AppendRunManifestHandler(run_repository=repository)
    command = AppendRunManifestCommand(
        identity=identity,
        expected_persisted_version=AggregateVersion(2),
        recorded_at=_OCCURRED_AT,
        source="s3://bucket/acquired-data.csv",
        acquisition_method="bulk-download",
    )

    CommandEntryPoint(handler)(command)

    assert len(run.manifests) == 1
    manifest = run.manifests[0]
    assert manifest.source == "s3://bucket/acquired-data.csv"
    assert manifest.acquisition_method == "bulk-download"
    assert manifest.run_id == identity.governance_id
    _, saved_version = repository.save_calls[0]
    assert saved_version is command.expected_persisted_version


def test_append_manifest_preserves_prior_manifests() -> None:
    identity = _identity()
    run = _acquiring_run(identity)
    run.append_manifest(
        DatasetManifest(
            run_id=identity.governance_id, recorded_at=_OCCURRED_AT, source="first-source"
        )
    )
    loaded = LoadedAggregate(aggregate=run, persisted_version=AggregateVersion(3))
    repository = _RecordingRunRepository(loaded, _save_result(4))
    handler = AppendRunManifestHandler(run_repository=repository)
    command = AppendRunManifestCommand(
        identity=identity,
        expected_persisted_version=AggregateVersion(3),
        recorded_at=_OCCURRED_AT,
        source="second-source",
    )

    handler.handle(command)

    assert [m.source for m in run.manifests] == ["first-source", "second-source"]


def test_append_manifest_invalid_state_propagates_and_save_never_called() -> None:
    identity = _identity()
    run = _run(identity)
    run.authorize(actor="seed", occurred_at=_OCCURRED_AT)
    run.start_acquisition(actor="seed", occurred_at=_OCCURRED_AT)
    run.start_normalization(actor="seed", occurred_at=_OCCURRED_AT)
    run.start_validation(actor="seed", occurred_at=_OCCURRED_AT)
    run.complete_execution(actor="seed", occurred_at=_OCCURRED_AT)  # EXECUTION_COMPLETED
    loaded = LoadedAggregate(aggregate=run, persisted_version=AggregateVersion(5))
    repository = _RecordingRunRepository(loaded, _save_result())
    handler = AppendRunManifestHandler(run_repository=repository)
    command = AppendRunManifestCommand(
        identity=identity,
        expected_persisted_version=AggregateVersion(5),
        recorded_at=_OCCURRED_AT,
        source="should-never-persist",
    )

    with pytest.raises(ValueError, match="may not be appended"):
        handler.handle(command)

    assert repository.save_calls == []


def test_append_manifest_propagates_optimistic_concurrency_conflict() -> None:
    identity = _identity()
    run = _acquiring_run(identity)
    loaded = LoadedAggregate(aggregate=run, persisted_version=AggregateVersion(2))
    exc = _occ_conflict(identity)
    repository = _FailingSaveRunRepository(loaded, exc)
    handler = AppendRunManifestHandler(run_repository=repository)  # type: ignore[arg-type]
    command = AppendRunManifestCommand(
        identity=identity,
        expected_persisted_version=AggregateVersion(1),
        recorded_at=_OCCURRED_AT,
        source="should-conflict",
    )

    with pytest.raises(OptimisticConcurrencyConflict) as excinfo:
        handler.handle(command)

    assert excinfo.value is exc


def test_append_manifest_propagates_aggregate_not_found() -> None:
    identity = _identity()
    exc = AggregateNotFound(aggregate_kind="Run", identity=identity)
    repository = _FailingGetRunRepository(exc)
    handler = AppendRunManifestHandler(run_repository=repository)  # type: ignore[arg-type]
    command = AppendRunManifestCommand(
        identity=identity,
        expected_persisted_version=AggregateVersion.initial(),
        recorded_at=_OCCURRED_AT,
        source="should-never-run",
    )

    with pytest.raises(AggregateNotFound) as excinfo:
        handler.handle(command)

    assert excinfo.value is exc
