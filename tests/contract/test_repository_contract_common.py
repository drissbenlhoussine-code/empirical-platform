"""MILESTONE-020 cross-cutting contract tests: exports, enum shape, and forbidden concepts."""

from __future__ import annotations

from tests.contract._fakes import (
    FakeCampaignRepository,
    FakeEvidencePackageRepository,
    FakeReviewRepository,
    FakeRunRepository,
    assert_conforms_to_campaign_repository,
    assert_conforms_to_evidence_package_repository,
    assert_conforms_to_review_repository,
    assert_conforms_to_run_repository,
)

import empirical_platform.campaign as campaign_exports
import empirical_platform.evidence as evidence_exports
import empirical_platform.review as review_exports
import empirical_platform.run as run_exports
import empirical_platform.shared.contracts as contracts_exports
from empirical_platform.campaign.repository import CampaignRepository
from empirical_platform.evidence.repository import EvidencePackageRepository
from empirical_platform.review.repository import ReviewRepository
from empirical_platform.run.repository import RunRepository
from empirical_platform.shared.contracts.repository import SaveOperation


def test_save_operation_is_exactly_three_closed_values() -> None:
    assert {member.value for member in SaveOperation} == {"created", "updated", "unchanged"}
    assert len(SaveOperation) == 3


def test_shared_contracts_public_exports() -> None:
    expected = {
        "AggregateAlreadyExists",
        "AggregateNotFound",
        "InvalidAggregateForPersistence",
        "InvalidPersistedAggregateState",
        "LoadedAggregate",
        "OptimisticConcurrencyConflict",
        "RepositoryContractError",
        "SaveOperation",
        "SaveResult",
    }
    assert set(contracts_exports.__all__) == expected
    for name in expected:
        assert hasattr(contracts_exports, name)


def test_aggregate_package_repository_exports() -> None:
    assert "CampaignRepository" in campaign_exports.__all__
    assert "RunRepository" in run_exports.__all__
    assert "EvidencePackageRepository" in evidence_exports.__all__
    assert "ReviewRepository" in review_exports.__all__


def test_no_retryability_concept_is_exposed() -> None:
    assert "Retryability" not in dir(contracts_exports)
    assert not any("retry" in name.lower() for name in contracts_exports.__all__)


def test_no_aggregate_kind_enum_is_exposed() -> None:
    assert "AggregateKind" not in dir(contracts_exports)
    assert not any("aggregatekind" in name.lower() for name in contracts_exports.__all__)


def test_no_generic_repository_base_is_exposed() -> None:
    for module in (campaign_exports, run_exports, evidence_exports, review_exports):
        assert not any(name == "Repository" for name in module.__all__)


def test_fakes_structurally_conform_to_repository_protocols() -> None:
    # Assignment to a Protocol-typed variable is a mypy-time structural check;
    # these calls also prove the fakes are constructible and Protocol-shaped.
    campaign_repository: CampaignRepository = FakeCampaignRepository()
    run_repository: RunRepository = FakeRunRepository()
    evidence_repository: EvidencePackageRepository = FakeEvidencePackageRepository()
    review_repository: ReviewRepository = FakeReviewRepository()

    assert_conforms_to_campaign_repository(campaign_repository)
    assert_conforms_to_run_repository(run_repository)
    assert_conforms_to_evidence_package_repository(evidence_repository)
    assert_conforms_to_review_repository(review_repository)
