"""MILESTONE-084 commands and queries for the decision-to-approval flow.

THE MARKET INPUTS ARE OPERATOR-ASSERTED. This milestone connects to no broker
and no market-data vendor, so every snapshot a proposal is evaluated against
reaches the platform because a human wrote it down -- exactly as MILESTONE-076
models operator-asserted position events. The platform records what was
asserted, checks it against the operator's own configured limits, and refuses
to proceed when it is stale, incomplete or not claimed to be real-time. It does
NOT verify that the asserted quote is what the market actually showed, and
nothing in this milestone should be read as though it did.

A consequence worth stating plainly rather than discovering later: a snapshot
asserted as DELAYED or FIXTURE always produces NO_TRADE
(MARKET_DATA_NOT_REAL_TIME). That is deliberate. A proposal built on data the
operator will not claim is real-time is not a proposal this product will make.

EVERY HANDLER IS ONE STEP. There is no handler that evaluates, approves and
issues in one call, because a human decision sits between those steps and a
convenience method that spanned it would be an approval nobody made.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal

from empirical_platform.decision_candidate.evaluation_context import (
    EvaluationContext,
    build_evaluation_context,
)
from empirical_platform.decision_candidate.evaluation_evidence_watermark_repository import (
    EvaluationEvidenceWatermarkRepository,
)
from empirical_platform.decision_candidate.operator_trading_configuration import (
    KillSwitchState,
    OperatorTradingConfiguration,
)
from empirical_platform.decision_candidate.product_market_inputs import (
    AccountSnapshot,
    InstrumentMetadata,
    LiquiditySnapshot,
    OpenOrderSnapshot,
    PositionSnapshot,
    QuoteSnapshot,
    SessionSnapshot,
    TradingCostEstimate,
)
from empirical_platform.decision_candidate.product_repositories import (
    ApprovalDecisionRepository,
    ApprovedOrderIntentRepository,
    EvaluationContextRepository,
    OperatorTradingConfigurationRepository,
    TradeProposalRepository,
)
from empirical_platform.decision_candidate.trade_approval import (
    ApprovalDecision,
    ApprovedOrderIntent,
    OperatorAction,
    build_approved_order_intent,
    record_operator_decision,
)
from empirical_platform.decision_candidate.trade_proposal import (
    ProposalStatus,
    TradeProposal,
    TradeProposalOutcome,
    evaluate_trade_proposal,
)

# The domain types below are re-exported deliberately, following the
# MILESTONE-083 REV-005 precedent: `entrypoints` may import `usecases` but not
# `decision_candidate`, and an entrypoint needs these names only to annotate
# what its own handler returns. Widening the architecture allowlist to give it
# a direct edge to the domain would be a real loosening of the boundary in
# exchange for an import statement, so the names are surfaced here -- this
# module already imports every one of them for its own handler signatures.
__all__ = [
    "ApprovalDecision",
    "ApprovedOrderIntent",
    "AuditHistory",
    "DecideTradeProposalCommand",
    "DecideTradeProposalHandler",
    "DecisionOutcome",
    "EvaluationContext",
    "GetApprovedOrderIntentHandler",
    "GetApprovedOrderIntentQuery",
    "GetAuditHistoryHandler",
    "GetAuditHistoryQuery",
    "GetOperatorTradingConfigurationHandler",
    "GetOperatorTradingConfigurationQuery",
    "GetSystemStatusHandler",
    "GetSystemStatusQuery",
    "GetTradeProposalHandler",
    "GetTradeProposalQuery",
    "InvalidateStaleProposalsCommand",
    "InvalidateStaleProposalsHandler",
    "InvalidationOutcome",
    "IssueApprovedOrderIntentCommand",
    "IssueApprovedOrderIntentHandler",
    "KillSwitchState",
    "ListTradeProposalsHandler",
    "ListTradeProposalsQuery",
    "NotFoundError",
    "OpenEvaluationContextCommand",
    "OpenEvaluationContextHandler",
    "OperatorAction",
    "OperatorTradingConfiguration",
    "PrepareTradeProposalCommand",
    "PrepareTradeProposalHandler",
    "ProposalStatus",
    "SaveOperatorTradingConfigurationCommand",
    "SaveOperatorTradingConfigurationHandler",
    "SetKillSwitchCommand",
    "SetKillSwitchHandler",
    "SystemStatus",
    "TradeProposal",
    "TradeProposalOutcome",
]


class NotFoundError(RuntimeError):
    """Raised when a named record does not exist.

    An explicit refusal rather than a None a caller must remember to check: a
    request for one specific proposal by identity wants that proposal or an
    answer, never a value that quietly means "nothing".
    """


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SaveOperatorTradingConfigurationCommand:
    configuration: OperatorTradingConfiguration


class SaveOperatorTradingConfigurationHandler:
    """Persists one configuration version. Versions are never edited."""

    __slots__ = ("_configurations",)

    def __init__(self, *, configuration_repository: OperatorTradingConfigurationRepository) -> None:
        self._configurations = configuration_repository

    def handle(
        self, command: SaveOperatorTradingConfigurationCommand
    ) -> OperatorTradingConfiguration:
        return self._configurations.save(command.configuration)


# ---------------------------------------------------------------------------
# Evaluation context
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class OpenEvaluationContextCommand:
    """Bind one evaluation to the inputs it will consume.

    The watermark is named, not supplied: the handler loads it, and refuses if
    it was never captured. A context cannot be opened against evidence that
    does not exist.
    """

    evaluation_context_id: str
    configuration_governance_id: str
    configuration_version: int
    watermark_governance_id: str
    quote_id: str
    account_snapshot_id: str
    session_id: str
    cost_estimate_id: str | None
    instrument_universe_version: str
    strategy_version: str
    created_at: datetime
    research_session_id: str | None = None
    decision_candidate_id: str | None = None


class OpenEvaluationContextHandler:
    """Loads the named configuration and watermark, then binds a context to both."""

    __slots__ = ("_configurations", "_contexts", "_watermarks")

    def __init__(
        self,
        *,
        configuration_repository: OperatorTradingConfigurationRepository,
        evaluation_context_repository: EvaluationContextRepository,
        evaluation_evidence_watermark_repository: EvaluationEvidenceWatermarkRepository,
    ) -> None:
        self._configurations = configuration_repository
        self._contexts = evaluation_context_repository
        self._watermarks = evaluation_evidence_watermark_repository

    def handle(self, command: OpenEvaluationContextCommand) -> EvaluationContext:
        configuration = self._configurations.get(
            command.configuration_governance_id, command.configuration_version
        )
        if configuration is None:
            raise NotFoundError(
                f"no configuration {command.configuration_governance_id!r} "
                f"version {command.configuration_version}"
            )
        watermark = self._watermarks.get(command.watermark_governance_id)
        if watermark is None:
            raise NotFoundError(
                f"no evaluation evidence watermark {command.watermark_governance_id!r} has "
                "ever been captured; an evaluation cannot be bound to evidence that does "
                "not exist"
            )
        return self._contexts.save(
            build_evaluation_context(
                evaluation_context_id=command.evaluation_context_id,
                configuration=configuration,
                watermark=watermark,
                quote_id=command.quote_id,
                account_snapshot_id=command.account_snapshot_id,
                session_id=command.session_id,
                cost_estimate_id=command.cost_estimate_id,
                instrument_universe_version=command.instrument_universe_version,
                strategy_version=command.strategy_version,
                created_at=command.created_at,
                research_session_id=command.research_session_id,
                decision_candidate_id=command.decision_candidate_id,
            )
        )


# ---------------------------------------------------------------------------
# Proposal
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PrepareTradeProposalCommand:
    """Evaluate one instrument against one context.

    DELIBERATELY no quantity, no price and no risk verdict. All three are
    derived by the engine; accepting them here would let a caller size a trade
    the configuration does not permit and then record it as though the rules
    had been applied.
    """

    proposal_governance_id: str
    evaluation_context_id: str
    symbol: str
    evaluated_at: datetime
    quote: QuoteSnapshot
    account: AccountSnapshot
    session: SessionSnapshot
    instrument: InstrumentMetadata
    liquidity: LiquiditySnapshot
    cost_estimate: TradingCostEstimate | None
    positions: tuple[PositionSnapshot, ...]
    open_orders: tuple[OpenOrderSnapshot, ...]
    evidence_age_seconds: Decimal


class PrepareTradeProposalHandler:
    """Evaluates one instrument and persists the proposal, if there is one.

    A NO_TRADE is returned, not raised, and nothing is written. A refusal is a
    legitimate answer -- most evaluations end in one -- and persisting a row for
    every refusal would fill the proposal table with things nobody proposed.
    """

    __slots__ = ("_configurations", "_contexts", "_proposals")

    def __init__(
        self,
        *,
        configuration_repository: OperatorTradingConfigurationRepository,
        evaluation_context_repository: EvaluationContextRepository,
        trade_proposal_repository: TradeProposalRepository,
    ) -> None:
        self._configurations = configuration_repository
        self._contexts = evaluation_context_repository
        self._proposals = trade_proposal_repository

    def handle(self, command: PrepareTradeProposalCommand) -> TradeProposalOutcome:
        outcome = evaluate_without_persisting(
            command,
            configuration_repository=self._configurations,
            evaluation_context_repository=self._contexts,
        )
        if outcome.proposal is None:
            return outcome
        stored = self._proposals.save(outcome.proposal)
        return TradeProposalOutcome(
            proposal=stored, no_trade_reason=None, risk_checks=outcome.risk_checks
        )


def evaluate_without_persisting(
    command: PrepareTradeProposalCommand,
    *,
    configuration_repository: OperatorTradingConfigurationRepository,
    evaluation_context_repository: EvaluationContextRepository,
) -> TradeProposalOutcome:
    """Load, evaluate, and write nothing.

    Shared with `PrepareTradeProposalHandler` rather than duplicated, and that
    sharing is the point: `explain-no-trade` must run the SAME evaluation the
    real command would, or it would explain a decision the product did not
    make. A second implementation, however carefully kept in step, would drift.
    """
    context = evaluation_context_repository.get(command.evaluation_context_id)
    if context is None:
        raise NotFoundError(f"no evaluation context {command.evaluation_context_id!r}")
    configuration = configuration_repository.get(
        context.configuration_governance_id, context.configuration_version
    )
    if configuration is None:  # pragma: no cover - a stored context cites a stored version
        raise NotFoundError(
            f"context {context.evaluation_context_id!r} cites configuration "
            f"{context.configuration_governance_id!r} version "
            f"{context.configuration_version}, which does not exist"
        )
    return evaluate_trade_proposal(
        configuration=configuration,
        evaluation_context_id=context.evaluation_context_id,
        proposal_governance_id=command.proposal_governance_id,
        evaluated_at=command.evaluated_at,
        symbol=command.symbol,
        quote=command.quote,
        account=command.account,
        session=command.session,
        instrument=command.instrument,
        liquidity=command.liquidity,
        cost_estimate=command.cost_estimate,
        positions=command.positions,
        open_orders=command.open_orders,
        evidence_age_seconds=command.evidence_age_seconds,
    )


@dataclass(frozen=True, slots=True)
class GetTradeProposalQuery:
    proposal_governance_id: str


class GetTradeProposalHandler:
    __slots__ = ("_proposals",)

    def __init__(self, *, trade_proposal_repository: TradeProposalRepository) -> None:
        self._proposals = trade_proposal_repository

    def handle(self, query: GetTradeProposalQuery) -> TradeProposal:
        proposal = self._proposals.get(query.proposal_governance_id)
        if proposal is None:
            raise NotFoundError(f"no trade proposal {query.proposal_governance_id!r}")
        return proposal


@dataclass(frozen=True, slots=True)
class ListTradeProposalsQuery:
    status: ProposalStatus


class ListTradeProposalsHandler:
    __slots__ = ("_proposals",)

    def __init__(self, *, trade_proposal_repository: TradeProposalRepository) -> None:
        self._proposals = trade_proposal_repository

    def handle(self, query: ListTradeProposalsQuery) -> tuple[TradeProposal, ...]:
        return self._proposals.list_by_status(query.status)


# ---------------------------------------------------------------------------
# Decision
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DecisionOutcome:
    """What one decision produced: the record, and the proposal's new state."""

    decision: ApprovalDecision
    proposal: TradeProposal


