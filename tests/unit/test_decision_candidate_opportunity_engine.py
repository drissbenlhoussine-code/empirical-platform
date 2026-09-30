"""MILESTONE-090 -- the Opportunity Engine domain: pure-function unit tests.

Every test here proves ONE deterministic rule with hand-computed expected values -- no fixture
magic, so a reader can verify the arithmetic by hand against the assertion.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

import pytest

from empirical_platform.decision_candidate.market_data import (
    Bar,
    BarInterval,
    Instrument,
    ObservationWindow,
)
from empirical_platform.decision_candidate.opportunity_engine import (
    ALLOWED_OPPORTUNITY_TRANSITIONS,
    AssetEvidence,
    MarketSessionState,
    OpportunityDecision,
    OpportunityEnginePolicy,
    OpportunityStatus,
    OwnerOpportunityAction,
    QuoteEvidence,
    RejectionReason,
    StructureMeasurements,
    TradePlanGeometry,
    TradingOpportunity,
    asset_eligibility_refusal,
    bar_evidence_refusal,
    build_trade_plan_geometry,
    entry_moved_refusal,
    evaluate_structure,
    is_opportunity_transition_allowed,
    liquidity_refusal,
    mandatory_liquidation_at,
    market_session_state,
    opportunity_quality,
    opportunity_valid_until,
    plan_geometry_refusal,
    position_size,
    price_bounds_refusal,
    rank_sort_key,
    reward_risk_refusal,
    session_permits_actionable,
)
from empirical_platform.decision_candidate.paper_execution import (
    ExecutionPolicy,
)
from empirical_platform.shared.brokerage.paper_time import BoundedInstant

_SYMBOL = "AAPL"


def _policy(**overrides: object) -> OpportunityEnginePolicy:
    defaults: dict[str, object] = {
        "policy_version": "M090-V1",
        "structure_lookback_bars": 5,
        "minimum_recent_share_volume": 1000,
        "minimum_reward_risk_ratio": Decimal("2"),
        "maximum_loss_per_trade": Decimal("100"),
        "top_n": 5,
        "entry_tolerance_percent": Decimal("0.5"),
        "opportunity_validity_seconds": 300,
    }
    defaults.update(overrides)
    return OpportunityEnginePolicy(**defaults)  # type: ignore[arg-type]


def _bar(*, minute: int, o: str, h: str, low: str, c: str, v: int) -> Bar:
    return Bar(
        instrument=Instrument(_SYMBOL),
        interval=BarInterval.ONE_MINUTE,
        timestamp=datetime(2026, 6, 10, 14, minute, tzinfo=UTC),
        open=Decimal(o),
        high=Decimal(h),
        low=Decimal(low),
        close=Decimal(c),
        volume=v,
    )


def _breakout_window() -> ObservationWindow:
    """5 reference bars in a bounded range [99, 101], rising lows, then a breakout bar."""
    bars = (
        _bar(minute=0, o="100.00", h="100.50", low="99.00", c="100.00", v=1000),
        _bar(minute=1, o="100.00", h="100.60", low="99.20", c="100.20", v=1000),
        _bar(minute=2, o="100.20", h="100.70", low="99.40", c="100.30", v=1000),
        _bar(minute=3, o="100.30", h="100.80", low="99.60", c="100.40", v=1000),
        _bar(minute=4, o="100.40", h="101.00", low="99.80", c="100.50", v=1000),
        # breakout: closes above 101.00 (the reference range high), low stays above the
        # reference trough (99.00), volume exceeds the 1000-share reference average.
        _bar(minute=5, o="100.50", h="101.80", low="100.10", c="101.50", v=2500),
    )
    return ObservationWindow(bars=bars)


def _no_breakout_window() -> ObservationWindow:
    bars = (
        _bar(minute=0, o="100.00", h="100.50", low="99.00", c="100.00", v=1000),
        _bar(minute=1, o="100.00", h="100.60", low="99.20", c="100.20", v=1000),
        _bar(minute=2, o="100.20", h="100.70", low="99.40", c="100.30", v=1000),
        _bar(minute=3, o="100.30", h="100.80", low="99.60", c="100.40", v=1000),
        _bar(minute=4, o="100.40", h="101.00", low="99.80", c="100.50", v=1000),
        # no breakout: closes BELOW the reference range high (101.00).
        _bar(minute=5, o="100.50", h="100.90", low="100.10", c="100.60", v=900),
    )
    return ObservationWindow(bars=bars)


# ---------------------------------------------------------------------------
# A. Data quality
# ---------------------------------------------------------------------------


def test_a_stale_quote_is_rejected() -> None:
    execution_policy = ExecutionPolicy(
        configuration_governance_id="CFG-090-0001",
        configuration_version=1,
        maximum_notional=Decimal("2000"),
        quote_maximum_age_seconds=30,
        maximum_spread_percent=Decimal("1"),
        watchlist=(_SYMBOL,),
        prohibited_instruments=(),
        earliest_entry_time=time(10, 0),
        latest_entry_time=time(15, 30),
        operator_timezone="UTC",
    )
    now = datetime(2026, 6, 10, 14, 0, tzinfo=UTC)
    broker_now = BoundedInstant(earliest=now, latest=now)
    stale = QuoteEvidence(
        bid=Decimal("100.00"),
        ask=Decimal("100.05"),
        captured_at=now - timedelta(seconds=120),
        source="alpaca-iex",
    )
    from empirical_platform.decision_candidate.opportunity_engine import quote_quality_refusal

    assert (
        quote_quality_refusal(quote=stale, execution_policy=execution_policy, broker_now=broker_now)
        is RejectionReason.QUOTE_STALE_OR_INVALID
    )


def test_missing_bars_are_rejected() -> None:
    assert bar_evidence_refusal(None, policy=_policy()) is RejectionReason.STALE_OR_MISSING_BARS


def test_too_few_reference_bars_are_rejected() -> None:
    thin = ObservationWindow(
        bars=(
            _bar(minute=0, o="100", h="100.5", low="99.5", c="100.2", v=1000),
            _bar(minute=1, o="100.2", h="100.6", low="99.8", c="100.3", v=1000),
        )
    )
    assert (
        bar_evidence_refusal(thin, policy=_policy(structure_lookback_bars=5))
        is RejectionReason.STALE_OR_MISSING_BARS
    )


def test_a_crossed_quote_is_rejected_by_the_reused_m085_gate() -> None:
    execution_policy = ExecutionPolicy(
        configuration_governance_id="CFG-090-0001",
        configuration_version=1,
        maximum_notional=Decimal("2000"),
        quote_maximum_age_seconds=30,
        maximum_spread_percent=Decimal("1"),
        watchlist=(_SYMBOL,),
        prohibited_instruments=(),
        earliest_entry_time=time(10, 0),
        latest_entry_time=time(15, 30),
        operator_timezone="UTC",
    )
    now = datetime(2026, 6, 10, 14, 0, tzinfo=UTC)
    broker_now = BoundedInstant(earliest=now, latest=now)
    from empirical_platform.decision_candidate.opportunity_engine import quote_quality_refusal

    crossed = QuoteEvidence(bid=Decimal("101"), ask=Decimal("100"), captured_at=now, source="x")
    assert (
        quote_quality_refusal(
            quote=crossed, execution_policy=execution_policy, broker_now=broker_now
        )
        is RejectionReason.QUOTE_STALE_OR_INVALID
    )


def test_bad_timestamps_are_rejected_by_observation_window_itself() -> None:
    """ObservationWindow (M057) already refuses non-chronological bars -- reused, not
    reimplemented."""
    with pytest.raises(ValueError, match="strictly ordered"):
        ObservationWindow(
            bars=(
                _bar(minute=1, o="100", h="100.5", low="99.5", c="100.2", v=1000),
                _bar(minute=0, o="100.2", h="100.6", low="99.8", c="100.3", v=1000),
            )
        )


# ---------------------------------------------------------------------------
# B. Liquidity / spread
# ---------------------------------------------------------------------------


def test_thin_recent_volume_is_rejected() -> None:
    window = _breakout_window()
    assert (
        liquidity_refusal(window, policy=_policy(minimum_recent_share_volume=10_000))
        is RejectionReason.INSUFFICIENT_LIQUIDITY
    )


def test_acceptable_liquidity_passes() -> None:
    window = _breakout_window()
    assert liquidity_refusal(window, policy=_policy(minimum_recent_share_volume=1000)) is None


def test_insufficient_bar_count_is_insufficient_evidence_not_illiquid() -> None:
    window = ObservationWindow(
        bars=(
            _bar(minute=0, o="100", h="100.5", low="99.5", c="100.2", v=1000),
            _bar(minute=1, o="100.2", h="100.6", low="99.8", c="100.3", v=1000),
        )
    )
    assert (
        liquidity_refusal(window, policy=_policy(structure_lookback_bars=5))
        is RejectionReason.INSUFFICIENT_EVIDENCE
    )


def test_wide_spread_is_rejected_by_the_reused_m085_gate() -> None:
    execution_policy = ExecutionPolicy(
        configuration_governance_id="CFG-090-0001",
        configuration_version=1,
        maximum_notional=Decimal("2000"),
        quote_maximum_age_seconds=30,
        maximum_spread_percent=Decimal("0.1"),
        watchlist=(_SYMBOL,),
        prohibited_instruments=(),
        earliest_entry_time=time(10, 0),
        latest_entry_time=time(15, 30),
        operator_timezone="UTC",
    )
    now = datetime(2026, 6, 10, 14, 0, tzinfo=UTC)
    broker_now = BoundedInstant(earliest=now, latest=now)
    from empirical_platform.decision_candidate.opportunity_engine import quote_quality_refusal

    wide = QuoteEvidence(bid=Decimal("100"), ask=Decimal("101"), captured_at=now, source="x")
    assert (
        quote_quality_refusal(quote=wide, execution_policy=execution_policy, broker_now=broker_now)
        is RejectionReason.QUOTE_STALE_OR_INVALID
    )


# ---------------------------------------------------------------------------
# C. Signal / structure
# ---------------------------------------------------------------------------


def test_a_valid_breakout_pattern_is_accepted() -> None:
    evaluation = evaluate_structure(_breakout_window(), lookback_bars=5)
    assert evaluation.is_long_candidate
    assert evaluation.measurements.range_high == Decimal("101.00")
    assert evaluation.measurements.current_close == Decimal("101.50")


def test_a_broken_pattern_close_not_above_range_high_is_rejected() -> None:
    evaluation = evaluate_structure(_no_breakout_window(), lookback_bars=5)
    assert not evaluation.is_long_candidate


def test_structure_requires_enough_reference_bars() -> None:
    thin = ObservationWindow(
        bars=(
            _bar(minute=0, o="100", h="100.5", low="99.5", c="100.2", v=1000),
            _bar(minute=1, o="100.2", h="100.6", low="99.8", c="100.3", v=1000),
        )
    )
    with pytest.raises(ValueError, match="reference bars"):
        evaluate_structure(thin, lookback_bars=5)


def test_the_same_window_and_lookback_always_produce_the_same_evaluation() -> None:
    """D. Determinism -- same evidence + same policy = same opportunity."""
    window = _breakout_window()
    first = evaluate_structure(window, lookback_bars=5)
    second = evaluate_structure(window, lookback_bars=5)
    assert first == second


# ---------------------------------------------------------------------------
# D. Risk
# ---------------------------------------------------------------------------


def test_stop_greater_than_or_equal_to_entry_is_refused() -> None:
    assert (
        plan_geometry_refusal(entry_price=Decimal("100"), stop_price=Decimal("100"))
        is RejectionReason.STOP_INVALID
    )
    assert (
        plan_geometry_refusal(entry_price=Decimal("100"), stop_price=Decimal("101"))
        is RejectionReason.STOP_INVALID
    )
    assert plan_geometry_refusal(entry_price=Decimal("100"), stop_price=Decimal("99")) is None


def test_trade_plan_geometry_computes_the_exact_documented_arithmetic() -> None:
    structure = StructureMeasurements(
        current_close=Decimal("101.50"),
        current_volume=2500,
        range_high=Decimal("101.00"),
        range_low=Decimal("99.00"),
        prior_swing_low=Decimal("100.10"),
        reference_average_volume=Decimal("1000"),
    )
    policy = _policy(minimum_reward_risk_ratio=Decimal("2"))
    geometry = build_trade_plan_geometry(
        entry_price=Decimal("101.50"), structure=structure, policy=policy
    )
    assert geometry is not None
    assert geometry.entry_price == Decimal("101.50")
    assert geometry.stop_price == Decimal("100.10")
    assert geometry.risk_per_share == Decimal("1.40")
    # target = entry + 2 * risk = 101.50 + 2.80 = 104.30
    assert geometry.target_price == Decimal("104.30")
    assert geometry.reward_per_share == Decimal("2.80")
    assert geometry.reward_risk_ratio == Decimal("2.00")


def test_trade_plan_geometry_refuses_when_the_structural_stop_is_not_below_entry() -> None:
    structure = StructureMeasurements(
        current_close=Decimal("100.00"),
        current_volume=1000,
        range_high=Decimal("101.00"),
        range_low=Decimal("99.00"),
        prior_swing_low=Decimal("100.50"),  # ABOVE the entry price below
        reference_average_volume=Decimal("1000"),
    )
    geometry = build_trade_plan_geometry(
        entry_price=Decimal("100.00"), structure=structure, policy=_policy()
    )
    assert geometry is None


def test_reward_risk_below_policy_floor_is_rejected() -> None:
    geometry = TradePlanGeometry(
        entry_price=Decimal("100"),
        stop_price=Decimal("99"),
        target_price=Decimal("101"),
        risk_per_share=Decimal("1"),
        reward_per_share=Decimal("1"),
        reward_risk_ratio=Decimal("1.00"),
    )
    assert (
        reward_risk_refusal(geometry, minimum_reward_risk_ratio=Decimal("2"))
        is RejectionReason.REWARD_RISK_TOO_LOW
    )


def test_quantity_is_the_minimum_of_every_applicable_cap() -> None:
    # risk cap: 100 / 1.40 = 71.4 -> 71 shares
    # trade cap: 2000 / 101.50 = 19.7 -> 19 shares  (the binding constraint)
    # percent cap: (10000 * 5% ) / 101.50 = 4.9 -> 4 shares (tighter still)
    quantity = position_size(
        entry_price=Decimal("101.50"),
        stop_price=Decimal("100.10"),
        maximum_loss=Decimal("100"),
        maximum_capital_per_trade=Decimal("2000"),
        maximum_percent_per_trade=Decimal("5"),
        deployable_capital=Decimal("10000"),
    )
    assert quantity == 4


def test_quantity_less_than_one_share_is_possible_and_must_be_rejected_by_the_caller() -> None:
    quantity = position_size(
        entry_price=Decimal("101.50"),
        stop_price=Decimal("100.10"),
        maximum_loss=Decimal("1"),  # far too small a risk budget for this geometry
        maximum_capital_per_trade=Decimal("2000"),
        maximum_percent_per_trade=Decimal("50"),
        deployable_capital=Decimal("10000"),
    )
    assert quantity == 0


def test_position_size_never_uses_leverage() -> None:
    """No combination of inputs can produce a notional exceeding deployable capital."""
    quantity = position_size(
        entry_price=Decimal("10"),
        stop_price=Decimal("9.99"),  # tiny risk-per-share, would demand huge size by risk alone
        maximum_loss=Decimal("100000"),  # deliberately huge
        maximum_capital_per_trade=Decimal("500"),
        maximum_percent_per_trade=Decimal("100"),
        deployable_capital=Decimal("500"),
    )
    notional = Decimal(quantity) * Decimal("10")
    assert notional <= Decimal("500")


# ---------------------------------------------------------------------------
# E. Session
# ---------------------------------------------------------------------------


def test_closed_market_is_market_closed_and_not_actionable() -> None:
    now = datetime(2026, 6, 10, 14, 0, tzinfo=UTC)
    state = market_session_state(
        is_open=False,
        broker_now=BoundedInstant(earliest=now, latest=now),
        earliest_entry_time=time(10, 0),
        latest_entry_time=time(15, 30),
        operator_timezone="UTC",
    )
    assert state is MarketSessionState.MARKET_CLOSED
    assert not session_permits_actionable(state)


def test_before_the_entry_window_is_premarket_research_and_not_actionable() -> None:
    now = datetime(2026, 6, 10, 9, 0, tzinfo=UTC)
    state = market_session_state(
        is_open=True,
        broker_now=BoundedInstant(earliest=now, latest=now),
        earliest_entry_time=time(10, 0),
        latest_entry_time=time(15, 30),
        operator_timezone="UTC",
    )
    assert state is MarketSessionState.PREMARKET_RESEARCH
    assert not session_permits_actionable(state)


def test_after_the_entry_window_is_closed_and_not_actionable() -> None:
    now = datetime(2026, 6, 10, 16, 0, tzinfo=UTC)
    state = market_session_state(
        is_open=True,
        broker_now=BoundedInstant(earliest=now, latest=now),
        earliest_entry_time=time(10, 0),
        latest_entry_time=time(15, 30),
        operator_timezone="UTC",
    )
    assert state is MarketSessionState.ENTRY_WINDOW_CLOSED
    assert not session_permits_actionable(state)


def test_inside_the_entry_window_is_the_only_actionable_state() -> None:
    now = datetime(2026, 6, 10, 14, 0, tzinfo=UTC)
    state = market_session_state(
        is_open=True,
        broker_now=BoundedInstant(earliest=now, latest=now),
        earliest_entry_time=time(10, 0),
        latest_entry_time=time(15, 30),
        operator_timezone="UTC",
    )
    assert state is MarketSessionState.REGULAR_SESSION
    assert session_permits_actionable(state)


def test_mandatory_exit_is_always_present_and_derived_from_the_shared_liquidation_time() -> None:
    result = mandatory_liquidation_at(
        session_date=date(2026, 6, 10), liquidation_time=time(15, 45), operator_timezone="UTC"
    )
    assert result == datetime(2026, 6, 10, 15, 45, tzinfo=UTC)


def test_opportunity_validity_never_exceeds_the_mandatory_liquidation_instant() -> None:
    generated_at = datetime(2026, 6, 10, 15, 40, tzinfo=UTC)
    liquidation_at = datetime(2026, 6, 10, 15, 45, tzinfo=UTC)
    policy = _policy(opportunity_validity_seconds=3600)  # would normally extend an hour
    valid_until = opportunity_valid_until(
        generated_at=generated_at, policy=policy, liquidation_at=liquidation_at
    )
    assert valid_until == liquidation_at  # capped, never past the mandatory exit


# ---------------------------------------------------------------------------
# F. Determinism (additional cases beyond structure, above)
# ---------------------------------------------------------------------------


def test_position_size_is_deterministic() -> None:
    kwargs = dict(
        entry_price=Decimal("101.50"),
        stop_price=Decimal("100.10"),
        maximum_loss=Decimal("100"),
        maximum_capital_per_trade=Decimal("2000"),
        maximum_percent_per_trade=Decimal("5"),
        deployable_capital=Decimal("10000"),
    )
    assert position_size(**kwargs) == position_size(**kwargs)  # type: ignore[arg-type]


def test_opportunity_quality_is_deterministic_and_bounded() -> None:
    structure = StructureMeasurements(
        current_close=Decimal("101.50"),
        current_volume=2500,
        range_high=Decimal("101.00"),
        range_low=Decimal("99.00"),
        prior_swing_low=Decimal("100.10"),
        reference_average_volume=Decimal("1000"),
    )
    geometry = TradePlanGeometry(
        entry_price=Decimal("101.50"),
        stop_price=Decimal("100.10"),
        target_price=Decimal("104.30"),
        risk_per_share=Decimal("1.40"),
        reward_per_share=Decimal("2.80"),
        reward_risk_ratio=Decimal("2.00"),
    )
    kwargs = dict(
        spread_percent=Decimal("0.05"),
        maximum_spread_percent=Decimal("1"),
        recent_volume=2500,
        minimum_recent_share_volume=1000,
        structure=structure,
        geometry=geometry,
        minimum_reward_risk_ratio=Decimal("2"),
        quote_age_seconds=Decimal("3"),
        maximum_quote_age_seconds=30,
    )
    first = opportunity_quality(**kwargs)  # type: ignore[arg-type]
    second = opportunity_quality(**kwargs)  # type: ignore[arg-type]
    assert first == second
    assert Decimal(0) <= first <= Decimal(100)


def test_ranking_never_reorders_a_rejected_opportunity_ahead_of_an_actionable_one() -> None:
    """Hard fail first, rank survivors second (Phase 14): rank_sort_key over a mix of statuses
    is defined, but the usecase layer must never rank a REJECTED opportunity into the top-N --
    that is proven at the usecase level; here we confirm no-score sorts last among ties."""
    now = datetime(2026, 6, 10, 14, 0, tzinfo=UTC)
    scored = TradingOpportunity(
        opportunity_id="OPP-1",
        policy_fingerprint="f" * 64,
        symbol="AAPL",
        generated_at=now,
        expires_at=now + timedelta(minutes=5),
        evidence_as_of=now,
        session=MarketSessionState.REGULAR_SESSION,
        bid=Decimal("101"),
        ask=Decimal("101.05"),
        spread_percent=Decimal("0.05"),
        entry_price=Decimal("101.50"),
        stop_price=Decimal("100.10"),
        target_price=Decimal("104.30"),
        risk_per_share=Decimal("1.40"),
        reward_per_share=Decimal("2.80"),
        reward_risk_ratio=Decimal("2.00"),
        quantity=4,
        notional=Decimal("406.00"),
        maximum_loss=Decimal("5.60"),
        mandatory_liquidation_at=now + timedelta(hours=1),
        structure_model_id="X",
        structure_model_version="1",
        evidence=("breakout",),
        quality_score=Decimal("80.0"),
        quality_model_id="X",
        quality_model_version="1",
        rejection_reasons=(),
        status=OpportunityStatus.ACTIONABLE,
    )
    unscored = TradingOpportunity(
        opportunity_id="OPP-2",
        policy_fingerprint="f" * 64,
        symbol="ZZZZ",
        generated_at=now,
        expires_at=now + timedelta(minutes=5),
        evidence_as_of=now,
        session=MarketSessionState.REGULAR_SESSION,
        bid=None,
        ask=None,
        spread_percent=None,
        entry_price=None,
        stop_price=None,
        target_price=None,
        risk_per_share=None,
        reward_per_share=None,
        reward_risk_ratio=None,
        quantity=None,
        notional=None,
        maximum_loss=None,
        mandatory_liquidation_at=None,
        structure_model_id="X",
        structure_model_version="1",
        evidence=(),
        quality_score=None,
        quality_model_id="X",
        quality_model_version="1",
        rejection_reasons=(RejectionReason.INSUFFICIENT_LIQUIDITY,),
        status=OpportunityStatus.REJECTED,
    )
    ordered = sorted((unscored, scored), key=rank_sort_key)
    assert ordered[0] is scored


# ---------------------------------------------------------------------------
# G. Look-ahead
# ---------------------------------------------------------------------------


def test_the_evaluation_bar_cannot_influence_its_own_reference_measurements() -> None:
    """Future bars cannot affect the current decision: the evaluation bar's own extreme values
    (a huge high/low/volume) must not leak into the reference range/average this decision is
    judged against -- ObservationWindow's own split (`reference_bars` excludes the last bar)
    is the entire defense, proven directly here."""
    bars = (
        _bar(minute=0, o="100.00", h="100.50", low="99.00", c="100.00", v=1000),
        _bar(minute=1, o="100.00", h="100.60", low="99.20", c="100.20", v=1000),
        _bar(minute=2, o="100.20", h="100.70", low="99.40", c="100.30", v=1000),
        _bar(minute=3, o="100.30", h="100.80", low="99.60", c="100.40", v=1000),
        _bar(minute=4, o="100.40", h="101.00", low="99.80", c="100.50", v=1000),
        # An extreme evaluation bar: if it leaked into the reference range, range_high would
        # be 500, not 101.00.
        _bar(minute=5, o="100.50", h="500.00", low="100.10", c="101.50", v=999999),
    )
    window = ObservationWindow(bars=bars)
    evaluation = evaluate_structure(window, lookback_bars=5)
    assert evaluation.measurements.range_high == Decimal("101.00")
    assert evaluation.measurements.reference_average_volume == Decimal("1000")


def test_reference_bars_never_include_the_evaluation_bar() -> None:
    window = _breakout_window()
    assert window.evaluation_bar not in window.reference_bars
    assert len(window.reference_bars) == len(window.bars) - 1


# ---------------------------------------------------------------------------
# H. Owner gate / statuses
# ---------------------------------------------------------------------------


def test_actionable_status_requires_every_hard_field_present() -> None:
    now = datetime(2026, 6, 10, 14, 0, tzinfo=UTC)
    with pytest.raises(ValueError, match="entry/stop/target/quantity"):
        TradingOpportunity(
            opportunity_id="OPP-1",
            policy_fingerprint="f" * 64,
            symbol="AAPL",
            generated_at=now,
            expires_at=now + timedelta(minutes=5),
            evidence_as_of=now,
            session=MarketSessionState.REGULAR_SESSION,
            bid=Decimal("101"),
            ask=Decimal("101.05"),
            spread_percent=Decimal("0.05"),
            entry_price=None,  # missing -- must refuse ACTIONABLE
            stop_price=None,
            target_price=None,
            risk_per_share=None,
            reward_per_share=None,
            reward_risk_ratio=None,
            quantity=None,
            notional=None,
            maximum_loss=None,
            mandatory_liquidation_at=None,
            structure_model_id="X",
            structure_model_version="1",
            evidence=(),
            quality_score=None,
            quality_model_id="X",
            quality_model_version="1",
            rejection_reasons=(),
            status=OpportunityStatus.ACTIONABLE,
        )


def test_a_rejected_opportunity_must_carry_a_reason() -> None:
    now = datetime(2026, 6, 10, 14, 0, tzinfo=UTC)
    with pytest.raises(ValueError, match="at least one rejection reason"):
        TradingOpportunity(
            opportunity_id="OPP-1",
            policy_fingerprint="f" * 64,
            symbol="AAPL",
            generated_at=now,
            expires_at=now + timedelta(minutes=5),
            evidence_as_of=now,
            session=MarketSessionState.REGULAR_SESSION,
            bid=None,
            ask=None,
            spread_percent=None,
            entry_price=None,
            stop_price=None,
            target_price=None,
            risk_per_share=None,
            reward_per_share=None,
            reward_risk_ratio=None,
            quantity=None,
            notional=None,
            maximum_loss=None,
            mandatory_liquidation_at=None,
            structure_model_id="X",
            structure_model_version="1",
            evidence=(),
            quality_score=None,
            quality_model_id="X",
            quality_model_version="1",
            rejection_reasons=(),  # empty -- must refuse REJECTED
            status=OpportunityStatus.REJECTED,
        )


def test_status_transitions_are_closed_and_invalidated_is_terminal() -> None:
    assert is_opportunity_transition_allowed(
        OpportunityStatus.CANDIDATE, OpportunityStatus.ACTIONABLE
    )
    assert is_opportunity_transition_allowed(
        OpportunityStatus.ACTIONABLE, OpportunityStatus.OWNER_APPROVED
    )
    assert not is_opportunity_transition_allowed(
        OpportunityStatus.CANDIDATE, OpportunityStatus.OWNER_APPROVED
    )  # cannot skip ACTIONABLE
    assert not is_opportunity_transition_allowed(
        OpportunityStatus.INVALIDATED, OpportunityStatus.ACTIONABLE
    )  # terminal
    assert ALLOWED_OPPORTUNITY_TRANSITIONS[OpportunityStatus.OWNER_APPROVED] == frozenset()
    assert ALLOWED_OPPORTUNITY_TRANSITIONS[OpportunityStatus.OWNER_IGNORED] == frozenset()
    assert ALLOWED_OPPORTUNITY_TRANSITIONS[OpportunityStatus.REJECTED] == frozenset()


def test_an_entry_moved_outside_tolerance_invalidates() -> None:
    policy = _policy(entry_tolerance_percent=Decimal("0.5"))
    # 1% move against a 0.5% tolerance.
    assert (
        entry_moved_refusal(
            evidence_entry_price=Decimal("100.00"),
            current_price=Decimal("101.00"),
            policy=policy,
        )
        is RejectionReason.ENTRY_MOVED_OUTSIDE_TOLERANCE
    )
    # A FAVORABLE move outside tolerance is refused too -- the Owner approved exact terms.
    assert (
        entry_moved_refusal(
            evidence_entry_price=Decimal("100.00"),
            current_price=Decimal("99.00"),
            policy=policy,
        )
        is RejectionReason.ENTRY_MOVED_OUTSIDE_TOLERANCE
    )
    # Within tolerance: fine.
    assert (
        entry_moved_refusal(
            evidence_entry_price=Decimal("100.00"),
            current_price=Decimal("100.30"),
            policy=policy,
        )
        is None
    )


def test_the_owner_decision_object_requires_an_owner_action() -> None:
    now = datetime(2026, 6, 10, 14, 0, tzinfo=UTC)
    decision = OpportunityDecision(
        decision_id="DEC-1",
        opportunity_id="OPP-1",
        action=OwnerOpportunityAction.APPROVE,
        decided_by="owner",
        decided_at=now,
    )
    assert decision.action is OwnerOpportunityAction.APPROVE
    with pytest.raises(ValueError, match="non-empty string"):
        OpportunityDecision(
            decision_id="",
            opportunity_id="OPP-1",
            action=OwnerOpportunityAction.APPROVE,
            decided_by="owner",
            decided_at=now,
        )


# ---------------------------------------------------------------------------
# Universe / asset eligibility (Phase 3)
# ---------------------------------------------------------------------------


def test_a_symbol_outside_the_watchlist_is_rejected_before_any_other_check() -> None:
    assert (
        asset_eligibility_refusal(
            asset=None,
            symbol="TSLA",
            watchlist=("AAPL",),
            prohibited_instruments=(),
            permitted_markets=(),
        )
        is RejectionReason.NOT_ON_WATCHLIST
    )


def test_a_prohibited_instrument_is_rejected_even_if_watchlisted() -> None:
    assert (
        asset_eligibility_refusal(
            asset=None,
            symbol="AAPL",
            watchlist=("AAPL",),
            prohibited_instruments=("AAPL",),
            permitted_markets=(),
        )
        is RejectionReason.PROHIBITED_INSTRUMENT
    )


def test_a_non_tradable_or_non_active_asset_is_rejected() -> None:
    inactive = AssetEvidence(symbol="AAPL", tradable=True, status="inactive", exchange="NASDAQ")
    assert (
        asset_eligibility_refusal(
            asset=inactive,
            symbol="AAPL",
            watchlist=("AAPL",),
            prohibited_instruments=(),
            permitted_markets=(),
        )
        is RejectionReason.NOT_ACTIVE
    )
    not_tradable = AssetEvidence(symbol="AAPL", tradable=False, status="active", exchange="NASDAQ")
    assert (
        asset_eligibility_refusal(
            asset=not_tradable,
            symbol="AAPL",
            watchlist=("AAPL",),
            prohibited_instruments=(),
            permitted_markets=(),
        )
        is RejectionReason.NOT_TRADABLE
    )


def test_a_symbol_off_the_approved_market_is_rejected() -> None:
    otc = AssetEvidence(symbol="AAPL", tradable=True, status="active", exchange="OTC")
    assert (
        asset_eligibility_refusal(
            asset=otc,
            symbol="AAPL",
            watchlist=("AAPL",),
            prohibited_instruments=(),
            permitted_markets=("NASDAQ", "NYSE"),
        )
        is RejectionReason.NOT_ON_APPROVED_MARKET
    )


def test_price_bounds_reject_low_priced_instruments() -> None:
    assert (
        price_bounds_refusal(price=Decimal("2.00"), minimum_price=Decimal("5"), maximum_price=None)
        is RejectionReason.PRICE_TOO_LOW
    )
    assert (
        price_bounds_refusal(
            price=Decimal("2000"), minimum_price=Decimal("5"), maximum_price=Decimal("1000")
        )
        is RejectionReason.PRICE_TOO_HIGH
    )
    assert (
        price_bounds_refusal(
            price=Decimal("100"), minimum_price=Decimal("5"), maximum_price=Decimal("1000")
        )
        is None
    )


def test_a_fully_eligible_asset_passes_every_universe_filter() -> None:
    ok = AssetEvidence(symbol="AAPL", tradable=True, status="active", exchange="NASDAQ")
    assert (
        asset_eligibility_refusal(
            asset=ok,
            symbol="AAPL",
            watchlist=("AAPL",),
            prohibited_instruments=(),
            permitted_markets=("NASDAQ",),
        )
        is None
    )
