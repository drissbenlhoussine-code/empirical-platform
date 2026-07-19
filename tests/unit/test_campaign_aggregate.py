from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from empirical_platform.campaign import (
    Campaign,
    CampaignLifecycleState,
    CampaignScopeStatement,
)
from empirical_platform.identifiers import CampaignId, DomainIdentity, RunId
from empirical_platform.shared.domain import AggregateVersion, TransitionSequence
from empirical_platform.shared.identifiers import RuntimeIdentifier

OCCURRED_AT = datetime(2026, 7, 18, tzinfo=UTC)


def _identity(value: str = "CAMP-0001") -> DomainIdentity[CampaignId]:
    return DomainIdentity(
        governance_id=CampaignId(value),
        runtime_id=RuntimeIdentifier("123e4567-e89b-42d3-a456-426614174018"),
    )


def _scope(
    value: str = "Validate documentation-supported L1 market-data capabilities",
) -> CampaignScopeStatement:
    return CampaignScopeStatement(value)


def _campaign(value: str = "CAMP-0001") -> Campaign:
    return Campaign(identity=_identity(value), scope_statement=_scope())


def _snapshot(campaign: Campaign) -> tuple[object, ...]:
    return (
        campaign.identity,
        campaign.scope_statement,
        campaign.state,
        campaign.version,
        campaign.next_transition_sequence,
        campaign.transition_history,
    )


def test_construction_sets_identity_scope_lifecycle_version_sequence_and_empty_history() -> None:
    identity = _identity()
    scope = _scope()

    campaign = Campaign(identity=identity, scope_statement=scope)

    assert campaign.identity == identity
    assert campaign.scope_statement == scope
    assert campaign.state is CampaignLifecycleState.DRAFT
    assert campaign.version == AggregateVersion.initial()
    assert campaign.next_transition_sequence == TransitionSequence.initial()
    assert campaign.transition_history == ()


def test_construction_rejects_wrong_identity_and_scope_types() -> None:
    with pytest.raises(TypeError, match="DomainIdentity"):
        Campaign(identity=CampaignId("CAMP-0001"), scope_statement=_scope())  # type: ignore[arg-type]

    with pytest.raises(TypeError, match="CampaignId"):
        Campaign(
            identity=DomainIdentity(
                governance_id=RunId("RUN-0001"),
                runtime_id=RuntimeIdentifier("123e4567-e89b-42d3-a456-426614174018"),
            ),
            scope_statement=_scope(),
        )

    with pytest.raises(TypeError, match="CampaignScopeStatement"):
        Campaign(identity=_identity(), scope_statement="scope")  # type: ignore[arg-type]


def test_identity_and_campaign_have_no_authority_or_run_mutation_surface() -> None:
    campaign = _campaign()

    assert not hasattr(campaign, "set_identity")
    assert not hasattr(campaign, "owner")
    assert not hasattr(campaign, "sponsor")
    assert not hasattr(campaign, "reviewer")
    assert not hasattr(campaign, "authorization")
    assert not hasattr(campaign, "readiness")
    assert not hasattr(campaign, "readiness_score")
    assert not hasattr(campaign, "readiness_checklist")
    assert not hasattr(campaign, "runs")
    assert not hasattr(campaign, "run_ids")
    assert not hasattr(campaign, "active_run_count")
    assert not hasattr(campaign, "dataset_manifest")
    assert not hasattr(campaign, "evidence_package")
    assert not hasattr(campaign, "review")


def test_campaign_scope_statement_is_immutable_validated_hashable_and_minimal() -> None:
    statement = CampaignScopeStatement("L1 trades, quotes, and NBBO")

    assert statement.value == "L1 trades, quotes, and NBBO"
    assert str(statement) == "L1 trades, quotes, and NBBO"
    assert statement == CampaignScopeStatement("L1 trades, quotes, and NBBO")
    assert hash(statement) == hash(CampaignScopeStatement("L1 trades, quotes, and NBBO"))
    with pytest.raises(FrozenInstanceError):
        statement.value = "changed"  # type: ignore[misc]
    assert not hasattr(statement, "run_id")
    assert not hasattr(statement, "dataset_id")
    assert not hasattr(statement, "evidence_package_id")
    assert not hasattr(statement, "review_id")
    assert not hasattr(statement, "vendor")
    assert not hasattr(statement, "trading_strategy")


