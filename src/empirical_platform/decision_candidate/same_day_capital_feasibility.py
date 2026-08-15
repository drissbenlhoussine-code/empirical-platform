"""MILESTONE-075 -- Same-day capital feasibility for one daily research session.

Pure, I/O-free. Answers exactly one question:

    Are THIS session's own approved position plans collectively satisfiable
    under one explicit, versioned capital policy?

Why this exists. M060 sizes every `PositionPlan` independently against the
same, full `supplied_account_equity`, capped at `maximum_notional_percent`
(0.25 at the shipped default). `build_position_plan()` takes no argument
describing any other position, so five approved plans in one session can
commit up to 125% of that equity. M067 already models concurrent capital
correctly -- but only for historical simulation. Nothing in the daily path
applied that reasoning to the artefact a human acts on each morning. This
module closes exactly that gap and nothing more.

What this is NOT. No position is taken. No capital is allocated or reserved.
No prior-day position is known or considered -- this repository has no
durable position state, and M075 does not create one. The capital base is the
number the operator supplied for sizing, not a verified account balance. This
is a DIAGNOSTIC over one RECOMMENDATION SET, not portfolio state, not
execution, not advice, and not a claim that any trade is profitable.

Temporal category. M074 surfaces HISTORICAL_EVIDENCE_AVAILABLE_AT(t). This
module introduces RECOMMENDATION_SET_FEASIBILITY_AT(t): a pure function of one
session's own approved plans plus one policy. It reads no state outside the
session, no prior day, and no market data of any kind -- so there is no
future-data channel, no cross-day channel, and no portfolio-state channel,
because there is no such input at all.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum

from empirical_platform.decision_candidate.portfolio_study import (
    DEFAULT_PORTFOLIO_CAPITAL_POLICY,
    PortfolioCapitalPolicy,
    PortfolioRejectionReason,
)

__all__ = [
    "CAPITAL_FEASIBILITY_BANNER",
    "SameDayCapitalAssessment",
    "SameDayCapitalOutcome",
    "SameDayCapitalVerdict",
    "SameDayPositionRequest",
    "UnassessableReason",
    "assess_same_day_capital_feasibility",
    "capital_policy_for_session",
]

#: Rendered verbatim wherever this assessment is shown. Every clause is load
# bearing: each one names a thing a reader might otherwise assume.
CAPITAL_FEASIBILITY_BANNER = (
    "feasibility of THIS session's own approved position plans against one explicit "
    "capital policy. NOT current portfolio state; NOT open positions; NOT prior-day "
    "exposure; NOT an allocation or reservation of capital; NOT execution; NOT a "
    "profitability claim. The capital base is the equity figure supplied for sizing, "
    "not a verified account balance."
)


class SameDayCapitalOutcome(StrEnum):
    """Closed vocabulary for the assessment as a whole.

    Deliberately NOT `PortfolioAllocationOutcome`. That enum's `ALLOCATED`
    member asserts capital *was allocated*; M075 allocates nothing. Only
    M067's *reason* vocabulary is reused, because those reasons are generic
    and reusing them keeps one definition in the repository.
    """

    FITS_WITHIN_CAPITAL = "FITS_WITHIN_CAPITAL"
    EXCEEDS_CAPITAL = "EXCEEDS_CAPITAL"
    NO_APPROVED_POSITION_PLANS = "NO_APPROVED_POSITION_PLANS"
    NOT_ASSESSABLE = "NOT_ASSESSABLE"


class UnassessableReason(StrEnum):
    """Why an assessment was withheld. Absence is never rendered as a pass."""

    SESSION_NOT_COMPLETED = "SESSION_NOT_COMPLETED"
    NON_POSITIVE_CAPITAL_BASE = "NON_POSITIVE_CAPITAL_BASE"


@dataclass(frozen=True, slots=True)
class SameDayPositionRequest:
    """One approved position plan's capital demand, as the brief already
    knows it. `rank` is the session's own operator-facing priority; `None`
    means the session recorded no rank for this decision."""

    rank: int | None
    instrument_symbol: str
    position_plan_governance_id: str
    quantity: int
    position_notional: Decimal
    actual_risk: Decimal
    supplied_account_equity: Decimal


@dataclass(frozen=True, slots=True)
class SameDayCapitalVerdict:
    """Per-plan verdict. `rejection_reason` is populated if and only if
    `fits` is False."""

    rank: int | None
    instrument_symbol: str
    position_plan_governance_id: str
    quantity: int
    position_notional: str
    actual_risk: str
    fits: bool
    rejection_reason: PortfolioRejectionReason | None
    cumulative_committed_notional: str


@dataclass(frozen=True, slots=True)
class SameDayCapitalAssessment:
    """The whole result. Every monetary value is a string of an exact
    `Decimal` -- no float is produced anywhere in this module."""

    outcome: SameDayCapitalOutcome
    unassessable_reason: UnassessableReason | None
    policy_id: str
    policy_version: str
    currency: str
    capital_base: str
    max_concurrent_positions: int
    max_capital_utilization_percent: str
    capital_ceiling: str
    requested_plan_count: int
    admitted_plan_count: int
    excluded_plan_count: int
    total_requested_notional: str
    total_admitted_notional: str
    total_admitted_risk: str
    utilization_percent_of_ceiling: str | None
    requested_percent_of_capital_base: str | None
    verdicts: tuple[SameDayCapitalVerdict, ...] = ()
    limitations: tuple[str, ...] = field(default_factory=tuple)


def capital_policy_for_session(
    *,
    capital_base: Decimal,
    template: PortfolioCapitalPolicy = DEFAULT_PORTFOLIO_CAPITAL_POLICY,
) -> PortfolioCapitalPolicy:
    """Build the policy for one session: the frozen M067 default's concurrency
    and utilisation limits, with `initial_capital` replaced by the equity this
    session actually sized against.

    The concurrency cap and utilisation cap are M067's own frozen defaults,
    reused rather than originated by M075.
    """
    return dataclasses.replace(template, initial_capital=capital_base)


def _ordering_key(request: SameDayPositionRequest) -> tuple[int, int, str]:
    """Deterministic priority: ranked plans first in rank order, then
    unranked, then symbol as an explicit tiebreak. Never depends on input
    order or on any set/dict iteration."""
    if request.rank is None:
        return (1, 0, request.instrument_symbol)
    return (0, request.rank, request.instrument_symbol)


def _unassessable(
    *,
    reason: UnassessableReason,
    policy: PortfolioCapitalPolicy,
    capital_base: Decimal,
    requested_plan_count: int,
    limitations: tuple[str, ...],
) -> SameDayCapitalAssessment:
    return SameDayCapitalAssessment(
        outcome=SameDayCapitalOutcome.NOT_ASSESSABLE,
        unassessable_reason=reason,
        policy_id=policy.policy_id,
        policy_version=policy.version,
        currency=policy.currency,
        capital_base=str(capital_base),
        max_concurrent_positions=policy.max_concurrent_positions,
        max_capital_utilization_percent=str(policy.max_capital_utilization_percent),
        capital_ceiling=str(Decimal("0")),
        requested_plan_count=requested_plan_count,
        admitted_plan_count=0,
        excluded_plan_count=0,
        total_requested_notional=str(Decimal("0")),
        total_admitted_notional=str(Decimal("0")),
        total_admitted_risk=str(Decimal("0")),
        utilization_percent_of_ceiling=None,
        requested_percent_of_capital_base=None,
        verdicts=(),
        limitations=limitations,
    )


def assess_same_day_capital_feasibility(
    *,
    requests: tuple[SameDayPositionRequest, ...],
    session_is_completed: bool,
    template_policy: PortfolioCapitalPolicy = DEFAULT_PORTFOLIO_CAPITAL_POLICY,
) -> SameDayCapitalAssessment:
    """Assess one session's approved position plans against one capital policy.

    Admission, in deterministic priority order, per plan:

      1. already at `max_concurrent_positions` -> MAX_CONCURRENT_POSITIONS
      2. committed + notional would exceed the ceiling ->
         MAX_CAPITAL_UTILIZATION_EXCEEDED
      3. otherwise admitted, and its notional is committed

    A plan that does not fit does NOT stop later, smaller plans from being
    admitted against the remaining capacity. That is a deliberate choice: the
    operator is better served by knowing the largest feasible subset in their
    own priority order than by an all-or-nothing verdict.

    The ceiling comparison is strict `>`, so a set that lands exactly on the
    utilisation limit is feasible.
    """
    limitations: list[str] = []

    usable: list[SameDayPositionRequest] = []
    for request in requests:
        if request.position_notional <= 0:
            limitations.append(
                f"{request.instrument_symbol}: excluded, non-positive position notional "
                f"{request.position_notional}"
            )
            continue
        if request.supplied_account_equity <= 0:
            limitations.append(
                f"{request.instrument_symbol}: excluded, non-positive supplied account "
                f"equity {request.supplied_account_equity}"
            )
            continue
        usable.append(request)

    excluded_count = len(requests) - len(usable)

    # Capital base: the equity the plans were actually sized against. Within a
    # session these are normally identical. If they differ, take the MINIMUM --
    # conservative, deterministic, and never an average.
    equities = {request.supplied_account_equity for request in usable}
    capital_base = min(equities) if equities else Decimal("0")
    if len(equities) > 1:
        limitations.append(
            "approved position plans in this session were sized against different account "
            f"equity figures ({', '.join(str(e) for e in sorted(equities))}); the smallest "
            "was used as the capital base"
        )

    # M067's `PortfolioCapitalPolicy` rejects a non-positive `initial_capital`,
    # and rightly so. When there is no usable capital base we must still report
    # the policy's *identity and limits* -- so the template is used for
    # reporting metadata and no invalid policy object is ever constructed.
    policy = (
        capital_policy_for_session(capital_base=capital_base, template=template_policy)
        if capital_base > 0
        else template_policy
    )

    if not session_is_completed:
        limitations.append(
            "session is not COMPLETED; a capital-feasibility verdict is withheld rather "
            "than presented as feasible"
        )
        return _unassessable(
            reason=UnassessableReason.SESSION_NOT_COMPLETED,
            policy=policy,
            capital_base=capital_base,
            requested_plan_count=len(requests),
            limitations=tuple(limitations),
        )

    if not usable:
        empty_outcome = (
            SameDayCapitalOutcome.NO_APPROVED_POSITION_PLANS
            if excluded_count == 0
            else SameDayCapitalOutcome.NOT_ASSESSABLE
        )
        if empty_outcome is SameDayCapitalOutcome.NOT_ASSESSABLE:
            return _unassessable(
                reason=UnassessableReason.NON_POSITIVE_CAPITAL_BASE,
                policy=policy,
                capital_base=capital_base,
                requested_plan_count=len(requests),
                limitations=tuple(limitations),
            )
        return SameDayCapitalAssessment(
            outcome=SameDayCapitalOutcome.NO_APPROVED_POSITION_PLANS,
            unassessable_reason=None,
            policy_id=policy.policy_id,
            policy_version=policy.version,
            currency=policy.currency,
            capital_base=str(capital_base),
            max_concurrent_positions=policy.max_concurrent_positions,
            max_capital_utilization_percent=str(policy.max_capital_utilization_percent),
            capital_ceiling=str(Decimal("0")),
            requested_plan_count=0,
            admitted_plan_count=0,
            excluded_plan_count=0,
            total_requested_notional=str(Decimal("0")),
            total_admitted_notional=str(Decimal("0")),
            total_admitted_risk=str(Decimal("0")),
            utilization_percent_of_ceiling=None,
            requested_percent_of_capital_base=None,
            verdicts=(),
            limitations=tuple(limitations),
        )

    if capital_base <= 0:
        return _unassessable(
            reason=UnassessableReason.NON_POSITIVE_CAPITAL_BASE,
            policy=policy,
            capital_base=capital_base,
            requested_plan_count=len(requests),
            limitations=tuple(limitations),
        )

    ceiling = capital_base * policy.max_capital_utilization_percent
    ordered = sorted(usable, key=_ordering_key)

    committed = Decimal("0")
    admitted_risk = Decimal("0")
    admitted_count = 0
    verdicts: list[SameDayCapitalVerdict] = []

    for request in ordered:
        reason: PortfolioRejectionReason | None = None
        if admitted_count >= policy.max_concurrent_positions:
            reason = PortfolioRejectionReason.MAX_CONCURRENT_POSITIONS
        elif committed + request.position_notional > ceiling:
            reason = PortfolioRejectionReason.MAX_CAPITAL_UTILIZATION_EXCEEDED

        if reason is None:
            committed += request.position_notional
            admitted_risk += request.actual_risk
            admitted_count += 1

        verdicts.append(
            SameDayCapitalVerdict(
                rank=request.rank,
                instrument_symbol=request.instrument_symbol,
                position_plan_governance_id=request.position_plan_governance_id,
                quantity=request.quantity,
                position_notional=str(request.position_notional),
                actual_risk=str(request.actual_risk),
                fits=reason is None,
                rejection_reason=reason,
                cumulative_committed_notional=str(committed),
            )
        )

    total_requested = sum((r.position_notional for r in ordered), Decimal("0"))
    outcome = (
        SameDayCapitalOutcome.FITS_WITHIN_CAPITAL
        if admitted_count == len(ordered)
        else SameDayCapitalOutcome.EXCEEDS_CAPITAL
    )
    if outcome is SameDayCapitalOutcome.EXCEEDS_CAPITAL:
        limitations.append(
            "this session's approved position plans cannot all be held at once under the "
            "stated capital policy; each plan was sized independently against the full "
            "account equity and no plan is aware of any other"
        )

    return SameDayCapitalAssessment(
        outcome=outcome,
        unassessable_reason=None,
        policy_id=policy.policy_id,
        policy_version=policy.version,
        currency=policy.currency,
        capital_base=str(capital_base),
        max_concurrent_positions=policy.max_concurrent_positions,
        max_capital_utilization_percent=str(policy.max_capital_utilization_percent),
        capital_ceiling=str(ceiling),
        requested_plan_count=len(ordered),
        admitted_plan_count=admitted_count,
        excluded_plan_count=excluded_count,
        total_requested_notional=str(total_requested),
        total_admitted_notional=str(committed),
        total_admitted_risk=str(admitted_risk),
        utilization_percent_of_ceiling=str(committed / ceiling) if ceiling > 0 else None,
        requested_percent_of_capital_base=str(total_requested / capital_base),
        verdicts=tuple(verdicts),
        limitations=tuple(limitations),
    )
