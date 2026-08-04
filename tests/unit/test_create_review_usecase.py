"""MILESTONE-042 behavioral tests for `CreateReviewHandler`.

Proves the frozen persistence flow (design Section 7): translate command
data into frozen value types, obtain `runtime_id` from the injected
`RuntimeIdentifierGenerator`, construct the `Review` aggregate, call
`ReviewRepository.add()` exactly once, and return the resulting
`DomainIdentity[ReviewId]`. Also proves transparent failure propagation
for every collaborator (frozen M029 invariant), that the handler never
depends on `EvidencePackageRepository` (design Section 6), and that the
handler is invocable through the frozen `CommandEntryPoint`.

Uses deterministic recording fakes/stubs, not mocks, for stronger evidence.
"""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING

import pytest

from empirical_platform.application.command import CommandEntryPoint
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import EvidencePackageId, ReviewId
from empirical_platform.review.aggregate import Review
from empirical_platform.shared.contracts.repository import (
    AggregateAlreadyExists,
    SaveOperation,
    SaveResult,
)
from empirical_platform.shared.domain.versioning import AggregateVersion
from empirical_platform.shared.identifiers import DeterministicRuntimeIdentifierGenerator
from empirical_platform.usecases.create_review import CreateReviewCommand, CreateReviewHandler

if TYPE_CHECKING:
    from empirical_platform.review.repository import ReviewRepository
    from empirical_platform.shared.contracts.command import CommandHandler

_RUNTIME_ID_VALUE = "12345678-1234-4321-8765-1234567890ab"


class _RecordingReviewRepository:
    """Records every `add()` call; conforms structurally to `ReviewRepository`."""

    def __init__(self) -> None:
        self.add_calls: list[Review] = []

    def get(self, identity: object) -> object:
        raise AssertionError("get() must not be called by CreateReviewHandler")

    def add(self, aggregate: Review) -> SaveResult:
        self.add_calls.append(aggregate)
        return SaveResult(operation=SaveOperation.CREATED, persisted_version=aggregate.version)

    def save(self, aggregate: Review, *, expected_persisted_version: AggregateVersion) -> object:
        raise AssertionError("save() must not be called by CreateReviewHandler")


class _FailingReviewRepository:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc
        self.add_calls = 0

    def get(self, identity: object) -> object:
        raise AssertionError("get() must not be called")

    def add(self, aggregate: Review) -> SaveResult:
        self.add_calls += 1
        raise self._exc

    def save(self, aggregate: Review, *, expected_persisted_version: AggregateVersion) -> object:
        raise AssertionError("save() must not be called")


class _FailingRuntimeIdentifierGenerator:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc
        self.generate_calls = 0

    def generate(self) -> object:
        self.generate_calls += 1
        raise self._exc


def _handler(repository: object, generator: object | None = None) -> CreateReviewHandler:
    return CreateReviewHandler(
        review_repository=repository,  # type: ignore[arg-type]
        runtime_identifier_generator=generator  # type: ignore[arg-type]
        or DeterministicRuntimeIdentifierGenerator([_RUNTIME_ID_VALUE]),
    )


def _command(
    *,
    review_governance_id: str = "REVIEW-0001",
    target_evidence_package_governance_id: str = "EVID-0001",
    reviewer_reference: str = "reviewer-alice",
) -> CreateReviewCommand:
    return CreateReviewCommand(
        review_governance_id=review_governance_id,
        target_evidence_package_governance_id=target_evidence_package_governance_id,
        reviewer_reference=reviewer_reference,
    )


def test_typed_conformance_check() -> None:
    """Mypy-checked proof that CreateReviewHandler conforms to
    CommandHandler[CreateReviewCommand, DomainIdentity[ReviewId]] without
    inheritance (structural typing only)."""
    repository: ReviewRepository = _RecordingReviewRepository()  # type: ignore[assignment]
    handler: CommandHandler[CreateReviewCommand, DomainIdentity[ReviewId]] = _handler(repository)
    assert handler is not None


def test_handler_constructor_accepts_no_evidence_package_repository_parameter() -> None:
    """Structural proof of the frozen target-existence decision (design
    Section 6): the constructor carries exactly two dependencies, neither
    named `evidence_package_repository`, confirming no EvidencePackage
    lookup is possible."""
    signature = inspect.signature(CreateReviewHandler.__init__)
    parameters = list(signature.parameters)
    assert parameters == ["self", "review_repository", "runtime_identifier_generator"]


def test_handler_returns_domain_identity_with_caller_supplied_governance_id() -> None:
    repository = _RecordingReviewRepository()
    handler = _handler(repository)

    result = handler.handle(_command(review_governance_id="REVIEW-0001"))

    assert isinstance(result, DomainIdentity)
    assert result.governance_id == ReviewId("REVIEW-0001")


def test_runtime_id_is_obtained_from_injected_generator() -> None:
    repository = _RecordingReviewRepository()
    generator = DeterministicRuntimeIdentifierGenerator([_RUNTIME_ID_VALUE])
    handler = _handler(repository, generator)

    result = handler.handle(_command())

    assert str(result.runtime_id) == _RUNTIME_ID_VALUE