@dataclass(frozen=True, slots=True)
class DecideTradeProposalCommand:
    """One human decision about one exact proposal.

    `operator_identity` is required and never defaulted. An approval whose
    operator is "system", "default" or absent is an approval nobody made, which
    is the thing this milestone exists to prevent.
    """

    proposal_governance_id: str
    decision_governance_id: str
    action: OperatorAction
    operator_identity: str
    decided_at: datetime

    def __post_init__(self) -> None:
        if not self.operator_identity.strip():
            raise ValueError("operator_identity must name the person who decided")


class DecideTradeProposalHandler:
    """Records the decision first, then moves the proposal to match it.

    That order is the safe one. The database admits a decision only while its
    proposal is still PREPARED and only with that proposal's current
    fingerprint, so if the status moved first, the decision could no longer be
    recorded and the proposal would sit APPROVED with nobody named as having
    approved it.
    """

    __slots__ = ("_configurations", "_decisions", "_proposals")

    def __init__(
        self,
        *,
        configuration_repository: OperatorTradingConfigurationRepository,
        approval_decision_repository: ApprovalDecisionRepository,
        trade_proposal_repository: TradeProposalRepository,
    ) -> None:
        self._configurations = configuration_repository
        self._decisions = approval_decision_repository
        self._proposals = trade_proposal_repository

    def handle(self, command: DecideTradeProposalCommand) -> DecisionOutcome:
        proposal = self._proposals.get(command.proposal_governance_id)
        if proposal is None:
            raise NotFoundError(f"no trade proposal {command.proposal_governance_id!r}")
        configuration = self._configurations.get(
            proposal.configuration_governance_id, proposal.configuration_version
        )
        if configuration is None:  # pragma: no cover - a stored proposal cites a stored version
            raise NotFoundError(
                f"proposal {proposal.proposal_governance_id!r} cites a configuration "
                "version that does not exist"
            )

        decision = self._decisions.record(
            record_operator_decision(
                proposal=proposal,
                decision_governance_id=command.decision_governance_id,
                action=command.action,
                operator_identity=command.operator_identity,
                decided_at=command.decided_at,
                approval_expiry_seconds=configuration.approval_expiry_seconds,
            )
        )
        moved = self._proposals.set_status(
            proposal.proposal_governance_id, decision.resulting_status
        )
        return DecisionOutcome(decision=decision, proposal=moved)


