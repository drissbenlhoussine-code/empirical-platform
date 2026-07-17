from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from empirical_platform.identifiers import CampaignId
from empirical_platform.shared.domain import (
    AggregateVersion,
    StateTransitionRecord,
    TransitionSequence,
)


def test_aggregate_version_is_non_negative_immutable_and_successor_based() -> None:
    version = AggregateVersion.initial()

    assert version.value == 0
    assert version.next() == AggregateVersion(1)
    with pytest.raises(ValueError):
        AggregateVersion(-1)
    with pytest.raises(TypeError):
        AggregateVersion(True)
    with pytest.raises(FrozenInstanceError):
        version.value = 99  # type: ignore[misc]


def test_transition_sequence_is_positive_immutable_and_distinct_from_version() -> None:
    sequence = TransitionSequence.initial()

    assert sequence.value == 1
    assert sequence.next() == TransitionSequence(2)
    assert sequence != AggregateVersion(1)
    with pytest.raises(ValueError):
        TransitionSequence(0)
    with pytest.raises(TypeError):
        TransitionSequence(False)
    with pytest.raises(FrozenInstanceError):
        sequence.value = 99  # type: ignore[misc]


def test_state_transition_record_is_immutable_historical_data_not_event() -> None:
    record = StateTransitionRecord(
        from_state="DRAFT",
        to_state="READY_FOR_AUTHORIZATION",
        version=AggregateVersion(1),
        sequence=TransitionSequence(1),
        actor="Campaign Owner",
        occurred_at=datetime(2026, 7, 17, tzinfo=UTC),
        identity_reference=CampaignId("CAMP-0001"),
        correlation_id="corr-1",
        reason="scope complete",
    )

    assert record.from_state == "DRAFT"
    assert record.to_state == "READY_FOR_AUTHORIZATION"
    assert record.identity_reference == CampaignId("CAMP-0001")
    assert record.correlation_id == "corr-1"
    assert not hasattr(record, "event_id")
    assert not hasattr(record, "outbox_id")
    with pytest.raises(FrozenInstanceError):
        record.to_state = "AUTHORIZED"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("field", "kwargs"),
    [
        ("from_state", {"from_state": ""}),
        ("to_state", {"to_state": ""}),
        ("actor", {"actor": ""}),
        ("correlation_id", {"correlation_id": ""}),
        ("reason", {"reason": ""}),
    ],
)
def test_state_transition_record_rejects_blank_required_context(
    field: str,
    kwargs: dict[str, str],
) -> None:
    base: dict[str, object] = {
        "from_state": "DRAFT",
        "to_state": "READY_FOR_AUTHORIZATION",
        "version": AggregateVersion(1),
        "sequence": TransitionSequence(1),
        "actor": "Campaign Owner",
        "occurred_at": datetime(2026, 7, 17, tzinfo=UTC),
    }
    base.update(kwargs)

    with pytest.raises(ValueError, match=field):
        StateTransitionRecord(**base)  # type: ignore[arg-type]