@pytest.mark.parametrize("value", ("", " ", "\t\n"))
def test_campaign_scope_statement_rejects_blank_values(value: str) -> None:
    with pytest.raises(ValueError, match="campaign scope statement"):
        CampaignScopeStatement(value)


def test_campaign_scope_statement_rejects_wrong_type() -> None:
    with pytest.raises(TypeError, match="campaign scope statement"):
        CampaignScopeStatement(123)  # type: ignore[arg-type]


def test_scope_replacement_is_draft_only_and_does_not_advance_sequence_or_history() -> None:
    campaign = _campaign()
    replacement = CampaignScopeStatement("Replacement scope")

    campaign.revise_scope_statement(replacement)
    campaign.revise_scope_statement(CampaignScopeStatement("Second replacement"))

    assert campaign.scope_statement == CampaignScopeStatement("Second replacement")
    assert campaign.state is CampaignLifecycleState.DRAFT
    assert campaign.version == AggregateVersion(2)
    assert campaign.next_transition_sequence == TransitionSequence.initial()
    assert campaign.transition_history == ()


def test_equal_scope_replacement_is_allowed_in_draft_and_counts_as_content_mutation() -> None:
    campaign = _campaign()
    same_value = CampaignScopeStatement(campaign.scope_statement.value)

    campaign.revise_scope_statement(same_value)

    assert campaign.scope_statement == same_value
    assert campaign.version == AggregateVersion(1)
    assert campaign.next_transition_sequence == TransitionSequence.initial()
    assert campaign.transition_history == ()


def test_scope_replacement_rejects_wrong_type_atomically() -> None:
    campaign = _campaign()
    before_type = _snapshot(campaign)
    with pytest.raises(TypeError, match="CampaignScopeStatement"):
        campaign.revise_scope_statement("replacement")  # type: ignore[arg-type]
    assert _snapshot(campaign) == before_type


@pytest.mark.parametrize(
    "state",
    (
        CampaignLifecycleState.READY_FOR_AUTHORIZATION,
        CampaignLifecycleState.AUTHORIZED,
        CampaignLifecycleState.ACTIVE,
        CampaignLifecycleState.SUSPENDED,
        CampaignLifecycleState.COMPLETED,
        CampaignLifecycleState.CANCELLED,
    ),
)
def test_scope_replacement_rejects_every_non_draft_state_atomically(
    state: CampaignLifecycleState,
) -> None:
    campaign = _campaign_at_state(state)
    before = _snapshot(campaign)

    with pytest.raises(ValueError, match="DRAFT"):
        campaign.revise_scope_statement(CampaignScopeStatement("too late"))

    assert _snapshot(campaign) == before


@pytest.mark.parametrize(
    ("method_name", "from_state", "to_state", "reason"),
    (
        (
            "prepare_for_authorization",
            CampaignLifecycleState.DRAFT,
            CampaignLifecycleState.READY_FOR_AUTHORIZATION,
            None,
        ),
        (
            "record_authorization",
            CampaignLifecycleState.READY_FOR_AUTHORIZATION,
            CampaignLifecycleState.AUTHORIZED,
            "authorization review accepted",
        ),
        (
            "activate",
            CampaignLifecycleState.AUTHORIZED,
            CampaignLifecycleState.ACTIVE,
            "campaign operation opened",
        ),
        (
            "suspend",
            CampaignLifecycleState.ACTIVE,
            CampaignLifecycleState.SUSPENDED,
            "governed pause",
        ),
        (
            "resume",
            CampaignLifecycleState.SUSPENDED,
            CampaignLifecycleState.ACTIVE,
            "restoration approved",
        ),
        (
            "complete",
            CampaignLifecycleState.ACTIVE,
            CampaignLifecycleState.COMPLETED,
            "completion basis recorded",
        ),
        (
            "cancel",
            CampaignLifecycleState.DRAFT,
            CampaignLifecycleState.CANCELLED,
            None,
        ),
        (
            "cancel",
            CampaignLifecycleState.READY_FOR_AUTHORIZATION,
            CampaignLifecycleState.CANCELLED,
            None,
        ),
        (
            "cancel",
            CampaignLifecycleState.AUTHORIZED,
            CampaignLifecycleState.CANCELLED,
            "abandoned before execution",
        ),
        (
            "cancel",
            CampaignLifecycleState.ACTIVE,
            CampaignLifecycleState.CANCELLED,
            "stopped before completion",
        ),
        (
            "cancel",
            CampaignLifecycleState.SUSPENDED,
            CampaignLifecycleState.CANCELLED,
            "not restored",
        ),
    ),
)
def test_every_allowed_lifecycle_transition_records_one_history_entry(
    method_name: str,
    from_state: CampaignLifecycleState,
    to_state: CampaignLifecycleState,
    reason: str | None,
) -> None:
    campaign = _campaign_at_state(from_state)
    before_version = campaign.version
    before_sequence = campaign.next_transition_sequence
    before_history_length = len(campaign.transition_history)

    kwargs = {
        "actor": "Campaign Owner",
        "occurred_at": OCCURRED_AT,
        "correlation_id": "corr-018",
    }
    if reason is not None:
        kwargs["reason"] = reason
    getattr(campaign, method_name)(**kwargs)

    assert campaign.state is to_state
    assert campaign.version == before_version.next()
    assert campaign.next_transition_sequence == before_sequence.next()
    assert len(campaign.transition_history) == before_history_length + 1
    record = campaign.transition_history[-1]
    assert record.from_state == from_state.value
    assert record.to_state == to_state.value
    assert record.version == before_version.next()
    assert record.sequence == before_sequence
    assert record.actor == "Campaign Owner"
    assert record.occurred_at == OCCURRED_AT
    assert record.identity_reference == campaign.identity
    assert record.correlation_id == "corr-018"
    assert record.reason == reason


