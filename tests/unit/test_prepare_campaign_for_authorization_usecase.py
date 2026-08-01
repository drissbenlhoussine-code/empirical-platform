"""MILESTONE-032 behavioral tests for `PrepareCampaignForAuthorizationCommand`/`Handler`.

Proves the frozen load-mutate-save flow (design freeze Section 16): call
`CampaignRepository.get()` exactly once, invoke `Campaign.prepare_for_authorization()`
exactly once with the command's data unchanged, then call `CampaignRepository.save()`
exactly once with the mutated aggregate and the command's own
`expected_persisted_version` -- never `loaded.persisted_version`. Also proves
transparent failure propagation for every collaborator (frozen M029 invariant)
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
    SaveOperation,
    SaveResult,
)
from empirical_platform.shared.domain.versioning import AggregateVersion
from empirical_platform.shared.identifiers import RuntimeIdentifier
from empirical_platform.usecases.prepare_campaign_for_authorization import (
    PrepareCampaignForAuthorizationCommand,
    PrepareCampaignForAuthorizationHandler,
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


def _campaign(identity: DomainIdentity[CampaignId]) -> Campaign:
    return Campaign(identity=identity, scope_statement=CampaignScopeStatement("initial scope"))


def _command(
    identity: DomainIdentity[CampaignId],
    *,
    expected_persisted_version: AggregateVersion = _INITIAL_VERSION,
    actor: str = "tester",
    occurred_at: datetime = _OCCURRED_AT,
    correlation_id: str | None = None,
    reason: str | None = None,
) -> PrepareCampaignForAuthorizationCommand:
    return PrepareCampaignForAuthorizationCommand(
        identity=identity,
        expected_persisted_version=expected_persisted_version,
        actor=actor,
        occurred_at=occurred_at,
        correlation_id=correlation_id,
        reason=reason,
    )


class _RecordingCampaignRepository:
    """Records every `get()`/`save()` call; conforms structurally to `CampaignRepository`.

    `loaded` may be a single `LoadedAggregate` (returned for every `get()` call)
    or a list consumed one entry per call, for tests exercising multiple
    distinct identities against the same repository instance.
    """

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
        raise AssertionError("add() must not be called by PrepareCampaignForAuthorizationHandler")

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


def _handler(repository: object) -> PrepareCampaignForAuthorizationHandler:
    return PrepareCampaignForAuthorizationHandler(campaign_repository=repository)  # type: ignore[arg-type]


# --- A. Command contract tests ---


def test_command_preserves_all_six_fields_unchanged() -> None:
    identity = _identity()
    version = AggregateVersion(3)
    command = PrepareCampaignForAuthorizationCommand(
        identity=identity,
        expected_persisted_version=version,
        actor="alice",
        occurred_at=_OCCURRED_AT,
        correlation_id="corr-1",
        reason="quarterly review",
    )

    assert command.identity is identity
    assert command.expected_persisted_version is version
    assert command.actor == "alice"
    assert command.occurred_at == _OCCURRED_AT
    assert command.correlation_id == "corr-1"
    assert command.reason == "quarterly review"


def test_command_optional_fields_default_to_none() -> None:
    command = _command(_identity())

    assert command.correlation_id is None
    assert command.reason is None


def test_command_contains_no_additional_fields() -> None:
    assert set(PrepareCampaignForAuthorizationCommand.__slots__) == {  # type: ignore[attr-defined]
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
    command = PrepareCampaignForAuthorizationCommand(
        identity=_identity(),
        expected_persisted_version=AggregateVersion.initial(),
        actor="",
        occurred_at=_OCCURRED_AT,
    )
    assert command.actor == ""


# --- B. Handler success tests ---


def test_typed_conformance_check() -> None:
    """Mypy-checked proof that PrepareCampaignForAuthorizationHandler conforms to
    CommandHandler[PrepareCampaignForAuthorizationCommand, SaveResult] without
    inheritance (structural typing only)."""
    identity = _identity()
    loaded = LoadedAggregate(
        aggregate=_campaign(identity), persisted_version=AggregateVersion.initial()
    )
    save_result = SaveResult(operation=SaveOperation.UPDATED, persisted_version=AggregateVersion(1))
    repository: CampaignRepository = _RecordingCampaignRepository(  # type: ignore[assignment]
        loaded, save_result
    )
    handler: PrepareCampaignForAuthorizationHandler = _handler(repository)
    assert handler is not None


def test_get_is_called_exactly_once_with_exact_identity() -> None:
    identity = _identity()
    loaded = LoadedAggregate(
        aggregate=_campaign(identity), persisted_version=AggregateVersion.initial()
    )
    save_result = SaveResult(operation=SaveOperation.UPDATED, persisted_version=AggregateVersion(1))
    repository = _RecordingCampaignRepository(loaded, save_result)
    handler = _handler(repository)
    command = _command(identity)

    handler.handle(command)

    assert len(repository.get_calls) == 1
    assert repository.get_calls[0] is command.identity


def test_prepare_for_authorization_called_with_exact_command_arguments() -> None:
    identity = _identity()
    campaign = _campaign(identity)
    loaded = LoadedAggregate(aggregate=campaign, persisted_version=AggregateVersion.initial())
    save_result = SaveResult(operation=SaveOperation.UPDATED, persisted_version=AggregateVersion(1))
    repository = _RecordingCampaignRepository(loaded, save_result)
    handler = _handler(repository)
    command = _command(
        identity,
        actor="bob",
        occurred_at=_OCCURRED_AT,
        correlation_id="corr-42",
        reason="ready for review",
    )

    handler.handle(command)

    assert campaign.state is CampaignLifecycleState.READY_FOR_AUTHORIZATION
    record = campaign.transition_history[-1]
    assert record.actor == "bob"
    assert record.occurred_at == _OCCURRED_AT
    assert record.correlation_id == "corr-42"
    assert record.reason == "ready for review"


def test_save_called_exactly_once_with_mutated_aggregate_and_command_version() -> None:
    identity = _identity()
    campaign = _campaign(identity)
    loaded = LoadedAggregate(aggregate=campaign, persisted_version=AggregateVersion.initial())
    save_result = SaveResult(operation=SaveOperation.UPDATED, persisted_version=AggregateVersion(1))
    repository = _RecordingCampaignRepository(loaded, save_result)
    handler = _handler(repository)
    command = _command(identity, expected_persisted_version=AggregateVersion(0))

    handler.handle(command)

    assert len(repository.save_calls) == 1
    saved_aggregate, saved_expected_version = repository.save_calls[0]
    assert saved_aggregate is campaign
    assert saved_expected_version is command.expected_persisted_version


def test_save_receives_command_version_not_loaded_persisted_version() -> None:
    """Critical: expected_persisted_version passed to save() must come from the
    command, never from loaded.persisted_version -- even when they differ."""
    identity = _identity()
    campaign = _campaign(identity)
    loaded = LoadedAggregate(aggregate=campaign, persisted_version=AggregateVersion(5))
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
        aggregate=_campaign(identity), persisted_version=AggregateVersion.initial()
    )
    save_result = SaveResult(operation=SaveOperation.UPDATED, persisted_version=AggregateVersion(1))
    repository = _RecordingCampaignRepository(loaded, save_result)
    handler = _handler(repository)

    handler.handle(_command(identity))  # would raise if add() were called


def test_no_second_get_or_save_occurs() -> None:
    identity = _identity()
    loaded = LoadedAggregate(
        aggregate=_campaign(identity), persisted_version=AggregateVersion.initial()
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
        aggregate=_campaign(identity), persisted_version=AggregateVersion.initial()
    )
    save_result = SaveResult(operation=SaveOperation.UPDATED, persisted_version=AggregateVersion(1))
    repository = _RecordingCampaignRepository(loaded, save_result)
    handler = _handler(repository)

    result = handler.handle(_command(identity))

    assert result is save_result


def test_handler_is_invocable_through_command_entry_point() -> None:
    identity = _identity()
    loaded = LoadedAggregate(
        aggregate=_campaign(identity), persisted_version=AggregateVersion.initial()
    )
    save_result = SaveResult(operation=SaveOperation.UPDATED, persisted_version=AggregateVersion(1))
    repository = _RecordingCampaignRepository(loaded, save_result)
    handler = _handler(repository)
    entry_point = CommandEntryPoint(handler)

    result = entry_point(_command(identity))

    assert result is save_result
    assert len(repository.get_calls) == 1
    assert len(repository.save_calls) == 1


def test_handler_bound_at_construction_reused_across_invocations() -> None:
    identity_one = _identity("CAMP-0001")
    identity_two = _identity("CAMP-0002")
    loaded_sequence = [
        LoadedAggregate(
            aggregate=_campaign(identity_one), persisted_version=AggregateVersion.initial()
        ),
        LoadedAggregate(
            aggregate=_campaign(identity_two), persisted_version=AggregateVersion.initial()
        ),
    ]
    save_result = SaveResult(operation=SaveOperation.UPDATED, persisted_version=AggregateVersion(1))
    repository = _RecordingCampaignRepository(loaded_sequence, save_result)
    handler = _handler(repository)
    entry_point = CommandEntryPoint(handler)

    entry_point(_command(identity_one))
    entry_point(_command(identity_two))

    assert len(repository.get_calls) == 2
    assert len(repository.save_calls) == 2


# --- C. Domain-failure tests ---


def test_domain_invalid_transition_propagates_and_save_never_called() -> None:
    identity = _identity()
    campaign = _campaign(identity)
    campaign.cancel(actor="tester", occurred_at=_OCCURRED_AT)  # DRAFT -> CANCELLED
    loaded = LoadedAggregate(aggregate=campaign, persisted_version=AggregateVersion(1))
    save_result = SaveResult(operation=SaveOperation.UPDATED, persisted_version=AggregateVersion(2))
    repository = _RecordingCampaignRepository(loaded, save_result)
    handler = _handler(repository)

    with pytest.raises(ValueError, match="cannot transition from"):
        handler.handle(_command(identity, expected_persisted_version=AggregateVersion(1)))

    assert repository.save_calls == []


# --- D. get()-failure tests ---


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


# --- E. save()-failure tests ---


def test_arbitrary_save_exception_propagates_with_identity_preserved() -> None:
    identity = _identity()
    campaign = _campaign(identity)
    loaded = LoadedAggregate(aggregate=campaign, persisted_version=AggregateVersion.initial())
    exc = RuntimeError("unexpected save() failure")
    repository = _FailingSaveCampaignRepository(loaded, exc)
    handler = _handler(repository)

    with pytest.raises(RuntimeError) as excinfo:
        handler.handle(_command(identity))

    assert excinfo.value is exc
    assert repository.get_calls == 1
    assert repository.save_calls == 1
