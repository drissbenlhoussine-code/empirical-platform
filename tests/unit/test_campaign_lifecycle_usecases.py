"""MILESTONE-056 behavioral tests for the six new Campaign lifecycle usecases:
`revise_campaign_scope_statement`, `record_campaign_authorization`,
`activate_campaign`, `suspend_campaign`, `resume_campaign`,
`complete_campaign`.

Each transition usecase mirrors the exact frozen load-mutate-save pattern
already proven by `prepare_campaign_for_authorization` (M032) and
`cancel_campaign` (M047): call `CampaignRepository.get()` exactly once,
invoke the corresponding `Campaign` domain method exactly once with the
command's data unchanged, then call `CampaignRepository.save()` exactly
once with the mutated aggregate and the command's own
`expected_persisted_version` -- never `loaded.persisted_version`.
Transparent failure propagation is proven once per usecase, not with
exhaustive breadth, since the underlying mechanism is identical and already
proven by M032/M047 (per this milestone's own instruction to reuse
established test infrastructure without chasing test quantity).

Uses deterministic recording fakes/stubs, not mocks, for stronger evidence.
"""

from __future__ import annotations

from datetime import UTC, datetime

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
from empirical_platform.usecases.activate_campaign import (
    ActivateCampaignCommand,
    ActivateCampaignHandler,
)
from empirical_platform.usecases.complete_campaign import (
    CompleteCampaignCommand,
    CompleteCampaignHandler,
)
from empirical_platform.usecases.record_campaign_authorization import (
    RecordCampaignAuthorizationCommand,
    RecordCampaignAuthorizationHandler,
)
from empirical_platform.usecases.resume_campaign import (
    ResumeCampaignCommand,
    ResumeCampaignHandler,
)
from empirical_platform.usecases.revise_campaign_scope_statement import (
    ReviseCampaignScopeStatementCommand,
    ReviseCampaignScopeStatementHandler,
)
from empirical_platform.usecases.suspend_campaign import (
    SuspendCampaignCommand,
    SuspendCampaignHandler,
)

_RUNTIME_ID_VALUE = "12345678-1234-4321-8765-1234567890ab"
_OCCURRED_AT = datetime(2026, 1, 1, tzinfo=UTC)


def _identity() -> DomainIdentity[CampaignId]:
    return DomainIdentity(
        governance_id=CampaignId("CAMP-0001"), runtime_id=RuntimeIdentifier(_RUNTIME_ID_VALUE)
    )


def _campaign(identity: DomainIdentity[CampaignId]) -> Campaign:
    return Campaign(identity=identity, scope_statement=CampaignScopeStatement("initial scope"))


def _ready_campaign(identity: DomainIdentity[CampaignId]) -> Campaign:
    campaign = _campaign(identity)
    campaign.prepare_for_authorization(actor="seed", occurred_at=_OCCURRED_AT)
    return campaign


def _authorized_campaign(identity: DomainIdentity[CampaignId]) -> Campaign:
    campaign = _ready_campaign(identity)
    campaign.record_authorization(reason="seed", actor="seed", occurred_at=_OCCURRED_AT)
    return campaign


def _active_campaign(identity: DomainIdentity[CampaignId]) -> Campaign:
    campaign = _authorized_campaign(identity)
    campaign.activate(reason="seed", actor="seed", occurred_at=_OCCURRED_AT)
    return campaign


def _suspended_campaign(identity: DomainIdentity[CampaignId]) -> Campaign:
    campaign = _active_campaign(identity)
    campaign.suspend(reason="seed", actor="seed", occurred_at=_OCCURRED_AT)
    return campaign


class _RecordingCampaignRepository:
    def __init__(self, loaded: LoadedAggregate[Campaign], save_result: SaveResult) -> None:
        self._loaded = loaded
        self._save_result = save_result
        self.get_calls: list[DomainIdentity[CampaignId]] = []
        self.save_calls: list[tuple[Campaign, AggregateVersion]] = []

    def get(self, identity: DomainIdentity[CampaignId]) -> LoadedAggregate[Campaign]:
        self.get_calls.append(identity)
        return self._loaded

    def add(self, aggregate: Campaign) -> SaveResult:
        raise AssertionError("add() must not be called")

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