def test_invalid_lifecycle_operations_are_atomic_from_every_state() -> None:
    operations = {
        "prepare_for_authorization": {"actor": "Campaign Owner", "occurred_at": OCCURRED_AT},
        "record_authorization": {
            "reason": "authorization review accepted",
            "actor": "Authorization Reviewer",
            "occurred_at": OCCURRED_AT,
        },
        "activate": {
            "reason": "campaign operation opened",
            "actor": "Campaign Operator",
            "occurred_at": OCCURRED_AT,
        },
        "suspend": {
            "reason": "governed pause",
            "actor": "Campaign Owner",
            "occurred_at": OCCURRED_AT,
        },
        "resume": {
            "reason": "restoration approved",
            "actor": "Campaign Owner",
            "occurred_at": OCCURRED_AT,
        },
        "complete": {
            "reason": "completion basis recorded",
            "actor": "Campaign Owner",
            "occurred_at": OCCURRED_AT,
        },
        "cancel": {
            "reason": "cancelled",
            "actor": "Campaign Owner",
            "occurred_at": OCCURRED_AT,
        },
    }
    allowed = {
        (CampaignLifecycleState.DRAFT, "prepare_for_authorization"),
        (CampaignLifecycleState.DRAFT, "cancel"),
        (CampaignLifecycleState.READY_FOR_AUTHORIZATION, "record_authorization"),
        (CampaignLifecycleState.READY_FOR_AUTHORIZATION, "cancel"),
        (CampaignLifecycleState.AUTHORIZED, "activate"),
        (CampaignLifecycleState.AUTHORIZED, "cancel"),
        (CampaignLifecycleState.ACTIVE, "suspend"),
        (CampaignLifecycleState.ACTIVE, "complete"),
        (CampaignLifecycleState.ACTIVE, "cancel"),
        (CampaignLifecycleState.SUSPENDED, "resume"),
        (CampaignLifecycleState.SUSPENDED, "cancel"),
    }

    for state in CampaignLifecycleState:
        for operation_name, kwargs in operations.items():
            if (state, operation_name) in allowed:
                continue
            campaign = _campaign_at_state(state)
            before = _snapshot(campaign)
            with pytest.raises(ValueError, match=state.value):
                getattr(campaign, operation_name)(**kwargs)
            assert _snapshot(campaign) == before


def test_lifecycle_metadata_validation_is_atomic() -> None:
    for kwargs, error in (
        ({"actor": " ", "occurred_at": OCCURRED_AT}, "actor"),
        ({"actor": "Campaign Owner", "occurred_at": "now"}, "datetime"),
        (
            {
                "actor": "Campaign Owner",
                "occurred_at": OCCURRED_AT,
                "correlation_id": " ",
            },
            "correlation_id",
        ),
        (
            {"actor": "Campaign Owner", "occurred_at": OCCURRED_AT, "reason": " "},
            "reason",
        ),
    ):
        campaign = _campaign()
        before = _snapshot(campaign)
        with pytest.raises((TypeError, ValueError), match=error):
            campaign.prepare_for_authorization(**kwargs)  # type: ignore[arg-type]
        assert _snapshot(campaign) == before


