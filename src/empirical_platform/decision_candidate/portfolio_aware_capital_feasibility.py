"""MILESTONE-077 — Portfolio-aware capital feasibility.

M075 answers: do THIS session's own approved position plans fit inside the
supplied equity? It answers that question with the portfolio deliberately
excluded -- its own rendered banner says "NOT current portfolio state; NOT open
positions; NOT prior-day exposure".

M076 records what the operator ASSERTED they hold.

Neither knows about the other. Nothing in the repository charges today's
proposals against exposure the operator has already taken, so a session can
report "fits within capital" to an operator whose capital is already fully
deployed. This module closes exactly that gap, additively, and changes the
meaning of neither milestone.

WHAT THE HELD FIGURE IS
-----------------------
Held exposure is Sigma (open quantity x asserted ENTRY price), taken straight
from M076's fold and never revalued. It is what the operator said they
committed at the price they said they paid.

It is NOT a market valuation, NOT a verified cost basis, NOT a broker balance,
and NOT a current value.

UTILIZATION, NOT DEPLETION
--------------------------
Charging held notional against the capital base does not claim the operator's
cash went down. Buying an asset converts cash into that asset and leaves equity
unchanged. M067's model is UTILIZATION -- `max_capital_utilization_percent`
measures how much of the capital base is DEPLOYED -- and a held asserted
position is deployed capital. The distinction is stated because the number is
otherwise easy to misread as a cash balance.

This module is pure: no I/O, no clock, no randomness, no float.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum

from empirical_platform.decision_candidate.operator_position_ledger import (
    DerivedPositionState,
    OperatorAssertedPositionEvent,
    OperatorPositionEventKind,
)
from empirical_platform.decision_candidate.portfolio_study import (
    DEFAULT_PORTFOLIO_CAPITAL_POLICY,
    PortfolioCapitalPolicy,
    PortfolioRejectionReason,
)
from empirical_platform.decision_candidate.same_day_capital_feasibility import (
    SameDayPositionRequest,
    capital_policy_for_session,
)

__all__ = [
    "PORTFOLIO_AWARE_FEASIBILITY_BANNER",
    "HeldAssertedPosition",
    "PortfolioAwareCapitalAssessment",
    "PortfolioAwarePlanVerdict",
    "PortfolioAwareOutcome",
    "PortfolioAwareUnassessableReason",
    "assess_portfolio_aware_capital_feasibility",
    "open_position_plan_lineage",
]

PORTFOLIO_AWARE_FEASIBILITY_BANNER = (
    "feasibility of THIS session's approved position plans AFTER charging exposure the "
    "operator has ASSERTED is already open, against one explicit capital policy. Held "
    "exposure is based on OPERATOR-ASSERTED position records: NOT broker-verified; the "
    "asserted price is NOT a current market price; NOT execution evidence; NOT a verified "
    "account balance; NOT a market valuation; NOT realized or unrealized P&L; NOT an "
    "allocation or reservation of capital; NOT a profitability claim; NOT advice. The "
    "capital base is the equity figure supplied for sizing, not a verified balance, and "
    "capital is measured as UTILIZATION of that base, not as a cash balance."
)


class PortfolioAwareOutcome(StrEnum):
    """Closed vocabulary for the assessment as a whole.

    Deliberately excludes ALLOCATED, EXECUTED, FILLED and VERIFIED: M077
    allocates nothing, executes nothing and verifies nothing.
    """

    FITS_WITHIN_REMAINING_CAPITAL = "FITS_WITHIN_REMAINING_CAPITAL"
    EXCEEDS_REMAINING_CAPITAL = "EXCEEDS_REMAINING_CAPITAL"
    ALREADY_AT_OR_OVER_CAPITAL = "ALREADY_AT_OR_OVER_CAPITAL"
    NO_APPROVED_POSITION_PLANS = "NO_APPROVED_POSITION_PLANS"
    NOT_ASSESSABLE = "NOT_ASSESSABLE"


class PortfolioAwareUnassessableReason(StrEnum):
    """Why a verdict was withheld. Absence is never rendered as a pass."""

    SESSION_NOT_COMPLETED = "SESSION_NOT_COMPLETED"
    NON_POSITIVE_CAPITAL_BASE = "NON_POSITIVE_CAPITAL_BASE"
    #: The ledger could not be read at all. Distinct from an empty ledger,
    # which is a real observation that nothing is held.
    LEDGER_UNAVAILABLE = "LEDGER_UNAVAILABLE"
    #: Persisted events do not fold into a coherent sequence.
    LEDGER_INCOHERENT = "LEDGER_INCOHERENT"


@dataclass(frozen=True, slots=True)
class HeldAssertedPosition:
    """One open position as the operator asserted it. Every value is an
    assertion; none is a market observation."""

    position_governance_id: str
    instrument_symbol: str
    open_quantity: int
    asserted_entry_price: str
    asserted_open_notional: str
    source_position_plan_governance_id: str | None


@dataclass(frozen=True, slots=True)
class PortfolioAwarePlanVerdict:
    """Per-plan verdict once held exposure has been charged."""

    rank: int | None
    instrument_symbol: str
    position_plan_governance_id: str
    quantity: int
    position_notional: str
    fits: bool
    rejection_reason: PortfolioRejectionReason | None
    #: Cumulative committed notional INCLUDING the held opening balance, so the
    # operator can see the running total against the ceiling.
    cumulative_committed_notional: str


@dataclass(frozen=True, slots=True)
class PortfolioAwareCapitalAssessment:
    """The whole result. Every monetary value is a string of an exact
    `Decimal` -- no float is produced anywhere in this module."""

    outcome: PortfolioAwareOutcome
    unassessable_reason: PortfolioAwareUnassessableReason | None
    policy_id: str
    policy_version: str
    currency: str
    capital_base: str
    max_concurrent_positions: int
    max_capital_utilization_percent: str
    capital_ceiling: str
    held_position_count: int
    held_asserted_notional: str
    #: Ceiling minus held asserted notional, floored at zero. Headroom under
    # this policy -- NOT a cash balance.
    remaining_capital_under_policy: str
    requested_plan_count: int
    admitted_plan_count: int
    excluded_plan_count: int
    total_admitted_notional: str
    #: Held + newly admitted. What utilisation would look like if every
    # admitted plan were acted upon. Not a claim that any of them will be.
    projected_committed_notional: str
    projected_utilization_percent_of_ceiling: str | None
    #: Governance ids of this session's plans that an OPEN asserted position
    # already cites. Excluded from the proposed set so one decision is never
    # charged twice.
    plans_already_acted_upon: tuple[str, ...] = ()
    held_positions: tuple[HeldAssertedPosition, ...] = ()
    verdicts: tuple[PortfolioAwarePlanVerdict, ...] = ()
    excluded_future_event_count: int = 0
    limitations: tuple[str, ...] = field(default_factory=tuple)


def open_position_plan_lineage(
    *,
    events: tuple[OperatorAssertedPositionEvent, ...],
    state: DerivedPositionState,
) -> frozenset[str]:
    """Plan governance ids cited by the OPENED event of a position that is
    still open at the state's `as_of`.

    M076's `DerivedPosition` does not carry lineage, and M076 is frozen. Rather
    than modify it, this projects the lineage from the same event tuple the
    caller already read -- it does not re-implement M076's fold, which remains
    the sole authority on what is open.

    Only OPEN positions count. A closed position released its exposure, so a
    plan it cited may legitimately be entered again.
    """
    open_keys = {position.position_governance_id for position in state.open_positions}
    return frozenset(
        event.source_position_plan_governance_id.strip()
        for event in events
        if event.kind is OperatorPositionEventKind.OPENED
        and event.position_governance_id in open_keys
        # A blank citation is not an identifier. Treating it as one would let a
        # malformed persisted row exclude an unrelated plan from the proposal
        # set, which is a silent and expensive kind of wrong.
        and event.source_position_plan_governance_id is not None
        and event.source_position_plan_governance_id.strip()
    )


def _held_positions_of(
    *,
    state: DerivedPositionState,
    lineage_by_key: dict[str, str | None],
) -> tuple[HeldAssertedPosition, ...]:
    return tuple(
        HeldAssertedPosition(
            position_governance_id=position.position_governance_id,
            instrument_symbol=position.instrument_symbol,
            open_quantity=position.open_quantity,
            asserted_entry_price=position.asserted_entry_price,
            asserted_open_notional=position.asserted_open_notional,
            source_position_plan_governance_id=lineage_by_key.get(position.position_governance_id),
        )
        for position in state.open_positions
    )


@dataclass(frozen=True, slots=True)
class _AssessmentContext:
    """The values every assessable outcome reports identically. Kept as a typed
    object rather than a dict so the builder stays type-checked."""

    policy: PortfolioCapitalPolicy
    capital_base: Decimal
    ceiling: Decimal
    remaining: Decimal
    held_count: int
    held_notional: Decimal
    held_positions: tuple[HeldAssertedPosition, ...]
    requested_plan_count: int
    plans_already_acted_upon: tuple[str, ...]
    excluded_future_event_count: int


def _assessment(
    *,
    context: _AssessmentContext,
    outcome: PortfolioAwareOutcome,
    admitted_plan_count: int,
    excluded_plan_count: int,
    total_admitted_notional: Decimal,
    projected_committed_notional: Decimal,
    verdicts: tuple[PortfolioAwarePlanVerdict, ...],
    limitations: tuple[str, ...],
) -> PortfolioAwareCapitalAssessment:
    """Build an assessable result from the shared context plus what varies."""
    return PortfolioAwareCapitalAssessment(
        outcome=outcome,
        unassessable_reason=None,
        policy_id=context.policy.policy_id,
        policy_version=context.policy.version,
        currency=context.policy.currency,
        capital_base=str(context.capital_base),
        max_concurrent_positions=context.policy.max_concurrent_positions,
        max_capital_utilization_percent=str(context.policy.max_capital_utilization_percent),
        capital_ceiling=str(context.ceiling),
        held_position_count=context.held_count,
        held_asserted_notional=str(context.held_notional),
        remaining_capital_under_policy=str(context.remaining),
        requested_plan_count=context.requested_plan_count,
        admitted_plan_count=admitted_plan_count,
        excluded_plan_count=excluded_plan_count,
        total_admitted_notional=str(total_admitted_notional),
        projected_committed_notional=str(projected_committed_notional),
        projected_utilization_percent_of_ceiling=_percent(
            projected_committed_notional, context.ceiling
        ),
        plans_already_acted_upon=context.plans_already_acted_upon,
        held_positions=context.held_positions,
        verdicts=verdicts,
        excluded_future_event_count=context.excluded_future_event_count,
        limitations=limitations,
    )


def _ordering_key(request: SameDayPositionRequest) -> tuple[int, int, str]:
    """Deterministic priority, identical to M075's so the two artifacts can
    never disagree about order: ranked plans first in rank order, then
    unranked, then symbol as an explicit tiebreak."""
    if request.rank is None:
        return (1, 0, request.instrument_symbol)
    return (0, request.rank, request.instrument_symbol)


def _percent(numerator: Decimal, denominator: Decimal) -> str | None:
    """Percent as an exact Decimal string, or `None` when undefined.

    Never returns "0" for an undefined ratio -- zero would read as "nothing
    used", which is a different and stronger claim than "not computable".
    """
    if denominator <= 0:
        return None
    return str((numerator / denominator * Decimal("100")).quantize(Decimal("0.01")))


def _unassessable(
    *,
    reason: PortfolioAwareUnassessableReason,
    policy: PortfolioCapitalPolicy,
    capital_base: Decimal,
    requested_plan_count: int,
    limitations: tuple[str, ...],
) -> PortfolioAwareCapitalAssessment:
    return PortfolioAwareCapitalAssessment(
        outcome=PortfolioAwareOutcome.NOT_ASSESSABLE,
        unassessable_reason=reason,
        policy_id=policy.policy_id,
        policy_version=policy.version,
        currency=policy.currency,
        capital_base=str(capital_base),
        max_concurrent_positions=policy.max_concurrent_positions,
        max_capital_utilization_percent=str(policy.max_capital_utilization_percent),
        capital_ceiling=str(Decimal("0")),
        held_position_count=0,
        held_asserted_notional=str(Decimal("0")),
        remaining_capital_under_policy=str(Decimal("0")),
        requested_plan_count=requested_plan_count,
        admitted_plan_count=0,
        excluded_plan_count=0,
        total_admitted_notional=str(Decimal("0")),
        projected_committed_notional=str(Decimal("0")),
        projected_utilization_percent_of_ceiling=None,
        limitations=limitations,
    )


def assess_portfolio_aware_capital_feasibility(
    *,
    requests: tuple[SameDayPositionRequest, ...],
    held_state: DerivedPositionState | None,
    held_plan_lineage: frozenset[str] = frozenset(),
    lineage_by_position_key: dict[str, str | None] | None = None,
    session_is_completed: bool,
    ledger_available: bool = True,
    template_policy: PortfolioCapitalPolicy = DEFAULT_PORTFOLIO_CAPITAL_POLICY,
) -> PortfolioAwareCapitalAssessment:
    """Assess this session's approved plans AFTER charging already-asserted
    exposure against one explicit capital policy.

    Admission, per plan, in deterministic priority order:

      1. a plan an OPEN asserted position already cites -> excluded once, named
      2. held + admitted position count at the cap -> MAX_CONCURRENT_POSITIONS
      3. held + committed + this notional exceeds the ceiling ->
         MAX_CAPITAL_UTILIZATION_EXCEEDED
      4. otherwise admitted, and its notional is committed

    The ceiling comparison is strict `>`, matching M075 exactly, so a set
    landing precisely on the limit is feasible.
    """
    limitations: list[str] = []

    usable: list[SameDayPositionRequest] = []
    already_acted: list[str] = []
    bad_data_excluded = 0
    # Filter in the SAME deterministic order the verdicts use, so `limitations`
    # and `plans_already_acted_upon` cannot depend on the caller's input order.
    for request in sorted(requests, key=_ordering_key):
        if request.position_plan_governance_id in held_plan_lineage:
            already_acted.append(request.position_plan_governance_id)
            limitations.append(
                f"{request.instrument_symbol}: excluded, an open operator-asserted "
                f"position already cites plan {request.position_plan_governance_id}; "
                "counting it again would charge one decision twice"
            )
            continue
        if request.position_notional <= 0:
            bad_data_excluded += 1
            limitations.append(
                f"{request.instrument_symbol}: excluded, non-positive position notional "
                f"{request.position_notional}"
            )
            continue
        if request.supplied_account_equity <= 0:
            bad_data_excluded += 1
            limitations.append(
                f"{request.instrument_symbol}: excluded, non-positive supplied account "
                f"equity {request.supplied_account_equity}"
            )
            continue
        usable.append(request)

    excluded_count = len(requests) - len(usable)

    # Capital base: identical rule to M075 -- the equity the plans were sized
    # against, minimum when they disagree. Conservative, deterministic, never
    # an average.
    equities = {request.supplied_account_equity for request in usable}
    capital_base = min(equities) if equities else Decimal("0")
    if len(equities) > 1:
        limitations.append(
            "approved position plans in this session were sized against different account "
            f"equity figures ({', '.join(str(e) for e in sorted(equities))}); the smallest "
            "was used as the capital base"
        )

    policy = (
        capital_policy_for_session(capital_base=capital_base, template=template_policy)
        if capital_base > 0
        else template_policy
    )

    if not ledger_available:
        limitations.append(
            "the operator position ledger could not be read; a portfolio-aware verdict is "
            "withheld rather than presented as if nothing were held"
        )
        return _unassessable(
            reason=PortfolioAwareUnassessableReason.LEDGER_UNAVAILABLE,
            policy=policy,
            capital_base=capital_base,
            requested_plan_count=len(requests),
            limitations=tuple(limitations),
        )

    if held_state is None:
        limitations.append(
            "persisted operator position events do not fold into a coherent sequence; a "
            "portfolio-aware verdict is withheld"
        )
        return _unassessable(
            reason=PortfolioAwareUnassessableReason.LEDGER_INCOHERENT,
            policy=policy,
            capital_base=capital_base,
            requested_plan_count=len(requests),
            limitations=tuple(limitations),
        )

    if not session_is_completed:
        limitations.append(
            "session is not COMPLETED; a portfolio-aware capital verdict is withheld "
            "rather than presented as feasible"
        )
        return _unassessable(
            reason=PortfolioAwareUnassessableReason.SESSION_NOT_COMPLETED,
            policy=policy,
            capital_base=capital_base,
            requested_plan_count=len(requests),
            limitations=tuple(limitations),
        )

    # M076 emits canonical exact Decimal strings, so this round-trips exactly.
    held_notional = Decimal(held_state.total_asserted_open_notional)
    held_count = len(held_state.open_positions)
    held_positions = _held_positions_of(
        state=held_state, lineage_by_key=lineage_by_position_key or {}
    )
    if held_state.excluded_future_event_count:
        limitations.append(
            f"{held_state.excluded_future_event_count} operator-asserted event(s) stamped "
            "after this session's as_of were excluded from the held snapshot"
        )
    if held_count:
        limitations.append(
            "held exposure is quantity x the operator's ASSERTED entry price; it is not "
            "revalued and is not a market valuation"
        )

    # A usable plan always carries positive equity, so a non-positive capital
    # base can only mean every plan was excluded as bad data. The ceiling is
    # then zero and no admission is possible -- but held exposure is still a
    # real observation and is still reported below.
    # NOT quantized. M075 uses the exact product, and rounding here would make
    # the two artifacts disagree about whether a boundary-value plan fits.
    ceiling = (
        capital_base * policy.max_capital_utilization_percent if capital_base > 0 else Decimal("0")
    )
    remaining = ceiling - held_notional
    if remaining < 0:
        remaining = Decimal("0")

    context = _AssessmentContext(
        policy=policy,
        capital_base=capital_base,
        ceiling=ceiling,
        remaining=remaining,
        held_count=held_count,
        held_notional=held_notional,
        held_positions=held_positions,
        requested_plan_count=len(requests),
        plans_already_acted_upon=tuple(sorted(already_acted)),
        excluded_future_event_count=held_state.excluded_future_event_count,
    )

    # No assessable plan remains. If plans were dropped as bad data that is a
    # withheld verdict; if there were simply none to propose (or all were
    # already acted upon) that is a real, reportable state -- and held exposure
    # is reported either way rather than hidden behind the absence of plans.
    if not usable:
        if bad_data_excluded:
            return _unassessable(
                reason=PortfolioAwareUnassessableReason.NON_POSITIVE_CAPITAL_BASE,
                policy=policy,
                capital_base=capital_base,
                requested_plan_count=len(requests),
                limitations=tuple(limitations),
            )
        return _assessment(
            context=context,
            outcome=PortfolioAwareOutcome.NO_APPROVED_POSITION_PLANS,
            admitted_plan_count=0,
            excluded_plan_count=excluded_count,
            total_admitted_notional=Decimal("0"),
            projected_committed_notional=held_notional,
            verdicts=(),
            limitations=tuple(limitations),
        )

    # Held exposure alone is already at or beyond the ceiling: nothing further
    # can be admitted, and saying so plainly is more useful than running the
    # loop and reporting a string of individual rejections.
    if held_notional >= ceiling and held_count:
        limitations.append(
            "operator-asserted exposure already meets or exceeds the capital ceiling under "
            "this policy; no additional plan can be admitted"
        )
        return _assessment(
            context=context,
            outcome=PortfolioAwareOutcome.ALREADY_AT_OR_OVER_CAPITAL,
            admitted_plan_count=0,
            excluded_plan_count=excluded_count + len(usable),
            total_admitted_notional=Decimal("0"),
            projected_committed_notional=held_notional,
            verdicts=tuple(
                PortfolioAwarePlanVerdict(
                    rank=request.rank,
                    instrument_symbol=request.instrument_symbol,
                    position_plan_governance_id=request.position_plan_governance_id,
                    quantity=request.quantity,
                    position_notional=str(request.position_notional),
                    fits=False,
                    rejection_reason=(PortfolioRejectionReason.MAX_CAPITAL_UTILIZATION_EXCEEDED),
                    cumulative_committed_notional=str(held_notional),
                )
                for request in sorted(usable, key=_ordering_key)
            ),
            limitations=tuple(limitations),
        )

    committed = held_notional
    admitted_positions = held_count
    verdicts: list[PortfolioAwarePlanVerdict] = []
    admitted = 0

    for request in sorted(usable, key=_ordering_key):
        reason: PortfolioRejectionReason | None = None
        if admitted_positions >= policy.max_concurrent_positions:
            reason = PortfolioRejectionReason.MAX_CONCURRENT_POSITIONS
        elif committed + request.position_notional > ceiling:
            reason = PortfolioRejectionReason.MAX_CAPITAL_UTILIZATION_EXCEEDED
        if reason is None:
            committed += request.position_notional
            admitted_positions += 1
            admitted += 1
        verdicts.append(
            PortfolioAwarePlanVerdict(
                rank=request.rank,
                instrument_symbol=request.instrument_symbol,
                position_plan_governance_id=request.position_plan_governance_id,
                quantity=request.quantity,
                position_notional=str(request.position_notional),
                fits=reason is None,
                rejection_reason=reason,
                cumulative_committed_notional=str(committed),
            )
        )

    outcome = (
        PortfolioAwareOutcome.FITS_WITHIN_REMAINING_CAPITAL
        if admitted == len(usable)
        else PortfolioAwareOutcome.EXCEEDS_REMAINING_CAPITAL
    )
    return _assessment(
        context=context,
        outcome=outcome,
        admitted_plan_count=admitted,
        excluded_plan_count=excluded_count + (len(usable) - admitted),
        total_admitted_notional=committed - held_notional,
        projected_committed_notional=committed,
        verdicts=tuple(verdicts),
        limitations=tuple(limitations),
    )
