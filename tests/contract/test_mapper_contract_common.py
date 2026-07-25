"""MILESTONE-021 cross-cutting mapper contract tests: exports and forbidden concepts."""

from __future__ import annotations

from tests.contract._mapper_fakes import (
    FakeCampaignMapper,
    FakeEvidencePackageMapper,
    FakeReviewMapper,
    FakeRunMapper,
)

import empirical_platform.campaign as campaign_exports
import empirical_platform.evidence as evidence_exports
import empirical_platform.review as review_exports
import empirical_platform.run as run_exports
import empirical_platform.shared.contracts as contracts_exports
from empirical_platform.campaign.mapper import CampaignMapper
from empirical_platform.evidence.mapper import EvidencePackageMapper
from empirical_platform.review.mapper import ReviewMapper
from empirical_platform.run.mapper import RunMapper


def test_shared_contracts_mapping_exports() -> None:
    expected = {
        "IdentityDurableRecord",
        "MapperError",
        "MapperErrorCategory",
        "TransitionDurableRecord",
    }
    for name in expected:
        assert name in contracts_exports.__all__
        assert hasattr(contracts_exports, name)


def test_aggregate_package_mapper_exports() -> None:
    assert "CampaignMapper" in campaign_exports.__all__
    assert "CampaignDurableRecord" in campaign_exports.__all__
    assert "RunMapper" in run_exports.__all__
    assert "RunDurableRecord" in run_exports.__all__
    assert "EvidencePackageMapper" in evidence_exports.__all__
    assert "EvidencePackageDurableRecord" in evidence_exports.__all__
    assert "ReviewMapper" in review_exports.__all__
    assert "ReviewDurableRecord" in review_exports.__all__


def test_no_generic_mapper_base_is_exposed() -> None:
    for module in (campaign_exports, run_exports, evidence_exports, review_exports):
        assert not any(name == "Mapper" for name in module.__all__)


def test_no_reconstruction_factory_is_exposed() -> None:
    for module in (campaign_exports, run_exports, evidence_exports, review_exports):
        assert not any(name.startswith("_reconstruct") for name in module.__all__)
        assert not any("reconstruct" in name.lower() for name in module.__all__)


def test_mapper_errors_are_distinct_from_repository_errors() -> None:
    from empirical_platform.shared.contracts.repository import RepositoryContractError

    assert not issubclass(contracts_exports.MapperError, RepositoryContractError)


def test_fakes_structurally_conform_to_mapper_protocols() -> None:
    # Assignment to a Protocol-typed variable is a mypy-time structural check;
    # these calls also prove the fakes are constructible and Protocol-shaped.
    campaign_mapper: CampaignMapper = FakeCampaignMapper()
    run_mapper: RunMapper = FakeRunMapper()
    evidence_mapper: EvidencePackageMapper = FakeEvidencePackageMapper()
    review_mapper: ReviewMapper = FakeReviewMapper()

    assert campaign_mapper is not None
    assert run_mapper is not None
    assert evidence_mapper is not None
    assert review_mapper is not None