@pytest.mark.parametrize(
    ("method_name", "state", "field_name"),
    (
        (
            "record_authorization",
            CampaignLifecycleState.READY_FOR_AUTHORIZATION,
            "authorization reason",
        ),
        ("activate", CampaignLifecycleState.AUTHORIZED, "activation reason"),
        ("suspend", CampaignLifecycleState.ACTIVE, "suspension reason"),
        ("resume", CampaignLifecycleState.SUSPENDED, "resume reason"),
        ("complete", CampaignLifecycleState.ACTIVE, "completion reason"),
    ),
)
def test_required_reason_operations_reject_blank_and_wrong_types_atomically(
    method_name: str,
    state: CampaignLifecycleState,
    field_name: str,
) -> None:
    for invalid_reason in (" ", 123):
        campaign = _campaign_at_state(state)
        before = _snapshot(campaign)
        with pytest.raises((TypeError, ValueError), match=field_name):
            getattr(campaign, method_name)(
                reason=invalid_reason,
                actor="Campaign Owner",
                occurred_at=OCCURRED_AT,
            )
        assert _snapshot(campaign) == before


@pytest.mark.parametrize(
    "state",
    (
        CampaignLifecycleState.AUTHORIZED,
        CampaignLifecycleState.ACTIVE,
        CampaignLifecycleState.SUSPENDED,
    ),
)
def test_cancel_requires_reason_after_authorization_boundary(state: CampaignLifecycleState) -> None:
    for invalid_reason in (None, " ", 123):
        campaign = _campaign_at_state(state)
        before = _snapshot(campaign)
        with pytest.raises((TypeError, ValueError), match="cancellation reason"):
            campaign.cancel(
                reason=invalid_reason,  # type: ignore[arg-type]
                actor="Campaign Owner",
                occurred_at=OCCURRED_AT,
            )
        assert _snapshot(campaign) == before


def test_cancel_allows_optional_reason_before_authorization_boundary() -> None:
    draft = _campaign()
    draft.cancel(actor="Campaign Owner", occurred_at=OCCURRED_AT)
    assert draft.state is CampaignLifecycleState.CANCELLED
    assert draft.transition_history[-1].reason is None

    ready = _campaign_at_state(CampaignLifecycleState.READY_FOR_AUTHORIZATION)
    ready.cancel(
        reason="abandon before authorization",
        actor="Campaign Owner",
        occurred_at=OCCURRED_AT,
    )
    assert ready.state is CampaignLifecycleState.CANCELLED
    assert ready.transition_history[-1].reason == "abandon before authorization"


def test_readiness_is_lifecycle_only_and_authorization_does_not_activate() -> None:
    campaign = _campaign()

    campaign.prepare_for_authorization(actor="Campaign Owner", occurred_at=OCCURRED_AT)
    assert campaign.state is CampaignLifecycleState.READY_FOR_AUTHORIZATION
    assert not hasattr(campaign, "is_ready")
    assert not hasattr(campaign, "ready")
    assert not hasattr(campaign, "readiness_calculator")
    assert not hasattr(campaign, "check_readiness")

    campaign.record_authorization(
        reason="authorization review accepted",
        actor="Authorization Reviewer",
        occurred_at=OCCURRED_AT,
    )
    assert campaign.state is CampaignLifecycleState.AUTHORIZED


def test_suspend_resume_repeat_and_terminal_rejections_are_atomic() -> None:
    active = _campaign_at_state(CampaignLifecycleState.ACTIVE)
    active.suspend(reason="governed pause", actor="Campaign Owner", occurred_at=OCCURRED_AT)
    suspended_snapshot = _snapshot(active)

    with pytest.raises(ValueError, match="SUSPENDED"):
        active.suspend(reason="again", actor="Campaign Owner", occurred_at=OCCURRED_AT)
    assert _snapshot(active) == suspended_snapshot

    active.resume(reason="restored", actor="Campaign Owner", occurred_at=OCCURRED_AT)
    resumed_snapshot = _snapshot(active)
    with pytest.raises(ValueError, match="ACTIVE"):
        active.resume(reason="again", actor="Campaign Owner", occurred_at=OCCURRED_AT)
    assert _snapshot(active) == resumed_snapshot

    completed = _campaign_at_state(CampaignLifecycleState.COMPLETED)
    before_completed = _snapshot(completed)
    with pytest.raises(ValueError, match="COMPLETED"):
        completed.resume(reason="restore terminal", actor="Campaign Owner", occurred_at=OCCURRED_AT)
    assert _snapshot(completed) == before_completed


