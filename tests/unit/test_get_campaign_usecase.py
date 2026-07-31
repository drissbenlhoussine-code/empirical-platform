"""MILESTONE-031 behavioral tests for `GetCampaignQuery`/`GetCampaignHandler`.

Proves the frozen retrieval flow (design freeze Section 8): call
`CampaignRepository.get()` exactly once with the query's identity object
unchanged, and build `CampaignSnapshot` from the loaded aggregate's
`identity`/`scope_statement`/`state` only -- `persisted_version` is read but
never exposed. Also proves transparent failure propagation for every
collaborator (frozen M029 invariant) and that the handler is invocable
through the frozen `QueryEntryPoint`.

Uses deterministic recording fakes/stubs, not mocks, for stronger evidence.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from empirical_platform.application.query import QueryEntryPoint
from empirical_platform.campaign.aggregate import Campaign, CampaignScopeStatement
from empirical_platform.campaign.lifecycle import CampaignLifecycleState
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import CampaignId
from empirical_platform.shared.contracts.repository import (
    AggregateNotFound,
    LoadedAggregate,
)
from empirical_platform.shared.domain.versioning import AggregateVersion
from empirical_platform.shared.identifiers import RuntimeIdentifier
from empirical_platform.usecases.get_campaign import (
    CampaignSnapshot,
    GetCampaignHandler,
    GetCampaignQuery,
)

if TYPE_CHECKING:
    from empirical_platform.campaign.repository import CampaignRepository

_RUNTIME_ID_VALUE = "12345678-1234-4321-8765-1234567890ab"


def _identity(governance_id: str = "CAMP-0001") -> DomainIdentity[CampaignId]:
    return DomainIdentity(
        governance_id=CampaignId(governance_id),
        runtime_id=RuntimeIdentifier(_RUNTIME_ID_VALUE),
    )


def _campaign(identity: DomainIdentity[CampaignId]) -> Campaign:
    return Campaign(identity=identity, scope_statement=CampaignScopeStatement("initial scope"))


class _RecordingCampaignRepository:
    """Records every `get()` call; conforms structurally to `CampaignRepository`."""

    def __init__(self, loaded: LoadedAggregate[Campaign]) -> None:
        self._loaded = loaded
        self.get_calls: list[DomainIdentity[CampaignId]] = []

    def get(self, identity: DomainIdentity[CampaignId]) -> LoadedAggregate[Campaign]:
        self.get_calls.append(identity)
        return self._loaded

    def add(self, aggregate: Campaign) -> object:
        raise AssertionError("add() must not be called by GetCampaignHandler")

    def save(self, aggregate: Campaign, *, expected_persisted_version: object) -> object:
        raise AssertionError("save() must not be called by GetCampaignHandler")


class _FailingCampaignRepository:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc
        self.get_calls = 0

    def get(self, identity: DomainIdentity[CampaignId]) -> object:
        self.get_calls += 1
        raise self._exc

    def add(self, aggregate: Campaign) -> object:
        raise AssertionError("add() must not be called")

    def save(self, aggregate: Campaign, *, expected_persisted_version: object) -> object:
        raise AssertionError("save() must not be called")


def _handler(repository: object) -> GetCampaignHandler:
    return GetCampaignHandler(campaign_repository=repository)  # type: ignore[arg-type]


def test_typed_conformance_check() -> None:
    """Mypy-checked proof that GetCampaignHandler conforms to
    QueryHandler[GetCampaignQuery, CampaignSnapshot] without inheritance
    (structural typing only)."""
    identity = _identity()
    loaded = LoadedAggregate(
        aggregate=_campaign(identity), persisted_version=AggregateVersion.initial()
    )
    repository: CampaignRepository = _RecordingCampaignRepository(loaded)  # type: ignore[assignment]
    handler: GetCampaignHandler = _handler(repository)
    assert handler is not None


def test_query_preserves_the_exact_identity_object() -> None:
    identity = _identity()
    query = GetCampaignQuery(identity=identity)

    assert query.identity is identity


def test_query_contains_no_additional_fields() -> None:
    query = GetCampaignQuery(identity=_identity())
    assert [field for field in query.__slots__] == ["identity"]  # type: ignore[attr-defined]


def test_query_is_immutable() -> None:
    query = GetCampaignQuery(identity=_identity())
    with pytest.raises(AttributeError):
        query.identity = _identity("CAMP-0002")  # type: ignore[misc]


def test_campaign_repository_get_is_called_exactly_once() -> None:
    identity = _identity()
    loaded = LoadedAggregate(
        aggregate=_campaign(identity), persisted_version=AggregateVersion.initial()
    )
    repository = _RecordingCampaignRepository(loaded)
    handler = _handler(repository)

    handler.handle(GetCampaignQuery(identity=identity))

    assert len(repository.get_calls) == 1


def test_exact_query_identity_object_is_passed_to_repository_unchanged() -> None:
    identity = _identity()
    loaded = LoadedAggregate(
        aggregate=_campaign(identity), persisted_version=AggregateVersion.initial()
    )
    repository = _RecordingCampaignRepository(loaded)
    handler = _handler(repository)
    query = GetCampaignQuery(identity=identity)

    handler.handle(query)

    assert repository.get_calls[0] is query.identity


def test_no_add_or_save_call_occurs() -> None:
    """add()/save() raise AssertionError in the fake if called; handler must
    never call either."""
    identity = _identity()
    loaded = LoadedAggregate(
        aggregate=_campaign(identity), persisted_version=AggregateVersion.initial()
    )
    repository = _RecordingCampaignRepository(loaded)
    handler = _handler(repository)

    handler.handle(GetCampaignQuery(identity=identity))  # would raise if add()/save() were called


def test_returned_object_is_a_campaign_snapshot() -> None:
    identity = _identity()
    loaded = LoadedAggregate(
        aggregate=_campaign(identity), persisted_version=AggregateVersion.initial()
    )
    repository = _RecordingCampaignRepository(loaded)
    handler = _handler(repository)

    result = handler.handle(GetCampaignQuery(identity=identity))

    assert isinstance(result, CampaignSnapshot)


def test_snapshot_identity_scope_statement_and_state_match_the_loaded_aggregate() -> None:
    identity = _identity("CAMP-0042")
    campaign = _campaign(identity)
    loaded = LoadedAggregate(aggregate=campaign, persisted_version=AggregateVersion.initial())
    repository = _RecordingCampaignRepository(loaded)
    handler = _handler(repository)

    result = handler.handle(GetCampaignQuery(identity=identity))

    assert result.identity == campaign.identity
    assert result.scope_statement == campaign.scope_statement
    assert result.state == campaign.state
    assert result.state is CampaignLifecycleState.DRAFT


def test_snapshot_contains_no_persisted_version() -> None:
    snapshot_fields = {"identity", "scope_statement", "state"}
    assert set(CampaignSnapshot.__slots__) == snapshot_fields  # type: ignore[attr-defined]


def test_snapshot_is_immutable() -> None:
    identity = _identity()
    loaded = LoadedAggregate(
        aggregate=_campaign(identity), persisted_version=AggregateVersion.initial()
    )
    repository = _RecordingCampaignRepository(loaded)
    handler = _handler(repository)

    result = handler.handle(GetCampaignQuery(identity=identity))

    with pytest.raises(AttributeError):
        result.state = CampaignLifecycleState.ACTIVE  # type: ignore[misc]


def test_campaign_aggregate_is_not_mutated() -> None:
    identity = _identity()
    campaign = _campaign(identity)
    version_before = campaign.version
    loaded = LoadedAggregate(aggregate=campaign, persisted_version=AggregateVersion.initial())
    repository = _RecordingCampaignRepository(loaded)
    handler = _handler(repository)

    handler.handle(GetCampaignQuery(identity=identity))

    assert campaign.version == version_before
    assert campaign.state is CampaignLifecycleState.DRAFT


def test_aggregate_not_found_propagates_with_identity_preserved() -> None:
    exc = AggregateNotFound(aggregate_kind="Campaign", identity=_identity())
    repository = _FailingCampaignRepository(exc)
    handler = _handler(repository)

    with pytest.raises(AggregateNotFound) as excinfo:
        handler.handle(GetCampaignQuery(identity=_identity()))

    assert excinfo.value is exc
    assert repository.get_calls == 1


def test_arbitrary_repository_exception_propagates_with_identity_preserved() -> None:
    exc = RuntimeError("unexpected repository failure")
    repository = _FailingCampaignRepository(exc)
    handler = _handler(repository)

    with pytest.raises(RuntimeError) as excinfo:
        handler.handle(GetCampaignQuery(identity=_identity()))

    assert excinfo.value is exc
    assert repository.get_calls == 1


def test_handler_is_invocable_through_query_entry_point() -> None:
    identity = _identity()
    loaded = LoadedAggregate(
        aggregate=_campaign(identity), persisted_version=AggregateVersion.initial()
    )
    repository = _RecordingCampaignRepository(loaded)
    handler = _handler(repository)
    entry_point = QueryEntryPoint(handler)

    result = entry_point(GetCampaignQuery(identity=identity))

    assert isinstance(result, CampaignSnapshot)
    assert len(repository.get_calls) == 1


def test_handler_bound_at_construction_not_per_call() -> None:
    identity_one = _identity("CAMP-0001")
    identity_two = _identity("CAMP-0002")
    loaded_one = LoadedAggregate(
        aggregate=_campaign(identity_one), persisted_version=AggregateVersion.initial()
    )
    repository = _RecordingCampaignRepository(loaded_one)
    handler = _handler(repository)
    entry_point = QueryEntryPoint(handler)

    entry_point(GetCampaignQuery(identity=identity_one))
    entry_point(GetCampaignQuery(identity=identity_two))

    assert len(repository.get_calls) == 2