# ---------------------------------------------------------------------------
# Intent
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class IssueApprovedOrderIntentCommand:
    """Derive the one intent an approval permits.

    Named `issue`, not `submit` or `send`. MILESTONE-084 writes a record and
    does nothing else with it: there is no broker client anywhere in this
    package, and an architecture rule keeps it that way.
    """

    intent_governance_id: str
    proposal_governance_id: str
    idempotency_key: str
    created_at: datetime


class IssueApprovedOrderIntentHandler:
    """Builds and stores one intent for one approved proposal."""

    __slots__ = ("_decisions", "_intents", "_proposals")

    def __init__(
        self,
        *,
        approval_decision_repository: ApprovalDecisionRepository,
        approved_order_intent_repository: ApprovedOrderIntentRepository,
        trade_proposal_repository: TradeProposalRepository,
    ) -> None:
        self._decisions = approval_decision_repository
        self._intents = approved_order_intent_repository
        self._proposals = trade_proposal_repository

    def handle(self, command: IssueApprovedOrderIntentCommand) -> ApprovedOrderIntent:
        proposal = self._proposals.get(command.proposal_governance_id)
        if proposal is None:
            raise NotFoundError(f"no trade proposal {command.proposal_governance_id!r}")
        decision = self._decisions.for_proposal(command.proposal_governance_id)
        if decision is None:
            raise NotFoundError(
                f"proposal {command.proposal_governance_id!r} has no recorded decision; an "
                "order intent requires an explicit approval, never the absence of a rejection"
            )
        return self._intents.issue(
            build_approved_order_intent(
                intent_governance_id=command.intent_governance_id,
                proposal=proposal,
                decision=decision,
                created_at=command.created_at,
                idempotency_key=command.idempotency_key,
            )
        )