def test_multiple_suspend_resume_cycles_are_allowed_and_sequence_exact() -> None:
    campaign = _campaign_at_state(CampaignLifecycleState.ACTIVE)

    campaign.suspend(reason="first pause", actor="Campaign Owner", occurred_at=OCCURRED_AT)
    campaign.resume(reason="first restoration", actor="Campaign Owner", occurred_at=OCCURRED_AT)
    campaign.suspend(reason="second pause", actor="Campaign Owner", occurred_at=OCCURRED_AT)
    campaign.resume(reason="second restoration", actor="Campaign Owner", occurred_at=OCCURRED_AT)

    assert campaign.state is CampaignLifecycleState.ACTIVE
    assert campaign.version == AggregateVersion(7)
    assert campaign.next_transition_sequence == TransitionSequence(8)
    assert [record.to_state for record in campaign.transition_history] == [
        "READY_FOR_AUTHORIZATION",
        "AUTHORIZED",
        "ACTIVE",
        "SUSPENDED",
        "ACTIVE",
        "SUSPENDED",
        "ACTIVE",
    ]
    assert [record.sequence for record in campaign.transition_history] == [
        TransitionSequence(1),
        TransitionSequence(2),
        TransitionSequence(3),
        TransitionSequence(4),
        TransitionSequence(5),
        TransitionSequence(6),
        TransitionSequence(7),
    ]


def test_terminal_immutability_blocks_lifecycle_and_scope_mutation() -> None:
    for terminal in (
        CampaignLifecycleState.COMPLETED,
        CampaignLifecycleState.CANCELLED,
    ):
        campaign = _campaign_at_state(terminal)
        before = _snapshot(campaign)

        with pytest.raises(ValueError, match=terminal.value):
            campaign.prepare_for_authorization(actor="Campaign Owner", occurred_at=OCCURRED_AT)
        with pytest.raises(ValueError, match=terminal.value):
            campaign.cancel(
                reason="second cancellation",
                actor="Campaign Owner",
                occurred_at=OCCURRED_AT,
            )
        with pytest.raises(ValueError, match=terminal.value):
            campaign.revise_scope_statement(CampaignScopeStatement("terminal mutation"))
        assert _snapshot(campaign) == before

    assert not hasattr(_campaign_at_state(CampaignLifecycleState.COMPLETED), "reopen")
    assert not hasattr(_campaign_at_state(CampaignLifecycleState.CANCELLED), "restart")
    assert not hasattr(_campaign_at_state(CampaignLifecycleState.CANCELLED), "retry")


def test_mixed_path_has_exact_cumulative_version_sequence_history_and_scope() -> None:
    campaign = _campaign()
    replacement = CampaignScopeStatement("Revised draft scope")

    campaign.revise_scope_statement(replacement)
    campaign.prepare_for_authorization(
        actor="Campaign Owner",
        occurred_at=OCCURRED_AT,
        reason="ready for review",
    )
    campaign.record_authorization(
        reason="authorization review accepted",
        actor="Authorization Reviewer",
        occurred_at=OCCURRED_AT,
    )
    campaign.activate(
        reason="campaign operation opened",
        actor="Campaign Operator",
        occurred_at=OCCURRED_AT,
    )
    campaign.suspend(reason="governed pause", actor="Campaign Owner", occurred_at=OCCURRED_AT)
    campaign.resume(reason="restored", actor="Campaign Owner", occurred_at=OCCURRED_AT)
    campaign.complete(
        reason="completion basis recorded",
        actor="Campaign Owner",
        occurred_at=OCCURRED_AT,
    )

    assert campaign.scope_statement == replacement
    assert campaign.state is CampaignLifecycleState.COMPLETED
    assert campaign.version == AggregateVersion(7)
    assert campaign.next_transition_sequence == TransitionSequence(7)
    assert [record.to_state for record in campaign.transition_history] == [
        "READY_FOR_AUTHORIZATION",
        "AUTHORIZED",
        "ACTIVE",
        "SUSPENDED",
        "ACTIVE",
        "COMPLETED",
    ]
    assert [record.sequence for record in campaign.transition_history] == [
        TransitionSequence(1),
        TransitionSequence(2),
        TransitionSequence(3),
        TransitionSequence(4),
        TransitionSequence(5),
        TransitionSequence(6),
    ]
    assert [record.version for record in campaign.transition_history] == [
        AggregateVersion(2),
        AggregateVersion(3),
        AggregateVersion(4),
        AggregateVersion(5),
        AggregateVersion(6),
        AggregateVersion(7),
    ]