def test_review_repository_add_is_called_exactly_once() -> None:
    repository = _RecordingReviewRepository()
    handler = _handler(repository)

    handler.handle(_command())

    assert len(repository.add_calls) == 1


def test_aggregate_supplied_to_add_has_expected_identity_target_and_reviewer() -> None:
    repository = _RecordingReviewRepository()
    generator = DeterministicRuntimeIdentifierGenerator([_RUNTIME_ID_VALUE])
    handler = _handler(repository, generator)
    command = _command(
        review_governance_id="REVIEW-0042",
        target_evidence_package_governance_id="EVID-0042",
        reviewer_reference="reviewer-bob",
    )

    handler.handle(command)

    persisted = repository.add_calls[0]
    assert persisted.identity.governance_id == ReviewId("REVIEW-0042")
    assert str(persisted.identity.runtime_id) == _RUNTIME_ID_VALUE
    assert persisted.target.evidence_package_id == EvidencePackageId("EVID-0042")
    assert str(persisted.reviewer) == "reviewer-bob"


def test_handler_returns_the_persisted_aggregates_identity() -> None:
    repository = _RecordingReviewRepository()
    handler = _handler(repository)

    result = handler.handle(_command())

    assert result is repository.add_calls[0].identity


def test_no_repository_pre_read_occurs() -> None:
    """get() raises AssertionError in the fake if called; handler must never call it."""
    repository = _RecordingReviewRepository()
    handler = _handler(repository)

    handler.handle(_command())  # would raise AssertionError if get() were called


def test_malformed_review_governance_id_propagates_unchanged() -> None:
    """ReviewId's own frozen format validation (M020) fires; handler adds no
    validation of its own and does not catch this failure. The generator
    must not be called and add() must not be called."""
    repository = _RecordingReviewRepository()
    generator = DeterministicRuntimeIdentifierGenerator([_RUNTIME_ID_VALUE])
    handler = _handler(repository, generator)
    command = _command(review_governance_id="not-a-valid-id")

    with pytest.raises(ValueError, match="Identifier must match"):
        handler.handle(command)

    assert repository.add_calls == []


def test_malformed_target_evidence_package_governance_id_propagates_unchanged() -> None:
    """EvidencePackageId's own frozen format validation (M020) fires after
    the ReviewId and runtime_id have already been constructed, but no
    add() call is reached."""
    repository = _RecordingReviewRepository()
    handler = _handler(repository)
    command = _command(target_evidence_package_governance_id="not-a-valid-id")

    with pytest.raises(ValueError, match="Identifier must match"):
        handler.handle(command)

    assert repository.add_calls == []


def test_empty_reviewer_reference_propagates_unchanged() -> None:
    """ReviewerReference's own frozen non-empty validation (M020) fires
    after ReviewId/EvidencePackageId have already been constructed, but no
    add() call is reached."""
    repository = _RecordingReviewRepository()
    handler = _handler(repository)
    command = _command(reviewer_reference="")

    with pytest.raises(ValueError, match="reviewer reference"):
        handler.handle(command)

    assert repository.add_calls == []


def test_repository_add_failure_propagates_with_identity_preserved() -> None:
    exc = AggregateAlreadyExists(aggregate_kind="Review", identity=object())
    repository = _FailingReviewRepository(exc)
    handler = _handler(repository)

    with pytest.raises(AggregateAlreadyExists) as excinfo:
        handler.handle(_command())

    assert excinfo.value is exc
    assert repository.add_calls == 1


def test_runtime_identifier_generator_failure_propagates_unchanged() -> None:
    exc = RuntimeError("identifier generation failed")
    generator = _FailingRuntimeIdentifierGenerator(exc)
    repository = _RecordingReviewRepository()
    handler = _handler(repository, generator)

    with pytest.raises(RuntimeError) as excinfo:
        handler.handle(_command())

    assert excinfo.value is exc
    assert generator.generate_calls == 1
    assert repository.add_calls == []


def test_handler_is_invocable_through_command_entry_point() -> None:
    repository = _RecordingReviewRepository()
    handler = _handler(repository)
    entry_point = CommandEntryPoint(handler)

    result = entry_point(_command())

    assert isinstance(result, DomainIdentity)
    assert len(repository.add_calls) == 1


def test_handler_bound_at_construction_not_per_call() -> None:
    repository = _RecordingReviewRepository()
    generator = DeterministicRuntimeIdentifierGenerator(
        [_RUNTIME_ID_VALUE, "87654321-4321-4321-8765-0987654321ba"]
    )
    handler = _handler(repository, generator)
    entry_point = CommandEntryPoint(handler)

    entry_point(_command(review_governance_id="REVIEW-0001"))
    entry_point(_command(review_governance_id="REVIEW-0002"))

    assert len(repository.add_calls) == 2


def test_command_is_a_plain_unvalidated_data_carrier() -> None:
    """No CreateReviewCommand-level validation exists; malformed data is
    accepted at construction and rejected only by the frozen value objects
    the handler later constructs."""
    command = CreateReviewCommand(
        review_governance_id="", target_evidence_package_governance_id="", reviewer_reference=""
    )
    assert command.review_governance_id == ""
    assert command.target_evidence_package_governance_id == ""
    assert command.reviewer_reference == ""