def _save_result(version: int = 1) -> SaveResult:
    return SaveResult(operation=SaveOperation.UPDATED, persisted_version=AggregateVersion(version))


def _occ_conflict(identity: DomainIdentity[CampaignId]) -> OptimisticConcurrencyConflict:
    return OptimisticConcurrencyConflict(
        aggregate_kind="Campaign",
        identity=identity,
        expected_persisted_version=AggregateVersion(0),
        aggregate_current_version=AggregateVersion(1),
        actual_persisted_version=AggregateVersion(1),
    )


# ---------------------------------------------------------------------------
# revise_campaign_scope_statement
# ---------------------------------------------------------------------------


def test_revise_scope_statement_replaces_value_and_saves_with_command_version() -> None:
    identity = _identity()
    campaign = _campaign(identity)
    loaded = LoadedAggregate(aggregate=campaign, persisted_version=AggregateVersion.initial())
    repository = _RecordingCampaignRepository(loaded, _save_result(1))
    handler = ReviseCampaignScopeStatementHandler(campaign_repository=repository)
    command = ReviseCampaignScopeStatementCommand(
        identity=identity,
        expected_persisted_version=AggregateVersion.initial(),
        scope_statement="a revised scope statement",
    )

    CommandEntryPoint(handler)(command)

    assert str(campaign.scope_statement) == "a revised scope statement"
    assert campaign.state is CampaignLifecycleState.DRAFT
    _, saved_version = repository.save_calls[0]
    assert saved_version is command.expected_persisted_version


def test_revise_scope_statement_outside_draft_propagates_and_save_never_called() -> None:
    identity = _identity()
    campaign = _ready_campaign(identity)  # READY_FOR_AUTHORIZATION, not DRAFT
    loaded = LoadedAggregate(aggregate=campaign, persisted_version=AggregateVersion(1))
    repository = _RecordingCampaignRepository(loaded, _save_result())
    handler = ReviseCampaignScopeStatementHandler(campaign_repository=repository)
    command = ReviseCampaignScopeStatementCommand(
        identity=identity,
        expected_persisted_version=AggregateVersion(1),
        scope_statement="should never persist",
    )

    with pytest.raises(ValueError, match="may be revised only while DRAFT"):
        handler.handle(command)

    assert repository.save_calls == []


def test_revise_scope_statement_propagates_optimistic_concurrency_conflict() -> None:
    identity = _identity()
    campaign = _campaign(identity)
    loaded = LoadedAggregate(aggregate=campaign, persisted_version=AggregateVersion.initial())
    exc = _occ_conflict(identity)
    repository = _FailingSaveCampaignRepository(loaded, exc)
    handler = ReviseCampaignScopeStatementHandler(campaign_repository=repository)  # type: ignore[arg-type]
    command = ReviseCampaignScopeStatementCommand(
        identity=identity,
        expected_persisted_version=AggregateVersion.initial(),
        scope_statement="should conflict",
    )

    with pytest.raises(OptimisticConcurrencyConflict) as excinfo:
        handler.handle(command)

    assert excinfo.value is exc


# ---------------------------------------------------------------------------
# record_campaign_authorization
# ---------------------------------------------------------------------------


def test_record_authorization_transitions_ready_campaign_and_saves_with_command_version() -> None:
    identity = _identity()
    campaign = _ready_campaign(identity)
    loaded = LoadedAggregate(aggregate=campaign, persisted_version=AggregateVersion(1))
    repository = _RecordingCampaignRepository(loaded, _save_result(2))
    handler = RecordCampaignAuthorizationHandler(campaign_repository=repository)
    command = RecordCampaignAuthorizationCommand(
        identity=identity,
        expected_persisted_version=AggregateVersion(1),
        reason="authorization approved",
        actor="operator",
        occurred_at=_OCCURRED_AT,
    )

    CommandEntryPoint(handler)(command)

    assert campaign.state is CampaignLifecycleState.AUTHORIZED
    _, saved_version = repository.save_calls[0]
    assert saved_version is command.expected_persisted_version


