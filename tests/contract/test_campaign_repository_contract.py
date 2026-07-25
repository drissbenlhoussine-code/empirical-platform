"""MILESTONE-020 contract tests for CampaignRepository, using an in-memory fake."""

from __future__ import annotations

import uuid

import pytest
from tests.contract._fakes import FakeCampaignRepository

from empirical_platform.campaign.aggregate import Campaign, CampaignScopeStatement
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import CampaignId
from empirical_platform.shared.contracts.repository import (
    AggregateAlreadyExists,
    AggregateNotFound,
    OptimisticConcurrencyConflict,
    SaveOperation,
)
from empirical_platform.shared.domain.versioning import AggregateVersion
from empirical_platform.shared.identifiers import RuntimeIdentifier


def _identity(governance_value: str = "CAMP-0001") -> DomainIdentity[CampaignId]:
    return DomainIdentity(
        governance_id=CampaignId(governance_value),
        runtime_id=RuntimeIdentifier(str(uuid.uuid4())),
    )


def _campaign(identity: DomainIdentity[CampaignId] | None = None) -> Campaign:
    return Campaign(
        identity=identity or _identity(),
        scope_statement=CampaignScopeStatement("initial scope"),
    )


def test_get_missing_raises_aggregate_not_found() -> None:
    repository = FakeCampaignRepository()

    with pytest.raises(AggregateNotFound) as excinfo:
        repository.get(_identity())

    assert excinfo.value.aggregate_kind == "Campaign"


def test_add_creates_and_returns_created_result() -> None:
    repository = FakeCampaignRepository()
    campaign = _campaign()

    result = repository.add(campaign)

    assert result.operation is SaveOperation.CREATED
    assert result.persisted_version == campaign.version


def test_add_duplicate_full_identity_raises_already_exists() -> None:
    repository = FakeCampaignRepository()
    identity = _identity()
    repository.add(_campaign(identity))

    with pytest.raises(AggregateAlreadyExists):
        repository.add(_campaign(identity))


def test_add_duplicate_governance_id_raises_already_exists() -> None:
    repository = FakeCampaignRepository()
    repository.add(_campaign(_identity("CAMP-0002")))

    colliding_identity = DomainIdentity(
        governance_id=CampaignId("CAMP-0002"),
        runtime_id=RuntimeIdentifier(str(uuid.uuid4())),
    )
    with pytest.raises(AggregateAlreadyExists):
        repository.add(_campaign(colliding_identity))


def test_add_duplicate_runtime_id_raises_already_exists() -> None:
    repository = FakeCampaignRepository()
    shared_runtime_id = RuntimeIdentifier(str(uuid.uuid4()))
    first_identity = DomainIdentity(
        governance_id=CampaignId("CAMP-0003"), runtime_id=shared_runtime_id
    )
    repository.add(_campaign(first_identity))

    colliding_identity = DomainIdentity(
        governance_id=CampaignId("CAMP-0004"), runtime_id=shared_runtime_id
    )
    with pytest.raises(AggregateAlreadyExists):
        repository.add(_campaign(colliding_identity))


def test_get_after_add_returns_loaded_aggregate_with_persisted_version() -> None:
    repository = FakeCampaignRepository()
    identity = _identity()
    campaign = _campaign(identity)
    repository.add(campaign)

    loaded = repository.get(identity)

    assert loaded.aggregate is campaign
    assert loaded.persisted_version == AggregateVersion.initial()


def test_loaded_persisted_version_does_not_change_when_aggregate_mutates() -> None:
    repository = FakeCampaignRepository()
    identity = _identity()
    campaign = _campaign(identity)
    repository.add(campaign)

    loaded = repository.get(identity)
    token_before_mutation = loaded.persisted_version

    campaign.revise_scope_statement(CampaignScopeStatement("revised scope"))

    assert loaded.persisted_version == token_before_mutation
    assert loaded.persisted_version != campaign.version


def test_loaded_aggregate_is_immutable() -> None:
    repository = FakeCampaignRepository()
    identity = _identity()
    campaign = _campaign(identity)
    repository.add(campaign)
    loaded = repository.get(identity)

    with pytest.raises(AttributeError):
        loaded.aggregate = campaign  # type: ignore[misc]
    with pytest.raises(AttributeError):
        loaded.persisted_version = AggregateVersion.initial()  # type: ignore[misc]


def test_save_on_missing_persisted_state_raises_aggregate_not_found() -> None:
    repository = FakeCampaignRepository()
    campaign = _campaign()

    with pytest.raises(AggregateNotFound):
        repository.save(campaign, expected_persisted_version=campaign.version)


def test_save_after_mutation_with_correct_expected_version_returns_updated() -> None:
    repository = FakeCampaignRepository()
    identity = _identity()
    campaign = _campaign(identity)
    repository.add(campaign)
    loaded = repository.get(identity)

    campaign.revise_scope_statement(CampaignScopeStatement("revised scope"))
    result = repository.save(campaign, expected_persisted_version=loaded.persisted_version)

    assert result.operation is SaveOperation.UPDATED
    assert result.persisted_version == campaign.version


def test_save_stale_expected_version_raises_conflict_with_facts() -> None:
    repository = FakeCampaignRepository()
    identity = _identity()
    campaign = _campaign(identity)
    repository.add(campaign)
    stale_version = campaign.version

    campaign.revise_scope_statement(CampaignScopeStatement("first revision"))
    repository.save(campaign, expected_persisted_version=stale_version)
    campaign.revise_scope_statement(CampaignScopeStatement("second revision"))

    with pytest.raises(OptimisticConcurrencyConflict) as excinfo:
        repository.save(campaign, expected_persisted_version=stale_version)

    assert excinfo.value.expected_persisted_version == stale_version
    assert excinfo.value.aggregate_current_version == campaign.version
    assert excinfo.value.actual_persisted_version is not None
    assert excinfo.value.actual_persisted_version != stale_version


def test_save_unchanged_returns_unchanged() -> None:
    repository = FakeCampaignRepository()
    identity = _identity()
    campaign = _campaign(identity)
    repository.add(campaign)
    loaded = repository.get(identity)

    result = repository.save(campaign, expected_persisted_version=loaded.persisted_version)

    assert result.operation is SaveOperation.UNCHANGED
    assert result.persisted_version == campaign.version


def test_repeated_save_requires_latest_expected_version() -> None:
    repository = FakeCampaignRepository()
    identity = _identity()
    campaign = _campaign(identity)
    repository.add(campaign)
    first_expected_version = campaign.version

    campaign.revise_scope_statement(CampaignScopeStatement("revision one"))
    first_result = repository.save(campaign, expected_persisted_version=first_expected_version)

    campaign.revise_scope_statement(CampaignScopeStatement("revision two"))
    second_result = repository.save(
        campaign, expected_persisted_version=first_result.persisted_version
    )

    assert second_result.operation is SaveOperation.UPDATED
    assert second_result.persisted_version == campaign.version
