"""MILESTONE-021 contract tests for CampaignMapper, using an in-memory fake."""

from __future__ import annotations

import uuid
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest
from tests.contract._mapper_fakes import FakeCampaignMapper

from empirical_platform.campaign._reconstruction import _reconstruct_campaign
from empirical_platform.campaign.aggregate import Campaign, CampaignScopeStatement
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import CampaignId
from empirical_platform.shared.contracts.mapping import MapperError, MapperErrorCategory
from empirical_platform.shared.identifiers import RuntimeIdentifier

OCCURRED_AT = datetime(2026, 7, 26, tzinfo=UTC)


def _identity() -> DomainIdentity[CampaignId]:
    return DomainIdentity(
        governance_id=CampaignId("CAMP-0001"),
        runtime_id=RuntimeIdentifier(str(uuid.uuid4())),
    )


def _campaign() -> Campaign:
    return Campaign(identity=_identity(), scope_statement=CampaignScopeStatement("initial scope"))


def test_round_trip_preserves_identity_and_initial_state() -> None:
    mapper = FakeCampaignMapper()
    campaign = _campaign()

    record = mapper.to_durable_record(campaign)
    state = mapper.from_durable_record(record)
    restored = _reconstruct_campaign(state)

    assert restored.identity == campaign.identity
    assert restored.version == campaign.version
    assert restored.state == campaign.state
    assert str(restored.scope_statement) == str(campaign.scope_statement)
    assert restored.transition_history == campaign.transition_history


def test_round_trip_preserves_non_trivial_history_and_version() -> None:
    mapper = FakeCampaignMapper()
    campaign = _campaign()
    campaign.prepare_for_authorization(actor="tester", occurred_at=OCCURRED_AT)
    campaign.record_authorization(reason="looks good", actor="tester", occurred_at=OCCURRED_AT)
    campaign.activate(reason="starting", actor="tester", occurred_at=OCCURRED_AT)

    record = mapper.to_durable_record(campaign)
    state = mapper.from_durable_record(record)
    restored = _reconstruct_campaign(state)

    assert restored.version == campaign.version
    assert restored.next_transition_sequence == campaign.next_transition_sequence
    assert len(restored.transition_history) == 3
    assert [t.to_state for t in restored.transition_history] == [
        t.to_state for t in campaign.transition_history
    ]
    assert [t.reason for t in restored.transition_history] == [
        t.reason for t in campaign.transition_history
    ]
    assert [t.identity_reference for t in restored.transition_history] == [
        t.identity_reference for t in campaign.transition_history
    ]


def test_durable_record_is_immutable() -> None:
    mapper = FakeCampaignMapper()
    record = mapper.to_durable_record(_campaign())

    with pytest.raises(FrozenInstanceError):
        record.scope_statement = "changed"  # type: ignore[misc]


def test_transition_durable_record_is_immutable() -> None:
    mapper = FakeCampaignMapper()
    campaign = _campaign()
    campaign.prepare_for_authorization(actor="tester", occurred_at=OCCURRED_AT)
    record = mapper.to_durable_record(campaign)

    with pytest.raises(FrozenInstanceError):
        record.transition_history[0].reason = "changed"  # type: ignore[misc]


def test_malformed_lifecycle_state_raises_mapper_error() -> None:
    mapper = FakeCampaignMapper()
    record = mapper.to_durable_record(_campaign())
    corrupted = type(record)(
        identity=record.identity,
        scope_statement=record.scope_statement,
        lifecycle_state="NOT_A_REAL_STATE",
        version=record.version,
        next_transition_sequence=record.next_transition_sequence,
        transition_history=record.transition_history,
    )

    with pytest.raises(MapperError) as excinfo:
        mapper.from_durable_record(corrupted)

    assert excinfo.value.category is MapperErrorCategory.INVALID_DURABLE_RECORD
    assert excinfo.value.aggregate_kind == "Campaign"