def test_record_authorization_invalid_transition_propagates_and_save_never_called() -> None:
    identity = _identity()
    campaign = _campaign(identity)  # DRAFT, not READY_FOR_AUTHORIZATION
    loaded = LoadedAggregate(aggregate=campaign, persisted_version=AggregateVersion.initial())
    repository = _RecordingCampaignRepository(loaded, _save_result())
    handler = RecordCampaignAuthorizationHandler(campaign_repository=repository)
    command = RecordCampaignAuthorizationCommand(
        identity=identity,
        expected_persisted_version=AggregateVersion.initial(),
        reason="should never persist",
        actor="operator",
        occurred_at=_OCCURRED_AT,
    )

    with pytest.raises(ValueError, match="cannot transition from"):
        handler.handle(command)

    assert repository.save_calls == []


def test_record_authorization_propagates_aggregate_not_found() -> None:
    identity = _identity()
    exc = AggregateNotFound(aggregate_kind="Campaign", identity=identity)
    repository = _FailingGetCampaignRepository(exc)
    handler = RecordCampaignAuthorizationHandler(campaign_repository=repository)  # type: ignore[arg-type]
    command = RecordCampaignAuthorizationCommand(
        identity=identity,
        expected_persisted_version=AggregateVersion.initial(),
        reason="should never run",
        actor="operator",
        occurred_at=_OCCURRED_AT,
    )

    with pytest.raises(AggregateNotFound) as excinfo:
        handler.handle(command)

    assert excinfo.value is exc


# ---------------------------------------------------------------------------
# activate_campaign
# ---------------------------------------------------------------------------


def test_activate_transitions_authorized_campaign_and_saves_with_command_version() -> None:
    identity = _identity()
    campaign = _authorized_campaign(identity)
    loaded = LoadedAggregate(aggregate=campaign, persisted_version=AggregateVersion(2))
    repository = _RecordingCampaignRepository(loaded, _save_result(3))
    handler = ActivateCampaignHandler(campaign_repository=repository)
    command = ActivateCampaignCommand(
        identity=identity,
        expected_persisted_version=AggregateVersion(2),
        reason="starting execution",
        actor="operator",
        occurred_at=_OCCURRED_AT,
    )

    CommandEntryPoint(handler)(command)

    assert campaign.state is CampaignLifecycleState.ACTIVE
    _, saved_version = repository.save_calls[0]
    assert saved_version is command.expected_persisted_version


def test_activate_propagates_optimistic_concurrency_conflict() -> None:
    identity = _identity()
    campaign = _authorized_campaign(identity)
    loaded = LoadedAggregate(aggregate=campaign, persisted_version=AggregateVersion(2))
    exc = _occ_conflict(identity)
    repository = _FailingSaveCampaignRepository(loaded, exc)
    handler = ActivateCampaignHandler(campaign_repository=repository)  # type: ignore[arg-type]
    command = ActivateCampaignCommand(
        identity=identity,
        expected_persisted_version=AggregateVersion(1),
        reason="should conflict",
        actor="operator",
        occurred_at=_OCCURRED_AT,
    )

    with pytest.raises(OptimisticConcurrencyConflict) as excinfo:
        handler.handle(command)

    assert excinfo.value is exc


# ---------------------------------------------------------------------------
# suspend_campaign
# ---------------------------------------------------------------------------


def test_suspend_transitions_active_campaign_and_saves_with_command_version() -> None:
    identity = _identity()
    campaign = _active_campaign(identity)
    loaded = LoadedAggregate(aggregate=campaign, persisted_version=AggregateVersion(3))
    repository = _RecordingCampaignRepository(loaded, _save_result(4))
    handler = SuspendCampaignHandler(campaign_repository=repository)
    command = SuspendCampaignCommand(
        identity=identity,
        expected_persisted_version=AggregateVersion(3),
        reason="pausing for review",
        actor="operator",
        occurred_at=_OCCURRED_AT,
    )

    CommandEntryPoint(handler)(command)

    assert campaign.state is CampaignLifecycleState.SUSPENDED
    _, saved_version = repository.save_calls[0]
    assert saved_version is command.expected_persisted_version


def test_suspend_invalid_transition_propagates_and_save_never_called() -> None:
    identity = _identity()
    campaign = _authorized_campaign(identity)  # AUTHORIZED, not ACTIVE
    loaded = LoadedAggregate(aggregate=campaign, persisted_version=AggregateVersion(2))
    repository = _RecordingCampaignRepository(loaded, _save_result())
    handler = SuspendCampaignHandler(campaign_repository=repository)
    command = SuspendCampaignCommand(
        identity=identity,
        expected_persisted_version=AggregateVersion(2),
        reason="should never persist",
        actor="operator",
        occurred_at=_OCCURRED_AT,
    )

    with pytest.raises(ValueError, match="cannot transition from"):
        handler.handle(command)

    assert repository.save_calls == []