def test_valid_cancellation_paths_have_exact_terminal_effects() -> None:
    for state in (
        CampaignLifecycleState.DRAFT,
        CampaignLifecycleState.READY_FOR_AUTHORIZATION,
        CampaignLifecycleState.AUTHORIZED,
        CampaignLifecycleState.ACTIVE,
        CampaignLifecycleState.SUSPENDED,
    ):
        campaign = _campaign_at_state(state)
        before_version = campaign.version
        before_sequence = campaign.next_transition_sequence
        reason = (
            None
            if state
            in (
                CampaignLifecycleState.DRAFT,
                CampaignLifecycleState.READY_FOR_AUTHORIZATION,
            )
            else f"cancel from {state.value}"
        )

        campaign.cancel(reason=reason, actor="Campaign Owner", occurred_at=OCCURRED_AT)

        assert campaign.state is CampaignLifecycleState.CANCELLED
        assert campaign.version == before_version.next()
        assert campaign.next_transition_sequence == before_sequence.next()
        assert campaign.transition_history[-1].from_state == state.value
        assert campaign.transition_history[-1].to_state == "CANCELLED"
        assert campaign.transition_history[-1].reason == reason


def test_campaign_has_no_deferred_infrastructure_or_cross_aggregate_surface() -> None:
    campaign = _campaign_at_state(CampaignLifecycleState.AUTHORIZED)

    assert not hasattr(campaign, "save")
    assert not hasattr(campaign, "load")
    assert not hasattr(campaign, "repository")
    assert not hasattr(campaign, "session")
    assert not hasattr(campaign, "database")
    assert not hasattr(campaign, "bucket")
    assert not hasattr(campaign, "object_key")
    assert not hasattr(campaign, "dispatch")
    assert not hasattr(campaign, "outbox")
    assert not hasattr(campaign, "audit")
    assert not hasattr(campaign, "decision_candidate")
    assert not hasattr(campaign, "decision_freeze")
    assert not hasattr(campaign, "vendor")
    assert not hasattr(campaign, "market_data")
    assert not hasattr(campaign, "trading")
    assert not hasattr(campaign, "orchestrator")


def _campaign_at_state(state: CampaignLifecycleState) -> Campaign:
    campaign = _campaign()
    if state is CampaignLifecycleState.DRAFT:
        return campaign

    campaign.prepare_for_authorization(actor="Campaign Owner", occurred_at=OCCURRED_AT)
    if state in (
        CampaignLifecycleState.READY_FOR_AUTHORIZATION,
        CampaignLifecycleState.CANCELLED,
    ):
        if state is CampaignLifecycleState.CANCELLED:
            campaign.cancel(actor="Campaign Owner", occurred_at=OCCURRED_AT)
        return campaign

    campaign.record_authorization(
        reason="authorization review accepted",
        actor="Authorization Reviewer",
        occurred_at=OCCURRED_AT,
    )
    if state is CampaignLifecycleState.AUTHORIZED:
        return campaign

    campaign.activate(
        reason="campaign operation opened",
        actor="Campaign Operator",
        occurred_at=OCCURRED_AT,
    )
    if state in (CampaignLifecycleState.ACTIVE, CampaignLifecycleState.COMPLETED):
        if state is CampaignLifecycleState.COMPLETED:
            campaign.complete(
                reason="completion basis recorded",
                actor="Campaign Owner",
                occurred_at=OCCURRED_AT,
            )
        return campaign

    campaign.suspend(reason="governed pause", actor="Campaign Owner", occurred_at=OCCURRED_AT)
    return campaign
