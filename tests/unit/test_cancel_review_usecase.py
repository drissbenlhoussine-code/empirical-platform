"""MILESTONE-049 behavioral tests for `CancelReviewCommand`/`CancelReviewHandler`.

Proves the frozen load-mutate-save flow: call `ReviewRepository.get()`
exactly once, invoke `Review.cancel()` exactly once with the command's
data unchanged, then call `ReviewRepository.save()` exactly once with the
mutated aggregate and the command's own `expected_persisted_version` --
never `loaded.persisted_version`. Also proves transparent failure
propagation for every collaborator, including the two distinct
non-conflict domain failure modes `cancel()` introduces (invalid state,
empty reason) -- and that the handler is invocable through the frozen
`CommandEntryPoint`.

Uses deterministic recording fakes/stubs, not mocks, for stronger evidence.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from empirical_platform.application.command import CommandEntryPoint
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import EvidencePackageId, ReviewId
from empirical_platform.review.aggregate import Review, ReviewerReference, ReviewTargetReference
from empirical_platform.review.lifecycle import ReviewDisposition, ReviewLifecycleState
from empirical_platform.shared.contracts.repository import (
    AggregateNotFound,
    LoadedAggregate,
    OptimisticConcurrencyConflict,
    SaveOperation,
    SaveResult,
)
from empirical_platform.shared.domain.versioning import AggregateVersion
from empirical_platform.shared.identifiers import RuntimeIdentifier
from empirical_platform.usecases.cancel_review import CancelReviewCommand, CancelReviewHandler

if TYPE_CHECKING:
    from empirical_platform.review.repository import ReviewRepository

_RUNTIME_ID_VALUE = "12345678-1234-4321-8765-1234567890ab"
_OCCURRED_AT = datetime(2026, 1, 1, tzinfo=UTC)
_INITIAL_VERSION = AggregateVersion.initial()


def _identity(governance_id: str = "REVIEW-0001") -> DomainIdentity[ReviewId]:
    return DomainIdentity(
        governance_id=ReviewId(governance_id),
        runtime_id=RuntimeIdentifier(_RUNTIME_ID_VALUE),
    )


def _assigned_review(identity: DomainIdentity[ReviewId]) -> Review:
    return Review(
        identity=identity,
        target=ReviewTargetReference(evidence_package_id=EvidencePackageId("EVID-0001")),
        reviewer=ReviewerReference("reviewer-1"),
    )


def _in_progress_review(identity: DomainIdentity[ReviewId]) -> Review:
    review = _assigned_review(identity)
    review.start(actor="tester", occurred_at=_OCCURRED_AT)
    return review


def _command(
    identity: DomainIdentity[ReviewId],
    *,
    expected_persisted_version: AggregateVersion = _INITIAL_VERSION,
    reason: str = "no longer needed",
    actor: str = "tester",
    occurred_at: datetime = _OCCURRED_AT,
    correlation_id: str | None = None,
) -> CancelReviewCommand:
    return CancelReviewCommand(
        identity=identity,
        expected_persisted_version=expected_persisted_version,
        reason=reason,
        actor=actor,
        occurred_at=occurred_at,
        correlation_id=correlation_id,
    )


class _RecordingReviewRepository:
    """Records every `get()`/`save()` call; conforms structurally to `ReviewRepository`."""

    def __init__(
        self,
        loaded: LoadedAggregate[Review] | list[LoadedAggregate[Review]],
        save_result: SaveResult,
    ) -> None:
        self._loaded_sequence = loaded if isinstance(loaded, list) else None
        self._loaded_single = None if isinstance(loaded, list) else loaded
        self._save_result = save_result
        self.get_calls: list[DomainIdentity[ReviewId]] = []
        self.save_calls: list[tuple[Review, AggregateVersion]] = []

    def get(self, identity: DomainIdentity[ReviewId]) -> LoadedAggregate[Review]:
        self.get_calls.append(identity)
        if self._loaded_sequence is not None:
            return self._loaded_sequence[len(self.get_calls) - 1]
        assert self._loaded_single is not None
        return self._loaded_single

    def add(self, aggregate: Review) -> SaveResult:
        raise AssertionError("add() must not be called by CancelReviewHandler")

    def save(
        self, aggregate: Review, *, expected_persisted_version: AggregateVersion
    ) -> SaveResult:
        self.save_calls.append((aggregate, expected_persisted_version))
        return self._save_result


class _FailingGetReviewRepository:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc
        self.get_calls = 0
        self.save_calls = 0

    def get(self, identity: DomainIdentity[ReviewId]) -> object:
        self.get_calls += 1
        raise self._exc

    def add(self, aggregate: Review) -> object:
        raise AssertionError("add() must not be called")

    def save(self, aggregate: Review, *, expected_persisted_version: object) -> object:
        self.save_calls += 1
        raise AssertionError("save() must not be called after get() failure")


class _FailingSaveReviewRepository:
    def __init__(self, loaded: LoadedAggregate[Review], exc: Exception) -> None:
        self._loaded = loaded
        self._exc = exc
        self.get_calls = 0
        self.save_calls = 0

    def get(self, identity: DomainIdentity[ReviewId]) -> LoadedAggregate[Review]:
        self.get_calls += 1
        return self._loaded

    def add(self, aggregate: Review) -> object:
        raise AssertionError("add() must not be called")

    def save(self, aggregate: Review, *, expected_persisted_version: AggregateVersion) -> object:
        self.save_calls += 1
        raise self._exc


def _handler(repository: object) -> CancelReviewHandler:
    return CancelReviewHandler(review_repository=repository)  # type: ignore[arg-type]


# --- A. Command contract tests ---


def test_command_preserves_all_six_fields_unchanged() -> None:
    identity = _identity()
    version = AggregateVersion(3)
    command = CancelReviewCommand(
        identity=identity,
        expected_persisted_version=version,
        reason="scope withdrawn",
        actor="alice",
        occurred_at=_OCCURRED_AT,
        correlation_id="corr-1",
    )

    assert command.identity is identity
    assert command.expected_persisted_version is version
    assert command.reason == "scope withdrawn"
    assert command.actor == "alice"
    assert command.occurred_at == _OCCURRED_AT
    assert command.correlation_id == "corr-1"


def test_command_optional_correlation_id_defaults_to_none() -> None:
    command = _command(_identity())

    assert command.correlation_id is None


def test_command_contains_no_additional_fields() -> None:
    assert set(CancelReviewCommand.__slots__) == {  # type: ignore[attr-defined]
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
    construction -- Review.cancel() itself validates later."""
    command = CancelReviewCommand(
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
        aggregate=_assigned_review(identity), persisted_version=AggregateVersion.initial()
    )
    save_result = SaveResult(operation=SaveOperation.UPDATED, persisted_version=AggregateVersion(1))
    repository: ReviewRepository = _RecordingReviewRepository(  # type: ignore[assignment]
        loaded, save_result
    )
    handler: CancelReviewHandler = _handler(repository)
    assert handler is not None


