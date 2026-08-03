"""MILESTONE-036 behavioral tests for `CreateEvidencePackageHandler`.

Proves the frozen persistence flow (design Section 9): translate command
data into frozen value types, obtain `runtime_id` from the injected
`RuntimeIdentifierGenerator`, construct the `EvidencePackage` aggregate,
call `EvidencePackageRepository.add()` exactly once, and return the
resulting `DomainIdentity[EvidencePackageId]`. Also proves transparent
failure propagation for every collaborator (frozen M029 invariant), that
the handler never depends on `RunRepository` (design Section 5), and that
the handler is invocable through the frozen `CommandEntryPoint`.

Uses deterministic recording fakes/stubs, not mocks, for stronger evidence.
"""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING

import pytest

from empirical_platform.application.command import CommandEntryPoint
from empirical_platform.evidence.package import EvidencePackage
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import EvidencePackageId, RunId
from empirical_platform.shared.contracts.repository import (
    AggregateAlreadyExists,
    SaveOperation,
    SaveResult,
)
from empirical_platform.shared.domain.versioning import AggregateVersion
from empirical_platform.shared.identifiers import DeterministicRuntimeIdentifierGenerator
from empirical_platform.usecases.create_evidence_package import (
    CreateEvidencePackageCommand,
    CreateEvidencePackageHandler,
)

if TYPE_CHECKING:
    from empirical_platform.evidence.repository import EvidencePackageRepository
    from empirical_platform.shared.contracts.command import CommandHandler

_RUNTIME_ID_VALUE = "12345678-1234-4321-8765-1234567890ab"


class _RecordingEvidencePackageRepository:
    """Records every `add()` call; conforms structurally to `EvidencePackageRepository`."""

    def __init__(self) -> None:
        self.add_calls: list[EvidencePackage] = []

    def get(self, identity: object) -> object:
        raise AssertionError("get() must not be called by CreateEvidencePackageHandler")

    def add(self, aggregate: EvidencePackage) -> SaveResult:
        self.add_calls.append(aggregate)
        return SaveResult(operation=SaveOperation.CREATED, persisted_version=aggregate.version)

    def save(
        self, aggregate: EvidencePackage, *, expected_persisted_version: AggregateVersion
    ) -> object:
        raise AssertionError("save() must not be called by CreateEvidencePackageHandler")


class _FailingEvidencePackageRepository:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc
        self.add_calls = 0

    def get(self, identity: object) -> object:
        raise AssertionError("get() must not be called")

    def add(self, aggregate: EvidencePackage) -> SaveResult:
        self.add_calls += 1
        raise self._exc

    def save(
        self, aggregate: EvidencePackage, *, expected_persisted_version: AggregateVersion
    ) -> object:
        raise AssertionError("save() must not be called")


class _FailingRuntimeIdentifierGenerator:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc
        self.generate_calls = 0

    def generate(self) -> object:
        self.generate_calls += 1
        raise self._exc


def _handler(repository: object, generator: object | None = None) -> CreateEvidencePackageHandler:
    return CreateEvidencePackageHandler(
        evidence_package_repository=repository,  # type: ignore[arg-type]
        runtime_identifier_generator=generator  # type: ignore[arg-type]
        or DeterministicRuntimeIdentifierGenerator([_RUNTIME_ID_VALUE]),
    )


def test_typed_conformance_check() -> None:
    """Mypy-checked proof that CreateEvidencePackageHandler conforms to
    CommandHandler[CreateEvidencePackageCommand, DomainIdentity[EvidencePackageId]]
    without inheritance (structural typing only)."""
    repository: EvidencePackageRepository = (  # type: ignore[assignment]
        _RecordingEvidencePackageRepository()
    )
    handler: CommandHandler[CreateEvidencePackageCommand, DomainIdentity[EvidencePackageId]] = (
        _handler(repository)
    )
    assert handler is not None


def test_handler_constructor_accepts_no_run_repository_parameter() -> None:
    """Structural proof of the frozen Run-existence decision (design Section
    5): the constructor carries exactly two dependencies, neither named
    `run_repository`, confirming no RunRepository lookup is possible."""
    signature = inspect.signature(CreateEvidencePackageHandler.__init__)
    parameters = list(signature.parameters)
    assert parameters == ["self", "evidence_package_repository", "runtime_identifier_generator"]


def test_handler_returns_domain_identity_with_caller_supplied_governance_id() -> None:
    repository = _RecordingEvidencePackageRepository()
    handler = _handler(repository)
    command = CreateEvidencePackageCommand(
        evidence_package_governance_id="EVID-0001", run_governance_id="RUN-0001"
    )

    result = handler.handle(command)

    assert isinstance(result, DomainIdentity)
    assert result.governance_id == EvidencePackageId("EVID-0001")


def test_runtime_id_is_obtained_from_injected_generator() -> None:
    repository = _RecordingEvidencePackageRepository()
    generator = DeterministicRuntimeIdentifierGenerator([_RUNTIME_ID_VALUE])
    handler = _handler(repository, generator)
    command = CreateEvidencePackageCommand(
        evidence_package_governance_id="EVID-0001", run_governance_id="RUN-0001"
    )

    result = handler.handle(command)

    assert str(result.runtime_id) == _RUNTIME_ID_VALUE


def test_evidence_package_repository_add_is_called_exactly_once() -> None:
    repository = _RecordingEvidencePackageRepository()
    handler = _handler(repository)
    command = CreateEvidencePackageCommand(
        evidence_package_governance_id="EVID-0001", run_governance_id="RUN-0001"
    )

    handler.handle(command)

    assert len(repository.add_calls) == 1


