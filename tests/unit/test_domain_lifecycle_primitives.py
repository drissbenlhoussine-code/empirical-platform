from empirical_platform.campaign import CampaignLifecycleState, RunLifecycleState
from empirical_platform.evidence import EvidencePackageLifecycleState
from empirical_platform.review import ReviewDisposition, ReviewLifecycleState


def test_campaign_lifecycle_states_match_frozen_milestone_012() -> None:
    assert {state.value for state in CampaignLifecycleState} == {
        "DRAFT",
        "READY_FOR_AUTHORIZATION",
        "AUTHORIZED",
        "ACTIVE",
        "SUSPENDED",
        "COMPLETED",
        "CANCELLED",
    }
    assert "ARCHIVED" not in {state.value for state in CampaignLifecycleState}


def test_run_lifecycle_states_match_frozen_milestone_012() -> None:
    assert {state.value for state in RunLifecycleState} == {
        "CREATED",
        "AUTHORIZED",
        "ACQUIRING",
        "NORMALIZING",
        "VALIDATING",
        "EXECUTION_COMPLETED",
        "FAILED",
        "CANCELLED",
    }
    assert "VALID" not in {state.value for state in RunLifecycleState}
    assert "INVALID" not in {state.value for state in RunLifecycleState}


def test_evidence_package_lifecycle_states_match_frozen_milestone_012() -> None:
    assert {state.value for state in EvidencePackageLifecycleState} == {
        "INITIALIZED",
        "COLLECTING",
        "SEALED",
        "INVALIDATED",
    }
    assert "REVIEWED" not in {state.value for state in EvidencePackageLifecycleState}


def test_review_lifecycle_and_disposition_are_separate() -> None:
    assert {state.value for state in ReviewLifecycleState} == {
        "ASSIGNED",
        "IN_PROGRESS",
        "COMPLETED",
        "CANCELLED",
    }
    assert {disposition.value for disposition in ReviewDisposition} == {
        "ACCEPTED",
        "REJECTED",
        "CHANGES_REQUESTED",
        "INCONCLUSIVE",
    }
    assert not {state.value for state in ReviewLifecycleState} & {
        disposition.value for disposition in ReviewDisposition
    }