@dataclass(frozen=True, slots=True)
class GetApprovedOrderIntentQuery:
    intent_governance_id: str


class GetApprovedOrderIntentHandler:
    __slots__ = ("_intents",)

    def __init__(self, *, approved_order_intent_repository: ApprovedOrderIntentRepository) -> None:
        self._intents = approved_order_intent_repository

    def handle(self, query: GetApprovedOrderIntentQuery) -> ApprovedOrderIntent:
        intent = self._intents.get(query.intent_governance_id)
        if intent is None:
            raise NotFoundError(f"no approved order intent {query.intent_governance_id!r}")
        return intent


# ---------------------------------------------------------------------------
# Configuration inspection
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class GetOperatorTradingConfigurationQuery:
    """Read one configuration version, or the latest if none is named."""

    configuration_governance_id: str
    configuration_version: int | None = None


class GetOperatorTradingConfigurationHandler:
    __slots__ = ("_configurations",)

    def __init__(self, *, configuration_repository: OperatorTradingConfigurationRepository) -> None:
        self._configurations = configuration_repository

    def handle(self, query: GetOperatorTradingConfigurationQuery) -> OperatorTradingConfiguration:
        configuration = (
            self._configurations.latest(query.configuration_governance_id)
            if query.configuration_version is None
            else self._configurations.get(
                query.configuration_governance_id, query.configuration_version
            )
        )
        if configuration is None:
            named = (
                "latest"
                if query.configuration_version is None
                else f"version {query.configuration_version}"
            )
            raise NotFoundError(f"no configuration {query.configuration_governance_id!r} ({named})")
        return configuration