def test_get_is_called_exactly_once_with_exact_identity() -> None:
    identity = _identity()
    loaded = LoadedAggregate(
        aggregate=_assigned_review(identity), persisted_version=AggregateVersion.initial()
    )
    save_result = SaveResult(operation=SaveOperation.UPDATED, persisted_version=AggregateVersion(1))
    repository = _RecordingReviewRepository(loaded, save_result)
    handler = _handler(repository)
    command = _command(identity)

    handler.handle(command)

    assert len(repository.get_calls) == 1
    assert repository.get_calls[0] is command.identity


def test_cancel_called_with_exact_command_arguments_from_assigned() -> None:
    identity = _identity()
    review = _assigned_review(identity)
    loaded = LoadedAggregate(aggregate=review, persisted_version=AggregateVersion.initial())
    save_result = SaveResult(operation=SaveOperation.UPDATED, persisted_version=AggregateVersion(1))
    repository = _RecordingReviewRepository(loaded, save_result)
    handler = _handler(repository)
    command = _command(
        identity,
        reason="assignment withdrawn",
        actor="bob",
        occurred_at=_OCCURRED_AT,
        correlation_id="corr-42",
    )

    handler.handle(command)

    assert review.state is ReviewLifecycleState.CANCELLED
    record = review.transition_history[-1]
    assert record.actor == "bob"
    assert record.occurred_at == _OCCURRED_AT
    assert record.correlation_id == "corr-42"
    assert record.reason == "assignment withdrawn"


def test_cancel_from_in_progress_succeeds() -> None:
    identity = _identity()
    review = _in_progress_review(identity)
    loaded = LoadedAggregate(aggregate=review, persisted_version=review.version)
    save_result = SaveResult(operation=SaveOperation.UPDATED, persisted_version=AggregateVersion(2))
    repository = _RecordingReviewRepository(loaded, save_result)
    handler = _handler(repository)
    command = _command(
        identity, expected_persisted_version=review.version, reason="withdrawn mid-review"
    )

    handler.handle(command)

    assert review.state is ReviewLifecycleState.CANCELLED
    assert review.transition_history[-1].from_state == "IN_PROGRESS"


