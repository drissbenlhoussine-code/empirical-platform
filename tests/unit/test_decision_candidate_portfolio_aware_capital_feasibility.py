"""MILESTONE-077 unit tests.

Written from the claims in
`MILESTONE_077_PORTFOLIO_AWARE_CAPITAL_FEASIBILITY_SCOPE_AND_DESIGN.md`,
not from the implementation's shape.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from empirical_platform.decision_candidate.operator_position_ledger import (
    OperatorAssertedPositionEvent,
    OperatorPositionEventKind,
    derive_position_state,
)
from empirical_platform.decision_candidate.portfolio_aware_capital_feasibility import (
    PORTFOLIO_AWARE_FEASIBILITY_BANNER,
    PortfolioAwareCapitalAssessment,
    PortfolioAwareOutcome,
    PortfolioAwareUnassessableReason,
    assess_portfolio_aware_capital_feasibility,
    open_position_plan_lineage,
)
from empirical_platform.decision_candidate.portfolio_study import (
    DEFAULT_PORTFOLIO_CAPITAL_POLICY,
    PortfolioRejectionReason,
)
from empirical_platform.decision_candidate.same_day_capital_feasibility import (
    SameDayPositionRequest,
)

AS_OF = datetime(2026, 4, 10, 16, 0, tzinfo=UTC)
EQUITY = Decimal("100000")


def event(
    *,
    gid: str,
    pos: str,
    symbol: str = "AAPL",
    kind: OperatorPositionEventKind = OperatorPositionEventKind.OPENED,
    quantity: int = 100,
    price: str = "100",
    at: datetime | None = None,
    plan: str | None = None,
) -> OperatorAssertedPositionEvent:
    moment = at or (AS_OF - timedelta(days=1))
    return OperatorAssertedPositionEvent(
        governance_id=gid,
        runtime_id=f"rt-{gid}",
        position_governance_id=pos,
        instrument_symbol=symbol,
        kind=kind,
        quantity=quantity,
        asserted_price=Decimal(price),
        event_timestamp=moment,
        recorded_at=moment,
        source_position_plan_governance_id=plan,
    )


def request(
    *,
    symbol: str = "MSFT",
    plan: str = "PLAN-1",
    rank: int | None = 1,
    notional: str = "10000",
    quantity: int = 50,
    equity: Decimal = EQUITY,
) -> SameDayPositionRequest:
    return SameDayPositionRequest(
        rank=rank,
        instrument_symbol=symbol,
        position_plan_governance_id=plan,
        quantity=quantity,
        position_notional=Decimal(notional),
        actual_risk=Decimal("500"),
        supplied_account_equity=equity,
    )


def assess(
    *,
    requests: tuple[SameDayPositionRequest, ...] = (),
    events: tuple[OperatorAssertedPositionEvent, ...] = (),
    as_of: datetime = AS_OF,
    completed: bool = True,
    ledger_available: bool = True,
    incoherent: bool = False,
) -> PortfolioAwareCapitalAssessment:
    state = None if incoherent else derive_position_state(events=events, as_of=as_of)
    lineage = (
        frozenset() if state is None else open_position_plan_lineage(events=events, state=state)
    )
    by_key: dict[str, str | None] = {
        e.position_governance_id: e.source_position_plan_governance_id
        for e in events
        if e.kind is OperatorPositionEventKind.OPENED
    }
    return assess_portfolio_aware_capital_feasibility(
        requests=requests,
        held_state=state,
        held_plan_lineage=lineage,
        lineage_by_position_key=by_key,
        session_is_completed=completed,
        ledger_available=ledger_available,
    )


# --------------------------------------------------------------------------
# Product acceptance scenarios A-J
# --------------------------------------------------------------------------


def test_scenario_a_no_existing_positions_and_plans_fit() -> None:
    result = assess(requests=(request(),))
    assert result.outcome is PortfolioAwareOutcome.FITS_WITHIN_REMAINING_CAPITAL
    assert result.held_position_count == 0
    assert Decimal(result.held_asserted_notional) == Decimal("0")
    assert result.admitted_plan_count == 1


def test_scenario_b_existing_position_consumes_part_of_capital() -> None:
    # held 100 x 700 = 70,000 of a 100,000 ceiling -> 30,000 headroom.
    held = (event(gid="E1", pos="P1", price="700"),)
    result = assess(
        requests=(
            request(symbol="MSFT", plan="PLAN-1", rank=1, notional="25000"),
            request(symbol="NVDA", plan="PLAN-2", rank=2, notional="25000"),
        ),
        events=held,
    )
    assert result.outcome is PortfolioAwareOutcome.EXCEEDS_REMAINING_CAPITAL
    assert Decimal(result.held_asserted_notional) == Decimal("70000")
    assert Decimal(result.remaining_capital_under_policy) == Decimal("30000")
    assert result.admitted_plan_count == 1
    assert result.verdicts[0].fits is True
    assert result.verdicts[1].fits is False
    assert (
        result.verdicts[1].rejection_reason
        is PortfolioRejectionReason.MAX_CAPITAL_UTILIZATION_EXCEEDED
    )


def test_scenario_c_existing_exposure_exactly_equals_capital() -> None:
    held = (event(gid="E1", pos="P1", quantity=1000, price="100"),)  # 100,000
    result = assess(requests=(request(),), events=held)
    assert result.outcome is PortfolioAwareOutcome.ALREADY_AT_OR_OVER_CAPITAL
    assert Decimal(result.remaining_capital_under_policy) == Decimal("0")
    assert result.admitted_plan_count == 0


def test_scenario_d_existing_exposure_exceeds_capital() -> None:
    held = (event(gid="E1", pos="P1", quantity=1500, price="100"),)  # 150,000
    result = assess(requests=(request(),), events=held)
    assert result.outcome is PortfolioAwareOutcome.ALREADY_AT_OR_OVER_CAPITAL
    assert Decimal(result.held_asserted_notional) == Decimal("150000")
    # Never negative -- headroom floors at zero.
    assert Decimal(result.remaining_capital_under_policy) == Decimal("0")


def test_scenario_e_position_closed_before_as_of_does_not_count() -> None:
    opened = event(gid="E1", pos="P1", at=AS_OF - timedelta(days=3), price="700")
    closed = event(
        gid="E2",
        pos="P1",
        kind=OperatorPositionEventKind.CLOSED,
        quantity=100,
        at=AS_OF - timedelta(days=2),
        price="720",
    )
    result = assess(requests=(request(),), events=(opened, closed))
    assert result.held_position_count == 0
    assert Decimal(result.held_asserted_notional) == Decimal("0")
    assert result.outcome is PortfolioAwareOutcome.FITS_WITHIN_REMAINING_CAPITAL


def test_scenario_f_reduction_before_as_of_reduces_exposure() -> None:
    opened = event(gid="E1", pos="P1", quantity=100, price="700", at=AS_OF - timedelta(days=3))
    reduced = event(
        gid="E2",
        pos="P1",
        kind=OperatorPositionEventKind.REDUCED,
        quantity=60,
        price="710",
        at=AS_OF - timedelta(days=2),
    )
    result = assess(events=(opened, reduced), requests=(request(),))
    # 40 remaining x the ORIGINAL asserted entry price of 700.
    assert Decimal(result.held_asserted_notional) == Decimal("28000")
    assert result.held_positions[0].open_quantity == 40
    assert result.held_positions[0].asserted_entry_price == "700"


def test_scenario_g_reduction_after_as_of_does_not_affect_snapshot() -> None:
    opened = event(gid="E1", pos="P1", quantity=100, price="700", at=AS_OF - timedelta(days=3))
    later = event(
        gid="E2",
        pos="P1",
        kind=OperatorPositionEventKind.REDUCED,
        quantity=60,
        price="710",
        at=AS_OF + timedelta(days=1),
    )
    result = assess(events=(opened, later), requests=())
    assert Decimal(result.held_asserted_notional) == Decimal("70000")
    assert result.excluded_future_event_count == 1
    assert any("after this session's as_of" in line for line in result.limitations)


def test_scenario_h_same_instant_different_offsets_agree() -> None:
    utc_moment = datetime(2026, 4, 9, 12, 0, tzinfo=UTC)
    offset_moment = datetime(2026, 4, 9, 8, 0, tzinfo=timezone(timedelta(hours=-4)))
    assert utc_moment == offset_moment
    a = assess(events=(event(gid="E1", pos="P1", at=utc_moment, price="700"),))
    b = assess(events=(event(gid="E1", pos="P1", at=offset_moment, price="700"),))
    assert a.held_asserted_notional == b.held_asserted_notional
    assert a.outcome is b.outcome


def test_scenario_i_asserted_price_is_not_market_valuation() -> None:
    result = assess(events=(event(gid="E1", pos="P1", price="700"),), requests=(request(),))
    assert any("not revalued" in line for line in result.limitations)
    assert "NOT a current market price" in PORTFOLIO_AWARE_FEASIBILITY_BANNER


def test_scenario_j_no_plans_but_positions_held_still_reports_exposure() -> None:
    result = assess(events=(event(gid="E1", pos="P1", price="700"),), requests=())
    assert result.outcome is PortfolioAwareOutcome.NO_APPROVED_POSITION_PLANS
    assert Decimal(result.held_asserted_notional) == Decimal("70000")
    assert result.held_position_count == 1


# --------------------------------------------------------------------------
# Double counting
# --------------------------------------------------------------------------


def test_plan_already_acted_upon_is_excluded_exactly_once() -> None:
    held = (event(gid="E1", pos="P1", symbol="MSFT", price="700", plan="PLAN-1"),)
    result = assess(requests=(request(plan="PLAN-1", symbol="MSFT"),), events=held)
    assert result.plans_already_acted_upon == ("PLAN-1",)
    assert result.admitted_plan_count == 0
    assert any("charge one decision twice" in line for line in result.limitations)


def test_plan_cited_by_a_closed_position_is_not_excluded() -> None:
    opened = event(gid="E1", pos="P1", plan="PLAN-1", at=AS_OF - timedelta(days=3), price="700")
    closed = event(
        gid="E2",
        pos="P1",
        kind=OperatorPositionEventKind.CLOSED,
        quantity=100,
        at=AS_OF - timedelta(days=2),
        price="720",
    )
    result = assess(requests=(request(plan="PLAN-1"),), events=(opened, closed))
    assert result.plans_already_acted_upon == ()
    assert result.admitted_plan_count == 1


def test_two_positions_citing_one_plan_exclude_it_once() -> None:
    held = (
        event(gid="E1", pos="P1", plan="PLAN-1", price="100", quantity=10),
        event(gid="E2", pos="P2", plan="PLAN-1", price="100", quantity=10),
    )
    result = assess(requests=(request(plan="PLAN-1"),), events=held)
    assert result.plans_already_acted_upon == ("PLAN-1",)


def test_lineage_for_an_unrelated_plan_does_not_exclude() -> None:
    held = (event(gid="E1", pos="P1", plan="PLAN-OTHER", price="100", quantity=10),)
    result = assess(requests=(request(plan="PLAN-1"),), events=held)
    assert result.plans_already_acted_upon == ()
    assert result.admitted_plan_count == 1


def test_same_instrument_without_lineage_is_a_new_position_not_a_duplicate() -> None:
    held = (event(gid="E1", pos="P1", symbol="MSFT", price="100", quantity=10),)
    result = assess(requests=(request(symbol="MSFT", plan="PLAN-1"),), events=held)
    assert result.plans_already_acted_upon == ()
    assert result.admitted_plan_count == 1


# --------------------------------------------------------------------------
# Caps and boundaries
# --------------------------------------------------------------------------


def test_exact_ceiling_boundary_is_feasible() -> None:
    held = (event(gid="E1", pos="P1", quantity=100, price="700"),)  # 70,000
    result = assess(requests=(request(notional="30000"),), events=held)
    assert result.outcome is PortfolioAwareOutcome.FITS_WITHIN_REMAINING_CAPITAL
    assert Decimal(result.projected_committed_notional) == Decimal("100000")


def test_one_cent_over_the_ceiling_is_infeasible() -> None:
    held = (event(gid="E1", pos="P1", quantity=100, price="700"),)
    result = assess(requests=(request(notional="30000.01"),), events=held)
    assert result.outcome is PortfolioAwareOutcome.EXCEEDS_REMAINING_CAPITAL


def test_held_positions_consume_the_concurrent_position_cap() -> None:
    held = tuple(
        event(gid=f"E{i}", pos=f"P{i}", quantity=1, price="1")
        for i in range(DEFAULT_PORTFOLIO_CAPITAL_POLICY.max_concurrent_positions)
    )
    result = assess(requests=(request(notional="10"),), events=held)
    assert result.admitted_plan_count == 0
    assert result.verdicts[0].rejection_reason is PortfolioRejectionReason.MAX_CONCURRENT_POSITIONS


def test_a_large_plan_does_not_block_a_smaller_feasible_one() -> None:
    result = assess(
        requests=(
            request(symbol="AAA", plan="P-A", rank=1, notional="90000"),
            request(symbol="BBB", plan="P-B", rank=2, notional="80000"),
            request(symbol="CCC", plan="P-C", rank=3, notional="10000"),
        )
    )
    assert [v.fits for v in result.verdicts] == [True, False, True]


# --------------------------------------------------------------------------
# Absence, withholding, malformed state
# --------------------------------------------------------------------------


def test_session_not_completed_is_withheld() -> None:
    result = assess(requests=(request(),), completed=False)
    assert result.outcome is PortfolioAwareOutcome.NOT_ASSESSABLE
    assert result.unassessable_reason is PortfolioAwareUnassessableReason.SESSION_NOT_COMPLETED


def test_unavailable_ledger_is_withheld_not_treated_as_empty() -> None:
    result = assess(requests=(request(),), ledger_available=False)
    assert result.outcome is PortfolioAwareOutcome.NOT_ASSESSABLE
    assert result.unassessable_reason is PortfolioAwareUnassessableReason.LEDGER_UNAVAILABLE
    assert result.admitted_plan_count == 0


def test_incoherent_ledger_is_withheld() -> None:
    result = assess(requests=(request(),), incoherent=True)
    assert result.unassessable_reason is PortfolioAwareUnassessableReason.LEDGER_INCOHERENT


def test_empty_ledger_is_assessed_not_withheld() -> None:
    result = assess(requests=(request(),), events=())
    assert result.outcome is PortfolioAwareOutcome.FITS_WITHIN_REMAINING_CAPITAL


def test_non_positive_capital_base_is_withheld() -> None:
    result = assess(requests=(request(equity=Decimal("0")),))
    assert result.outcome is PortfolioAwareOutcome.NOT_ASSESSABLE


def test_non_positive_notional_is_named_not_silently_dropped() -> None:
    result = assess(requests=(request(notional="0"),))
    assert any("non-positive position notional" in line for line in result.limitations)


def test_differing_equities_use_the_minimum_and_say_so() -> None:
    result = assess(
        requests=(
            request(symbol="AAA", plan="P-A", equity=Decimal("100000")),
            request(symbol="BBB", plan="P-B", rank=2, equity=Decimal("60000")),
        )
    )
    assert Decimal(result.capital_base) == Decimal("60000")
    assert any("different account equity" in line for line in result.limitations)


def test_undefined_utilization_is_none_never_zero() -> None:
    result = assess(requests=(request(equity=Decimal("-1")),))
    assert result.projected_utilization_percent_of_ceiling is None


# --------------------------------------------------------------------------
# Determinism and honesty
# --------------------------------------------------------------------------


def test_verdict_order_is_deterministic_regardless_of_input_order() -> None:
    a = request(symbol="ZZZ", plan="P-Z", rank=2, notional="1000")
    b = request(symbol="AAA", plan="P-A", rank=1, notional="1000")
    forward = assess(requests=(a, b))
    reverse = assess(requests=(b, a))
    assert [v.instrument_symbol for v in forward.verdicts] == ["AAA", "ZZZ"]
    assert forward == reverse


def test_unranked_plans_sort_after_ranked_then_by_symbol() -> None:
    result = assess(
        requests=(
            request(symbol="MMM", plan="P-M", rank=None, notional="10"),
            request(symbol="BBB", plan="P-B", rank=None, notional="10"),
            request(symbol="ZZZ", plan="P-Z", rank=1, notional="10"),
        )
    )
    assert [v.instrument_symbol for v in result.verdicts] == ["ZZZ", "BBB", "MMM"]


def test_repeated_assessment_is_identical() -> None:
    events = (event(gid="E1", pos="P1", price="700"),)
    first = assess(requests=(request(),), events=events)
    second = assess(requests=(request(),), events=events)
    assert first == second


@pytest.mark.parametrize(
    "forbidden", ["EXECUTED", "FILLED", "VERIFIED", "ALLOCATED", "MARKET_VALUE"]
)
def test_forbidden_vocabulary_absent_from_outcomes(forbidden: str) -> None:
    assert all(forbidden not in member.value for member in PortfolioAwareOutcome)
    assert all(forbidden not in member.value for member in PortfolioAwareUnassessableReason)


def test_banner_denies_every_claim_m077_does_not_make() -> None:
    for denial in (
        "NOT broker-verified",
        "NOT a current market price",
        "NOT execution evidence",
        "NOT a verified account balance",
        "NOT a market valuation",
        "NOT realized or unrealized P&L",
        "NOT a profitability claim",
        "NOT advice",
    ):
        assert denial in PORTFOLIO_AWARE_FEASIBILITY_BANNER


def test_no_float_is_produced_anywhere() -> None:
    result = assess(events=(event(gid="E1", pos="P1", price="700"),), requests=(request(),))
    for value in (
        result.capital_base,
        result.held_asserted_notional,
        result.remaining_capital_under_policy,
        result.total_admitted_notional,
        result.projected_committed_notional,
    ):
        assert isinstance(value, str)
        Decimal(value)


def test_m075_semantics_are_not_reused_for_allocation() -> None:
    from empirical_platform.decision_candidate.portfolio_study import (
        PortfolioAllocationOutcome,
    )

    assert PortfolioAllocationOutcome.ALLOCATED.value not in {
        member.value for member in PortfolioAwareOutcome
    }


# --------------------------------------------------------------------------
# Regressions for defects found by the hostile implementation review
# --------------------------------------------------------------------------


def test_already_acted_upon_list_is_deterministic_regardless_of_input_order() -> None:
    """Implementation review R01. The list was built by iterating `requests` in
    caller order, so two orderings of the same input produced different
    tuples -- and therefore different assessments."""
    held = (
        event(gid="E1", pos="P1", plan="PLAN-B", price="10", quantity=1),
        event(gid="E2", pos="P2", plan="PLAN-A", price="10", quantity=1),
    )
    a = request(symbol="AAA", plan="PLAN-A", rank=1)
    b = request(symbol="BBB", plan="PLAN-B", rank=2)
    forward = assess(requests=(a, b), events=held)
    reverse = assess(requests=(b, a), events=held)
    assert forward.plans_already_acted_upon == ("PLAN-A", "PLAN-B")
    assert forward.plans_already_acted_upon == reverse.plans_already_acted_upon
    assert forward == reverse


def test_limitation_order_is_deterministic_regardless_of_input_order() -> None:
    """Implementation review R02. Same root cause as R01, different symptom."""
    a = request(symbol="AAA", plan="PLAN-A", rank=1, notional="0")
    b = request(symbol="BBB", plan="PLAN-B", rank=2, notional="0")
    assert assess(requests=(a, b)).limitations == assess(requests=(b, a)).limitations


def test_ceiling_boundary_agrees_exactly_with_m075() -> None:
    """Implementation review R03. M077 quantised the ceiling to two places
    while M075 uses the exact product, so a boundary-value plan was FEASIBLE
    under M075 and INFEASIBLE under M077 over identical inputs."""
    from empirical_platform.decision_candidate.same_day_capital_feasibility import (
        assess_same_day_capital_feasibility,
    )

    equity = Decimal("100000.005")
    requests = (request(notional="100000.005", equity=equity),)
    same_day = assess_same_day_capital_feasibility(requests=requests, session_is_completed=True)
    portfolio = assess(requests=requests)
    assert Decimal(portfolio.capital_ceiling) == Decimal(same_day.capital_ceiling)
    assert portfolio.verdicts[0].fits == same_day.verdicts[0].fits is True


def test_with_no_held_exposure_admission_matches_m075_exactly() -> None:
    """The strongest parity claim: with an empty ledger M077 must admit
    precisely the plans M075 admits."""
    from empirical_platform.decision_candidate.same_day_capital_feasibility import (
        assess_same_day_capital_feasibility,
    )

    requests = (
        request(symbol="AAA", plan="P-A", rank=1, notional="60000"),
        request(symbol="BBB", plan="P-B", rank=2, notional="50000"),
        request(symbol="CCC", plan="P-C", rank=3, notional="10000"),
    )
    same_day = assess_same_day_capital_feasibility(requests=requests, session_is_completed=True)
    portfolio = assess(requests=requests)
    assert [v.fits for v in portfolio.verdicts] == [v.fits for v in same_day.verdicts]
    assert portfolio.admitted_plan_count == same_day.admitted_plan_count


def test_blank_persisted_plan_citation_is_not_treated_as_an_identifier() -> None:
    """Implementation review R04. A persisted OPENED event citing an empty
    plan id put "" into the lineage set, so a malformed row could exclude an
    unrelated plan from the proposal set entirely."""
    held = (event(gid="E1", pos="P1", plan="", price="10", quantity=1),)
    assert assess(requests=(request(plan="PLAN-1"),), events=held).admitted_plan_count == 1
    blank = assess(requests=(request(plan=""),), events=held)
    assert blank.plans_already_acted_upon == ()
    assert blank.admitted_plan_count == 1


def test_whitespace_only_plan_citation_is_also_ignored() -> None:
    held = (event(gid="E1", pos="P1", plan="   ", price="10", quantity=1),)
    assert assess(requests=(request(plan="PLAN-1"),), events=held).admitted_plan_count == 1


# --------------------------------------------------------------------------
# Owner correction: capital-base authority is derived BEFORE already-acted
# plans are removed from the new-proposal set
# --------------------------------------------------------------------------


def test_all_plans_already_acted_keeps_the_session_capital_base() -> None:
    """Owner finding. Removing already-acted plans before deriving the capital
    base made a fully-acted session report a capital base of zero, and with it
    a zero ceiling -- which is not what the session recorded."""
    held = (event(gid="E1", pos="P1", plan="PLAN-1", price="700", quantity=100),)
    result = assess(requests=(request(plan="PLAN-1"),), events=held)

    assert Decimal(result.capital_base) == EQUITY
    assert Decimal(result.capital_ceiling) == EQUITY
    assert Decimal(result.held_asserted_notional) == Decimal("70000")
    assert Decimal(result.remaining_capital_under_policy) == Decimal("30000")
    assert result.plans_already_acted_upon == ("PLAN-1",)
    assert result.admitted_plan_count == 0


def test_all_plans_already_acted_is_not_reported_as_no_approved_plans() -> None:
    """Honesty of the wording: the session DID approve plans. Saying it had
    none would be a false statement about the session."""
    held = (event(gid="E1", pos="P1", plan="PLAN-1", price="700", quantity=100),)
    result = assess(requests=(request(plan="PLAN-1"),), events=held)

    assert result.outcome is PortfolioAwareOutcome.ALL_PLANS_ALREADY_ACTED_UPON
    assert result.outcome is not PortfolioAwareOutcome.NO_APPROVED_POSITION_PLANS
    assert any("already cited by an open" in line for line in result.limitations)


def test_genuinely_no_plans_still_reports_no_approved_position_plans() -> None:
    """The distinction must cut both ways."""
    result = assess(requests=(), events=(event(gid="E1", pos="P1", price="700"),))
    assert result.outcome is PortfolioAwareOutcome.NO_APPROVED_POSITION_PLANS
    assert result.plans_already_acted_upon == ()


def test_an_acted_plan_with_the_smaller_equity_still_sets_the_capital_base() -> None:
    """M075 minimum-equity semantics preserved: the minimum is taken over every
    valid approved plan, acted upon or not."""
    held = (event(gid="E1", pos="P1", plan="PLAN-LOW", price="10", quantity=1),)
    result = assess(
        requests=(
            request(symbol="AAA", plan="PLAN-LOW", rank=1, equity=Decimal("40000")),
            request(symbol="BBB", plan="PLAN-NEW", rank=2, equity=Decimal("100000")),
        ),
        events=held,
    )
    assert Decimal(result.capital_base) == Decimal("40000")
    assert result.plans_already_acted_upon == ("PLAN-LOW",)
    assert [v.position_plan_governance_id for v in result.verdicts] == ["PLAN-NEW"]


def test_a_new_plan_with_the_smaller_equity_still_sets_the_capital_base() -> None:
    held = (event(gid="E1", pos="P1", plan="PLAN-HIGH", price="10", quantity=1),)
    result = assess(
        requests=(
            request(symbol="AAA", plan="PLAN-HIGH", rank=1, equity=Decimal("100000")),
            request(symbol="BBB", plan="PLAN-NEW", rank=2, equity=Decimal("40000")),
        ),
        events=held,
    )
    assert Decimal(result.capital_base) == Decimal("40000")
    assert any("different account equity" in line for line in result.limitations)


def test_an_acted_plan_with_invalid_equity_is_not_a_capital_authority() -> None:
    """A plan with a non-positive equity is not a credible capital base,
    whether or not it was acted upon."""
    held = (event(gid="E1", pos="P1", plan="PLAN-BAD", price="10", quantity=1),)
    result = assess(
        requests=(
            request(symbol="AAA", plan="PLAN-BAD", rank=1, equity=Decimal("0")),
            request(symbol="BBB", plan="PLAN-NEW", rank=2, equity=Decimal("80000")),
        ),
        events=held,
    )
    assert Decimal(result.capital_base) == Decimal("80000")
    assert "PLAN-BAD" not in result.plans_already_acted_upon
    assert any("non-positive supplied account equity" in line for line in result.limitations)


def test_every_plan_invalid_remains_not_assessable() -> None:
    result = assess(requests=(request(equity=Decimal("0")),))
    assert result.outcome is PortfolioAwareOutcome.NOT_ASSESSABLE
    assert result.unassessable_reason is PortfolioAwareUnassessableReason.NON_POSITIVE_CAPITAL_BASE


def test_acted_plans_contribute_zero_new_proposed_notional() -> None:
    """The acted plan informs capital authority but must not consume headroom
    a second time -- the held snapshot already accounts for it."""
    held = (event(gid="E1", pos="P1", plan="PLAN-ACTED", price="700", quantity=100),)
    result = assess(
        requests=(
            request(symbol="AAA", plan="PLAN-ACTED", rank=1, notional="70000"),
            request(symbol="BBB", plan="PLAN-NEW", rank=2, notional="30000"),
        ),
        events=held,
    )
    # 70,000 held + 30,000 proposed lands exactly on the 100,000 ceiling. Had
    # the acted plan been charged again, this would have been infeasible.
    assert result.outcome is PortfolioAwareOutcome.FITS_WITHIN_REMAINING_CAPITAL
    assert Decimal(result.total_admitted_notional) == Decimal("30000")
    assert Decimal(result.projected_committed_notional) == Decimal("100000")


def test_capital_base_derivation_is_deterministic_regardless_of_input_order() -> None:
    held = (
        event(gid="E1", pos="P1", plan="PLAN-B", price="10", quantity=1),
        event(gid="E2", pos="P2", plan="PLAN-A", price="10", quantity=1),
    )
    a = request(symbol="AAA", plan="PLAN-A", rank=1, equity=Decimal("55000"))
    b = request(symbol="BBB", plan="PLAN-B", rank=2, equity=Decimal("45000"))
    c = request(symbol="CCC", plan="PLAN-C", rank=3, equity=Decimal("65000"))
    forward = assess(requests=(a, b, c), events=held)
    reverse = assess(requests=(c, b, a), events=held)
    assert Decimal(forward.capital_base) == Decimal("45000")
    assert forward.plans_already_acted_upon == ("PLAN-A", "PLAN-B")
    assert forward == reverse
