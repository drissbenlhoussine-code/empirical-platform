"""MILESTONE-033 behavioral tests for `CreateRunHandler`.

Proves the frozen persistence flow (design freeze Section 17): translate
command data into frozen value types, obtain `runtime_id` from the injected
`RuntimeIdentifierGenerator`, construct the `Run` aggregate, call
`RunRepository.add()` exactly once, and return the resulting
`DomainIdentity[RunId]`. Also proves transparent failure propagation for
every collaborator (frozen M029 invariant), that the handler never depends
on `CampaignRepository` (design freeze Section 11), and that the handler is
invocable through the frozen `CommandEntryPoint`.

Uses deterministic recording fakes/stubs, not mocks, for stronger evidence.
"""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING

import pytest

from empirical_platform.application.command import CommandEntryPoint
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import CampaignId, RunId
from empirical_platform.run.aggregate import Run
from empirical_platform.shared.contracts.repository import (
    AggregateAlreadyExists,
    SaveOperation,
    SaveResult,
)
from empirical_platform.shared.domain.versioning import AggregateVersion
from empirical_platform.shared.identifiers import DeterministicRuntimeIdentifierGenerator
from empirical_platform.usecases.create_run import CreateRunCommand, CreateRunHandler

if TYPE_CHECKING:
    from empirical_platform.run.repository import RunRepository
    from empirical_platform.shared.contracts.command import CommandHandler

_RUNTIME_ID_VALUE = "12345678-1234-4321-8765-1234567890ab"


class _RecordingRunRepository:
    """Records every `add()` call; conforms structurally to `RunRepository`."""

    def __init__(self) -> None:
        self.add_calls: list[Run] = []

    def get(self, identity: object) -> object:
        raise AssertionError("get() must not be called by CreateRunHandler")

    def add(self, aggregate: Run) -> SaveResult:
        self.add_calls.append(aggregate)
        return SaveResult(operation=SaveOperation.CREATED, persisted_version=aggregate.version)

    def save(self, aggregate: Run, *, expected_persisted_version: AggregateVersion) -> object:
        raise AssertionError("save() must not be called by CreateRunHandler")


class _FailingRunRepository:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc
        self.add_calls = 0

    def get(self, identity: object) -> object:
        raise AssertionError("get() must not be called")

    def add(self, aggregate: Run) -> SaveResult:
        self.add_calls += 1
        raise self._exc

    def save(self, aggregate: Run, *, expected_persisted_version: AggregateVersion) -> object:
        raise AssertionError("save() must not be called")


class _FailingRuntimeIdentifierGenerator:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc
        self.generate_calls = 0

    def generate(self) -> object:
        self.generate_calls += 1
        raise self._exc


def _handler(repository: object, generator: object | None = None) -> CreateRunHandler:
    return CreateRunHandler(
        run_repository=repository,  # type: ignore[arg-type]
        runtime_identifier_generator=generator  # type: ignore[arg-type]
        or DeterministicRuntimeIdentifierGenerator([_RUNTIME_ID_VALUE]),
    )


def test_typed_conformance_check() -> None:
    """Mypy-checked proof that CreateRunHandler conforms to
    CommandHandler[CreateRunCommand, DomainIdentity[RunId]] without
    inheritance (structural typing only)."""
    repository: RunRepository = _RecordingRunRepository()  # type: ignore[assignment]
    handler: CommandHandler[CreateRunCommand, DomainIdentity[RunId]] = _handler(repository)
    assert handler is not None


def test_handler_constructor_accepts_no_campaign_repository_parameter() -> None:
    """Structural proof of the frozen Campaign-existence decision (design
    freeze Section 11): the constructor carries exactly two dependencies,
    neither named `campaign_repository`, confirming no CampaignRepository
    lookup is possible."""
    signature = inspect.signature(CreateRunHandler.__init__)
    parameters = list(signature.parameters)
    assert parameters == ["self", "run_repository", "runtime_identifier_generator"]


def test_handler_returns_domain_identity_with_caller_supplied_run_id() -> None:
    repository = _RecordingRunRepository()
    handler = _handler(repository)
    command = CreateRunCommand(run_governance_id="RUN-0001", campaign_governance_id="CAMP-0001")

    result = handler.handle(command)

    assert isinstance(result, DomainIdentity)
    assert result.governance_id == RunId("RUN-0001")


def test_runtime_id_is_obtained_from_injected_generator() -> None:
    repository = _RecordingRunRepository()
    generator = DeterministicRuntimeIdentifierGenerator([_RUNTIME_ID_VALUE])
    handler = _handler(repository, generator)
    command = CreateRunCommand(run_governance_id="RUN-0001", campaign_governance_id="CAMP-0001")

    result = handler.handle(command)

    assert str(result.runtime_id) == _RUNTIME_ID_VALUE


def test_run_repository_add_is_called_exactly_once() -> None:
    repository = _RecordingRunRepository()
    handler = _handler(repository)
    command = CreateRunCommand(run_governance_id="RUN-0001", campaign_governance_id="CAMP-0001")

    handler.handle(command)

    assert len(repository.add_calls) == 1


