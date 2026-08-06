"""MILESTONE-047 behavioral tests for `CancelCampaignCommand`/`CancelCampaignHandler`.

Proves the frozen load-mutate-save flow: call `CampaignRepository.get()`
exactly once, invoke `Campaign.cancel()` exactly once with the command's
data unchanged, then call `CampaignRepository.save()` exactly once with the
mutated aggregate and the command's own `expected_persisted_version` --
never `loaded.persisted_version`. Also proves transparent failure
propagation for every collaborator, including the three distinct
non-conflict domain failure modes `cancel()`'s state-dependent conditional
validation introduces (invalid state, missing-required reason,
present-when-must-be-empty reason) -- the first transition in this
project's lineage with more than two non-conflict domain failure modes --
and that the handler is invocable through the frozen `CommandEntryPoint`.

Uses deterministic recording fakes/stubs, not mocks, for stronger evidence.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from empirical_platform.application.command import CommandEntryPoint
from empirical_platform.campaign.aggregate import Campaign, CampaignScopeStatement
from empirical_platform.campaign.lifecycle import CampaignLifecycleState
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import CampaignId
from empirical_platform.shared.contracts.repository import (
    AggregateNotFound,
    LoadedAggregate,
    OptimisticConcurrencyConflict,
    SaveOperation,
    SaveResult,
)
from empirical_platform.shared.domain.versioning import AggregateVersion
from empirical_platform.shared.identifiers import RuntimeIdentifier
from empirical_platform.usecases.cancel_campaign import (
    CancelCampaignCommand,
    CancelCampaignHandler,
)

if TYPE_CHECKING:
    from empirical_platform.campaign.repository import CampaignRepository

_RUNTIME_ID_VALUE = "12345678-1234-4321-8765-1234567890ab"
_OCCURRED_AT = datetime(2026, 1, 1, tzinfo=UTC)
_INITIAL_VERSION = AggregateVersion.initial()


def _identity(governance_id: str = "CAMP-0001") -> DomainIdentity[CampaignId]:
    return DomainIdentity(
        governance_id=CampaignId(governance_id),
        runtime_id=RuntimeIdentifier(_RUNTIME_ID_VALUE),
    )


def _draft_campaign(identity: DomainIdentity[CampaignId]) -> Campaign:
    return Campaign(
        identity=identity, scope_statement=CampaignScopeStatement("a real scope statement")
    )


def _authorized_campaign(identity: DomainIdentity[CampaignId]) -> Campaign:
    campaign = _draft_campaign(identity)
    campaign.prepare_for_authorization(actor="tester", occurred_at=_OCCURRED_AT)
    campaign.record_authorization(reason="approved", actor="tester", occurred_at=_OCCURRED_AT)
    return campaign


def _command(
    identity: DomainIdentity[CampaignId],
    *,
    expected_persisted_version: AggregateVersion = _INITIAL_VERSION,
    actor: str = "tester",
    occurred_at: datetime = _OCCURRED_AT,
    reason: str | None = None,
    correlation_id: str | None = None,
) -> CancelCampaignCommand:
    return CancelCampaignCommand(
        identity=identity,
        expected_persisted_version=expected_persisted_version,
        actor=actor,
        occurred_at=occurred_at,
        reason=reason,
        correlation_id=correlation_id,
    )


class _RecordingCampaignRepository:
    """Records every `get()`/`save()` call; conforms structurally to `CampaignRepository`."""

    def __init__(
        self,
        loaded: LoadedAggregate[Campaign] | list[LoadedAggregate[Campaign]],
        save_result: SaveResult,
    ) -> None:
        self._loaded_sequence = loaded if isinstance(loaded, list) else None
        self._loaded_single = None if isinstance(loaded, list) else loaded
        self._save_result = save_result
        self.get_calls: list[DomainIdentity[CampaignId]] = []
        self.save_calls: list[tuple[Campaign, AggregateVersion]] = []

    def get(self, identity: DomainIdentity[CampaignId]) -> LoadedAggregate[Campaign]:
        self.get_calls.append(identity)
        if self._loaded_sequence is not None:
            return self._loaded_sequence[len(self.get_calls) - 1]
        assert self._loaded_single is not None
        return self._loaded_single

    def add(self, aggregate: Campaign) -> SaveResult:
        raise AssertionError("add() must not be called by CancelCampaignHandler")

    def save(
        self, aggregate: Campaign, *, expected_persisted_version: AggregateVersion
    ) -> SaveResult:
        self.save_calls.append((aggregate, expected_persisted_version))
        return self._save_result


class _FailingGetCampaignRepository:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc
        self.get_calls = 0
        self.save_calls = 0

    def get(self, identity: DomainIdentity[CampaignId]) -> object:
        self.get_calls += 1
        raise self._exc

    def add(self, aggregate: Campaign) -> object:
        raise AssertionError("add() must not be called")

    def save(self, aggregate: Campaign, *, expected_persisted_version: object) -> object:
        self.save_calls += 1
        raise AssertionError("save() must not be called after get() failure")


class _FailingSaveCampaignRepository:
    def __init__(self, loaded: LoadedAggregate[Campaign], exc: Exception) -> None:
        self._loaded = loaded
        self._exc = exc
        self.get_calls = 0
        self.save_calls = 0

    def get(self, identity: DomainIdentity[CampaignId]) -> LoadedAggregate[Campaign]:
        self.get_calls += 1
        return self._loaded

    def add(self, aggregate: Campaign) -> object:
        raise AssertionError("add() must not be called")

    def save(self, aggregate: Campaign, *, expected_persisted_version: AggregateVersion) -> object:
        self.save_calls += 1
        raise self._exc


def _handler(repository: object) -> CancelCampaignHandler:
    return CancelCampaignHandler(campaign_repository=repository)  # type: ignore[arg-type]


# --- A. Command contract tests ---


def test_command_preserves_all_six_fields_unchanged() -> None:
    identity = _identity()
    version = AggregateVersion(3)
    command = CancelCampaignCommand(
        identity=identity,
        expected_persisted_version=version,
        actor="alice",
        occurred_at=_OCCURRED_AT,
        reason="no longer needed",
        correlation_id="corr-1",
    )

    assert command.identity is identity
    assert command.expected_persisted_version is version
    assert command.actor == "alice"
    assert command.occurred_at == _OCCURRED_AT
    assert command.reason == "no longer needed"
    assert command.correlation_id == "corr-1"


def test_command_optional_reason_and_correlation_id_default_to_none() -> None:
    command = _command(_identity())

    assert command.reason is None
    assert command.correlation_id is None


def test_command_contains_no_additional_fields() -> None:
    assert set(CancelCampaignCommand.__slots__) == {  # type: ignore[attr-defined]
        "identity",
        "expected_persisted_version",
        "actor",
        "occurred_at",
        "reason",
        "correlation_id",
    }


def test_command_is_immutable() -> None:
    command = _command(_identity())
    with pytest.raises(AttributeError):
        command.actor = "someone-else"  # type: ignore[misc]


def test_command_construction_performs_no_business_validation() -> None:
    """No duplicated domain validation; reason=None is always constructible
    regardless of the eventual aggregate's state -- Campaign.cancel() itself
    decides whether None is acceptable."""
    command = CancelCampaignCommand(
        identity=_identity(),
        expected_persisted_version=AggregateVersion.initial(),
        actor="",
        occurred_at=_OCCURRED_AT,
        reason=None,
    )
    assert command.actor == ""
    assert command.reason is None


# --- B. Handler success tests ---


def test_typed_conformance_check() -> None:
    identity = _identity()
    loaded = LoadedAggregate(
        aggregate=_draft_campaign(identity), persisted_version=AggregateVersion.initial()
    )
    save_result = SaveResult(operation=SaveOperation.UPDATED, persisted_version=AggregateVersion(1))
    repository: CampaignRepository = _RecordingCampaignRepository(  # type: ignore[assignment]
        loaded, save_result
    )
    handler: CancelCampaignHandler = _handler(repository)
    assert handler is not None


def test_get_is_called_exactly_once_with_exact_identity() -> None:
    identity = _identity()
    loaded = LoadedAggregate(
        aggregate=_draft_campaign(identity), persisted_version=AggregateVersion.initial()
    )
    save_result = SaveResult(operation=SaveOperation.UPDATED, persisted_version=AggregateVersion(1))
    repository = _RecordingCampaignRepository(loaded, save_result)
    handler = _handler(repository)
    command = _command(identity)

    handler.handle(command)

    assert len(repository.get_calls) == 1
    assert repository.get_calls[0] is command.identity


def test_cancel_called_with_exact_command_arguments_from_draft() -> None:
    identity = _identity()
    campaign = _draft_campaign(identity)
    loaded = LoadedAggregate(aggregate=campaign, persisted_version=AggregateVersion.initial())
    save_result = SaveResult(operation=SaveOperation.UPDATED, persisted_version=AggregateVersion(1))
    repository = _RecordingCampaignRepository(loaded, save_result)
    handler = _handler(repository)
    command = _command(
        identity,
        actor="bob",
        occurred_at=_OCCURRED_AT,
        reason="scope abandoned",
        correlation_id="corr-42",
    )

    handler.handle(command)

    assert campaign.state is CampaignLifecycleState.CANCELLED
    record = campaign.transition_history[-1]
    assert record.actor == "bob"
    assert record.occurred_at == _OCCURRED_AT
    assert record.correlation_id == "corr-42"
    assert record.reason == "scope abandoned"


def test_cancel_from_authorized_requires_reason_and_succeeds_when_present() -> None:
    identity = _identity()
    campaign = _authorized_campaign(identity)
    loaded = LoadedAggregate(aggregate=campaign, persisted_version=campaign.version)
    save_result = SaveResult(operation=SaveOperation.UPDATED, persisted_version=AggregateVersion(3))
    repository = _RecordingCampaignRepository(loaded, save_result)
    handler = _handler(repository)
    command = _command(
        identity, expected_persisted_version=campaign.version, reason="authorization revoked"
    )

    handler.handle(command)

    assert campaign.state is CampaignLifecycleState.CANCELLED
    assert campaign.transition_history[-1].reason == "authorization revoked"


def test_save_called_exactly_once_with_mutated_aggregate_and_command_version() -> None:
    identity = _identity()
    campaign = _draft_campaign(identity)
    loaded = LoadedAggregate(aggregate=campaign, persisted_version=AggregateVersion.initial())
    save_result = SaveResult(operation=SaveOperation.UPDATED, persisted_version=AggregateVersion(1))
    repository = _RecordingCampaignRepository(loaded, save_result)
    handler = _handler(repository)
    command = _command(identity, expected_persisted_version=AggregateVersion.initial())

    handler.handle(command)

    assert len(repository.save_calls) == 1
    saved_aggregate, saved_expected_version = repository.save_calls[0]
    assert saved_aggregate is campaign
    assert saved_expected_version is command.expected_persisted_version


def test_save_receives_command_version_not_loaded_persisted_version() -> None:
    """Critical: expected_persisted_version passed to save() must come from the
    command, never from loaded.persisted_version -- even when they differ."""
    identity = _identity()
    campaign = _draft_campaign(identity)
    loaded = LoadedAggregate(aggregate=campaign, persisted_version=AggregateVersion(9))
    save_result = SaveResult(operation=SaveOperation.UPDATED, persisted_version=AggregateVersion(1))
    repository = _RecordingCampaignRepository(loaded, save_result)
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
        aggregate=_draft_campaign(identity), persisted_version=AggregateVersion.initial()
    )
    save_result = SaveResult(operation=SaveOperation.UPDATED, persisted_version=AggregateVersion(1))
    repository = _RecordingCampaignRepository(loaded, save_result)
    handler = _handler(repository)

    handler.handle(_command(identity))  # would raise if add() were called


def test_no_second_get_or_save_occurs() -> None:
    identity = _identity()
    loaded = LoadedAggregate(
        aggregate=_draft_campaign(identity), persisted_version=AggregateVersion.initial()
    )
    save_result = SaveResult(operation=SaveOperation.UPDATED, persisted_version=AggregateVersion(1))
    repository = _RecordingCampaignRepository(loaded, save_result)
    handler = _handler(repository)

    handler.handle(_command(identity))

    assert len(repository.get_calls) == 1
    assert len(repository.save_calls) == 1


def test_returned_object_is_the_exact_save_result() -> None:
    identity = _identity()
    loaded = LoadedAggregate(
        aggregate=_draft_campaign(identity), persisted_version=AggregateVersion.initial()
    )
    save_result = SaveResult(operation=SaveOperation.UPDATED, persisted_version=AggregateVersion(1))
    repository = _RecordingCampaignRepository(loaded, save_result)
    handler = _handler(repository)

    result = handler.handle(_command(identity))

    assert result is save_result


def test_handler_is_invocable_through_command_entry_point() -> None:
    identity = _identity()
    loaded = LoadedAggregate(
        aggregate=_draft_campaign(identity), persisted_version=AggregateVersion.initial()
    )
    save_result = SaveResult(operation=SaveOperation.UPDATED, persisted_version=AggregateVersion(1))
    repository = _RecordingCampaignRepository(loaded, save_result)
    handler = _handler(repository)
    entry_point = CommandEntryPoint(handler)

    result = entry_point(_command(identity))

    assert result is save_result
    assert len(repository.get_calls) == 1
    assert len(repository.save_calls) == 1


# --- C. Transition-history proof ---


def test_successful_cancel_produces_exactly_one_transition_record() -> None:
    identity = _identity()
    campaign = _draft_campaign(identity)
    version_before = campaign.version
    history_length_before = len(campaign.transition_history)
    loaded = LoadedAggregate(aggregate=campaign, persisted_version=AggregateVersion.initial())
    save_result = SaveResult(operation=SaveOperation.UPDATED, persisted_version=AggregateVersion(1))
    repository = _RecordingCampaignRepository(loaded, save_result)
    handler = _handler(repository)
    command = _command(identity, reason="abandoned", actor="carol", correlation_id="corr-99")

    handler.handle(command)

    assert campaign.state is CampaignLifecycleState.CANCELLED
    assert campaign.version == version_before.next()
    assert len(campaign.transition_history) == history_length_before + 1
    record = campaign.transition_history[-1]
    assert record.from_state == "DRAFT"
    assert record.to_state == "CANCELLED"
    assert record.version == campaign.version
    assert record.actor == "carol"
    assert record.correlation_id == "corr-99"
    assert record.reason == "abandoned"


# --- D. Domain-failure tests (three distinct non-conflict failure modes) ---


def test_invalid_state_completed_propagates_and_save_never_called() -> None:
    identity = _identity()
    campaign = _authorized_campaign(identity)
    campaign.activate(reason="go", actor="tester", occurred_at=_OCCURRED_AT)
    campaign.complete(reason="done", actor="tester", occurred_at=_OCCURRED_AT)
    loaded = LoadedAggregate(aggregate=campaign, persisted_version=campaign.version)
    save_result = SaveResult(operation=SaveOperation.UPDATED, persisted_version=AggregateVersion(9))
    repository = _RecordingCampaignRepository(loaded, save_result)
    handler = _handler(repository)

    with pytest.raises(ValueError, match="cannot transition from COMPLETED"):
        handler.handle(_command(identity, expected_persisted_version=campaign.version))

    assert repository.save_calls == []


def test_missing_reason_when_required_raises_type_error_and_save_never_called() -> None:
    identity = _identity()
    campaign = _authorized_campaign(identity)
    loaded = LoadedAggregate(aggregate=campaign, persisted_version=campaign.version)
    save_result = SaveResult(operation=SaveOperation.UPDATED, persisted_version=AggregateVersion(9))
    repository = _RecordingCampaignRepository(loaded, save_result)
    handler = _handler(repository)

    with pytest.raises(TypeError, match="cancellation reason must be a string"):
        handler.handle(_command(identity, expected_persisted_version=campaign.version, reason=None))

    assert repository.save_calls == []


def test_empty_reason_when_optional_raises_value_error_and_save_never_called() -> None:
    identity = _identity()
    campaign = _draft_campaign(identity)
    loaded = LoadedAggregate(aggregate=campaign, persisted_version=campaign.version)
    save_result = SaveResult(operation=SaveOperation.UPDATED, persisted_version=AggregateVersion(9))
    repository = _RecordingCampaignRepository(loaded, save_result)
    handler = _handler(repository)

    with pytest.raises(ValueError, match="reason must be non-empty"):
        handler.handle(_command(identity, expected_persisted_version=campaign.version, reason="  "))

    assert repository.save_calls == []


# --- E. get()-failure tests ---


def test_aggregate_not_found_from_get_propagates_with_identity_preserved() -> None:
    exc = AggregateNotFound(aggregate_kind="Campaign", identity=_identity())
    repository = _FailingGetCampaignRepository(exc)
    handler = _handler(repository)

    with pytest.raises(AggregateNotFound) as excinfo:
        handler.handle(_command(_identity()))

    assert excinfo.value is exc
    assert repository.get_calls == 1
    assert repository.save_calls == 0


def test_arbitrary_get_exception_propagates_unchanged() -> None:
    exc = RuntimeError("unexpected get() failure")
    repository = _FailingGetCampaignRepository(exc)
    handler = _handler(repository)

    with pytest.raises(RuntimeError) as excinfo:
        handler.handle(_command(_identity()))

    assert excinfo.value is exc
    assert repository.save_calls == 0


# --- F. save()-failure tests ---


def test_optimistic_concurrency_conflict_from_save_propagates_unchanged() -> None:
    identity = _identity()
    campaign = _draft_campaign(identity)
    exc = OptimisticConcurrencyConflict(
        aggregate_kind="Campaign",
        identity=identity,
        expected_persisted_version=AggregateVersion(0),
        aggregate_current_version=AggregateVersion(1),
        actual_persisted_version=AggregateVersion(1),
    )
    loaded = LoadedAggregate(aggregate=campaign, persisted_version=AggregateVersion.initial())
    repository = _FailingSaveCampaignRepository(loaded, exc)
    handler = _handler(repository)

    with pytest.raises(OptimisticConcurrencyConflict) as excinfo:
        handler.handle(_command(identity))

    assert excinfo.value is exc
    assert repository.get_calls == 1
    assert repository.save_calls == 1


def test_arbitrary_save_exception_propagates_with_identity_preserved() -> None:
    identity = _identity()
    campaign = _draft_campaign(identity)
    loaded = LoadedAggregate(aggregate=campaign, persisted_version=AggregateVersion.initial())
    exc = RuntimeError("unexpected save() failure")
    repository = _FailingSaveCampaignRepository(loaded, exc)
    handler = _handler(repository)

    with pytest.raises(RuntimeError) as excinfo:
        handler.handle(_command(identity))

    assert excinfo.value is exc
    assert repository.get_calls == 1
    assert repository.save_calls == 1
