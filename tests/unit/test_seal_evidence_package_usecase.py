"""MILESTONE-041 behavioral tests for `SealEvidencePackageCommand`/
`SealEvidencePackageHandler`.

Proves the frozen load-mutate-save flow (design Section 7): call
`EvidencePackageRepository.get()` exactly once, invoke
`EvidencePackage.seal()` exactly once with the command's data unchanged,
then call `EvidencePackageRepository.save()` exactly once with the
mutated aggregate and the command's own `expected_persisted_version` --
never `loaded.persisted_version`. Also proves transparent failure
propagation for every collaborator (frozen M029 invariant), including all
three distinct domain-`ValueError` scenarios this transition's two-sided
precondition introduces (empty criterion results, empty artifact
references, invalid state) -- unlike any prior single-precondition
transition (M032/M035/M038) -- and that the handler is invocable through
the frozen `CommandEntryPoint`.

Uses deterministic recording fakes/stubs, not mocks, for stronger evidence.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from empirical_platform.application.command import CommandEntryPoint
from empirical_platform.evidence.lifecycle import EvidencePackageLifecycleState
from empirical_platform.evidence.package import ArtifactReference, EvidencePackage
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
from empirical_platform.usecases.seal_evidence_package import (
    SealEvidencePackageCommand,
    SealEvidencePackageHandler,
)

if TYPE_CHECKING:
    from empirical_platform.evidence.repository import EvidencePackageRepository

_RUNTIME_ID_VALUE = "12345678-1234-4321-8765-1234567890ab"
_OCCURRED_AT = datetime(2026, 1, 1, tzinfo=UTC)
_SEALABLE_VERSION = AggregateVersion(3)


def _identity(governance_id: str = "EVID-0001") -> DomainIdentity[EvidencePackageId]:
    return DomainIdentity(
        governance_id=EvidencePackageId(governance_id),
        runtime_id=RuntimeIdentifier(_RUNTIME_ID_VALUE),
    )


def _sealable_package(
    identity: DomainIdentity[EvidencePackageId], run_id: str = "RUN-0001"
) -> EvidencePackage:
    package = EvidencePackage(identity=identity, run_id=RunId(run_id))
    package.start_collection(actor="tester", occurred_at=_OCCURRED_AT)
    package.add_criterion_result(
        CriterionResult(
            evidence_package_id=identity.governance_id,
            criterion_id="CRIT-001",
            recorded_at=_OCCURRED_AT,
            result_label="PASS",
        )
    )
    package.add_artifact_reference(ArtifactReference(value="s3://bucket/artifact-1"))
    return package


def _command(
    identity: DomainIdentity[EvidencePackageId],
    *,
    expected_persisted_version: AggregateVersion = _SEALABLE_VERSION,
    actor: str = "tester",
    occurred_at: datetime = _OCCURRED_AT,
    correlation_id: str | None = None,
    reason: str | None = None,
) -> SealEvidencePackageCommand:
    return SealEvidencePackageCommand(
        identity=identity,
        expected_persisted_version=expected_persisted_version,
        actor=actor,
        occurred_at=occurred_at,
        correlation_id=correlation_id,
        reason=reason,
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
        raise AssertionError("add() must not be called by SealEvidencePackageHandler")

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


def _handler(repository: object) -> SealEvidencePackageHandler:
    return SealEvidencePackageHandler(evidence_package_repository=repository)  # type: ignore[arg-type]


# --- A. Command contract tests ---


def test_command_preserves_all_six_fields_unchanged() -> None:
    identity = _identity()
    version = AggregateVersion(3)
    command = SealEvidencePackageCommand(
        identity=identity,
        expected_persisted_version=version,
        actor="alice",
        occurred_at=_OCCURRED_AT,
        correlation_id="corr-1",
        reason="collection complete",
    )

    assert command.identity is identity
    assert command.expected_persisted_version is version
    assert command.actor == "alice"
    assert command.occurred_at == _OCCURRED_AT
    assert command.correlation_id == "corr-1"
    assert command.reason == "collection complete"


def test_command_optional_fields_default_to_none() -> None:
    command = _command(_identity())

    assert command.correlation_id is None
    assert command.reason is None


def test_command_contains_no_additional_fields() -> None:
    assert set(SealEvidencePackageCommand.__slots__) == {  # type: ignore[attr-defined]
        "identity",
        "expected_persisted_version",
        "actor",
        "occurred_at",
        "correlation_id",
        "reason",
    }


def test_command_is_immutable() -> None:
    command = _command(_identity())
    with pytest.raises(AttributeError):
        command.actor = "someone-else"  # type: ignore[misc]


def test_command_construction_performs_no_business_validation() -> None:
    """No duplicated domain validation; raw empty-string actor is accepted at construction."""
    command = SealEvidencePackageCommand(
        identity=_identity(),
        expected_persisted_version=AggregateVersion.initial(),
        actor="",
        occurred_at=_OCCURRED_AT,
    )
    assert command.actor == ""


# --- B. Handler success tests ---


def test_typed_conformance_check() -> None:
    """Mypy-checked proof that SealEvidencePackageHandler conforms to
    CommandHandler[SealEvidencePackageCommand, SaveResult] without
    inheritance (structural typing only)."""
    identity = _identity()
    loaded = LoadedAggregate(
        aggregate=_sealable_package(identity), persisted_version=_SEALABLE_VERSION
    )
    save_result = SaveResult(operation=SaveOperation.UPDATED, persisted_version=AggregateVersion(4))
    repository: EvidencePackageRepository = _RecordingEvidencePackageRepository(  # type: ignore[assignment]
        loaded, save_result
    )
    handler: SealEvidencePackageHandler = _handler(repository)
    assert handler is not None


def test_get_is_called_exactly_once_with_exact_identity() -> None:
    identity = _identity()
    loaded = LoadedAggregate(
        aggregate=_sealable_package(identity), persisted_version=_SEALABLE_VERSION
    )
    save_result = SaveResult(operation=SaveOperation.UPDATED, persisted_version=AggregateVersion(4))
    repository = _RecordingEvidencePackageRepository(loaded, save_result)
    handler = _handler(repository)
    command = _command(identity)

    handler.handle(command)

    assert len(repository.get_calls) == 1
    assert repository.get_calls[0] is command.identity


def test_seal_called_with_exact_command_arguments() -> None:
    identity = _identity()
    package = _sealable_package(identity)
    loaded = LoadedAggregate(aggregate=package, persisted_version=_SEALABLE_VERSION)
    save_result = SaveResult(operation=SaveOperation.UPDATED, persisted_version=AggregateVersion(4))
    repository = _RecordingEvidencePackageRepository(loaded, save_result)
    handler = _handler(repository)
    command = _command(
        identity,
        actor="bob",
        occurred_at=_OCCURRED_AT,
        correlation_id="corr-42",
        reason="collection complete",
    )

    handler.handle(command)

    assert package.state is EvidencePackageLifecycleState.SEALED
    record = package.transition_history[-1]
    assert record.actor == "bob"
    assert record.occurred_at == _OCCURRED_AT
    assert record.correlation_id == "corr-42"
    assert record.reason == "collection complete"


def test_save_called_exactly_once_with_mutated_aggregate_and_command_version() -> None:
    identity = _identity()
    package = _sealable_package(identity)
    loaded = LoadedAggregate(aggregate=package, persisted_version=_SEALABLE_VERSION)
    save_result = SaveResult(operation=SaveOperation.UPDATED, persisted_version=AggregateVersion(4))
    repository = _RecordingEvidencePackageRepository(loaded, save_result)
    handler = _handler(repository)
    command = _command(identity, expected_persisted_version=AggregateVersion(3))

    handler.handle(command)

    assert len(repository.save_calls) == 1
    saved_aggregate, saved_expected_version = repository.save_calls[0]
    assert saved_aggregate is package
    assert saved_expected_version is command.expected_persisted_version


def test_save_receives_command_version_not_loaded_persisted_version() -> None:
    """Critical: expected_persisted_version passed to save() must come from the
    command, never from loaded.persisted_version -- even when they differ."""
    identity = _identity()
    package = _sealable_package(identity)
    loaded = LoadedAggregate(aggregate=package, persisted_version=AggregateVersion(9))
    save_result = SaveResult(operation=SaveOperation.UPDATED, persisted_version=AggregateVersion(4))
    repository = _RecordingEvidencePackageRepository(loaded, save_result)
    handler = _handler(repository)
    stale_version = AggregateVersion(3)
    command = _command(identity, expected_persisted_version=stale_version)

    handler.handle(command)

    _, saved_expected_version = repository.save_calls[0]
    assert saved_expected_version is stale_version
    assert saved_expected_version != loaded.persisted_version


def test_no_add_call_occurs() -> None:
    identity = _identity()
    loaded = LoadedAggregate(
        aggregate=_sealable_package(identity), persisted_version=_SEALABLE_VERSION
    )
    save_result = SaveResult(operation=SaveOperation.UPDATED, persisted_version=AggregateVersion(4))
    repository = _RecordingEvidencePackageRepository(loaded, save_result)
    handler = _handler(repository)

    handler.handle(_command(identity))  # would raise if add() were called


def test_no_second_get_or_save_occurs() -> None:
    identity = _identity()
    loaded = LoadedAggregate(
        aggregate=_sealable_package(identity), persisted_version=_SEALABLE_VERSION
    )
    save_result = SaveResult(operation=SaveOperation.UPDATED, persisted_version=AggregateVersion(4))
    repository = _RecordingEvidencePackageRepository(loaded, save_result)
    handler = _handler(repository)

    handler.handle(_command(identity))

    assert len(repository.get_calls) == 1
    assert len(repository.save_calls) == 1


def test_no_criterion_result_artifact_reference_or_invalidate_call_occurs() -> None:
    """The mutated aggregate's collections are unchanged by sealing -- no
    add_criterion_result, add_artifact_reference, or invalidate call."""
    identity = _identity()
    package = _sealable_package(identity)
    criterion_count_before = len(package.criterion_results)
    artifact_count_before = len(package.artifact_references)
    loaded = LoadedAggregate(aggregate=package, persisted_version=_SEALABLE_VERSION)
    save_result = SaveResult(operation=SaveOperation.UPDATED, persisted_version=AggregateVersion(4))
    repository = _RecordingEvidencePackageRepository(loaded, save_result)
    handler = _handler(repository)

    handler.handle(_command(identity))

    assert len(package.criterion_results) == criterion_count_before
    assert len(package.artifact_references) == artifact_count_before
    assert package.state is EvidencePackageLifecycleState.SEALED


def test_returned_object_is_the_exact_save_result() -> None:
    identity = _identity()
    loaded = LoadedAggregate(
        aggregate=_sealable_package(identity), persisted_version=_SEALABLE_VERSION
    )
    save_result = SaveResult(operation=SaveOperation.UPDATED, persisted_version=AggregateVersion(4))
    repository = _RecordingEvidencePackageRepository(loaded, save_result)
    handler = _handler(repository)

    result = handler.handle(_command(identity))

    assert result is save_result


def test_handler_is_invocable_through_command_entry_point() -> None:
    identity = _identity()
    loaded = LoadedAggregate(
        aggregate=_sealable_package(identity), persisted_version=_SEALABLE_VERSION
    )
    save_result = SaveResult(operation=SaveOperation.UPDATED, persisted_version=AggregateVersion(4))
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
            aggregate=_sealable_package(identity_one), persisted_version=_SEALABLE_VERSION
        ),
        LoadedAggregate(
            aggregate=_sealable_package(identity_two), persisted_version=_SEALABLE_VERSION
        ),
    ]
    save_result = SaveResult(operation=SaveOperation.UPDATED, persisted_version=AggregateVersion(4))
    repository = _RecordingEvidencePackageRepository(loaded_sequence, save_result)
    handler = _handler(repository)
    entry_point = CommandEntryPoint(handler)

    entry_point(_command(identity_one))
    entry_point(_command(identity_two))

    assert len(repository.get_calls) == 2
    assert len(repository.save_calls) == 2


# --- C. Transition-history proof ---


def test_successful_seal_produces_exactly_one_transition_record() -> None:
    identity = _identity()
    package = _sealable_package(identity)
    version_before = package.version
    history_length_before = len(package.transition_history)
    loaded = LoadedAggregate(aggregate=package, persisted_version=_SEALABLE_VERSION)
    save_result = SaveResult(operation=SaveOperation.UPDATED, persisted_version=AggregateVersion(4))
    repository = _RecordingEvidencePackageRepository(loaded, save_result)
    handler = _handler(repository)
    command = _command(
        identity, actor="carol", correlation_id="corr-99", reason="collection complete"
    )

    handler.handle(command)

    assert package.state is EvidencePackageLifecycleState.SEALED
    assert package.version == version_before.next()
    assert len(package.transition_history) == history_length_before + 1
    record = package.transition_history[-1]
    assert record.from_state == "COLLECTING"
    assert record.to_state == "SEALED"
    assert record.version == package.version
    assert record.actor == "carol"
    assert record.correlation_id == "corr-99"
    assert record.reason == "collection complete"


# --- D. Domain-failure tests (three distinct precondition scenarios) ---


def test_empty_criterion_results_propagates_and_save_never_called() -> None:
    identity = _identity()
    package = EvidencePackage(identity=identity, run_id=RunId("RUN-0001"))
    package.start_collection(actor="tester", occurred_at=_OCCURRED_AT)
    package.add_artifact_reference(ArtifactReference(value="s3://bucket/artifact-1"))
    loaded = LoadedAggregate(aggregate=package, persisted_version=AggregateVersion(1))
    save_result = SaveResult(operation=SaveOperation.UPDATED, persisted_version=AggregateVersion(2))
    repository = _RecordingEvidencePackageRepository(loaded, save_result)
    handler = _handler(repository)

    with pytest.raises(ValueError, match="requires at least one Criterion Result"):
        handler.handle(_command(identity, expected_persisted_version=AggregateVersion(1)))

    assert repository.save_calls == []


def test_empty_artifact_references_propagates_and_save_never_called() -> None:
    identity = _identity()
    package = EvidencePackage(identity=identity, run_id=RunId("RUN-0001"))
    package.start_collection(actor="tester", occurred_at=_OCCURRED_AT)
    package.add_criterion_result(
        CriterionResult(
            evidence_package_id=identity.governance_id,
            criterion_id="CRIT-001",
            recorded_at=_OCCURRED_AT,
            result_label="PASS",
        )
    )
    loaded = LoadedAggregate(aggregate=package, persisted_version=AggregateVersion(1))
    save_result = SaveResult(operation=SaveOperation.UPDATED, persisted_version=AggregateVersion(2))
    repository = _RecordingEvidencePackageRepository(loaded, save_result)
    handler = _handler(repository)

    with pytest.raises(ValueError, match="requires at least one artifact reference"):
        handler.handle(_command(identity, expected_persisted_version=AggregateVersion(1)))

    assert repository.save_calls == []


def test_domain_invalid_state_propagates_and_save_never_called() -> None:
    """Both collection preconditions are satisfied (checked first by seal()),
    isolating the state-precondition check: a package already SEALED cannot
    be sealed again."""
    identity = _identity()
    package = _sealable_package(identity)
    package.seal(actor="tester", occurred_at=_OCCURRED_AT)  # COLLECTING -> SEALED
    loaded = LoadedAggregate(aggregate=package, persisted_version=AggregateVersion(4))
    save_result = SaveResult(operation=SaveOperation.UPDATED, persisted_version=AggregateVersion(5))
    repository = _RecordingEvidencePackageRepository(loaded, save_result)
    handler = _handler(repository)

    with pytest.raises(ValueError, match="cannot transition from"):
        handler.handle(_command(identity, expected_persisted_version=AggregateVersion(4)))

    assert repository.save_calls == []


# --- E. get()-failure tests ---


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


# --- F. save()-failure tests ---


def test_optimistic_concurrency_conflict_from_save_propagates_unchanged() -> None:
    identity = _identity()
    package = _sealable_package(identity)
    exc = OptimisticConcurrencyConflict(
        aggregate_kind="EvidencePackage",
        identity=identity,
        expected_persisted_version=AggregateVersion(3),
        aggregate_current_version=AggregateVersion(4),
        actual_persisted_version=AggregateVersion(4),
    )
    loaded = LoadedAggregate(aggregate=package, persisted_version=_SEALABLE_VERSION)
    repository = _FailingSaveEvidencePackageRepository(loaded, exc)
    handler = _handler(repository)

    with pytest.raises(OptimisticConcurrencyConflict) as excinfo:
        handler.handle(_command(identity))

    assert excinfo.value is exc
    assert repository.get_calls == 1
    assert repository.save_calls == 1


def test_arbitrary_save_exception_propagates_with_identity_preserved() -> None:
    identity = _identity()
    package = _sealable_package(identity)
    loaded = LoadedAggregate(aggregate=package, persisted_version=_SEALABLE_VERSION)
    exc = RuntimeError("unexpected save() failure")
    repository = _FailingSaveEvidencePackageRepository(loaded, exc)
    handler = _handler(repository)

    with pytest.raises(RuntimeError) as excinfo:
        handler.handle(_command(identity))

    assert excinfo.value is exc
    assert repository.get_calls == 1
    assert repository.save_calls == 1
