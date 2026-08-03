"""MILESTONE-039 behavioral tests for
`RecordEvidencePackageCriterionResultCommand`/`RecordEvidencePackageCriterionResultHandler`.

Proves the frozen load-mutate-save flow (design Section 8): call
`EvidencePackageRepository.get()` exactly once, construct exactly one
`CriterionResult` with `evidence_package_id` derived from the loaded
aggregate's own identity (never a separately-supplied command field --
design Section 4), invoke `EvidencePackage.add_criterion_result()` exactly
once, then call `EvidencePackageRepository.save()` exactly once with the
mutated aggregate and the command's own `expected_persisted_version` --
never `loaded.persisted_version`. Also proves transparent failure
propagation for every collaborator (frozen M029 invariant), including
propagation of `OptimisticConcurrencyConflict` via a fake repository
(design Section 20), and that the handler is invocable through the frozen
`CommandEntryPoint`.

Uses deterministic recording fakes/stubs, not mocks, for stronger evidence.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from empirical_platform.application.command import CommandEntryPoint
from empirical_platform.evidence.lifecycle import EvidencePackageLifecycleState
from empirical_platform.evidence.package import EvidencePackage
from empirical_platform.evidence.results import CriterionResult
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import EvidencePackageId, RunId
from empirical_platform.shared.contracts.repository import (
    AggregateNotFound,
    LoadedAggregate,
    OptimisticConcurrencyConflict,
    SaveOperation,
    SaveResult,
)
from empirical_platform.shared.domain.versioning import AggregateVersion
from empirical_platform.shared.identifiers import RuntimeIdentifier
from empirical_platform.usecases.record_evidence_package_criterion_result import (
    RecordEvidencePackageCriterionResultCommand,
    RecordEvidencePackageCriterionResultHandler,
)

if TYPE_CHECKING:
    from empirical_platform.evidence.repository import EvidencePackageRepository

_RUNTIME_ID_VALUE = "12345678-1234-4321-8765-1234567890ab"
_OCCURRED_AT = datetime(2026, 1, 1, tzinfo=UTC)
_INITIAL_VERSION = AggregateVersion.initial()
_COLLECTING_VERSION = AggregateVersion(1)


def _identity(governance_id: str = "EVID-0001") -> DomainIdentity[EvidencePackageId]:
    return DomainIdentity(
        governance_id=EvidencePackageId(governance_id),
        runtime_id=RuntimeIdentifier(_RUNTIME_ID_VALUE),
    )


def _collecting_package(
    identity: DomainIdentity[EvidencePackageId], run_id: str = "RUN-0001"
) -> EvidencePackage:
    package = EvidencePackage(identity=identity, run_id=RunId(run_id))
    package.start_collection(actor="tester", occurred_at=_OCCURRED_AT)
    return package


def _command(
    identity: DomainIdentity[EvidencePackageId],
    *,
    expected_persisted_version: AggregateVersion = _COLLECTING_VERSION,
    criterion_id: str = "CRIT-001",
    recorded_at: datetime = _OCCURRED_AT,
    result_label: str = "PASS",
    summary: str | None = None,
    evidence_references: tuple[str, ...] = (),
) -> RecordEvidencePackageCriterionResultCommand:
    return RecordEvidencePackageCriterionResultCommand(
        identity=identity,
        expected_persisted_version=expected_persisted_version,
        criterion_id=criterion_id,
        recorded_at=recorded_at,
        result_label=result_label,
        summary=summary,
        evidence_references=evidence_references,
    )


class _RecordingEvidencePackageRepository:
    """Records every `get()`/`save()` call; conforms structurally to `EvidencePackageRepository`."""

    def __init__(
        self,
        loaded: LoadedAggregate[EvidencePackage] | list[LoadedAggregate[EvidencePackage]],
        save_result: SaveResult,
    ) -> None:
        self._loaded_sequence = loaded if isinstance(loaded, list) else None
        self._loaded_single = None if isinstance(loaded, list) else loaded
        self._save_result = save_result
        self.get_calls: list[DomainIdentity[EvidencePackageId]] = []
        self.save_calls: list[tuple[EvidencePackage, AggregateVersion]] = []

    def get(self, identity: DomainIdentity[EvidencePackageId]) -> LoadedAggregate[EvidencePackage]:
        self.get_calls.append(identity)
        if self._loaded_sequence is not None:
            return self._loaded_sequence[len(self.get_calls) - 1]
        assert self._loaded_single is not None
        return self._loaded_single

    def add(self, aggregate: EvidencePackage) -> SaveResult:
        raise AssertionError(
            "add() must not be called by RecordEvidencePackageCriterionResultHandler"
        )

    def save(
        self, aggregate: EvidencePackage, *, expected_persisted_version: AggregateVersion
    ) -> SaveResult:
        self.save_calls.append((aggregate, expected_persisted_version))
        return self._save_result


class _FailingGetEvidencePackageRepository:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc
        self.get_calls = 0
        self.save_calls = 0

    def get(self, identity: DomainIdentity[EvidencePackageId]) -> object:
        self.get_calls += 1
        raise self._exc

    def add(self, aggregate: EvidencePackage) -> object:
        raise AssertionError("add() must not be called")

    def save(self, aggregate: EvidencePackage, *, expected_persisted_version: object) -> object:
        self.save_calls += 1
        raise AssertionError("save() must not be called after get() failure")


class _FailingSaveEvidencePackageRepository:
    def __init__(self, loaded: LoadedAggregate[EvidencePackage], exc: Exception) -> None:
        self._loaded = loaded
        self._exc = exc
        self.get_calls = 0
        self.save_calls = 0

    def get(self, identity: DomainIdentity[EvidencePackageId]) -> LoadedAggregate[EvidencePackage]:
        self.get_calls += 1
        return self._loaded

    def add(self, aggregate: EvidencePackage) -> object:
        raise AssertionError("add() must not be called")

    def save(
        self, aggregate: EvidencePackage, *, expected_persisted_version: AggregateVersion
    ) -> object:
        self.save_calls += 1
        raise self._exc


def _handler(repository: object) -> RecordEvidencePackageCriterionResultHandler:
    return RecordEvidencePackageCriterionResultHandler(evidence_package_repository=repository)  # type: ignore[arg-type]


# --- A. Command contract tests ---


def test_command_preserves_all_seven_fields_unchanged() -> None:
    identity = _identity()
    version = AggregateVersion(3)
    command = RecordEvidencePackageCriterionResultCommand(
        identity=identity,
        expected_persisted_version=version,
        criterion_id="CRIT-042",
        recorded_at=_OCCURRED_AT,
        result_label="FAIL",
        summary="did not meet threshold",
        evidence_references=("s3://bucket/ref-1",),
    )

    assert command.identity is identity
    assert command.expected_persisted_version is version
    assert command.criterion_id == "CRIT-042"
    assert command.recorded_at == _OCCURRED_AT
    assert command.result_label == "FAIL"
    assert command.summary == "did not meet threshold"
    assert command.evidence_references == ("s3://bucket/ref-1",)


def test_command_optional_fields_default_to_empty() -> None:
    command = _command(_identity())

    assert command.summary is None
    assert command.evidence_references == ()


def test_command_contains_no_additional_fields() -> None:
    assert set(RecordEvidencePackageCriterionResultCommand.__slots__) == {  # type: ignore[attr-defined]
        "identity",
        "expected_persisted_version",
        "criterion_id",
        "recorded_at",
        "result_label",
        "summary",
        "evidence_references",
    }


def test_command_is_immutable() -> None:
    command = _command(_identity())
    with pytest.raises(AttributeError):
        command.criterion_id = "CRIT-999"  # type: ignore[misc]


def test_command_construction_performs_no_business_validation() -> None:
    """No duplicated domain validation; raw empty-string criterion_id is
    accepted at construction -- CriterionResult itself validates later."""
    command = RecordEvidencePackageCriterionResultCommand(
        identity=_identity(),
        expected_persisted_version=AggregateVersion.initial(),
        criterion_id="",
        recorded_at=_OCCURRED_AT,
        result_label="PASS",
    )
    assert command.criterion_id == ""


# --- B. Handler success tests ---


def test_typed_conformance_check() -> None:
    """Mypy-checked proof that RecordEvidencePackageCriterionResultHandler
    conforms to
    CommandHandler[RecordEvidencePackageCriterionResultCommand, SaveResult]
    without inheritance (structural typing only)."""
    identity = _identity()
    loaded = LoadedAggregate(
        aggregate=_collecting_package(identity), persisted_version=AggregateVersion(1)
    )
    save_result = SaveResult(operation=SaveOperation.UPDATED, persisted_version=AggregateVersion(2))
    repository: EvidencePackageRepository = _RecordingEvidencePackageRepository(  # type: ignore[assignment]
        loaded, save_result
    )
    handler: RecordEvidencePackageCriterionResultHandler = _handler(repository)
    assert handler is not None


def test_get_is_called_exactly_once_with_exact_identity() -> None:
    identity = _identity()
    loaded = LoadedAggregate(
        aggregate=_collecting_package(identity), persisted_version=AggregateVersion(1)
    )
    save_result = SaveResult(operation=SaveOperation.UPDATED, persisted_version=AggregateVersion(2))
    repository = _RecordingEvidencePackageRepository(loaded, save_result)
    handler = _handler(repository)
    command = _command(identity)

    handler.handle(command)

    assert len(repository.get_calls) == 1
    assert repository.get_calls[0] is command.identity


def test_criterion_result_evidence_package_id_is_derived_not_supplied() -> None:
    """Critical: evidence_package_id on the constructed CriterionResult must
    come from the loaded aggregate's own identity, never from a separately
    supplied command field (design Section 4) -- there is no such field on
    the command at all."""
    identity = _identity("EVID-0042")
    package = _collecting_package(identity)
    loaded = LoadedAggregate(aggregate=package, persisted_version=AggregateVersion(1))
    save_result = SaveResult(operation=SaveOperation.UPDATED, persisted_version=AggregateVersion(2))
    repository = _RecordingEvidencePackageRepository(loaded, save_result)
    handler = _handler(repository)
    command = _command(identity, criterion_id="CRIT-777")

    handler.handle(command)

    recorded = package.criterion_results[-1]
    assert recorded.evidence_package_id == identity.governance_id
    assert recorded.criterion_id == "CRIT-777"


def test_add_criterion_result_called_with_exact_command_arguments() -> None:
    identity = _identity()
    package = _collecting_package(identity)
    loaded = LoadedAggregate(aggregate=package, persisted_version=AggregateVersion(1))
    save_result = SaveResult(operation=SaveOperation.UPDATED, persisted_version=AggregateVersion(2))
    repository = _RecordingEvidencePackageRepository(loaded, save_result)
    handler = _handler(repository)
    command = _command(
        identity,
        criterion_id="CRIT-100",
        result_label="PASS",
        summary="met all thresholds",
        evidence_references=("ref-a", "ref-b"),
    )

    handler.handle(command)

    assert len(package.criterion_results) == 1
    recorded = package.criterion_results[0]
    assert recorded.criterion_id == "CRIT-100"
    assert recorded.result_label == "PASS"
    assert recorded.summary == "met all thresholds"
    assert recorded.evidence_references == ("ref-a", "ref-b")
    assert package.state is EvidencePackageLifecycleState.COLLECTING


def test_save_called_exactly_once_with_mutated_aggregate_and_command_version() -> None:
    identity = _identity()
    package = _collecting_package(identity)
    loaded = LoadedAggregate(aggregate=package, persisted_version=AggregateVersion(1))
    save_result = SaveResult(operation=SaveOperation.UPDATED, persisted_version=AggregateVersion(2))
    repository = _RecordingEvidencePackageRepository(loaded, save_result)
    handler = _handler(repository)
    command = _command(identity, expected_persisted_version=AggregateVersion(1))

    handler.handle(command)

    assert len(repository.save_calls) == 1
    saved_aggregate, saved_expected_version = repository.save_calls[0]
    assert saved_aggregate is package
    assert saved_expected_version is command.expected_persisted_version


def test_save_receives_command_version_not_loaded_persisted_version() -> None:
    """Critical: expected_persisted_version passed to save() must come from the
    command, never from loaded.persisted_version -- even when they differ."""
    identity = _identity()
    package = _collecting_package(identity)
    loaded = LoadedAggregate(aggregate=package, persisted_version=AggregateVersion(5))
    save_result = SaveResult(operation=SaveOperation.UPDATED, persisted_version=AggregateVersion(6))
    repository = _RecordingEvidencePackageRepository(loaded, save_result)
    handler = _handler(repository)
    stale_version = AggregateVersion(1)
    command = _command(identity, expected_persisted_version=stale_version)

    handler.handle(command)

    _, saved_expected_version = repository.save_calls[0]
    assert saved_expected_version is stale_version
    assert saved_expected_version != loaded.persisted_version


def test_no_add_call_occurs() -> None:
    identity = _identity()
    loaded = LoadedAggregate(
        aggregate=_collecting_package(identity), persisted_version=AggregateVersion(1)
    )
    save_result = SaveResult(operation=SaveOperation.UPDATED, persisted_version=AggregateVersion(2))
    repository = _RecordingEvidencePackageRepository(loaded, save_result)
    handler = _handler(repository)

    handler.handle(_command(identity))  # would raise if add() were called


def test_no_second_get_or_save_occurs() -> None:
    identity = _identity()
    loaded = LoadedAggregate(
        aggregate=_collecting_package(identity), persisted_version=AggregateVersion(1)
    )
    save_result = SaveResult(operation=SaveOperation.UPDATED, persisted_version=AggregateVersion(2))
    repository = _RecordingEvidencePackageRepository(loaded, save_result)
    handler = _handler(repository)

    handler.handle(_command(identity))

    assert len(repository.get_calls) == 1
    assert len(repository.save_calls) == 1


def test_no_artifact_reference_seal_or_start_collection_call_occurs() -> None:
    """The mutated aggregate carries only the newly recorded criterion result
    -- no artifact reference, no seal, no re-invocation of start_collection."""
    identity = _identity()
    package = _collecting_package(identity)
    loaded = LoadedAggregate(aggregate=package, persisted_version=AggregateVersion(1))
    save_result = SaveResult(operation=SaveOperation.UPDATED, persisted_version=AggregateVersion(2))
    repository = _RecordingEvidencePackageRepository(loaded, save_result)
    handler = _handler(repository)

    handler.handle(_command(identity))

    assert package.artifact_references == ()
    assert package.state is EvidencePackageLifecycleState.COLLECTING
    assert len(package.transition_history) == 1  # only the original start_collection() transition


def test_returned_object_is_the_exact_save_result() -> None:
    identity = _identity()
    loaded = LoadedAggregate(
        aggregate=_collecting_package(identity), persisted_version=AggregateVersion(1)
    )
    save_result = SaveResult(operation=SaveOperation.UPDATED, persisted_version=AggregateVersion(2))
    repository = _RecordingEvidencePackageRepository(loaded, save_result)
    handler = _handler(repository)

    result = handler.handle(_command(identity))

    assert result is save_result


def test_handler_is_invocable_through_command_entry_point() -> None:
    identity = _identity()
    loaded = LoadedAggregate(
        aggregate=_collecting_package(identity), persisted_version=AggregateVersion(1)
    )
    save_result = SaveResult(operation=SaveOperation.UPDATED, persisted_version=AggregateVersion(2))
    repository = _RecordingEvidencePackageRepository(loaded, save_result)
    handler = _handler(repository)
    entry_point = CommandEntryPoint(handler)

    result = entry_point(_command(identity))

    assert result is save_result
    assert len(repository.get_calls) == 1
    assert len(repository.save_calls) == 1


def test_handler_bound_at_construction_reused_across_invocations() -> None:
    identity_one = _identity("EVID-0001")
    identity_two = _identity("EVID-0002")
    loaded_sequence = [
        LoadedAggregate(
            aggregate=_collecting_package(identity_one), persisted_version=AggregateVersion(1)
        ),
        LoadedAggregate(
            aggregate=_collecting_package(identity_two), persisted_version=AggregateVersion(1)
        ),
    ]
    save_result = SaveResult(operation=SaveOperation.UPDATED, persisted_version=AggregateVersion(2))
    repository = _RecordingEvidencePackageRepository(loaded_sequence, save_result)
    handler = _handler(repository)
    entry_point = CommandEntryPoint(handler)

    entry_point(_command(identity_one))
    entry_point(_command(identity_two))

    assert len(repository.get_calls) == 2
    assert len(repository.save_calls) == 2


# --- C. Domain-failure tests ---


def test_domain_invalid_state_propagates_and_save_never_called() -> None:
    identity = _identity()
    package = EvidencePackage(identity=identity, run_id=RunId("RUN-0001"))  # still INITIALIZED
    loaded = LoadedAggregate(aggregate=package, persisted_version=AggregateVersion.initial())
    save_result = SaveResult(operation=SaveOperation.UPDATED, persisted_version=AggregateVersion(1))
    repository = _RecordingEvidencePackageRepository(loaded, save_result)
    handler = _handler(repository)

    with pytest.raises(ValueError, match="may be added only while COLLECTING"):
        handler.handle(_command(identity, expected_persisted_version=AggregateVersion.initial()))

    assert repository.save_calls == []


def test_duplicate_criterion_id_propagates_and_save_never_called() -> None:
    identity = _identity()
    package = _collecting_package(identity)
    package.add_criterion_result(
        CriterionResult(
            evidence_package_id=identity.governance_id,
            criterion_id="CRIT-001",
            recorded_at=_OCCURRED_AT,
            result_label="PASS",
        )
    )
    loaded = LoadedAggregate(aggregate=package, persisted_version=AggregateVersion(2))
    save_result = SaveResult(operation=SaveOperation.UPDATED, persisted_version=AggregateVersion(3))
    repository = _RecordingEvidencePackageRepository(loaded, save_result)
    handler = _handler(repository)

    with pytest.raises(ValueError, match="criterion_id already exists"):
        handler.handle(
            _command(
                identity, criterion_id="CRIT-001", expected_persisted_version=AggregateVersion(2)
            )
        )

    assert repository.save_calls == []


# --- D. get()-failure tests ---


def test_aggregate_not_found_from_get_propagates_with_identity_preserved() -> None:
    exc = AggregateNotFound(aggregate_kind="EvidencePackage", identity=_identity())
    repository = _FailingGetEvidencePackageRepository(exc)
    handler = _handler(repository)

    with pytest.raises(AggregateNotFound) as excinfo:
        handler.handle(_command(_identity()))

    assert excinfo.value is exc
    assert repository.get_calls == 1
    assert repository.save_calls == 0


def test_arbitrary_get_exception_propagates_unchanged() -> None:
    exc = RuntimeError("unexpected get() failure")
    repository = _FailingGetEvidencePackageRepository(exc)
    handler = _handler(repository)

    with pytest.raises(RuntimeError) as excinfo:
        handler.handle(_command(_identity()))

    assert excinfo.value is exc
    assert repository.save_calls == 0


# --- E. save()-failure tests ---


def test_optimistic_concurrency_conflict_from_save_propagates_unchanged() -> None:
    identity = _identity()
    package = _collecting_package(identity)
    exc = OptimisticConcurrencyConflict(
        aggregate_kind="EvidencePackage",
        identity=identity,
        expected_persisted_version=AggregateVersion(1),
        aggregate_current_version=AggregateVersion(2),
        actual_persisted_version=AggregateVersion(2),
    )
    loaded = LoadedAggregate(aggregate=package, persisted_version=AggregateVersion(1))
    repository = _FailingSaveEvidencePackageRepository(loaded, exc)
    handler = _handler(repository)

    with pytest.raises(OptimisticConcurrencyConflict) as excinfo:
        handler.handle(_command(identity))

    assert excinfo.value is exc
    assert repository.get_calls == 1
    assert repository.save_calls == 1


def test_arbitrary_save_exception_propagates_with_identity_preserved() -> None:
    identity = _identity()
    package = _collecting_package(identity)
    loaded = LoadedAggregate(aggregate=package, persisted_version=AggregateVersion(1))
    exc = RuntimeError("unexpected save() failure")
    repository = _FailingSaveEvidencePackageRepository(loaded, exc)
    handler = _handler(repository)

    with pytest.raises(RuntimeError) as excinfo:
        handler.handle(_command(identity))

    assert excinfo.value is exc
    assert repository.get_calls == 1
    assert repository.save_calls == 1
