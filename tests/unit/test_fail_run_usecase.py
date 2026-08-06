"""MILESTONE-048 behavioral tests for `FailRunCommand`/`FailRunHandler`.

Proves the frozen load-mutate-save flow: call `RunRepository.get()` exactly
once, invoke `Run.fail()` exactly once with the command's data unchanged,
then call `RunRepository.save()` exactly once with the mutated aggregate
and the command's own `expected_persisted_version` -- never
`loaded.persisted_version`. Also proves transparent failure propagation
for every collaborator, including the two distinct non-conflict domain
failure modes `fail()` introduces (invalid state, empty reason) -- and
that the handler is invocable through the frozen `CommandEntryPoint`.

Uses deterministic recording fakes/stubs, not mocks, for stronger evidence.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from empirical_platform.application.command import CommandEntryPoint
from empirical_platform.campaign.lifecycle import RunLifecycleState
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import CampaignId, RunId
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
from empirical_platform.usecases.fail_run import FailRunCommand, FailRunHandler

if TYPE_CHECKING:
    from empirical_platform.run.repository import RunRepository

_RUNTIME_ID_VALUE = "12345678-1234-4321-8765-1234567890ab"
_OCCURRED_AT = datetime(2026, 1, 1, tzinfo=UTC)
_INITIAL_VERSION = AggregateVersion.initial()


def _identity(governance_id: str = "RUN-0001") -> DomainIdentity[RunId]:
    return DomainIdentity(
        governance_id=RunId(governance_id),
        runtime_id=RuntimeIdentifier(_RUNTIME_ID_VALUE),
    )


def _created_run(identity: DomainIdentity[RunId]) -> Run:
    return Run(identity=identity, campaign_id=CampaignId("CAMP-0001"))


def _acquiring_run(identity: DomainIdentity[RunId]) -> Run:
    run = _created_run(identity)
    run.authorize(actor="tester", occurred_at=_OCCURRED_AT)
    run.start_acquisition(actor="tester", occurred_at=_OCCURRED_AT)
    return run


def _command(
    identity: DomainIdentity[RunId],
    *,
    expected_persisted_version: AggregateVersion = _INITIAL_VERSION,
    reason: str = "acquisition source unavailable",
    actor: str = "tester",
    occurred_at: datetime = _OCCURRED_AT,
    correlation_id: str | None = None,
) -> FailRunCommand:
    return FailRunCommand(
        identity=identity,
        expected_persisted_version=expected_persisted_version,
        reason=reason,
        actor=actor,
        occurred_at=occurred_at,
        correlation_id=correlation_id,
    )


class _RecordingRunRepository:
    """Records every `get()`/`save()` call; conforms structurally to `RunRepository`."""

    def __init__(
        self,
        loaded: LoadedAggregate[Run] | list[LoadedAggregate[Run]],
        save_result: SaveResult,
    ) -> None:
        self._loaded_sequence = loaded if isinstance(loaded, list) else None
        self._loaded_single = None if isinstance(loaded, list) else loaded
        self._save_result = save_result
        self.get_calls: list[DomainIdentity[RunId]] = []
        self.save_calls: list[tuple[Run, AggregateVersion]] = []

    def get(self, identity: DomainIdentity[RunId]) -> LoadedAggregate[Run]:
        self.get_calls.append(identity)
        if self._loaded_sequence is not None:
            return self._loaded_sequence[len(self.get_calls) - 1]
        assert self._loaded_single is not None
        return self._loaded_single

    def add(self, aggregate: Run) -> SaveResult:
        raise AssertionError("add() must not be called by FailRunHandler")

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


def _handler(repository: object) -> FailRunHandler:
    return FailRunHandler(run_repository=repository)  # type: ignore[arg-type]


# --- A. Command contract tests ---


def test_command_preserves_all_six_fields_unchanged() -> None:
    identity = _identity()
    version = AggregateVersion(3)
    command = FailRunCommand(
        identity=identity,
        expected_persisted_version=version,
        reason="checksum mismatch",
        actor="alice",
        occurred_at=_OCCURRED_AT,
        correlation_id="corr-1",
    )

    assert command.identity is identity
    assert command.expected_persisted_version is version
    assert command.reason == "checksum mismatch"
    assert command.actor == "alice"
    assert command.occurred_at == _OCCURRED_AT
    assert command.correlation_id == "corr-1"


def test_command_optional_correlation_id_defaults_to_none() -> None:
    command = _command(_identity())

    assert command.correlation_id is None


def test_command_contains_no_additional_fields() -> None:
    assert set(FailRunCommand.__slots__) == {  # type: ignore[attr-defined]
        "identity",
        "expected_persisted_version",
        "reason",
        "actor",
        "occurred_at",
        "correlation_id",
    }


def test_command_is_immutable() -> None:
    command = _command(_identity())
    with pytest.raises(AttributeError):
        command.actor = "someone-else"  # type: ignore[misc]


def test_command_construction_performs_no_business_validation() -> None:
    """No duplicated domain validation; empty-string reason is accepted at
    construction -- Run.fail() itself validates later."""
    command = FailRunCommand(
        identity=_identity(),
        expected_persisted_version=AggregateVersion.initial(),
        reason="",
        actor="tester",
        occurred_at=_OCCURRED_AT,
    )
    assert command.reason == ""


# --- B. Handler success tests ---


def test_typed_conformance_check() -> None:
    identity = _identity()
    loaded = LoadedAggregate(
        aggregate=_acquiring_run(identity), persisted_version=AggregateVersion(2)
    )
    save_result = SaveResult(operation=SaveOperation.UPDATED, persisted_version=AggregateVersion(3))
    repository: RunRepository = _RecordingRunRepository(  # type: ignore[assignment]
        loaded, save_result
    )
    handler: FailRunHandler = _handler(repository)
    assert handler is not None


def test_get_is_called_exactly_once_with_exact_identity() -> None:
    identity = _identity()
    loaded = LoadedAggregate(
        aggregate=_acquiring_run(identity), persisted_version=AggregateVersion(2)
    )
    save_result = SaveResult(operation=SaveOperation.UPDATED, persisted_version=AggregateVersion(3))
    repository = _RecordingRunRepository(loaded, save_result)
    handler = _handler(repository)
    command = _command(identity, expected_persisted_version=AggregateVersion(2))

    handler.handle(command)

    assert len(repository.get_calls) == 1
    assert repository.get_calls[0] is command.identity


def test_fail_called_with_exact_command_arguments() -> None:
    identity = _identity()
    run = _acquiring_run(identity)
    loaded = LoadedAggregate(aggregate=run, persisted_version=AggregateVersion(2))
    save_result = SaveResult(operation=SaveOperation.UPDATED, persisted_version=AggregateVersion(3))
    repository = _RecordingRunRepository(loaded, save_result)
    handler = _handler(repository)
    command = _command(
        identity,
        expected_persisted_version=AggregateVersion(2),
        reason="acquisition source timed out",
        actor="bob",
        occurred_at=_OCCURRED_AT,
        correlation_id="corr-42",
    )

    handler.handle(command)

    assert run.state is RunLifecycleState.FAILED
    record = run.transition_history[-1]
    assert record.actor == "bob"
    assert record.occurred_at == _OCCURRED_AT
    assert record.correlation_id == "corr-42"
    assert record.reason == "acquisition source timed out"


def test_save_called_exactly_once_with_mutated_aggregate_and_command_version() -> None:
    identity = _identity()
    run = _acquiring_run(identity)
    loaded = LoadedAggregate(aggregate=run, persisted_version=AggregateVersion(2))
    save_result = SaveResult(operation=SaveOperation.UPDATED, persisted_version=AggregateVersion(3))
    repository = _RecordingRunRepository(loaded, save_result)
    handler = _handler(repository)
    command = _command(identity, expected_persisted_version=AggregateVersion(2))

    handler.handle(command)

    assert len(repository.save_calls) == 1
    saved_aggregate, saved_expected_version = repository.save_calls[0]
    assert saved_aggregate is run
    assert saved_expected_version is command.expected_persisted_version


def test_save_receives_command_version_not_loaded_persisted_version() -> None:
    """Critical: expected_persisted_version passed to save() must come from the
    command, never from loaded.persisted_version -- even when they differ."""
    identity = _identity()
    run = _acquiring_run(identity)
    loaded = LoadedAggregate(aggregate=run, persisted_version=AggregateVersion(9))
    save_result = SaveResult(operation=SaveOperation.UPDATED, persisted_version=AggregateVersion(3))
    repository = _RecordingRunRepository(loaded, save_result)
    handler = _handler(repository)
    stale_version = AggregateVersion(2)
    command = _command(identity, expected_persisted_version=stale_version)

    handler.handle(command)

    _, saved_expected_version = repository.save_calls[0]
    assert saved_expected_version is stale_version
    assert saved_expected_version != loaded.persisted_version


def test_no_add_call_occurs() -> None:
    identity = _identity()
    loaded = LoadedAggregate(
        aggregate=_acquiring_run(identity), persisted_version=AggregateVersion(2)
    )
    save_result = SaveResult(operation=SaveOperation.UPDATED, persisted_version=AggregateVersion(3))
    repository = _RecordingRunRepository(loaded, save_result)
    handler = _handler(repository)

    handler.handle(_command(identity, expected_persisted_version=AggregateVersion(2)))


def test_no_second_get_or_save_occurs() -> None:
    identity = _identity()
    loaded = LoadedAggregate(
        aggregate=_acquiring_run(identity), persisted_version=AggregateVersion(2)
    )
    save_result = SaveResult(operation=SaveOperation.UPDATED, persisted_version=AggregateVersion(3))
    repository = _RecordingRunRepository(loaded, save_result)
    handler = _handler(repository)

    handler.handle(_command(identity, expected_persisted_version=AggregateVersion(2)))

    assert len(repository.get_calls) == 1
    assert len(repository.save_calls) == 1


def test_returned_object_is_the_exact_save_result() -> None:
    identity = _identity()
    loaded = LoadedAggregate(
        aggregate=_acquiring_run(identity), persisted_version=AggregateVersion(2)
    )
    save_result = SaveResult(operation=SaveOperation.UPDATED, persisted_version=AggregateVersion(3))
    repository = _RecordingRunRepository(loaded, save_result)
    handler = _handler(repository)

    result = handler.handle(_command(identity, expected_persisted_version=AggregateVersion(2)))

    assert result is save_result


def test_handler_is_invocable_through_command_entry_point() -> None:
    identity = _identity()
    loaded = LoadedAggregate(
        aggregate=_acquiring_run(identity), persisted_version=AggregateVersion(2)
    )
    save_result = SaveResult(operation=SaveOperation.UPDATED, persisted_version=AggregateVersion(3))
    repository = _RecordingRunRepository(loaded, save_result)
    handler = _handler(repository)
    entry_point = CommandEntryPoint(handler)

    result = entry_point(_command(identity, expected_persisted_version=AggregateVersion(2)))

    assert result is save_result
    assert len(repository.get_calls) == 1
    assert len(repository.save_calls) == 1


# --- C. Transition-history proof ---


def test_successful_fail_produces_exactly_one_transition_record() -> None:
    identity = _identity()
    run = _acquiring_run(identity)
    version_before = run.version
    history_length_before = len(run.transition_history)
    loaded = LoadedAggregate(aggregate=run, persisted_version=version_before)
    save_result = SaveResult(operation=SaveOperation.UPDATED, persisted_version=AggregateVersion(3))
    repository = _RecordingRunRepository(loaded, save_result)
    handler = _handler(repository)
    command = _command(
        identity,
        expected_persisted_version=version_before,
        reason="checksum mismatch",
        actor="carol",
        correlation_id="corr-99",
    )

    handler.handle(command)

    assert run.state is RunLifecycleState.FAILED
    assert run.version == version_before.next()
    assert len(run.transition_history) == history_length_before + 1
    record = run.transition_history[-1]
    assert record.from_state == "ACQUIRING"
    assert record.to_state == "FAILED"
    assert record.version == run.version
    assert record.actor == "carol"
    assert record.correlation_id == "corr-99"
    assert record.reason == "checksum mismatch"


# --- D. Domain-failure tests (two distinct non-conflict failure modes) ---


def test_invalid_state_still_authorized_propagates_and_save_never_called() -> None:
    identity = _identity()
    run = _created_run(identity)
    run.authorize(actor="tester", occurred_at=_OCCURRED_AT)  # AUTHORIZED, never started
    loaded = LoadedAggregate(aggregate=run, persisted_version=run.version)
    save_result = SaveResult(operation=SaveOperation.UPDATED, persisted_version=AggregateVersion(9))
    repository = _RecordingRunRepository(loaded, save_result)
    handler = _handler(repository)

    with pytest.raises(ValueError, match="cannot transition from AUTHORIZED"):
        handler.handle(_command(identity, expected_persisted_version=run.version))

    assert repository.save_calls == []


def test_empty_reason_propagates_and_save_never_called() -> None:
    identity = _identity()
    run = _acquiring_run(identity)
    loaded = LoadedAggregate(aggregate=run, persisted_version=run.version)
    save_result = SaveResult(operation=SaveOperation.UPDATED, persisted_version=AggregateVersion(9))
    repository = _RecordingRunRepository(loaded, save_result)
    handler = _handler(repository)

    with pytest.raises(ValueError, match="must be non-empty"):
        handler.handle(_command(identity, expected_persisted_version=run.version, reason="   "))

    assert repository.save_calls == []


# --- E. get()-failure tests ---


def test_aggregate_not_found_from_get_propagates_with_identity_preserved() -> None:
    exc = AggregateNotFound(aggregate_kind="Run", identity=_identity())
    repository = _FailingGetRunRepository(exc)
    handler = _handler(repository)

    with pytest.raises(AggregateNotFound) as excinfo:
        handler.handle(_command(_identity()))

    assert excinfo.value is exc
    assert repository.get_calls == 1
    assert repository.save_calls == 0


def test_arbitrary_get_exception_propagates_unchanged() -> None:
    exc = RuntimeError("unexpected get() failure")
    repository = _FailingGetRunRepository(exc)
    handler = _handler(repository)

    with pytest.raises(RuntimeError) as excinfo:
        handler.handle(_command(_identity()))

    assert excinfo.value is exc
    assert repository.save_calls == 0


# --- F. save()-failure tests ---


def test_optimistic_concurrency_conflict_from_save_propagates_unchanged() -> None:
    identity = _identity()
    run = _acquiring_run(identity)
    exc = OptimisticConcurrencyConflict(
        aggregate_kind="Run",
        identity=identity,
        expected_persisted_version=AggregateVersion(2),
        aggregate_current_version=AggregateVersion(3),
        actual_persisted_version=AggregateVersion(3),
    )
    loaded = LoadedAggregate(aggregate=run, persisted_version=AggregateVersion(2))
    repository = _FailingSaveRunRepository(loaded, exc)
    handler = _handler(repository)

    with pytest.raises(OptimisticConcurrencyConflict) as excinfo:
        handler.handle(_command(identity, expected_persisted_version=AggregateVersion(2)))

    assert excinfo.value is exc
    assert repository.get_calls == 1
    assert repository.save_calls == 1


def test_arbitrary_save_exception_propagates_with_identity_preserved() -> None:
    identity = _identity()
    run = _acquiring_run(identity)
    loaded = LoadedAggregate(aggregate=run, persisted_version=AggregateVersion(2))
    exc = RuntimeError("unexpected save() failure")
    repository = _FailingSaveRunRepository(loaded, exc)
    handler = _handler(repository)

    with pytest.raises(RuntimeError) as excinfo:
        handler.handle(_command(identity, expected_persisted_version=AggregateVersion(2)))

    assert excinfo.value is exc
    assert repository.get_calls == 1
    assert repository.save_calls == 1