# ---------------------------------------------------------------------------
# The kill switch
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SetKillSwitchCommand:
    """Engage or disengage the global stop.

    THIS WRITES A NEW CONFIGURATION VERSION. The kill switch is a field of a
    versioned, immutable configuration, so moving it is not an edit -- it is a
    new version, recorded alongside the one it supersedes. That is the whole
    point: a reader can see when the switch moved and what policy was in force
    on either side of it, which an in-place flag would not preserve.
    """

    configuration_governance_id: str
    engaged: bool


class SetKillSwitchHandler:
    """Copies the latest configuration forward with the switch moved."""

    __slots__ = ("_configurations",)

    def __init__(self, *, configuration_repository: OperatorTradingConfigurationRepository) -> None:
        self._configurations = configuration_repository

    def handle(self, command: SetKillSwitchCommand) -> OperatorTradingConfiguration:
        current = self._configurations.latest(command.configuration_governance_id)
        if current is None:
            raise NotFoundError(
                f"no configuration {command.configuration_governance_id!r} to engage a "
                "kill switch on; a switch with no policy behind it stops nothing"
            )
        target = KillSwitchState.ENGAGED if command.engaged else KillSwitchState.DISENGAGED
        if current.kill_switch is target:
            # Already there. Writing an identical new version would add a
            # governance record of a change that did not happen.
            return current
        return self._configurations.save(
            replace(
                current,
                configuration_version=current.configuration_version + 1,
                kill_switch=target,
            )
        )


# ---------------------------------------------------------------------------
# Invalidating proposals that can no longer be acted on
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class InvalidationOutcome:
    """What one sweep did, and why each proposal was moved."""

    expired: tuple[str, ...]
    invalidated: tuple[str, ...]

    @property
    def total(self) -> int:
        return len(self.expired) + len(self.invalidated)


@dataclass(frozen=True, slots=True)
class InvalidateStaleProposalsCommand:
    """Move PREPARED proposals that can no longer be approved out of the queue.

    Two distinct reasons, kept distinct in the result rather than collapsed:

      - EXPIRED: the proposal's own expiry has passed at `as_of`.
      - INVALIDATED: a newer configuration version exists, so the policy the
        proposal was evaluated under is no longer the operator's policy.

    `as_of` is a parameter, never a clock read here. The sweep is as
    reproducible as everything else in this milestone.
    """

    as_of: datetime
    configuration_governance_id: str | None = None


class InvalidateStaleProposalsHandler:
    """Sweeps the PREPARED queue. Touches nothing that is already terminal."""

    __slots__ = ("_configurations", "_proposals")

    def __init__(
        self,
        *,
        configuration_repository: OperatorTradingConfigurationRepository,
        trade_proposal_repository: TradeProposalRepository,
    ) -> None:
        self._configurations = configuration_repository
        self._proposals = trade_proposal_repository

    def handle(self, command: InvalidateStaleProposalsCommand) -> InvalidationOutcome:
        expired: list[str] = []
        invalidated: list[str] = []
        latest_versions: dict[str, int] = {}

        for proposal in self._proposals.list_by_status(ProposalStatus.PREPARED):
            if command.configuration_governance_id is not None and (
                proposal.configuration_governance_id != command.configuration_governance_id
            ):
                continue

            if proposal.expired_at(command.as_of):
                self._proposals.set_status(proposal.proposal_governance_id, ProposalStatus.EXPIRED)
                expired.append(proposal.proposal_governance_id)
                continue

            # Expiry is checked first on purpose: an expired proposal is
            # expired whatever the configuration did afterwards, and reporting
            # it as INVALIDATED would describe the wrong reason.
            governance_id = proposal.configuration_governance_id
            if governance_id not in latest_versions:
                latest = self._configurations.latest(governance_id)
                latest_versions[governance_id] = (
                    proposal.configuration_version
                    if latest is None
                    else latest.configuration_version
                )
            if latest_versions[governance_id] > proposal.configuration_version:
                self._proposals.set_status(
                    proposal.proposal_governance_id, ProposalStatus.INVALIDATED
                )
                invalidated.append(proposal.proposal_governance_id)

        return InvalidationOutcome(expired=tuple(expired), invalidated=tuple(invalidated))