def test_aggregate_supplied_to_add_has_expected_identity_and_campaign_id() -> None:
    repository = _RecordingRunRepository()
    generator = DeterministicRuntimeIdentifierGenerator([_RUNTIME_ID_VALUE])
    handler = _handler(repository, generator)
    command = CreateRunCommand(run_governance_id="RUN-0042", campaign_governance_id="CAMP-0042")

    handler.handle(command)

    persisted = repository.add_calls[0]
    assert persisted.identity.governance_id == RunId("RUN-0042")
    assert str(persisted.identity.runtime_id) == _RUNTIME_ID_VALUE
    assert persisted.campaign_id == CampaignId("CAMP-0042")


def test_handler_returns_the_persisted_aggregates_identity() -> None:
    repository = _RecordingRunRepository()
    handler = _handler(repository)
    command = CreateRunCommand(run_governance_id="RUN-0001", campaign_governance_id="CAMP-0001")

    result = handler.handle(command)

    assert result is repository.add_calls[0].identity


def test_no_repository_pre_read_occurs() -> None:
    """get() raises AssertionError in the fake if called; handler must never call it."""
    repository = _RecordingRunRepository()
    handler = _handler(repository)
    command = CreateRunCommand(run_governance_id="RUN-0001", campaign_governance_id="CAMP-0001")

    handler.handle(command)  # would raise AssertionError if get() were called


def test_malformed_run_governance_id_propagates_unchanged() -> None:
    """RunId's own frozen format validation (M020) fires; handler adds no
    validation of its own and does not catch this failure. The generator
    must not be called and add() must not be called."""
    repository = _RecordingRunRepository()
    generator = DeterministicRuntimeIdentifierGenerator([_RUNTIME_ID_VALUE])
    handler = _handler(repository, generator)
    command = CreateRunCommand(
        run_governance_id="not-a-valid-id", campaign_governance_id="CAMP-0001"
    )

    with pytest.raises(ValueError, match="Identifier must match"):
        handler.handle(command)

    assert repository.add_calls == []


def test_malformed_campaign_governance_id_propagates_unchanged() -> None:
    """CampaignId's own frozen format validation (M020) fires after the
    RunId and runtime_id have already been constructed (creation-sequence
    step 5), but no add() call is reached."""
    repository = _RecordingRunRepository()
    handler = _handler(repository)
    command = CreateRunCommand(
        run_governance_id="RUN-0001", campaign_governance_id="not-a-valid-id"
    )

    with pytest.raises(ValueError, match="Identifier must match"):
        handler.handle(command)

    assert repository.add_calls == []


def test_repository_add_failure_propagates_with_identity_preserved() -> None:
    exc = AggregateAlreadyExists(aggregate_kind="Run", identity=object())
    repository = _FailingRunRepository(exc)
    handler = _handler(repository)
    command = CreateRunCommand(run_governance_id="RUN-0001", campaign_governance_id="CAMP-0001")

    with pytest.raises(AggregateAlreadyExists) as excinfo:
        handler.handle(command)

    assert excinfo.value is exc
    assert repository.add_calls == 1


def test_runtime_identifier_generator_failure_propagates_unchanged() -> None:
    exc = RuntimeError("identifier generation failed")
    generator = _FailingRuntimeIdentifierGenerator(exc)
    repository = _RecordingRunRepository()
    handler = _handler(repository, generator)
    command = CreateRunCommand(run_governance_id="RUN-0001", campaign_governance_id="CAMP-0001")

    with pytest.raises(RuntimeError) as excinfo:
        handler.handle(command)

    assert excinfo.value is exc
    assert generator.generate_calls == 1
    assert repository.add_calls == []


def test_handler_is_invocable_through_command_entry_point() -> None:
    repository = _RecordingRunRepository()
    handler = _handler(repository)
    entry_point = CommandEntryPoint(handler)
    command = CreateRunCommand(run_governance_id="RUN-0001", campaign_governance_id="CAMP-0001")

    result = entry_point(command)

    assert isinstance(result, DomainIdentity)
    assert len(repository.add_calls) == 1


def test_handler_bound_at_construction_not_per_call() -> None:
    repository = _RecordingRunRepository()
    generator = DeterministicRuntimeIdentifierGenerator(
        [_RUNTIME_ID_VALUE, "87654321-4321-4321-8765-0987654321ba"]
    )
    handler = _handler(repository, generator)
    entry_point = CommandEntryPoint(handler)

    entry_point(CreateRunCommand(run_governance_id="RUN-0001", campaign_governance_id="CAMP-0001"))
    entry_point(CreateRunCommand(run_governance_id="RUN-0002", campaign_governance_id="CAMP-0001"))

    assert len(repository.add_calls) == 2


def test_command_is_a_plain_unvalidated_data_carrier() -> None:
    """No CreateRunCommand-level validation exists; malformed data is
    accepted at construction and rejected only by the frozen value objects
    the handler later constructs."""
    command = CreateRunCommand(run_governance_id="", campaign_governance_id="")
    assert command.run_governance_id == ""
    assert command.campaign_governance_id == ""