def test_save_called_exactly_once_with_mutated_aggregate_and_command_version() -> None:
    identity = _identity()
    review = _assigned_review(identity)
    loaded = LoadedAggregate(aggregate=review, persisted_version=AggregateVersion.initial())
    save_result = SaveResult(operation=SaveOperation.UPDATED, persisted_version=AggregateVersion(1))
    repository = _RecordingReviewRepository(loaded, save_result)
    handler = _handler(repository)
    command = _command(identity, expected_persisted_version=AggregateVersion.initial())

    handler.handle(command)

    assert len(repository.save_calls) == 1
    saved_aggregate, saved_expected_version = repository.save_calls[0]
    assert saved_aggregate is review
    assert saved_expected_version is command.expected_persisted_version


def test_save_receives_command_version_not_loaded_persisted_version() -> None:
    """Critical: expected_persisted_version passed to save() must come from the
    command, never from loaded.persisted_version -- even when they differ."""
    identity = _identity()
    review = _assigned_review(identity)
    loaded = LoadedAggregate(aggregate=review, persisted_version=AggregateVersion(9))
    save_result = SaveResult(operation=SaveOperation.UPDATED, persisted_version=AggregateVersion(1))
    repository = _RecordingReviewRepository(loaded, save_result)
    handler = _handler(repository)
    stale_version = AggregateVersion(0)
    command = _command(identity, expected_persisted_version=stale_version)

    handler.handle(command)

    _, saved_expected_version = repository.save_calls[0]
    assert saved_expected_version is stale_version
    assert saved_expected_version != loaded.persisted_version


def test_no_add_call_occurs() -> None:
    identity = _identity()
    loaded = LoadedAggregate(
        aggregate=_assigned_review(identity), persisted_version=AggregateVersion.initial()
    )
    save_result = SaveResult(operation=SaveOperation.UPDATED, persisted_version=AggregateVersion(1))
    repository = _RecordingReviewRepository(loaded, save_result)
    handler = _handler(repository)

    handler.handle(_command(identity))  # would raise if add() were called


def test_no_second_get_or_save_occurs() -> None:
    identity = _identity()
    loaded = LoadedAggregate(
        aggregate=_assigned_review(identity), persisted_version=AggregateVersion.initial()
    )
    save_result = SaveResult(operation=SaveOperation.UPDATED, persisted_version=AggregateVersion(1))
    repository = _RecordingReviewRepository(loaded, save_result)
    handler = _handler(repository)

    handler.handle(_command(identity))

    assert len(repository.get_calls) == 1
    assert len(repository.save_calls) == 1


def test_returned_object_is_the_exact_save_result() -> None:
    identity = _identity()
    loaded = LoadedAggregate(
        aggregate=_assigned_review(identity), persisted_version=AggregateVersion.initial()
    )
    save_result = SaveResult(operation=SaveOperation.UPDATED, persisted_version=AggregateVersion(1))
    repository = _RecordingReviewRepository(loaded, save_result)
    handler = _handler(repository)

    result = handler.handle(_command(identity))

    assert result is save_result


def test_handler_is_invocable_through_command_entry_point() -> None:
    identity = _identity()
    loaded = LoadedAggregate(
        aggregate=_assigned_review(identity), persisted_version=AggregateVersion.initial()
    )
    save_result = SaveResult(operation=SaveOperation.UPDATED, persisted_version=AggregateVersion(1))
    repository = _RecordingReviewRepository(loaded, save_result)
    handler = _handler(repository)
    entry_point = CommandEntryPoint(handler)

    result = entry_point(_command(identity))

    assert result is save_result
    assert len(repository.get_calls) == 1
    assert len(repository.save_calls) == 1


# --- C. Transition-history proof ---