# ---------------------------------------------------------------------------
# Audit history and system status
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AuditHistory:
    """The whole chain behind one proposal, in the order it happened."""

    proposal: TradeProposal
    context: EvaluationContext | None
    configuration: OperatorTradingConfiguration | None
    decision: ApprovalDecision | None
    intent: ApprovedOrderIntent | None


@dataclass(frozen=True, slots=True)
class GetAuditHistoryQuery:
    proposal_governance_id: str


class GetAuditHistoryHandler:
    """Assembles one proposal's full provenance for a human reader.

    Each link is optional in the RESULT but not in reality: a stored proposal
    always cites a stored context and configuration. They are typed as optional
    so that a chain broken by something outside this milestone's enforcement
    boundary is reported as broken rather than raising and telling the operator
    nothing about the rest.
    """

    __slots__ = ("_configurations", "_contexts", "_decisions", "_intents", "_proposals")

    def __init__(
        self,
        *,
        configuration_repository: OperatorTradingConfigurationRepository,
        evaluation_context_repository: EvaluationContextRepository,
        approval_decision_repository: ApprovalDecisionRepository,
        approved_order_intent_repository: ApprovedOrderIntentRepository,
        trade_proposal_repository: TradeProposalRepository,
    ) -> None:
        self._configurations = configuration_repository
        self._contexts = evaluation_context_repository
        self._decisions = approval_decision_repository
        self._intents = approved_order_intent_repository
        self._proposals = trade_proposal_repository

    def handle(self, query: GetAuditHistoryQuery) -> AuditHistory:
        proposal = self._proposals.get(query.proposal_governance_id)
        if proposal is None:
            raise NotFoundError(f"no trade proposal {query.proposal_governance_id!r}")
        return AuditHistory(
            proposal=proposal,
            context=self._contexts.get(proposal.evaluation_context_id),
            configuration=self._configurations.get(
                proposal.configuration_governance_id, proposal.configuration_version
            ),
            decision=self._decisions.for_proposal(proposal.proposal_governance_id),
            intent=self._intents.for_proposal(proposal.proposal_governance_id),
        )


@dataclass(frozen=True, slots=True)
class SystemStatus:
    """What the product is currently able and unable to do."""

    proposal_counts: Mapping[ProposalStatus, int]
    configuration_governance_id: str | None
    configuration_version: int | None
    account_mode: str | None
    kill_switch: str | None
    #: Fixed. MILESTONE-084 has no order-submission capability, so this is a
    #: constant rather than a probe of one -- there is nothing to probe.
    submission_capability: str = "NONE"


@dataclass(frozen=True, slots=True)
class GetSystemStatusQuery:
    configuration_governance_id: str | None = None


class GetSystemStatusHandler:
    __slots__ = ("_configurations", "_proposals")

    def __init__(
        self,
        *,
        configuration_repository: OperatorTradingConfigurationRepository,
        trade_proposal_repository: TradeProposalRepository,
    ) -> None:
        self._configurations = configuration_repository
        self._proposals = trade_proposal_repository

    def handle(self, query: GetSystemStatusQuery) -> SystemStatus:
        configuration = (
            None
            if query.configuration_governance_id is None
            else self._configurations.latest(query.configuration_governance_id)
        )
        return SystemStatus(
            proposal_counts=self._proposals.counts_by_status(),
            configuration_governance_id=(
                None if configuration is None else configuration.configuration_governance_id
            ),
            configuration_version=(
                None if configuration is None else configuration.configuration_version
            ),
            account_mode=None if configuration is None else configuration.account_mode.value,
            kill_switch=None if configuration is None else configuration.kill_switch.value,
        )
