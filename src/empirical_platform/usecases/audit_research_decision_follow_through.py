"""MILESTONE-078. Audit what a research session's approved plans have recorded
against them in the operator's own ledger.

Read-only with respect to M070 and M076: both are consumed through their frozen
public contracts and neither is modified.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from empirical_platform.decision_candidate.operator_position_ledger import (
    LedgerRejectionError,
    derive_position_state,
)
from empirical_platform.decision_candidate.operator_position_ledger_repository import (
    OperatorPositionLedgerRepository,
)
from empirical_platform.decision_candidate.research_decision_follow_through import (
    ApprovedPlanReference,
    ResearchDecisionFollowThrough,
    audit_research_decision_follow_through,
)
from empirical_platform.decision_candidate.research_session import ResearchSession
from empirical_platform.decision_candidate.research_session_repository import (
    ResearchSessionRepository,
)
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import ResearchSessionId

__all__ = [
    "AuditResearchDecisionFollowThroughHandler",
    "AuditResearchDecisionFollowThroughQuery",
    "approved_plan_references",
]


@dataclass(frozen=True, slots=True)
class AuditResearchDecisionFollowThroughQuery:
    """`as_of` is required and inclusive -- see the domain module for why there
    is deliberately no default."""

    identity: DomainIdentity[ResearchSessionId]
    as_of: datetime

    def __post_init__(self) -> None:
        # Implementation review R03. A naive `as_of` makes M076's fold raise
        # LedgerRejectionError, which the handler below converts to
        # LEDGER_INCOHERENT -- telling the operator their persisted data is
        # corrupt when in fact the REQUEST was malformed. A bad request is
        # rejected here, at construction, before any I/O, so the two conditions
        # can never be confused.
        if self.as_of.tzinfo is None or self.as_of.utcoffset() is None:
            raise ValueError("as_of must be timezone-aware; a naive datetime has no instant")


def approved_plan_references(session: ResearchSession) -> tuple[ApprovedPlanReference, ...]:
    """The session's approved position plans, as the session itself recorded
    them.

    MILESTONE-070's orchestrator persists `position_plan_governance_id` on the
    APPROVED branch only, so its presence is exactly the session's own record
    of an approved position plan. No status string is re-derived here.
    """
    return tuple(
        ApprovedPlanReference(
            rank=decision.rank,
            instrument_symbol=decision.instrument_symbol,
            position_plan_governance_id=decision.position_plan_governance_id,
        )
        for decision in session.decisions
        if decision.position_plan_governance_id is not None
    )


class AuditResearchDecisionFollowThroughHandler:
    """Join one persisted session to the persisted operator ledger."""

    __slots__ = ("_sessions", "_ledger")

    def __init__(
        self,
        *,
        research_session_repository: ResearchSessionRepository,
        operator_position_ledger_repository: OperatorPositionLedgerRepository | None = None,
    ) -> None:
        self._sessions = research_session_repository
        self._ledger = operator_position_ledger_repository

    def handle(
        self, query: AuditResearchDecisionFollowThroughQuery
    ) -> ResearchDecisionFollowThrough:
        session = self._sessions.get(query.identity)
        plans = approved_plan_references(session)
        session_governance_id = str(session.identity.governance_id)

        if self._ledger is None:
            return audit_research_decision_follow_through(
                session_governance_id=session_governance_id,
                session_as_of=session.as_of,
                approved_plans=plans,
                events=(),
                held_state=None,
                as_of=query.as_of,
                ledger_available=False,
            )
        try:
            events = self._ledger.list_all()
            state = derive_position_state(events=events, as_of=query.as_of)
        except LedgerRejectionError:
            # Bad DATA is withheld honestly. A broken DATABASE is not caught
            # here and propagates, so a failed deployment is never disguised as
            # a soft verdict.
            return audit_research_decision_follow_through(
                session_governance_id=session_governance_id,
                session_as_of=session.as_of,
                approved_plans=plans,
                events=(),
                held_state=None,
                as_of=query.as_of,
                ledger_available=True,
            )
        return audit_research_decision_follow_through(
            session_governance_id=session_governance_id,
            session_as_of=session.as_of,
            approved_plans=plans,
            events=events,
            held_state=state,
            as_of=query.as_of,
            ledger_available=True,
        )
