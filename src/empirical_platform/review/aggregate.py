"""Process-local Review aggregate behavior."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import ClassVar

from empirical_platform.identifiers import DomainIdentity, EvidencePackageId, ReviewId
from empirical_platform.review.lifecycle import ReviewDisposition, ReviewLifecycleState
from empirical_platform.shared.domain import (
    AggregateVersion,
    StateTransitionRecord,
    TransitionSequence,
)


@dataclass(frozen=True, slots=True)
class ReviewTargetReference:
    """Immutable Evidence Package target reference for one Review."""

    evidence_package_id: EvidencePackageId
    target_kind: str = field(default="EVIDENCE_PACKAGE", init=False)
    EXPECTED_KIND: ClassVar[str] = "EVIDENCE_PACKAGE"

    def __post_init__(self) -> None:
        if not isinstance(self.evidence_package_id, EvidencePackageId):
            raise TypeError("evidence_package_id must be an EvidencePackageId")


@dataclass(frozen=True, slots=True)
class ReviewerReference:
    """Opaque local reviewer reference data, not authority."""

    value: str

    def __post_init__(self) -> None:
        _require_non_empty(self.value, "reviewer reference")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class ReviewFinding:
    """Immutable finding owned by one Review aggregate."""

    sequence: int
    text: str
    rationale: str | None = None
    evidence_references: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.sequence, int) or isinstance(self.sequence, bool):
            raise TypeError("finding sequence must be an integer")
        if self.sequence < 1:
            raise ValueError("finding sequence must be positive")
        _require_non_empty(self.text, "finding text")
        _require_optional_non_empty(self.rationale, "finding rationale")
        if not isinstance(self.evidence_references, tuple):
            raise TypeError("evidence_references must be a tuple")
        for reference in self.evidence_references:
            _require_non_empty(reference, "evidence reference")


class Review:
    """Process-local Review aggregate root."""

    __slots__ = (
        "_cancellation_reason",
        "_disposition",
        "_final_disposition_rationale",
        "_findings",
        "_identity",
        "_next_finding_sequence",
        "_next_transition_sequence",
        "_reviewer",
        "_state",
        "_target",
        "_transition_history",
        "_version",
    )

    def __init__(
        self,
        *,
        identity: DomainIdentity[ReviewId],
        target: ReviewTargetReference,
        reviewer: ReviewerReference,
    ) -> None:
        if not isinstance(identity, DomainIdentity):
            raise TypeError("identity must be a DomainIdentity[ReviewId]")
        if not isinstance(identity.governance_id, ReviewId):
            raise TypeError("identity governance_id must be a ReviewId")
        if not isinstance(target, ReviewTargetReference):
            raise TypeError("target must be a ReviewTargetReference")
        if not isinstance(reviewer, ReviewerReference):
            raise TypeError("reviewer must be a ReviewerReference")

        self._identity = identity
        self._target = target
        self._reviewer = reviewer
        self._state = ReviewLifecycleState.ASSIGNED
        self._version = AggregateVersion.initial()
        self._next_transition_sequence = TransitionSequence.initial()
        self._transition_history: tuple[StateTransitionRecord[DomainIdentity[ReviewId]], ...] = ()
        self._findings: tuple[ReviewFinding, ...] = ()
        self._next_finding_sequence = 1
        self._disposition: ReviewDisposition | None = None
        self._final_disposition_rationale: str | None = None
        self._cancellation_reason: str | None = None

    @property
    def identity(self) -> DomainIdentity[ReviewId]:
        """Return immutable Review identity."""
        return self._identity

    @property
    def target(self) -> ReviewTargetReference:
        """Return immutable Review target reference."""
        return self._target

    @property
    def reviewer(self) -> ReviewerReference:
        """Return opaque reviewer reference data."""
        return self._reviewer

    @property
    def state(self) -> ReviewLifecycleState:
        """Return current lifecycle state."""
        return self._state

    @property
    def version(self) -> AggregateVersion:
        """Return current aggregate version."""
        return self._version

    @property
    def next_transition_sequence(self) -> TransitionSequence:
        """Return the sequence available for the next lifecycle transition."""
        return self._next_transition_sequence

    @property
    def transition_history(self) -> tuple[StateTransitionRecord[DomainIdentity[ReviewId]], ...]:
        """Return immutable lifecycle transition history."""
        return self._transition_history

    @property
    def findings(self) -> tuple[ReviewFinding, ...]:
        """Return immutable Review findings in insertion order."""
        return self._findings

    @property
    def disposition(self) -> ReviewDisposition | None:
        """Return final Review disposition, if completed."""
        return self._disposition

    @property
    def final_disposition_rationale(self) -> str | None:
        """Return final disposition rationale, if completed."""
        return self._final_disposition_rationale

    @property
    def cancellation_reason(self) -> str | None:
        """Return cancellation reason, if cancelled."""
        return self._cancellation_reason

    def start(
        self,
        *,
        actor: str,
        occurred_at: datetime,
        correlation_id: str | None = None,
        reason: str | None = None,
    ) -> None:
        """Transition the Review from ASSIGNED to IN_PROGRESS."""
        self._transition(
            allowed_states=(ReviewLifecycleState.ASSIGNED,),
            next_state=ReviewLifecycleState.IN_PROGRESS,
            actor=actor,
            occurred_at=occurred_at,
            correlation_id=correlation_id,
            reason=reason,
        )

    def add_finding(
        self,
        *,
        text: str,
        rationale: str | None = None,
        evidence_references: tuple[str, ...] = (),
    ) -> None:
        """Append a bounded immutable finding while the Review is in progress."""
        if self._state is not ReviewLifecycleState.IN_PROGRESS:
            raise ValueError("findings may be added only while IN_PROGRESS")
        finding = ReviewFinding(
            sequence=self._next_finding_sequence,
            text=text,
            rationale=rationale,
            evidence_references=evidence_references,
        )
        next_version = self._version.next()
        next_findings = (*self._findings, finding)
        next_finding_sequence = self._next_finding_sequence + 1

        self._version = next_version
        self._findings = next_findings
        self._next_finding_sequence = next_finding_sequence

    def complete(
        self,
        *,
        disposition: ReviewDisposition,
        final_disposition_rationale: str,
        actor: str,
        occurred_at: datetime,
        correlation_id: str | None = None,
    ) -> None:
        """Complete the Review with one final disposition and rationale."""
        if self._state is not ReviewLifecycleState.IN_PROGRESS:
            raise ValueError(
                f"Review may complete only while IN_PROGRESS; current state is {self._state.value}"
            )
        if not self._findings:
            raise ValueError("Review requires at least one finding before completion")
        if not isinstance(disposition, ReviewDisposition):
            raise TypeError("disposition must be a ReviewDisposition")
        _require_non_empty(final_disposition_rationale, "final disposition rationale")

        self._transition(
            allowed_states=(ReviewLifecycleState.IN_PROGRESS,),
            next_state=ReviewLifecycleState.COMPLETED,
            actor=actor,
            occurred_at=occurred_at,
            correlation_id=correlation_id,
            reason=final_disposition_rationale,
        )
        self._disposition = disposition
        self._final_disposition_rationale = final_disposition_rationale

    def cancel(
        self,
        *,
        reason: str,
        actor: str,
        occurred_at: datetime,
        correlation_id: str | None = None,
    ) -> None:
        """Cancel the Review from a non-terminal state."""
        _require_non_empty(reason, "cancellation reason")
        self._transition(
            allowed_states=(
                ReviewLifecycleState.ASSIGNED,
                ReviewLifecycleState.IN_PROGRESS,
            ),
            next_state=ReviewLifecycleState.CANCELLED,
            actor=actor,
            occurred_at=occurred_at,
            correlation_id=correlation_id,
            reason=reason,
        )
        self._cancellation_reason = reason

    def _transition(
        self,
        *,
        allowed_states: tuple[ReviewLifecycleState, ...],
        next_state: ReviewLifecycleState,
        actor: str,
        occurred_at: datetime,
        correlation_id: str | None,
        reason: str | None,
    ) -> None:
        if self._state not in allowed_states:
            allowed = ", ".join(state.value for state in allowed_states)
            raise ValueError(f"cannot transition from {self._state.value}; expected {allowed}")
        if not isinstance(occurred_at, datetime):
            raise TypeError("occurred_at must be a datetime")
        _require_non_empty(actor, "actor")
        _require_optional_non_empty(correlation_id, "correlation_id")
        _require_optional_non_empty(reason, "reason")

        next_version = self._version.next()
        current_sequence = self._next_transition_sequence
        next_sequence = current_sequence.next()
        record = StateTransitionRecord(
            from_state=self._state.value,
            to_state=next_state.value,
            version=next_version,
            sequence=current_sequence,
            actor=actor,
            occurred_at=occurred_at,
            identity_reference=self._identity,
            correlation_id=correlation_id,
            reason=reason,
        )
        next_history = (*self._transition_history, record)

        self._state = next_state
        self._version = next_version
        self._next_transition_sequence = next_sequence
        self._transition_history = next_history


def _require_non_empty(value: str, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if value.strip() == "":
        raise ValueError(f"{field_name} must be non-empty")


def _require_optional_non_empty(value: str | None, field_name: str) -> None:
    if value is None:
        return
    _require_non_empty(value, field_name)
