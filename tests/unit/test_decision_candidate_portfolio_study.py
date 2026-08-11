"""MILESTONE-067 pure unit tests: portfolio capital-allocation domain.

Capital policy validation, allocation-decision validation, the
event-driven capital-allocation replay engine (tie-breaks, concurrency,
release semantics, accounting invariants), drawdown computation, and
capital-sensitivity scenarios. Exercises the internal computational core
(`_PooledOpportunity`, `_simulate_capital_allocation`,
`_build_event_timeline`, `_max_drawdown_from_equity_curve`,
`_capital_sensitivity_view`) directly with hand-constructed synthetic
opportunities -- mirroring the established M066 precedent of unit-testing
private domain helpers directly, while `build_portfolio_evidence_report`'s
full upstream-binding pipeline is exercised via real PostgreSQL
acceptance tests against the real M064 fixture.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from empirical_platform.decision_candidate.portfolio_study import (
    DEFAULT_PORTFOLIO_CAPITAL_POLICY,
    CapitalSensitivityLabel,
    PortfolioAllocationDecision,
    PortfolioAllocationOutcome,
    PortfolioCapitalPolicy,
    PortfolioEquityObservation,
    PortfolioEventKind,
    PortfolioRejectionReason,
    _capital_sensitivity_view,
    _max_drawdown_from_equity_curve,
    _PooledOpportunity,
    _simulate_capital_allocation,
)

_T0 = datetime(2026, 1, 1, 9, 30, tzinfo=UTC)


def _opp(
    *,
    window: str = "BTRUN-0001",
    seq: int,
    symbol: str,
    rank: int = 1,
    entry_offset_min: int,
    exit_offset_min: int,
    risk: str = "100",
    pnl: str = "10",
) -> _PooledOpportunity:
    return _PooledOpportunity(
        source_window_id=window,
        trade_sequence=seq,
        instrument_symbol=symbol,
        scan_rank=rank,
        entry_timestamp=_T0 + timedelta(minutes=entry_offset_min),
        exit_timestamp=_T0 + timedelta(minutes=exit_offset_min),
        risk_amount=Decimal(risk),
        net_pnl=Decimal(pnl),
    )


_POLICY = PortfolioCapitalPolicy(
    policy_id="TEST-POLICY",
    version="1",
    initial_capital=Decimal("1000"),
    currency="USD",
    max_concurrent_positions=10,
    max_capital_utilization_percent=Decimal("1.00"),
)


# --------------------------------------------------------------------------
# PortfolioCapitalPolicy validation
# --------------------------------------------------------------------------


def test_capital_policy_rejects_zero_initial_capital() -> None:
    with pytest.raises(ValueError, match="initial_capital must be positive"):
        PortfolioCapitalPolicy(
            policy_id="X",
            version="1",
            initial_capital=Decimal("0"),
            currency="USD",
            max_concurrent_positions=1,
            max_capital_utilization_percent=Decimal("1"),
        )


def test_capital_policy_rejects_negative_initial_capital() -> None:
    with pytest.raises(ValueError, match="initial_capital must be positive"):
        PortfolioCapitalPolicy(
            policy_id="X",
            version="1",
            initial_capital=Decimal("-100"),
            currency="USD",
            max_concurrent_positions=1,
            max_capital_utilization_percent=Decimal("1"),
        )


def test_capital_policy_rejects_zero_max_concurrent_positions() -> None:
    with pytest.raises(ValueError, match="max_concurrent_positions must be at least 1"):
        PortfolioCapitalPolicy(
            policy_id="X",
            version="1",
            initial_capital=Decimal("1000"),
            currency="USD",
            max_concurrent_positions=0,
            max_capital_utilization_percent=Decimal("1"),
        )


def test_capital_policy_rejects_zero_max_utilization() -> None:
    with pytest.raises(ValueError, match=r"max_capital_utilization_percent must be in \(0, 1\]"):
        PortfolioCapitalPolicy(
            policy_id="X",
            version="1",
            initial_capital=Decimal("1000"),
            currency="USD",
            max_concurrent_positions=1,
            max_capital_utilization_percent=Decimal("0"),
        )


def test_capital_policy_rejects_utilization_above_one() -> None:
    with pytest.raises(ValueError, match=r"max_capital_utilization_percent must be in \(0, 1\]"):
        PortfolioCapitalPolicy(
            policy_id="X",
            version="1",
            initial_capital=Decimal("1000"),
            currency="USD",
            max_concurrent_positions=1,
            max_capital_utilization_percent=Decimal("1.5"),
        )


def test_capital_policy_rejects_lowercase_currency() -> None:
    with pytest.raises(ValueError, match="currency must be a 3-letter uppercase code"):
        PortfolioCapitalPolicy(
            policy_id="X",
            version="1",
            initial_capital=Decimal("1000"),
            currency="usd",
            max_concurrent_positions=1,
            max_capital_utilization_percent=Decimal("1"),
        )


def test_capital_policy_rejects_empty_policy_id() -> None:
    with pytest.raises(ValueError, match="policy_id"):
        PortfolioCapitalPolicy(
            policy_id="   ",
            version="1",
            initial_capital=Decimal("1000"),
            currency="USD",
            max_concurrent_positions=1,
            max_capital_utilization_percent=Decimal("1"),
        )


def test_default_capital_policy_is_valid() -> None:
    assert DEFAULT_PORTFOLIO_CAPITAL_POLICY.initial_capital == Decimal("100000")


# --------------------------------------------------------------------------
# PortfolioAllocationDecision validation
# --------------------------------------------------------------------------


def test_allocation_decision_rejects_allocated_with_rejection_reason() -> None:
    with pytest.raises(ValueError, match="must not carry a rejection_reason"):
        PortfolioAllocationDecision(
            opportunity_sequence=1,
            source_window_id="W1",
            trade_sequence=1,
            instrument_symbol="AAPL",
            scan_rank=1,
            entry_timestamp=_T0,
            exit_timestamp=_T0,
            risk_amount=Decimal("100"),
            net_pnl=Decimal("10"),
            decision=PortfolioAllocationOutcome.ALLOCATED,
            rejection_reason=PortfolioRejectionReason.MAX_CONCURRENT_POSITIONS,
        )


def test_allocation_decision_rejects_rejected_without_reason() -> None:
    with pytest.raises(ValueError, match="must carry a rejection_reason"):
        PortfolioAllocationDecision(
            opportunity_sequence=1,
            source_window_id="W1",
            trade_sequence=1,
            instrument_symbol="AAPL",
            scan_rank=1,
            entry_timestamp=_T0,
            exit_timestamp=_T0,
            risk_amount=Decimal("100"),
            net_pnl=Decimal("10"),
            decision=PortfolioAllocationOutcome.REJECTED,
            rejection_reason=None,
        )


def test_allocation_decision_rejects_exit_before_entry() -> None:
    with pytest.raises(ValueError, match="exit_timestamp must not precede entry_timestamp"):
        PortfolioAllocationDecision(
            opportunity_sequence=1,
            source_window_id="W1",
            trade_sequence=1,
            instrument_symbol="AAPL",
            scan_rank=1,
            entry_timestamp=_T0,
            exit_timestamp=_T0 - timedelta(minutes=1),
            risk_amount=Decimal("100"),
            net_pnl=Decimal("10"),
            decision=PortfolioAllocationOutcome.ALLOCATED,
            rejection_reason=None,
        )


def test_allocation_decision_rejects_non_positive_risk_amount() -> None:
    with pytest.raises(ValueError, match="risk_amount must be positive"):
        PortfolioAllocationDecision(
            opportunity_sequence=1,
            source_window_id="W1",
            trade_sequence=1,
            instrument_symbol="AAPL",
            scan_rank=1,
            entry_timestamp=_T0,
            exit_timestamp=_T0,
            risk_amount=Decimal("0"),
            net_pnl=Decimal("10"),
            decision=PortfolioAllocationOutcome.ALLOCATED,
            rejection_reason=None,
        )


def test_allocation_decision_rejects_naive_timestamps() -> None:
    with pytest.raises(ValueError, match="entry_timestamp must be timezone-aware"):
        PortfolioAllocationDecision(
            opportunity_sequence=1,
            source_window_id="W1",
            trade_sequence=1,
            instrument_symbol="AAPL",
            scan_rank=1,
            entry_timestamp=datetime(2026, 1, 1, 9, 30),  # noqa: DTZ001
            exit_timestamp=_T0,
            risk_amount=Decimal("100"),
            net_pnl=Decimal("10"),
            decision=PortfolioAllocationOutcome.ALLOCATED,
            rejection_reason=None,
        )


# --------------------------------------------------------------------------
# PortfolioEquityObservation validation
# --------------------------------------------------------------------------


def test_equity_observation_rejects_negative_occupied_capital() -> None:
    with pytest.raises(ValueError, match="occupied_capital must be non-negative"):
        PortfolioEquityObservation(
            sequence_index=1,
            event_timestamp=_T0,
            event_kind=PortfolioEventKind.OPEN,
            equity=Decimal("1000"),
            occupied_capital=Decimal("-1"),
            available_capital=Decimal("999"),
            open_position_count=1,
        )


def test_equity_observation_rejects_negative_open_position_count() -> None:
    with pytest.raises(ValueError, match="open_position_count must be non-negative"):
        PortfolioEquityObservation(
            sequence_index=1,
            event_timestamp=_T0,
            event_kind=PortfolioEventKind.OPEN,
            equity=Decimal("1000"),
            occupied_capital=Decimal("0"),
            available_capital=Decimal("1000"),
            open_position_count=-1,
        )


# --------------------------------------------------------------------------
# Empty / degenerate inputs
# --------------------------------------------------------------------------


def test_empty_opportunities_produce_no_decisions_or_observations() -> None:
    decisions, equity = _simulate_capital_allocation((), _POLICY)
    assert decisions == ()
    assert equity == ()


def test_single_opportunity_within_capital_is_allocated() -> None:
    opp = _opp(seq=1, symbol="AAPL", entry_offset_min=0, exit_offset_min=5)
    decisions, equity = _simulate_capital_allocation((opp,), _POLICY)
    assert len(decisions) == 1
    assert decisions[0].decision is PortfolioAllocationOutcome.ALLOCATED
    assert len(equity) == 2  # one OPEN, one CLOSE
    assert equity[0].event_kind is PortfolioEventKind.OPEN
    assert equity[1].event_kind is PortfolioEventKind.CLOSE
    assert equity[1].equity == _POLICY.initial_capital + Decimal("10.000000")


def test_single_opportunity_exceeding_capital_is_rejected() -> None:
    opp = _opp(seq=1, symbol="AAPL", entry_offset_min=0, exit_offset_min=5, risk="5000")
    decisions, equity = _simulate_capital_allocation((opp,), _POLICY)
    assert decisions[0].decision is PortfolioAllocationOutcome.REJECTED
    assert decisions[0].rejection_reason is PortfolioRejectionReason.INSUFFICIENT_AVAILABLE_CAPITAL
    assert equity == ()


# --------------------------------------------------------------------------
# All-rejected / all-accepted attacks
# --------------------------------------------------------------------------


def test_all_opportunities_rejected_when_capital_is_far_too_small() -> None:
    tiny_policy = PortfolioCapitalPolicy(
        policy_id="TINY",
        version="1",
        initial_capital=Decimal("1"),
        currency="USD",
        max_concurrent_positions=10,
        max_capital_utilization_percent=Decimal("1"),
    )
    opps = tuple(
        _opp(seq=i, symbol="AAPL", entry_offset_min=i, exit_offset_min=i + 5, risk="100")
        for i in range(5)
    )
    decisions, equity = _simulate_capital_allocation(opps, tiny_policy)
    assert all(d.decision is PortfolioAllocationOutcome.REJECTED for d in decisions)
    assert equity == ()


def test_all_opportunities_accepted_when_capital_is_ample() -> None:
    ample_policy = PortfolioCapitalPolicy(
        policy_id="AMPLE",
        version="1",
        initial_capital=Decimal("1000000"),
        currency="USD",
        max_concurrent_positions=100,
        max_capital_utilization_percent=Decimal("1"),
    )
    opps = tuple(
        _opp(seq=i, symbol="AAPL", entry_offset_min=i, exit_offset_min=i + 5, risk="100")
        for i in range(5)
    )
    decisions, _equity = _simulate_capital_allocation(opps, ample_policy)
    assert all(d.decision is PortfolioAllocationOutcome.ALLOCATED for d in decisions)


# --------------------------------------------------------------------------
# Concurrency / capital bottleneck
# --------------------------------------------------------------------------


def test_second_overlapping_opportunity_rejected_for_insufficient_capital() -> None:
    policy = PortfolioCapitalPolicy(
        policy_id="X",
        version="1",
        initial_capital=Decimal("150"),
        currency="USD",
        max_concurrent_positions=10,
        max_capital_utilization_percent=Decimal("1"),
    )
    first = _opp(seq=1, symbol="AAPL", rank=1, entry_offset_min=0, exit_offset_min=10, risk="100")
    second = _opp(seq=2, symbol="MSFT", rank=2, entry_offset_min=1, exit_offset_min=5, risk="100")
    decisions, _equity = _simulate_capital_allocation((first, second), policy)
    by_seq = {d.trade_sequence: d for d in decisions}
    assert by_seq[1].decision is PortfolioAllocationOutcome.ALLOCATED
    assert by_seq[2].decision is PortfolioAllocationOutcome.REJECTED
    assert by_seq[2].rejection_reason is PortfolioRejectionReason.INSUFFICIENT_AVAILABLE_CAPITAL


def test_max_concurrent_positions_rejection() -> None:
    policy = PortfolioCapitalPolicy(
        policy_id="X",
        version="1",
        initial_capital=Decimal("10000"),
        currency="USD",
        max_concurrent_positions=1,
        max_capital_utilization_percent=Decimal("1"),
    )
    first = _opp(seq=1, symbol="AAPL", rank=1, entry_offset_min=0, exit_offset_min=10, risk="10")
    second = _opp(seq=2, symbol="MSFT", rank=2, entry_offset_min=1, exit_offset_min=5, risk="10")
    decisions, _equity = _simulate_capital_allocation((first, second), policy)
    by_seq = {d.trade_sequence: d for d in decisions}
    assert by_seq[1].decision is PortfolioAllocationOutcome.ALLOCATED
    assert by_seq[2].decision is PortfolioAllocationOutcome.REJECTED
    assert by_seq[2].rejection_reason is PortfolioRejectionReason.MAX_CONCURRENT_POSITIONS


def test_max_capital_utilization_rejection() -> None:
    policy = PortfolioCapitalPolicy(
        policy_id="X",
        version="1",
        initial_capital=Decimal("1000"),
        currency="USD",
        max_concurrent_positions=10,
        max_capital_utilization_percent=Decimal("0.10"),
    )
    first = _opp(seq=1, symbol="AAPL", rank=1, entry_offset_min=0, exit_offset_min=10, risk="90")
    second = _opp(seq=2, symbol="MSFT", rank=2, entry_offset_min=1, exit_offset_min=5, risk="90")
    decisions, _equity = _simulate_capital_allocation((first, second), policy)
    by_seq = {d.trade_sequence: d for d in decisions}
    assert by_seq[1].decision is PortfolioAllocationOutcome.ALLOCATED
    assert by_seq[2].decision is PortfolioAllocationOutcome.REJECTED
    assert by_seq[2].rejection_reason is PortfolioRejectionReason.MAX_CAPITAL_UTILIZATION_EXCEEDED


def test_no_double_spending_two_non_overlapping_opportunities_both_allocated() -> None:
    """Sequential (non-overlapping) opportunities each get the full
    capital pool -- proves capital is genuinely released, not held
    forever (mission Phase 9)."""
    policy = PortfolioCapitalPolicy(
        policy_id="X",
        version="1",
        initial_capital=Decimal("100"),
        currency="USD",
        max_concurrent_positions=10,
        max_capital_utilization_percent=Decimal("1"),
    )
    first = _opp(seq=1, symbol="AAPL", entry_offset_min=0, exit_offset_min=5, risk="100")
    second = _opp(seq=2, symbol="MSFT", entry_offset_min=10, exit_offset_min=15, risk="100")
    decisions, _equity = _simulate_capital_allocation((first, second), policy)
    assert all(d.decision is PortfolioAllocationOutcome.ALLOCATED for d in decisions)


# --------------------------------------------------------------------------
# Release semantics
# --------------------------------------------------------------------------


def test_capital_unavailable_while_open_then_available_after_exit() -> None:
    policy = PortfolioCapitalPolicy(
        policy_id="X",
        version="1",
        initial_capital=Decimal("100"),
        currency="USD",
        max_concurrent_positions=10,
        max_capital_utilization_percent=Decimal("1"),
    )
    first = _opp(seq=1, symbol="AAPL", entry_offset_min=0, exit_offset_min=5, risk="100")
    # Competing opportunity while the first is still open -- must be rejected.
    competing = _opp(seq=2, symbol="MSFT", entry_offset_min=1, exit_offset_min=6, risk="100")
    # Same-size opportunity opening only after the first's own exit -- must succeed.
    later = _opp(seq=3, symbol="GOOG", entry_offset_min=6, exit_offset_min=10, risk="100")
    decisions, _equity = _simulate_capital_allocation((first, competing, later), policy)
    by_seq = {d.trade_sequence: d for d in decisions}
    assert by_seq[1].decision is PortfolioAllocationOutcome.ALLOCATED
    assert by_seq[2].decision is PortfolioAllocationOutcome.REJECTED
    assert by_seq[3].decision is PortfolioAllocationOutcome.ALLOCATED


# --------------------------------------------------------------------------
# Event ordering / tie-break attacks
# --------------------------------------------------------------------------


def test_close_before_open_at_same_instant_frees_capital_for_competitor() -> None:
    policy = PortfolioCapitalPolicy(
        policy_id="X",
        version="1",
        initial_capital=Decimal("100"),
        currency="USD",
        max_concurrent_positions=10,
        max_capital_utilization_percent=Decimal("1"),
    )
    first = _opp(seq=1, symbol="AAPL", entry_offset_min=0, exit_offset_min=5, risk="100")
    # Opens at the exact instant `first` closes -- must succeed because
    # CLOSE is processed before OPEN at the same timestamp.
    second = _opp(seq=2, symbol="MSFT", entry_offset_min=5, exit_offset_min=10, risk="100")
    decisions, _equity = _simulate_capital_allocation((first, second), policy)
    assert all(d.decision is PortfolioAllocationOutcome.ALLOCATED for d in decisions)


def test_simultaneous_opens_ordered_by_scan_rank_reuses_upstream_ranking() -> None:
    """Two opportunities open at the exact same instant and together
    exceed available capital -- the better-ranked one (lower scan_rank)
    must win, per the frozen upstream ranking, never a new alpha model."""
    policy = PortfolioCapitalPolicy(
        policy_id="X",
        version="1",
        initial_capital=Decimal("150"),
        currency="USD",
        max_concurrent_positions=10,
        max_capital_utilization_percent=Decimal("1"),
    )
    weaker_rank = _opp(
        seq=1, symbol="ZZZZ", rank=5, entry_offset_min=0, exit_offset_min=5, risk="100"
    )
    stronger_rank = _opp(
        seq=2, symbol="AAAA", rank=1, entry_offset_min=0, exit_offset_min=5, risk="100"
    )
    decisions, _equity = _simulate_capital_allocation((weaker_rank, stronger_rank), policy)
    by_seq = {d.trade_sequence: d for d in decisions}
    assert by_seq[2].decision is PortfolioAllocationOutcome.ALLOCATED  # rank 1 wins
    assert by_seq[1].decision is PortfolioAllocationOutcome.REJECTED


def test_zero_duration_opportunity_opens_before_its_own_close() -> None:
    """entry_timestamp == exit_timestamp must not paradoxically try to
    close before opening -- the position is genuinely allocated then
    immediately released within the same instant."""
    opp = _opp(seq=1, symbol="AAPL", entry_offset_min=5, exit_offset_min=5, risk="100", pnl="7")
    decisions, equity = _simulate_capital_allocation((opp,), _POLICY)
    assert decisions[0].decision is PortfolioAllocationOutcome.ALLOCATED
    assert len(equity) == 2
    assert equity[0].event_kind is PortfolioEventKind.OPEN
    assert equity[1].event_kind is PortfolioEventKind.CLOSE
    assert equity[1].equity == _POLICY.initial_capital + Decimal("7.000000")


def test_zero_duration_opportunity_briefly_occupies_capital_at_its_own_instant() -> None:
    """A zero-duration opportunity's own self-close is ordered *after*
    every OPEN at the same instant (priority 2, vs. priority 1 for
    opens) -- it cannot un-reject a same-instant competitor's OPEN
    attempt, since a position genuinely, if briefly, occupies capital
    during its own instant and processing is a single forward pass with
    no backtracking. This is the deliberate, documented tie-break (a
    zero-duration trade's own CLOSE must never be confused with a
    *different* trade's CLOSE, which does still free capital before
    same-instant OPENs)."""
    policy = PortfolioCapitalPolicy(
        policy_id="X",
        version="1",
        initial_capital=Decimal("100"),
        currency="USD",
        max_concurrent_positions=10,
        max_capital_utilization_percent=Decimal("1"),
    )
    zero_duration = _opp(
        seq=1, symbol="AAPL", rank=1, entry_offset_min=5, exit_offset_min=5, risk="100"
    )
    competitor = _opp(
        seq=2, symbol="MSFT", rank=2, entry_offset_min=5, exit_offset_min=10, risk="100"
    )
    decisions, _equity = _simulate_capital_allocation((zero_duration, competitor), policy)
    by_seq = {d.trade_sequence: d for d in decisions}
    assert by_seq[1].decision is PortfolioAllocationOutcome.ALLOCATED
    assert by_seq[2].decision is PortfolioAllocationOutcome.REJECTED
    assert by_seq[2].rejection_reason is PortfolioRejectionReason.INSUFFICIENT_AVAILABLE_CAPITAL


def test_real_overlapping_trades_produce_concurrent_open_positions() -> None:
    """Regression guard for the bug caught during real-data sanity
    checking: overlapping opportunities must genuinely coexist as open
    positions, never be opened-then-immediately-closed one at a time."""
    a = _opp(seq=1, symbol="TSLA", rank=1, entry_offset_min=0, exit_offset_min=2)
    b = _opp(seq=2, symbol="NVDA", rank=2, entry_offset_min=1, exit_offset_min=1)
    c = _opp(seq=3, symbol="GOOG", rank=3, entry_offset_min=1, exit_offset_min=3)
    decisions, equity = _simulate_capital_allocation((a, b, c), _POLICY)
    assert all(d.decision is PortfolioAllocationOutcome.ALLOCATED for d in decisions)
    max_concurrent = max(p.open_position_count for p in equity)
    assert max_concurrent >= 2


# --------------------------------------------------------------------------
# Accounting invariants
# --------------------------------------------------------------------------


def test_available_capital_stays_non_negative_for_profitable_trades() -> None:
    opps = tuple(
        _opp(seq=i, symbol="AAPL", entry_offset_min=i, exit_offset_min=i + 5, risk="333")
        for i in range(5)
    )
    _decisions, equity = _simulate_capital_allocation(opps, _POLICY)
    assert all(p.available_capital >= 0 for p in equity)


def test_available_capital_can_go_negative_when_a_realized_loss_exceeds_its_own_risk_amount() -> (
    None
):
    """A closed position's real net_pnl (which real M061 trades show can
    include slippage/cost beyond the position's own nominal risk_amount)
    is credited back in full, not clamped -- confirmed here as a
    deliberate domain decision, not a crash or a silently hidden loss."""
    policy = PortfolioCapitalPolicy(
        policy_id="X",
        version="1",
        initial_capital=Decimal("150"),
        currency="USD",
        max_concurrent_positions=10,
        max_capital_utilization_percent=Decimal("1"),
    )
    catastrophic_loss = _opp(
        seq=1, symbol="AAPL", entry_offset_min=0, exit_offset_min=5, risk="149", pnl="-500"
    )
    _decisions, equity = _simulate_capital_allocation((catastrophic_loss,), policy)
    assert equity[-1].available_capital < 0
    assert equity[-1].equity == policy.initial_capital + Decimal("-500.000000")


def test_occupied_capital_never_negative() -> None:
    opps = tuple(
        _opp(seq=i, symbol="AAPL", entry_offset_min=i, exit_offset_min=i + 5, risk="50")
        for i in range(5)
    )
    _decisions, equity = _simulate_capital_allocation(opps, _POLICY)
    assert all(p.occupied_capital >= 0 for p in equity)


def test_available_plus_occupied_equals_initial_plus_realized_pnl_at_every_point() -> None:
    """Full accounting reconciliation at every single observation: no
    capital is created or destroyed."""
    opps = tuple(
        _opp(seq=i, symbol="AAPL", entry_offset_min=i, exit_offset_min=i + 5, risk="50", pnl="3")
        for i in range(5)
    )
    _decisions, equity = _simulate_capital_allocation(opps, _POLICY)
    for point in equity:
        realized_so_far = point.equity - _POLICY.initial_capital
        assert point.available_capital + point.occupied_capital == (
            _POLICY.initial_capital + realized_so_far
        )


def test_rejected_trades_do_not_affect_realized_pnl() -> None:
    policy = PortfolioCapitalPolicy(
        policy_id="X",
        version="1",
        initial_capital=Decimal("100"),
        currency="USD",
        max_concurrent_positions=10,
        max_capital_utilization_percent=Decimal("1"),
    )
    allocated = _opp(
        seq=1, symbol="AAPL", entry_offset_min=0, exit_offset_min=5, risk="100", pnl="10"
    )
    rejected = _opp(
        seq=2, symbol="MSFT", entry_offset_min=1, exit_offset_min=3, risk="100", pnl="-999"
    )
    _decisions, equity = _simulate_capital_allocation((allocated, rejected), policy)
    assert equity[-1].equity == policy.initial_capital + Decimal("10.000000")


def test_no_duplicate_release_each_position_closes_exactly_once() -> None:
    opp = _opp(seq=1, symbol="AAPL", entry_offset_min=0, exit_offset_min=5)
    _decisions, equity = _simulate_capital_allocation((opp,), _POLICY)
    close_events = [p for p in equity if p.event_kind is PortfolioEventKind.CLOSE]
    assert len(close_events) == 1


# --------------------------------------------------------------------------
# Order independence
# --------------------------------------------------------------------------


def test_shuffled_input_order_produces_identical_canonical_result() -> None:
    opps = tuple(
        _opp(
            seq=i, symbol=s, rank=i, entry_offset_min=i % 4, exit_offset_min=(i % 4) + 3, risk="80"
        )
        for i, s in enumerate(("AAPL", "MSFT", "GOOG", "AMZN", "NVDA", "TSLA"), start=1)
    )
    forward = _simulate_capital_allocation(opps, _POLICY)
    reversed_order = _simulate_capital_allocation(tuple(reversed(opps)), _POLICY)
    forward_by_seq = {d.trade_sequence: d.decision for d in forward[0]}
    reversed_by_seq = {d.trade_sequence: d.decision for d in reversed_order[0]}
    assert forward_by_seq == reversed_by_seq


# --------------------------------------------------------------------------
# Future-data firewall
# --------------------------------------------------------------------------


def test_mutating_a_later_opportunity_does_not_change_earlier_decisions() -> None:
    policy = PortfolioCapitalPolicy(
        policy_id="X",
        version="1",
        initial_capital=Decimal("150"),
        currency="USD",
        max_concurrent_positions=10,
        max_capital_utilization_percent=Decimal("1"),
    )
    early = _opp(seq=1, symbol="AAPL", entry_offset_min=0, exit_offset_min=5, risk="100")
    late_original = _opp(
        seq=2, symbol="MSFT", entry_offset_min=100, exit_offset_min=105, risk="100"
    )
    late_mutated = _opp(
        seq=2, symbol="MSFT", entry_offset_min=100, exit_offset_min=105, risk="149", pnl="-500"
    )
    decisions_original, equity_original = _simulate_capital_allocation(
        (early, late_original), policy
    )
    decisions_mutated, equity_mutated = _simulate_capital_allocation((early, late_mutated), policy)
    early_original = next(d for d in decisions_original if d.trade_sequence == 1)
    early_after_mutation = next(d for d in decisions_mutated if d.trade_sequence == 1)
    assert early_original == early_after_mutation
    assert equity_original[0] == equity_mutated[0]
    assert equity_original[1] == equity_mutated[1]


# --------------------------------------------------------------------------
# Drawdown
# --------------------------------------------------------------------------


def test_max_drawdown_of_monotonic_gains_is_zero() -> None:
    points = (
        PortfolioEquityObservation(
            sequence_index=1,
            event_timestamp=_T0,
            event_kind=PortfolioEventKind.CLOSE,
            equity=Decimal("1100"),
            occupied_capital=Decimal("0"),
            available_capital=Decimal("1100"),
            open_position_count=0,
        ),
        PortfolioEquityObservation(
            sequence_index=2,
            event_timestamp=_T0 + timedelta(minutes=1),
            event_kind=PortfolioEventKind.CLOSE,
            equity=Decimal("1200"),
            occupied_capital=Decimal("0"),
            available_capital=Decimal("1200"),
            open_position_count=0,
        ),
    )
    assert _max_drawdown_from_equity_curve(points, Decimal("1000")) == Decimal("0.000000")


def test_max_drawdown_peak_to_trough_not_naive_sum() -> None:
    """Overlapping losing positions produce a portfolio-level drawdown
    computed from the true equity sequence -- never a naive sum of
    unrelated individual-trade drawdowns (mission Phase 14/25)."""
    points = (
        PortfolioEquityObservation(
            sequence_index=1,
            event_timestamp=_T0,
            event_kind=PortfolioEventKind.CLOSE,
            equity=Decimal("1500"),
            occupied_capital=Decimal("0"),
            available_capital=Decimal("1500"),
            open_position_count=0,
        ),
        PortfolioEquityObservation(
            sequence_index=2,
            event_timestamp=_T0 + timedelta(minutes=1),
            event_kind=PortfolioEventKind.CLOSE,
            equity=Decimal("1000"),
            occupied_capital=Decimal("0"),
            available_capital=Decimal("1000"),
            open_position_count=0,
        ),
        PortfolioEquityObservation(
            sequence_index=3,
            event_timestamp=_T0 + timedelta(minutes=2),
            event_kind=PortfolioEventKind.CLOSE,
            equity=Decimal("1300"),
            occupied_capital=Decimal("0"),
            available_capital=Decimal("1300"),
            open_position_count=0,
        ),
    )
    # peak 1500 -> trough 1000 -> drawdown 500; the later recovery to
    # 1300 must not reduce the recorded max drawdown.
    assert _max_drawdown_from_equity_curve(points, Decimal("1000")) == Decimal("500.000000")


def test_overlapping_losses_produce_correct_simultaneous_drawdown() -> None:
    """Two overlapping losing positions closing separately must combine
    into one coherent portfolio drawdown, not two independent ones."""
    policy = PortfolioCapitalPolicy(
        policy_id="X",
        version="1",
        initial_capital=Decimal("1000"),
        currency="USD",
        max_concurrent_positions=10,
        max_capital_utilization_percent=Decimal("1"),
    )
    loss_a = _opp(
        seq=1, symbol="AAPL", entry_offset_min=0, exit_offset_min=10, risk="100", pnl="-80"
    )
    loss_b = _opp(
        seq=2, symbol="MSFT", entry_offset_min=1, exit_offset_min=5, risk="100", pnl="-60"
    )
    _decisions, equity = _simulate_capital_allocation((loss_a, loss_b), policy)
    max_dd = _max_drawdown_from_equity_curve(equity, policy.initial_capital)
    # Both losses are realized by the end -- total drawdown must reflect
    # the full combined loss (-140), not just the larger individual one.
    assert max_dd == Decimal("140.000000")


# --------------------------------------------------------------------------
# Capital sensitivity (descriptive only, never alters canonical result)
# --------------------------------------------------------------------------


def test_capital_sensitivity_view_reduced_capital_can_increase_rejections() -> None:
    opps = tuple(
        _opp(seq=i, symbol="AAPL", entry_offset_min=0, exit_offset_min=5, risk="60")
        for i in range(1, 4)
    )
    canonical_policy = PortfolioCapitalPolicy(
        policy_id="X",
        version="1",
        initial_capital=Decimal("200"),
        currency="USD",
        max_concurrent_positions=10,
        max_capital_utilization_percent=Decimal("1"),
    )
    reduced_policy = PortfolioCapitalPolicy(
        policy_id="X-REDUCED",
        version="1",
        initial_capital=Decimal("50"),
        currency="USD",
        max_concurrent_positions=10,
        max_capital_utilization_percent=Decimal("1"),
    )
    canonical_view = _capital_sensitivity_view(
        CapitalSensitivityLabel.CANONICAL, opps, canonical_policy
    )
    reduced_view = _capital_sensitivity_view(
        CapitalSensitivityLabel.REDUCED_CAPITAL, opps, reduced_policy
    )
    assert reduced_view.rejected_count >= canonical_view.rejected_count