def test_successful_cancel_produces_exactly_one_transition_record() -> None:
    identity = _identity()
    review = _assigned_review(identity)
    version_before = review.version
    history_length_before = len(review.transition_history)
    loaded = LoadedAggregate(aggregate=review, persisted_version=AggregateVersion.initial())
    save_result = SaveResult(operation=SaveOperation.UPDATED, persisted_version=AggregateVersion(1))
    repository = _RecordingReviewRepository(loaded, save_result)
    handler = _handler(repository)
    command = _command(identity, reason="abandoned", actor="carol", correlation_id="corr-99")

    handler.handle(command)

    assert review.state is ReviewLifecycleState.CANCELLED
    assert review.version == version_before.next()
    assert len(review.transition_history) == history_length_before + 1
    record = review.transition_history[-1]
    assert record.from_state == "ASSIGNED"
    assert record.to_state == "CANCELLED"
    assert record.version == review.version
    assert record.actor == "carol"
    assert record.correlation_id == "corr-99"
    assert record.reason == "abandoned"


# --- D. Domain-failure tests (two distinct non-conflict failure modes) ---


def test_invalid_state_completed_propagates_and_save_never_called() -> None:
    identity = _identity()
    review = _in_progress_review(identity)
    review.add_finding(text="a real finding")
    review.complete(
        disposition=ReviewDisposition.ACCEPTED,
        final_disposition_rationale="all criteria satisfied",
        actor="tester",
        occurred_at=_OCCURRED_AT,
    )
    loaded = LoadedAggregate(aggregate=review, persisted_version=review.version)
    save_result = SaveResult(operation=SaveOperation.UPDATED, persisted_version=AggregateVersion(9))
    repository = _RecordingReviewRepository(loaded, save_result)
    handler = _handler(repository)

    with pytest.raises(ValueError, match="cannot transition from COMPLETED"):
        handler.handle(_command(identity, expected_persisted_version=review.version))

    assert repository.save_calls == []


def test_empty_reason_propagates_and_save_never_called() -> None:
    identity = _identity()
    review = _assigned_review(identity)
    loaded = LoadedAggregate(aggregate=review, persisted_version=review.version)
    save_result = SaveResult(operation=SaveOperation.UPDATED, persisted_version=AggregateVersion(9))
    repository = _RecordingReviewRepository(loaded, save_result)
    handler = _handler(repository)

    with pytest.raises(ValueError, match="must be non-empty"):
        handler.handle(_command(identity, expected_persisted_version=review.version, reason="   "))

    assert repository.save_calls == []


# --- E. get()-failure tests ---


def test_aggregate_not_found_from_get_propagates_with_identity_preserved() -> None:
    exc = AggregateNotFound(aggregate_kind="Review", identity=_identity())
    repository = _FailingGetReviewRepository(exc)
    handler = _handler(repository)

    with pytest.raises(AggregateNotFound) as excinfo:
        handler.handle(_command(_identity()))

    assert excinfo.value is exc
    assert repository.get_calls == 1
    assert repository.save_calls == 0


def test_arbitrary_get_exception_propagates_unchanged() -> None:
    exc = RuntimeError("unexpected get() failure")
    repository = _FailingGetReviewRepository(exc)
    handler = _handler(repository)

    with pytest.raises(RuntimeError) as excinfo:
        handler.handle(_command(_identity()))

    assert excinfo.value is exc
    assert repository.save_calls == 0


# --- F. save()-failure tests ---


def test_optimistic_concurrency_conflict_from_save_propagates_unchanged() -> None:
    identity = _identity()
    review = _assigned_review(identity)
    exc = OptimisticConcurrencyConflict(
        aggregate_kind="Review",
        identity=identity,
        expected_persisted_version=AggregateVersion(0),
        aggregate_current_version=AggregateVersion(1),
        actual_persisted_version=AggregateVersion(1),
    )
    loaded = LoadedAggregate(aggregate=review, persisted_version=AggregateVersion.initial())
    repository = _FailingSaveReviewRepository(loaded, exc)
    handler = _handler(repository)

    with pytest.raises(OptimisticConcurrencyConflict) as excinfo:
        handler.handle(_command(identity))

    assert excinfo.value is exc
    assert repository.get_calls == 1
    assert repository.save_calls == 1


def test_arbitrary_save_exception_propagates_with_identity_preserved() -> None:
    identity = _identity()
    review = _assigned_review(identity)
    loaded = LoadedAggregate(aggregate=review, persisted_version=AggregateVersion.initial())
    exc = RuntimeError("unexpected save() failure")
    repository = _FailingSaveReviewRepository(loaded, exc)
    handler = _handler(repository)

    with pytest.raises(RuntimeError) as excinfo:
        handler.handle(_command(identity))

    assert excinfo.value is exc
    assert repository.get_calls == 1
    assert repository.save_calls == 1
