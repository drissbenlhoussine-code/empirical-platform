"""MILESTONE-084 persistence-neutral contracts for the decision-to-approval core.

WHAT IS ABSENT IS THE POINT. There is no `update`, no `delete`, and no method
anywhere below that can move an intent out of NOT_SUBMITTED, because
MILESTONE-084 has no such transition to offer. A future milestone that gains
one must add it here, in the open, rather than find it already waiting.

There is also no method that takes an approval and a proposal chosen
independently: `issue_intent` derives everything from the two rows it is given
and the database re-derives it again. Two layers say the same thing on purpose
-- the application refusal is the fast, legible one, and the database refusal
is the one that survives a caller who never came through here.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from empirical_platform.decision_candidate.evaluation_context import EvaluationContext
from empirical_platform.decision_candidate.operator_trading_configuration import (
    OperatorTradingConfiguration,
)
from empirical_platform.decision_candidate.trade_approval import (
    ApprovalDecision,
    ApprovedOrderIntent,
)
from empirical_platform.decision_candidate.trade_proposal import ProposalStatus, TradeProposal

__all__ = [
    "ApprovalDecisionRepository",
    "ApprovedOrderIntentRepository",
    "EvaluationContextRepository",
    "OperatorTradingConfigurationRepository",
    "TradeProposalRepository",
]


class OperatorTradingConfigurationRepository(Protocol):
    """Append-only store of versioned operator policy."""

    def save(self, configuration: OperatorTradingConfiguration) -> OperatorTradingConfiguration:
        """Persist one configuration version.

        Versions are never edited. Changing policy means storing a new version,
        so that every proposal can name the exact policy text that governed it.
        """
        ...

    def get(
        self, configuration_governance_id: str, configuration_version: int
    ) -> OperatorTradingConfiguration | None: ...

    def latest(self, configuration_governance_id: str) -> OperatorTradingConfiguration | None: ...


class EvaluationContextRepository(Protocol):
    """Append-only store of what one evaluation consumed."""

    def save(self, context: EvaluationContext) -> EvaluationContext: ...

    def get(self, evaluation_context_id: str) -> EvaluationContext | None: ...


class TradeProposalRepository(Protocol):
    """Append-only store of proposals, with status as the one mutable field."""

    def save(self, proposal: TradeProposal) -> TradeProposal: ...

    def get(self, proposal_governance_id: str) -> TradeProposal | None: ...

    def list_by_status(self, status: ProposalStatus) -> tuple[TradeProposal, ...]: ...

    def counts_by_status(self) -> Mapping[ProposalStatus, int]:
        """How many proposals sit in each status.

        A count rather than a listing: a status summary should not have to load
        every proposal and its risk-check evidence to say how many there are.
        """
        ...

    def set_status(self, proposal_governance_id: str, status: ProposalStatus) -> TradeProposal:
        """Move one proposal along the closed transition table.

        Implementations MUST NOT accept any other field. The database refuses a
        statement that changes an order term regardless, but an interface that
        offered the option would invite a caller to try.
        """
        ...


class ApprovalDecisionRepository(Protocol):
    """Append-only store of explicit human decisions."""

    def record(self, decision: ApprovalDecision) -> ApprovalDecision:
        """Persist one decision about one proposal.

        There is at most one decision per proposal, enforced by the database.
        A caller that wants to change its mind after deciding cannot: it must
        prepare a new proposal, which is a new thing to approve.
        """
        ...

    def get(self, decision_governance_id: str) -> ApprovalDecision | None: ...

    def for_proposal(self, proposal_governance_id: str) -> ApprovalDecision | None: ...


class ApprovedOrderIntentRepository(Protocol):
    """Append-only store of broker-neutral, never-submitted order intents."""

    def issue(self, intent: ApprovedOrderIntent) -> ApprovedOrderIntent:
        """Persist one intent for one approved proposal.

        Deliberately named `issue`, not `submit` or `send`: this milestone
        hands an intent onward to a human-readable record and to nothing else.
        """
        ...

    def get(self, intent_governance_id: str) -> ApprovedOrderIntent | None: ...

    def for_proposal(self, proposal_governance_id: str) -> ApprovedOrderIntent | None: ...