def test_aggregate_supplied_to_add_has_expected_identity_and_run_id() -> None:
    repository = _RecordingEvidencePackageRepository()
    generator = DeterministicRuntimeIdentifierGenerator([_RUNTIME_ID_VALUE])
    handler = _handler(repository, generator)
    command = CreateEvidencePackageCommand(
        evidence_package_governance_id="EVID-0042", run_governance_id="RUN-0042"
    )

    handler.handle(command)

    persisted = repository.add_calls[0]
    assert persisted.identity.governance_id == EvidencePackageId("EVID-0042")
    assert str(persisted.identity.runtime_id) == _RUNTIME_ID_VALUE
    assert persisted.run_id == RunId("RUN-0042")


def test_handler_returns_the_persisted_aggregates_identity() -> None:
    repository = _RecordingEvidencePackageRepository()
    handler = _handler(repository)
    command = CreateEvidencePackageCommand(
        evidence_package_governance_id="EVID-0001", run_governance_id="RUN-0001"
    )

    result = handler.handle(command)

    assert result is repository.add_calls[0].identity


def test_no_repository_pre_read_occurs() -> None:
    """get() raises AssertionError in the fake if called; handler must never call it."""
    repository = _RecordingEvidencePackageRepository()
    handler = _handler(repository)
    command = CreateEvidencePackageCommand(
        evidence_package_governance_id="EVID-0001", run_governance_id="RUN-0001"
    )

    handler.handle(command)  # would raise AssertionError if get() were called


def test_malformed_evidence_package_governance_id_propagates_unchanged() -> None:
    """EvidencePackageId's own frozen format validation (M020) fires;
    handler adds no validation of its own and does not catch this failure.
    The generator must not be called and add() must not be called."""
    repository = _RecordingEvidencePackageRepository()
    generator = DeterministicRuntimeIdentifierGenerator([_RUNTIME_ID_VALUE])
    handler = _handler(repository, generator)
    command = CreateEvidencePackageCommand(
        evidence_package_governance_id="not-a-valid-id", run_governance_id="RUN-0001"
    )

    with pytest.raises(ValueError, match="Identifier must match"):
        handler.handle(command)

    assert repository.add_calls == []


def test_malformed_run_governance_id_propagates_unchanged() -> None:
    """RunId's own frozen format validation (M020) fires after the
    EvidencePackageId and runtime_id have already been constructed, but no
    add() call is reached."""
    repository = _RecordingEvidencePackageRepository()
    handler = _handler(repository)
    command = CreateEvidencePackageCommand(
        evidence_package_governance_id="EVID-0001", run_governance_id="not-a-valid-id"
    )

    with pytest.raises(ValueError, match="Identifier must match"):
        handler.handle(command)

    assert repository.add_calls == []


def test_repository_add_failure_propagates_with_identity_preserved() -> None:
    exc = AggregateAlreadyExists(aggregate_kind="EvidencePackage", identity=object())
    repository = _FailingEvidencePackageRepository(exc)
    handler = _handler(repository)
    command = CreateEvidencePackageCommand(
        evidence_package_governance_id="EVID-0001", run_governance_id="RUN-0001"
    )

    with pytest.raises(AggregateAlreadyExists) as excinfo:
        handler.handle(command)

    assert excinfo.value is exc
    assert repository.add_calls == 1


def test_runtime_identifier_generator_failure_propagates_unchanged() -> None:
    exc = RuntimeError("identifier generation failed")
    generator = _FailingRuntimeIdentifierGenerator(exc)
    repository = _RecordingEvidencePackageRepository()
    handler = _handler(repository, generator)
    command = CreateEvidencePackageCommand(
        evidence_package_governance_id="EVID-0001", run_governance_id="RUN-0001"
    )

    with pytest.raises(RuntimeError) as excinfo:
        handler.handle(command)

    assert excinfo.value is exc
    assert generator.generate_calls == 1
    assert repository.add_calls == []


def test_handler_is_invocable_through_command_entry_point() -> None:
    repository = _RecordingEvidencePackageRepository()
    handler = _handler(repository)
    entry_point = CommandEntryPoint(handler)
    command = CreateEvidencePackageCommand(
        evidence_package_governance_id="EVID-0001", run_governance_id="RUN-0001"
    )

    result = entry_point(command)

    assert isinstance(result, DomainIdentity)
    assert len(repository.add_calls) == 1


def test_handler_bound_at_construction_not_per_call() -> None:
    repository = _RecordingEvidencePackageRepository()
    generator = DeterministicRuntimeIdentifierGenerator(
        [_RUNTIME_ID_VALUE, "87654321-4321-4321-8765-0987654321ba"]
    )
    handler = _handler(repository, generator)
    entry_point = CommandEntryPoint(handler)

    entry_point(
        CreateEvidencePackageCommand(
            evidence_package_governance_id="EVID-0001", run_governance_id="RUN-0001"
        )
    )
    entry_point(
        CreateEvidencePackageCommand(
            evidence_package_governance_id="EVID-0002", run_governance_id="RUN-0001"
        )
    )

    assert len(repository.add_calls) == 2


def test_command_is_a_plain_unvalidated_data_carrier() -> None:
    """No CreateEvidencePackageCommand-level validation exists; malformed
    data is accepted at construction and rejected only by the frozen value
    objects the handler later constructs."""
    command = CreateEvidencePackageCommand(evidence_package_governance_id="", run_governance_id="")
    assert command.evidence_package_governance_id == ""
    assert command.run_governance_id == ""
