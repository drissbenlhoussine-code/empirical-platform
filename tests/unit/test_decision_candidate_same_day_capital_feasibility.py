"""MILESTONE-075 -- same-day capital feasibility, pure rule.

Every test here targets a specific attack from the M075 adversarial design
review. Happy paths are the minority on purpose.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from empirical_platform.decision_candidate.portfolio_study import (
    DEFAULT_PORTFOLIO_CAPITAL_POLICY,
    PortfolioRejectionReason,
)
from empirical_platform.decision_candidate.same_day_capital_feasibility import (
    CAPITAL_FEASIBILITY_BANNER,
    SameDayCapitalAssessment,
    SameDayCapitalOutcome,
    SameDayPositionRequest,
    UnassessableReason,
    assess_same_day_capital_feasibility,
    capital_policy_for_session,
)

_EQUITY = Decimal("100000")


def _req(
    *,
    rank: int | None,
    symbol: str,
    notional: str,
    risk: str = "1000",
    equity: Decimal = _EQUITY,
    quantity: int = 100,
) -> SameDayPositionRequest:
    return SameDayPositionRequest(
        rank=rank,
        instrument_symbol=symbol,
        position_plan_governance_id=f"POS-{symbol}",
        quantity=quantity,
        position_notional=Decimal(notional),
        actual_risk=Decimal(risk),
        supplied_account_equity=equity,
    )


def _assess(
    requests: tuple[SameDayPositionRequest, ...], *, completed: bool = True
) -> SameDayCapitalAssessment:
    return assess_same_day_capital_feasibility(requests=requests, session_is_completed=completed)


# --------------------------------------------------------------------------
# The defect this milestone exists to expose
# --------------------------------------------------------------------------


def test_five_plans_each_at_the_m060_notional_cap_exceed_capital() -> None:
    """The whole reason M075 exists: M060 caps each plan at 25% of the SAME
    equity, so five approved plans commit 125%. Before M075 the brief said
    nothing about this."""
    requests = tuple(
        _req(rank=i, symbol=s, notional="25000")
        for i, s in enumerate(["AAPL", "MSFT", "GOOG", "AMZN", "NVDA"], start=1)
    )
    result = _assess(requests)
    assert result.outcome is SameDayCapitalOutcome.EXCEEDS_CAPITAL
    assert result.admitted_plan_count == 4
    assert result.requested_plan_count == 5
    assert result.requested_percent_of_capital_base == "1.25"
    assert result.verdicts[-1].instrument_symbol == "NVDA"
    assert result.verdicts[-1].fits is False
    assert (
        result.verdicts[-1].rejection_reason
        is PortfolioRejectionReason.MAX_CAPITAL_UTILIZATION_EXCEEDED
    )
    assert any("cannot all be held at once" in limit for limit in result.limitations)


def test_four_plans_landing_exactly_on_the_ceiling_are_feasible() -> None:
    """D05: the ceiling comparison is strict `>`, so exactly 100% fits.
    An off-by-one here would reject a genuinely feasible set."""
    requests = tuple(
        _req(rank=i, symbol=s, notional="25000")
        for i, s in enumerate(["AAPL", "MSFT", "GOOG", "AMZN"], start=1)
    )
    result = _assess(requests)
    assert result.outcome is SameDayCapitalOutcome.FITS_WITHIN_CAPITAL
    assert result.admitted_plan_count == 4
    assert Decimal(result.utilization_percent_of_ceiling or "0") == Decimal("1")


def test_one_cent_over_the_ceiling_does_not_fit() -> None:
    requests = (
        _req(rank=1, symbol="AAPL", notional="99999.99"),
        _req(rank=2, symbol="MSFT", notional="0.02"),
    )
    result = _assess(requests)
    assert result.outcome is SameDayCapitalOutcome.EXCEEDS_CAPITAL
    assert result.verdicts[1].fits is False


# --------------------------------------------------------------------------
# Determinism (D01, D02, D03)
# --------------------------------------------------------------------------


def test_admission_order_is_by_rank_then_symbol() -> None:
    requests = (
        _req(rank=3, symbol="GOOG", notional="10000"),
        _req(rank=1, symbol="AAPL", notional="10000"),
        _req(rank=2, symbol="MSFT", notional="10000"),
    )
    result = _assess(requests)
    assert [v.instrument_symbol for v in result.verdicts] == ["AAPL", "MSFT", "GOOG"]


def test_duplicate_ranks_are_broken_deterministically_by_symbol() -> None:
    """D02: without an explicit tiebreak this ordering would be arbitrary."""
    requests = (
        _req(rank=1, symbol="ZZZZ", notional="10000"),
        _req(rank=1, symbol="AAAA", notional="10000"),
    )
    assert [v.instrument_symbol for v in _assess(requests).verdicts] == ["AAAA", "ZZZZ"]


def test_unranked_plans_sort_after_ranked_plans() -> None:
    """D01: `rank` is `int | None`; a None must not crash and must not
    outrank an explicitly ranked plan."""
    requests = (
        _req(rank=None, symbol="AAAA", notional="10000"),
        _req(rank=9, symbol="ZZZZ", notional="10000"),
    )
    assert [v.instrument_symbol for v in _assess(requests).verdicts] == ["ZZZZ", "AAAA"]


def test_result_is_independent_of_input_order() -> None:
    forward = tuple(
        _req(rank=i, symbol=s, notional="30000")
        for i, s in enumerate(["AAPL", "MSFT", "GOOG", "AMZN"], start=1)
    )
    assert _assess(forward) == _assess(tuple(reversed(forward)))


def test_repeated_assessment_is_deterministic() -> None:
    requests = tuple(
        _req(rank=i, symbol=s, notional="26000")
        for i, s in enumerate(["AAPL", "MSFT", "GOOG", "AMZN"], start=1)
    )
    assert _assess(requests) == _assess(requests)


# --------------------------------------------------------------------------
# Concurrency cap
# --------------------------------------------------------------------------


def test_concurrency_cap_rejects_the_eleventh_plan_even_when_capital_remains() -> None:
    requests = tuple(_req(rank=i, symbol=f"S{i:02d}", notional="1000") for i in range(1, 12))
    result = _assess(requests)
    assert DEFAULT_PORTFOLIO_CAPITAL_POLICY.max_concurrent_positions == 10
    assert result.admitted_plan_count == 10
    assert result.outcome is SameDayCapitalOutcome.EXCEEDS_CAPITAL
    last = result.verdicts[-1]
    assert last.rejection_reason is PortfolioRejectionReason.MAX_CONCURRENT_POSITIONS
    # capital was nowhere near exhausted -- 11k of 100k
    assert Decimal(result.total_admitted_notional) == Decimal("10000")


# --------------------------------------------------------------------------
# D20 -- a large plan does not starve later smaller plans
# --------------------------------------------------------------------------


def test_a_plan_that_does_not_fit_does_not_block_a_later_smaller_plan() -> None:
    requests = (
        _req(rank=1, symbol="BIG", notional="90000"),
        _req(rank=2, symbol="HUGE", notional="50000"),
        _req(rank=3, symbol="TINY", notional="5000"),
    )
    result = _assess(requests)
    fits = {v.instrument_symbol: v.fits for v in result.verdicts}
    assert fits == {"BIG": True, "HUGE": False, "TINY": True}
    assert Decimal(result.total_admitted_notional) == Decimal("95000")


# --------------------------------------------------------------------------
# Empty / withheld states (D12, D13, D15) -- absence is never a pass
# --------------------------------------------------------------------------


def test_no_approved_plans_is_its_own_outcome_not_a_pass() -> None:
    result = _assess(())
    assert result.outcome is SameDayCapitalOutcome.NO_APPROVED_POSITION_PLANS
    assert result.outcome is not SameDayCapitalOutcome.FITS_WITHIN_CAPITAL
    assert result.verdicts == ()


def test_incomplete_session_withholds_a_verdict() -> None:
    requests = (_req(rank=1, symbol="AAPL", notional="10000"),)
    result = _assess(requests, completed=False)
    assert result.outcome is SameDayCapitalOutcome.NOT_ASSESSABLE
    assert result.unassessable_reason is UnassessableReason.SESSION_NOT_COMPLETED
    assert any("withheld" in limit for limit in result.limitations)


@pytest.mark.parametrize("equity", ["0", "-1"])
def test_non_positive_equity_withholds_a_verdict(equity: str) -> None:
    requests = (_req(rank=1, symbol="AAPL", notional="10000", equity=Decimal(equity)),)
    result = _assess(requests)
    assert result.outcome is SameDayCapitalOutcome.NOT_ASSESSABLE
    assert result.unassessable_reason is UnassessableReason.NON_POSITIVE_CAPITAL_BASE
    assert any("non-positive supplied account equity" in x for x in result.limitations)


@pytest.mark.parametrize("notional", ["0", "-100"])
def test_non_positive_notional_is_excluded_and_named(notional: str) -> None:
    """D14: excluded plans are never silently dropped."""
    requests = (
        _req(rank=1, symbol="GOOD", notional="10000"),
        _req(rank=2, symbol="BAD", notional=notional),
    )
    result = _assess(requests)
    assert result.excluded_plan_count == 1
    assert result.requested_plan_count == 1
    assert any("BAD" in limit for limit in result.limitations)
    assert [v.instrument_symbol for v in result.verdicts] == ["GOOD"]


# --------------------------------------------------------------------------
# D11 -- inconsistent equity
# --------------------------------------------------------------------------


def test_inconsistent_equity_uses_the_minimum_and_says_so() -> None:
    requests = (
        _req(rank=1, symbol="AAPL", notional="30000", equity=Decimal("100000")),
        _req(rank=2, symbol="MSFT", notional="30000", equity=Decimal("50000")),
    )
    result = _assess(requests)
    assert result.capital_base == "50000"
    assert any("different account equity" in limit for limit in result.limitations)
    # never averaged
    assert result.capital_base != "75000"


# --------------------------------------------------------------------------
# Honesty and typing
# --------------------------------------------------------------------------


def test_banner_disclaims_every_thing_a_reader_might_assume() -> None:
    lowered = CAPITAL_FEASIBILITY_BANNER.lower()
    for forbidden_assumption in (
        "not current portfolio state",
        "not open positions",
        "not prior-day exposure",
        "not execution",
        "not a profitability claim",
    ):
        assert forbidden_assumption in lowered
    assert "not a verified account balance" in lowered


def test_outcome_vocabulary_never_claims_an_allocation_occurred() -> None:
    """D06: reusing M067's ALLOCATED would assert capital was allocated."""
    assert "ALLOCATED" not in {member.value for member in SameDayCapitalOutcome}