# ---------------------------------------------------------------------------
# resume_campaign
# ---------------------------------------------------------------------------


def test_resume_transitions_suspended_campaign_and_saves_with_command_version() -> None:
    identity = _identity()
    campaign = _suspended_campaign(identity)
    loaded = LoadedAggregate(aggregate=campaign, persisted_version=AggregateVersion(4))
    repository = _RecordingCampaignRepository(loaded, _save_result(5))
    handler = ResumeCampaignHandler(campaign_repository=repository)
    command = ResumeCampaignCommand(
        identity=identity,
        expected_persisted_version=AggregateVersion(4),
        reason="resuming execution",
        actor="operator",
        occurred_at=_OCCURRED_AT,
    )

    CommandEntryPoint(handler)(command)

    assert campaign.state is CampaignLifecycleState.ACTIVE
    _, saved_version = repository.save_calls[0]
    assert saved_version is command.expected_persisted_version


def test_resume_propagates_optimistic_concurrency_conflict() -> None:
    identity = _identity()
    campaign = _suspended_campaign(identity)
    loaded = LoadedAggregate(aggregate=campaign, persisted_version=AggregateVersion(4))
    exc = _occ_conflict(identity)
    repository = _FailingSaveCampaignRepository(loaded, exc)
    handler = ResumeCampaignHandler(campaign_repository=repository)  # type: ignore[arg-type]
    command = ResumeCampaignCommand(
        identity=identity,
        expected_persisted_version=AggregateVersion(3),
        reason="should conflict",
        actor="operator",
        occurred_at=_OCCURRED_AT,
    )

    with pytest.raises(OptimisticConcurrencyConflict) as excinfo:
        handler.handle(command)

    assert excinfo.value is exc


# ---------------------------------------------------------------------------
# complete_campaign
# ---------------------------------------------------------------------------


def test_complete_transitions_active_campaign_and_saves_with_command_version() -> None:
    identity = _identity()
    campaign = _active_campaign(identity)
    loaded = LoadedAggregate(aggregate=campaign, persisted_version=AggregateVersion(3))
    repository = _RecordingCampaignRepository(loaded, _save_result(4))
    handler = CompleteCampaignHandler(campaign_repository=repository)
    command = CompleteCampaignCommand(
        identity=identity,
        expected_persisted_version=AggregateVersion(3),
        reason="objectives met",
        actor="operator",
        occurred_at=_OCCURRED_AT,
    )

    CommandEntryPoint(handler)(command)

    assert campaign.state is CampaignLifecycleState.COMPLETED
    _, saved_version = repository.save_calls[0]
    assert saved_version is command.expected_persisted_version


def test_complete_invalid_transition_propagates_and_save_never_called() -> None:
    identity = _identity()
    campaign = _suspended_campaign(identity)  # SUSPENDED, not ACTIVE
    loaded = LoadedAggregate(aggregate=campaign, persisted_version=AggregateVersion(4))
    repository = _RecordingCampaignRepository(loaded, _save_result())
    handler = CompleteCampaignHandler(campaign_repository=repository)
    command = CompleteCampaignCommand(
        identity=identity,
        expected_persisted_version=AggregateVersion(4),
        reason="should never persist",
        actor="operator",
        occurred_at=_OCCURRED_AT,
    )

    with pytest.raises(ValueError, match="cannot transition from"):
        handler.handle(command)

    assert repository.save_calls == []


def test_complete_propagates_aggregate_not_found() -> None:
    identity = _identity()
    exc = AggregateNotFound(aggregate_kind="Campaign", identity=identity)
    repository = _FailingGetCampaignRepository(exc)
    handler = CompleteCampaignHandler(campaign_repository=repository)  # type: ignore[arg-type]
    command = CompleteCampaignCommand(
        identity=identity,
        expected_persisted_version=AggregateVersion.initial(),
        reason="should never run",
        actor="operator",
        occurred_at=_OCCURRED_AT,
    )

    with pytest.raises(AggregateNotFound) as excinfo:
        handler.handle(command)

    assert excinfo.value is exc
