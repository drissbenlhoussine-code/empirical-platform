"""MILESTONE-084 -- the human approval state machine and the approved order intent.

WHAT THIS IS. The boundary at which a human Owner authorizes one exact,
immutable order -- and the broker-neutral record that authorization produces.

APPROVAL AUTHORIZES ONE EXACT VERSION, NOT AN INTENTION. An approval binds the
proposal identity, the proposal version, and the content fingerprint together.
Change the quantity, the price, the symbol, the order type, the expiry or the
governing configuration version and the fingerprint changes, so the old approval
no longer matches anything. There is no wildcard approval, no approval that
covers several proposals, no approval inherited by a successor version, and no
approval that arrives by timeout or by the absence of a rejection.

WHAT AN APPROVAL IS NOT. It is not an executed trade, and in MILESTONE-084 it is
not permission to submit anything: this milestone has no code path that reaches
a broker. An `ApprovedOrderIntent` is the hand-off record M085 will later read;
its submission state is fixed at `NOT_SUBMITTED` and this milestone provides no
transition away from it.

THE TRANSITION TABLE IS THE CONTRACT. `ALLOWED_TRANSITIONS` below is mirrored by
a database trigger. The domain refuses an illegal transition so a caller gets a
clear error; the database refuses it so a direct-SQL writer cannot bypass the
domain. Neither alone would be enough.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType

from empirical_platform.decision_candidate.operator_trading_configuration import OrderType
from empirical_platform.decision_candidate.trade_proposal import ProposalStatus, TradeProposal

__all__ = [
    "ALLOWED_TRANSITIONS",
    "ApprovalDecision",
    "ApprovedOrderIntent",
    "OperatorAction",
    "SubmissionState",
    "build_approved_order_intent",
    "is_transition_allowed",
    "record_operator_decision",
]

_MAXIMUM_IDENTIFIER_LENGTH = 64


class OperatorAction(StrEnum):
    """What the human Owner explicitly did.

    Every member is an affirmative act. There is deliberately no member meaning
    "did nothing" or "let it lapse": expiry is a state the system computes, not
    a decision the operator can be recorded as having made.
    """

    APPROVE = "APPROVE"
    REJECT = "REJECT"
    CANCEL = "CANCEL"


class SubmissionState(StrEnum):
    """Whether an approved intent has reached a broker.

    MILESTONE-084 defines exactly one member. SUBMITTED is not declared here,
    because declaring a state this milestone cannot produce would describe a
    capability that does not exist. M085 introduces the broker boundary and the
    states that go with it.
    """

    NOT_SUBMITTED = "NOT_SUBMITTED"


#: The closed transition table, mirrored by the database trigger.
#:
#: PREPARED is the only state with outgoing transitions. Every terminal state is
#: genuinely terminal: an approved proposal cannot be re-approved into a new
#: shape, a rejected one cannot be revived, and an expired one cannot be
#: resumed. A changed proposal is a NEW proposal with a new identity.
ALLOWED_TRANSITIONS: MappingProxyType[ProposalStatus, frozenset[ProposalStatus]] = MappingProxyType(
    {
        ProposalStatus.PREPARED: frozenset(
            {
                ProposalStatus.APPROVED,
                ProposalStatus.REJECTED,
                ProposalStatus.CANCELLED,
                ProposalStatus.EXPIRED,
                ProposalStatus.INVALIDATED,
            }
        ),
        ProposalStatus.APPROVED: frozenset(),
        ProposalStatus.REJECTED: frozenset(),
        ProposalStatus.CANCELLED: frozenset(),
        ProposalStatus.EXPIRED: frozenset(),
        ProposalStatus.INVALIDATED: frozenset(),
    }
)


def is_transition_allowed(current: ProposalStatus, target: ProposalStatus) -> bool:
    """Whether `current -> target` is one of the closed allowed transitions."""
    if not isinstance(current, ProposalStatus) or not isinstance(target, ProposalStatus):
        raise ValueError("both states must be ProposalStatus members")
    return target in ALLOWED_TRANSITIONS[current]


def _require_identifier(value: str, *, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    if len(value) > _MAXIMUM_IDENTIFIER_LENGTH:
        raise ValueError(f"{field} must be at most {_MAXIMUM_IDENTIFIER_LENGTH} characters")


def _require_aware(value: datetime, *, field: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"{field} must be a timezone-aware datetime")


@dataclass(frozen=True, slots=True)
class ApprovalDecision:
    """One durable, auditable operator decision about one exact proposal version."""

    decision_governance_id: str
    proposal_governance_id: str
    proposal_version: int
    approved_fingerprint: str
    action: OperatorAction
    operator_identity: str
    decided_at: datetime
    expires_at: datetime | None
    resulting_status: ProposalStatus

    def __post_init__(self) -> None:
        _require_identifier(self.decision_governance_id, field="decision_governance_id")
        _require_identifier(self.proposal_governance_id, field="proposal_governance_id")
        _require_identifier(self.operator_identity, field="operator_identity")
        if isinstance(self.proposal_version, bool) or not isinstance(self.proposal_version, int):
            raise ValueError("proposal_version must be an int")
        if self.proposal_version < 1:
            raise ValueError("proposal_version must start at 1")
        if not isinstance(self.approved_fingerprint, str) or len(self.approved_fingerprint) != 64:
            raise ValueError("approved_fingerprint must be a 64-character hex digest")
        if not isinstance(self.action, OperatorAction):
            raise ValueError("action must be an OperatorAction")
        _require_aware(self.decided_at, field="decided_at")
        if not isinstance(self.resulting_status, ProposalStatus):
            raise ValueError("resulting_status must be a ProposalStatus")

        expected = {
            OperatorAction.APPROVE: ProposalStatus.APPROVED,
            OperatorAction.REJECT: ProposalStatus.REJECTED,
            OperatorAction.CANCEL: ProposalStatus.CANCELLED,
        }[self.action]
        if self.resulting_status is not expected:
            raise ValueError(
                f"action {self.action.value} must produce {expected.value}, "
                f"not {self.resulting_status.value}"
            )

        if self.action is OperatorAction.APPROVE:
            if self.expires_at is None:
                raise ValueError("an APPROVE decision must carry an approval expiry")
            _require_aware(self.expires_at, field="expires_at")
            if self.expires_at <= self.decided_at:
                raise ValueError("expires_at must follow decided_at")
        elif self.expires_at is not None:
            raise ValueError(
                "only an APPROVE decision carries an expiry: a rejection or "
                "cancellation does not lapse"
            )

    def is_expired_at(self, instant: datetime) -> bool:
        """Whether an approval has lapsed as of a caller-supplied instant."""
        _require_aware(instant, field="instant")
        if self.expires_at is None:
            return False
        return instant >= self.expires_at


def record_operator_decision(
    *,
    proposal: TradeProposal,
    decision_governance_id: str,
    action: OperatorAction,
    operator_identity: str,
    decided_at: datetime,
    approval_expiry_seconds: int,
) -> ApprovalDecision:
    """Record one explicit operator decision against one exact proposal version.

    Refuses when the proposal is not in PREPARED, when it has already expired,
    or when the resulting transition is not in the closed table. The fingerprint
    recorded is the proposal's own, so an approval can only ever match the exact
    order terms the operator was shown.
    """
    if not isinstance(proposal, TradeProposal):
        raise ValueError("proposal must be a TradeProposal")
    if not isinstance(action, OperatorAction):
        raise ValueError("action must be an OperatorAction")
    _require_aware(decided_at, field="decided_at")
    if isinstance(approval_expiry_seconds, bool) or not isinstance(approval_expiry_seconds, int):
        raise ValueError("approval_expiry_seconds must be an int")
    if approval_expiry_seconds <= 0:
        raise ValueError("approval_expiry_seconds must be positive")

    target = {
        OperatorAction.APPROVE: ProposalStatus.APPROVED,
        OperatorAction.REJECT: ProposalStatus.REJECTED,
        OperatorAction.CANCEL: ProposalStatus.CANCELLED,
    }[action]
    if not is_transition_allowed(proposal.status, target):
        raise ValueError(f"{proposal.status.value} -> {target.value} is not an allowed transition")
    if proposal.expired_at(decided_at):
        raise ValueError(
            "the proposal expired before this decision; an expired proposal cannot be "
            "approved, and a new proposal must be produced instead"
        )

    expires_at = (
        decided_at + timedelta(seconds=approval_expiry_seconds)
        if action is OperatorAction.APPROVE
        else None
    )
    return ApprovalDecision(
        decision_governance_id=decision_governance_id,
        proposal_governance_id=proposal.proposal_governance_id,
        proposal_version=proposal.proposal_version,
        approved_fingerprint=proposal.content_fingerprint,
        action=action,
        operator_identity=operator_identity,
        decided_at=decided_at,
        expires_at=expires_at,
        resulting_status=target,
    )


@dataclass(frozen=True, slots=True)
class ApprovedOrderIntent:
    """The immutable, broker-neutral hand-off record for MILESTONE-085.

    Carries only what a future paper-execution milestone needs to prepare an
    order. It carries no broker identity, no credential, no endpoint and no
    submission timestamp, because none of those exist in this milestone.
    """

    intent_governance_id: str
    proposal_governance_id: str
    proposal_version: int
    approved_fingerprint: str
    decision_governance_id: str

    symbol: str
    side: str
    quantity: int
    order_type: OrderType
    limit_price: Decimal | None
    currency: str
    time_in_force: str
    mandatory_liquidation_at: datetime

    account_mode_required: str
    idempotency_key: str
    configuration_governance_id: str
    configuration_version: int
    evaluation_context_id: str

    created_at: datetime
    expires_at: datetime
    submission_state: SubmissionState

    def __post_init__(self) -> None:
        for field_name in (
            "intent_governance_id",
            "proposal_governance_id",
            "decision_governance_id",
            "idempotency_key",
            "configuration_governance_id",
            "evaluation_context_id",
        ):
            _require_identifier(getattr(self, field_name), field=field_name)
        for field_name in ("proposal_version", "configuration_version"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{field_name} must be an int starting at 1")
        if len(self.approved_fingerprint) != 64:
            raise ValueError("approved_fingerprint must be a 64-character hex digest")
        if self.side != "BUY":
            raise ValueError("side must be BUY: this product is long-only")
        if self.symbol != self.symbol.strip().upper():
            raise ValueError("symbol must be upper-case and unpadded")
        if isinstance(self.quantity, bool) or not isinstance(self.quantity, int):
            raise ValueError("quantity must be an int")
        if self.quantity <= 0:
            raise ValueError("quantity must be positive")
        if not isinstance(self.order_type, OrderType):
            raise ValueError("order_type must be an OrderType")
        if self.order_type is OrderType.LIMIT and self.limit_price is None:
            raise ValueError("a LIMIT intent must carry a limit_price")
        if self.order_type is OrderType.MARKET and self.limit_price is not None:
            raise ValueError("a MARKET intent must not carry a limit_price")
        if self.time_in_force != "DAY":
            raise ValueError(
                "time_in_force must be DAY: an intraday-only product cannot express an "
                "order that survives the session"
            )
        if self.account_mode_required != "PREPARATION":
            raise ValueError(
                "account_mode_required must be PREPARATION in MILESTONE-084: this "
                "milestone cannot submit an order, so an intent may not declare that it "
                "is ready for a paper or live account"
            )
        if self.submission_state is not SubmissionState.NOT_SUBMITTED:
            raise ValueError(
                "submission_state must be NOT_SUBMITTED: MILESTONE-084 provides no "
                "transition away from it"
            )
        for field_name in ("created_at", "expires_at", "mandatory_liquidation_at"):
            _require_aware(getattr(self, field_name), field=field_name)
        if self.expires_at <= self.created_at:
            raise ValueError("expires_at must follow created_at")


def build_approved_order_intent(
    *,
    intent_governance_id: str,
    proposal: TradeProposal,
    decision: ApprovalDecision,
    created_at: datetime,
    idempotency_key: str,
) -> ApprovedOrderIntent:
    """Derive the one intent a valid approval permits.

    Every refusal below is a state the database also refuses, so a caller cannot
    reach a forbidden intent by going around this function.
    """
    if not isinstance(proposal, TradeProposal):
        raise ValueError("proposal must be a TradeProposal")
    if not isinstance(decision, ApprovalDecision):
        raise ValueError("decision must be an ApprovalDecision")
    _require_aware(created_at, field="created_at")

    if decision.action is not OperatorAction.APPROVE:
        raise ValueError("an order intent requires an APPROVE decision")
    if decision.proposal_governance_id != proposal.proposal_governance_id:
        raise ValueError("the decision does not belong to this proposal")
    if decision.proposal_version != proposal.proposal_version:
        raise ValueError(
            "the decision approved a different proposal version; a changed proposal "
            "requires a new approval"
        )
    if decision.approved_fingerprint != proposal.content_fingerprint:
        raise ValueError(
            "the approved fingerprint does not match the proposal's current order "
            "terms; the proposal changed after it was approved"
        )
    if proposal.status is not ProposalStatus.APPROVED:
        raise ValueError("the proposal is not APPROVED")
    if proposal.expired_at(created_at):
        raise ValueError("the proposal expired before the intent was created")
    if decision.is_expired_at(created_at):
        raise ValueError("the approval expired before the intent was created")

    return ApprovedOrderIntent(
        intent_governance_id=intent_governance_id,
        proposal_governance_id=proposal.proposal_governance_id,
        proposal_version=proposal.proposal_version,
        approved_fingerprint=proposal.content_fingerprint,
        decision_governance_id=decision.decision_governance_id,
        symbol=proposal.symbol,
        side=proposal.side,
        quantity=proposal.quantity,
        order_type=proposal.order_type,
        limit_price=proposal.limit_price,
        currency=proposal.currency,
        time_in_force="DAY",
        mandatory_liquidation_at=proposal.mandatory_liquidation_at,
        account_mode_required="PREPARATION",
        idempotency_key=idempotency_key,
        configuration_governance_id=proposal.configuration_governance_id,
        configuration_version=proposal.configuration_version,
        evaluation_context_id=proposal.evaluation_context_id,
        created_at=created_at,
        expires_at=proposal.expires_at,
        submission_state=SubmissionState.NOT_SUBMITTED,
    )