def test_policy_reuses_the_frozen_m067_limits_and_only_swaps_capital() -> None:
    """D22: the concurrency and utilisation caps are M067's, not invented."""
    policy = capital_policy_for_session(capital_base=Decimal("12345"))
    assert policy.initial_capital == Decimal("12345")
    assert (
        policy.max_concurrent_positions == DEFAULT_PORTFOLIO_CAPITAL_POLICY.max_concurrent_positions
    )
    assert (
        policy.max_capital_utilization_percent
        == DEFAULT_PORTFOLIO_CAPITAL_POLICY.max_capital_utilization_percent
    )


def test_every_monetary_output_is_an_exact_decimal_string_not_a_float() -> None:
    """D04: a float anywhere here would silently corrupt money."""
    requests = (_req(rank=1, symbol="AAPL", notional="33333.33", risk="333.33"),)
    result = _assess(requests)
    for value in (
        result.capital_base,
        result.capital_ceiling,
        result.total_requested_notional,
        result.total_admitted_notional,
        result.total_admitted_risk,
    ):
        assert isinstance(value, str)
        Decimal(value)  # exact, no ValueError
    assert result.total_admitted_notional == "33333.33"
    assert result.total_admitted_risk == "333.33"


def test_rejection_reason_is_set_if_and_only_if_a_plan_does_not_fit() -> None:
    requests = tuple(_req(rank=i, symbol=f"S{i}", notional="60000") for i in range(1, 4))
    result = _assess(requests)
    for verdict in result.verdicts:
        assert (verdict.rejection_reason is None) is verdict.fits


def test_cumulative_committed_notional_only_advances_on_admitted_plans() -> None:
    requests = (
        _req(rank=1, symbol="A", notional="60000"),
        _req(rank=2, symbol="B", notional="60000"),
        _req(rank=3, symbol="C", notional="30000"),
    )
    result = _assess(requests)
    assert [v.cumulative_committed_notional for v in result.verdicts] == [
        "60000",
        "60000",
        "90000",
    ]


def test_zero_capital_base_reports_policy_identity_without_constructing_it() -> None:
    """Regression for a real defect found by these tests: `PortfolioCapitalPolicy`
    rejects a non-positive `initial_capital`, so the withheld-verdict paths used
    to raise `ValueError` instead of reporting. The policy's identity and limits
    must still be reported."""
    result = _assess(())
    assert result.policy_id == DEFAULT_PORTFOLIO_CAPITAL_POLICY.policy_id
    assert result.policy_version == DEFAULT_PORTFOLIO_CAPITAL_POLICY.version
    assert (
        result.max_concurrent_positions == DEFAULT_PORTFOLIO_CAPITAL_POLICY.max_concurrent_positions
    )
    withheld = _assess((_req(rank=1, symbol="AAPL", notional="1000", equity=Decimal("0")),))
    assert withheld.outcome is SameDayCapitalOutcome.NOT_ASSESSABLE
    assert withheld.policy_id == DEFAULT_PORTFOLIO_CAPITAL_POLICY.policy_id
