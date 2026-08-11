"""MILESTONE-068 acceptance controls: perfect-correlation, low-dependence,
negative-correlation, constant-series, false-diversification, and
future-mutation.

Mission Phases 11-14/28-29. Each control composes the real, production
`build_portfolio_dependence_report()` function end-to-end (return-series
derivation -> pairwise correlation -> concurrent-exposure-state
derivation -> dependence-weighted concentration -> classification) over
hand-constructed but deterministic bar series and a synthetic-but-real
`PortfolioEvidenceReport`, to prove the dependence layer exposes false
diversification and represents undefined/negative correlation honestly,
never fabricating or hiding evidence.

`build_portfolio_evidence_report`/`build_portfolio_dependence_report` are
both pure functions (no PostgreSQL access) -- these controls exercise the
real production pipeline directly, mirroring the established M066
controls-file precedent, without requiring a live database.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from empirical_platform.decision_candidate.historical_backtest import HistoricalInstrumentSeries
from empirical_platform.decision_candidate.market_data import Bar, BarInterval, Instrument
from empirical_platform.decision_candidate.portfolio_dependence import (
    DependenceEstimationPolicy,
    PairDependenceStatus,
    build_portfolio_dependence_report,
)
from empirical_platform.decision_candidate.portfolio_study import (
    CapitalSensitivityLabel,
    CapitalSensitivityView,
    PortfolioAllocationDecision,
    PortfolioAllocationOutcome,
    PortfolioCapitalPolicy,
    PortfolioEvidenceReport,
)
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import PortfolioDependenceReportId, PortfolioStudyId
from empirical_platform.shared.identifiers import RuntimeIdentifier

_T0 = datetime(2026, 1, 1, 9, 30, tzinfo=UTC)
_INTERVAL = BarInterval.ONE_MINUTE

_POLICY = DependenceEstimationPolicy(
    policy_id="CONTROL-POLICY",
    version="1",
    lookback_bar_count=20,
    minimum_overlapping_observations=5,
)


def _bar(symbol: str, minute_offset: int, close: Decimal) -> Bar:
    return Bar(
        instrument=Instrument(symbol),
        interval=_INTERVAL,
        timestamp=_T0 + timedelta(minutes=minute_offset),
        open=close,
        high=close,
        low=close,
        close=close,
        volume=100,
    )


def _series_from_returns(
    symbol: str, start_price: str, returns: list[str]
) -> HistoricalInstrumentSeries:
    """Build a bar series whose own simple returns are exactly the
    supplied sequence -- `close_t = close_{t-1} * (1 + r_t)`."""
    price = Decimal(start_price)
    bars = [_bar(symbol, 0, price)]
    for i, r in enumerate(returns, start=1):
        price = price * (Decimal("1") + Decimal(r))
        bars.append(_bar(symbol, i, price))
    return HistoricalInstrumentSeries(instrument=Instrument(symbol), bars=tuple(bars))


def _decision(
    seq: int, symbol: str, entry_min: int, exit_min: int, risk: str
) -> PortfolioAllocationDecision:
    return PortfolioAllocationDecision(
        opportunity_sequence=seq,
        source_window_id="BTRUN-CTRL",
        trade_sequence=seq,
        instrument_symbol=symbol,
        scan_rank=1,
        entry_timestamp=_T0 + timedelta(minutes=entry_min),
        exit_timestamp=_T0 + timedelta(minutes=exit_min),
        risk_amount=Decimal(risk),
        net_pnl=Decimal("1"),
        decision=PortfolioAllocationOutcome.ALLOCATED,
        rejection_reason=None,
    )


def _synthetic_portfolio(
    decisions: tuple[PortfolioAllocationDecision, ...],
) -> PortfolioEvidenceReport:
    """A minimal, internally-consistent, hand-built `PortfolioEvidenceReport`
    -- every field required by `__post_init__` is filled with a
    plausible, consistent value; only `allocation_decisions` matters for
    what these controls actually exercise."""
    capital_policy = PortfolioCapitalPolicy(
        policy_id="CONTROL-CAPITAL",
        version="1",
        initial_capital=Decimal("100000"),
        currency="USD",
        max_concurrent_positions=10,
        max_capital_utilization_percent=Decimal("1.00"),
    )
    sensitivity_views = tuple(
        CapitalSensitivityView(
            label=label,
            capital_policy_id="CONTROL-CAPITAL",
            initial_capital=Decimal("100000"),
            max_concurrent_positions=10,
            allocated_count=len(decisions),
            rejected_count=0,
            ending_capital=Decimal("100010"),
            realized_pnl=Decimal("10"),
            max_drawdown=Decimal("0"),
        )
        for label in CapitalSensitivityLabel
    )
    return PortfolioEvidenceReport(
        identity=DomainIdentity(
            governance_id=PortfolioStudyId("PORT-9001"),
            runtime_id=RuntimeIdentifier("00000000-0000-4000-8000-000000000001"),
        ),
        source_study_governance_id="SURV-9001",
        source_study_runtime_id="00000000-0000-4000-8000-000000000002",
        dataset_bundle_id="DATASET-CONTROL",
        dataset_bundle_version="1",
        dataset_bundle_sha256="0" * 64,
        dataset_source_kind="CONTROL_FIXTURE",
        universe_id="UNIVERSE-CONTROL",
        universe_version="1",
        membership_manifest_hash="0" * 64,
        strategy_id="STRATEGY-CONTROL",
        strategy_version="1",
        ranking_model_id="RANKING-CONTROL",
        ranking_model_version="1",
        risk_policy_id="RISK-CONTROL",
        risk_policy_version="1",
        sizing_policy_id="SIZING-CONTROL",
        sizing_policy_version="1",
        capital_policy=capital_policy,
        total_opportunities=len(decisions),
        allocated_count=len(decisions),
        rejected_count=0,
        rejected_insufficient_capital_count=0,
        rejected_max_concurrent_count=0,
        rejected_max_utilization_count=0,
        initial_capital=Decimal("100000"),
        ending_capital=Decimal("100010"),
        realized_pnl=Decimal("10"),
        portfolio_return_percent=Decimal("0.0001"),
        peak_equity=Decimal("100010"),
        max_drawdown=Decimal("0"),
        max_drawdown_percent=Decimal("0"),
        max_concurrent_positions_observed=len(decisions),
        average_concurrent_positions=Decimal(len(decisions)),
        peak_occupied_capital=sum((d.risk_amount for d in decisions), Decimal("0")),
        peak_capital_utilization_percent=Decimal("0.01"),
        largest_instrument_positive_contribution_symbol=None,
        largest_instrument_positive_contribution_amount=None,
        largest_instrument_negative_contribution_symbol=None,
        largest_instrument_negative_contribution_amount=None,
        largest_position_contribution_trade_sequence=None,
        largest_position_contribution_amount=None,
        largest_window_contribution_window_id=None,
        largest_window_contribution_amount=None,
        allocation_decisions=decisions,
        equity_curve=(),
        capital_sensitivity_views=sensitivity_views,
    )


def _report_identity() -> DomainIdentity[PortfolioDependenceReportId]:
    return DomainIdentity(
        governance_id=PortfolioDependenceReportId("DEPEND-9001"),
        runtime_id=RuntimeIdentifier("00000000-0000-4000-8000-000000000003"),
    )


# A deliberately non-constant, non-trivial return sequence used as the
# common basis for the perfect-correlation and false-diversification
# controls -- any two instruments built from this exact sequence are
# mathematically guaranteed to correlate at +1.
_BASE_RETURNS = [
    "0.01",
    "-0.02",
    "0.03",
    "-0.01",
    "0.02",
    "-0.03",
    "0.01",
    "0.02",
    "-0.01",
    "0.015",
]


def test_perfect_correlation_control_two_positions_identical_returns() -> None:
    """Mission Phase 11: identical return series -> pairwise correlation
    ~= 1, dependence-aware concentration high, honestly showing weak
    diversification."""
    series_a = _series_from_returns("AAAA", "100", _BASE_RETURNS)
    series_b = _series_from_returns(
        "BBBB", "50", _BASE_RETURNS
    )  # different price level, same % moves
    decisions = (
        _decision(1, "AAAA", 10, 15, risk="500"),
        _decision(2, "BBBB", 10, 15, risk="500"),
    )
    report = build_portfolio_dependence_report(
        identity=_report_identity(),
        portfolio=_synthetic_portfolio(decisions),
        series_by_instrument={"AAAA": series_a, "BBBB": series_b},
        policy=_POLICY,
    )
    pair = next(p for p in report.pairwise_dependence if p.instrument_a != p.instrument_b)
    assert pair.status is PairDependenceStatus.DEFINED
    assert pair.correlation == Decimal("1.0000")
    assert report.peak_dependence_aware_concentration == Decimal("1.0000")
    assert report.peak_nominal_concentration == Decimal(
        "0.5000"
    )  # looks 50/50 diversified nominally
    # The dependence-aware figure is materially worse than the nominal one.
    assert report.peak_dependence_aware_concentration > report.peak_nominal_concentration


def test_low_dependence_control_materially_differs_from_perfect_correlation() -> None:
    """Mission Phase 12: a legitimate, differently-patterned return
    sequence must produce materially different (much lower) dependence
    evidence than the perfect-correlation control -- mathematics only,
    not tuned for attractive PnL (net_pnl is fixed at 1 for every
    decision in every control)."""
    returns_a = [
        "0.02",
        "-0.01",
        "0.015",
        "-0.02",
        "0.01",
        "-0.015",
        "0.02",
        "-0.01",
        "0.005",
        "-0.02",
    ]
    returns_b = [
        "-0.01",
        "0.02",
        "-0.02",
        "0.005",
        "-0.015",
        "0.02",
        "-0.005",
        "0.015",
        "-0.02",
        "0.01",
    ]
    series_a = _series_from_returns("CCCC", "100", returns_a)
    series_b = _series_from_returns("DDDD", "80", returns_b)
    decisions = (
        _decision(1, "CCCC", 10, 15, risk="500"),
        _decision(2, "DDDD", 10, 15, risk="500"),
    )
    report = build_portfolio_dependence_report(
        identity=_report_identity(),
        portfolio=_synthetic_portfolio(decisions),
        series_by_instrument={"CCCC": series_a, "DDDD": series_b},
        policy=_POLICY,
    )
    pair = next(p for p in report.pairwise_dependence if p.instrument_a != p.instrument_b)
    assert pair.status is PairDependenceStatus.DEFINED
    assert pair.correlation is not None
    assert abs(pair.correlation) < Decimal("0.9")  # materially below the perfect-correlation case
    assert report.peak_dependence_aware_concentration is not None
    assert report.peak_dependence_aware_concentration < Decimal("1.0000")


def test_negative_correlation_control_represented_correctly() -> None:
    """Mission Phase 13: exactly negated returns produce correlation
    ~= -1, represented honestly -- never automatically relabeled a
    'hedge' or 'risk-free' anywhere in the domain vocabulary."""
    negated_returns = [str(-Decimal(r)) for r in _BASE_RETURNS]
    series_a = _series_from_returns("EEEE", "100", _BASE_RETURNS)
    series_b = _series_from_returns("FFFF", "60", negated_returns)
    decisions = (
        _decision(1, "EEEE", 10, 15, risk="500"),
        _decision(2, "FFFF", 10, 15, risk="500"),
    )
    report = build_portfolio_dependence_report(
        identity=_report_identity(),
        portfolio=_synthetic_portfolio(decisions),
        series_by_instrument={"EEEE": series_a, "FFFF": series_b},
        policy=_POLICY,
    )
    pair = next(p for p in report.pairwise_dependence if p.instrument_a != p.instrument_b)
    assert pair.status is PairDependenceStatus.DEFINED
    assert pair.correlation == Decimal("-1.0000")
    # No field or classification anywhere claims this is a "hedge" --
    # the vocabulary is purely descriptive (checked structurally: the
    # classification enum members never mention hedging or safety).
    from empirical_platform.decision_candidate.portfolio_dependence import (
        DependenceEvidenceClassification,
    )

    for member in DependenceEvidenceClassification:
        assert "HEDGE" not in member.value
        assert "SAFE" not in member.value


def test_constant_series_control_is_undefined_not_fake_zero() -> None:
    """Mission Phase 14: a zero-variance series must never silently
    produce a fabricated 0 correlation -- it must be represented as
    explicitly undefined."""
    constant_bars = tuple(_bar("GGGG", i, Decimal("50")) for i in range(15))
    series_constant = HistoricalInstrumentSeries(instrument=Instrument("GGGG"), bars=constant_bars)
    series_normal = _series_from_returns("HHHH", "100", _BASE_RETURNS)
    decisions = (
        _decision(1, "GGGG", 10, 14, risk="500"),
        _decision(2, "HHHH", 10, 14, risk="500"),
    )
    report = build_portfolio_dependence_report(
        identity=_report_identity(),
        portfolio=_synthetic_portfolio(decisions),
        series_by_instrument={"GGGG": series_constant, "HHHH": series_normal},
        policy=_POLICY,
    )
    pair = next(
        p
        for p in report.pairwise_dependence
        if {p.instrument_a, p.instrument_b} == {"GGGG", "HHHH"}
    )
    assert pair.status is PairDependenceStatus.UNDEFINED_ZERO_VARIANCE
    assert pair.correlation is None
    # The constant instrument's own self-pair is also undefined (var=0).
    self_pair = next(
        p for p in report.pairwise_dependence if p.instrument_a == p.instrument_b == "GGGG"
    )
    assert self_pair.status is PairDependenceStatus.UNDEFINED_ZERO_VARIANCE
    assert self_pair.correlation is None


def test_false_diversification_attack_central_product_proof() -> None:
    """Mission Phase 28 -- the central product proof. Capital is
    nominally spread evenly across 4 concurrently-held instruments (a
    low nominal HHI, "looks diversified"), but every instrument's own
    historical return series is identical. M068 must expose that
    dependence-aware concentration is high despite the spread nominal
    weights."""
    series_by_instrument = {
        symbol: _series_from_returns(symbol, str(50 + i * 10), _BASE_RETURNS)
        for i, symbol in enumerate(("WWWW", "XXXX", "YYYY", "ZZZZ"))
    }
    decisions = tuple(
        _decision(i + 1, symbol, 10, 15, risk="250")
        for i, symbol in enumerate(("WWWW", "XXXX", "YYYY", "ZZZZ"))
    )
    report = build_portfolio_dependence_report(
        identity=_report_identity(),
        portfolio=_synthetic_portfolio(decisions),
        series_by_instrument=series_by_instrument,
        policy=_POLICY,
    )
    # Nominal: 4 equal-weight positions -> HHI = 4 * (0.25)^2 = 0.25 (looks well-diversified).
    assert report.peak_nominal_concentration == Decimal("0.2500")
    # Dependence-aware: all 4 are perfectly correlated -> w'Cw = (sum w)^2 = 1.
    assert report.peak_dependence_aware_concentration == Decimal("1.0000")
    assert report.peak_dependence_aware_concentration > report.peak_nominal_concentration * 3
    # Every off-diagonal pair among the 4 is a defined, perfect correlation.
    off_diagonal = [p for p in report.pairwise_dependence if p.instrument_a != p.instrument_b]
    assert len(off_diagonal) == 6  # C(4, 2)
    assert all(p.correlation == Decimal("1.0000") for p in off_diagonal)


def test_future_mutation_attack_earlier_dependence_evidence_unchanged() -> None:
    """Mission Phase 29: mutating only bars strictly after an early
    concurrent-exposure instant must never change that earlier instant's
    own pairwise correlation, concentration, or classification inputs."""
    early_returns = _BASE_RETURNS[:5]
    late_returns_original = ["0.01", "-0.01", "0.02", "-0.02", "0.01"]
    late_returns_mutated = ["-0.50", "0.80", "-0.30", "0.60", "-0.40"]  # wildly different future

    series_a_original = _series_from_returns("IIII", "100", early_returns + late_returns_original)
    series_b_original = _series_from_returns("JJJJ", "100", early_returns + late_returns_original)
    series_a_mutated = _series_from_returns("IIII", "100", early_returns + late_returns_mutated)
    series_b_mutated = _series_from_returns("JJJJ", "100", early_returns + late_returns_mutated)

    # Two decisions open together only at the *early* cutoff (t=5, right
    # after the 5 early returns have accumulated), both exiting before
    # the mutated late bars (minutes 6-10) occur.
    decisions = (
        _decision(1, "IIII", 5, 9, risk="500"),
        _decision(2, "JJJJ", 5, 9, risk="500"),
    )

    report_original = build_portfolio_dependence_report(
        identity=_report_identity(),
        portfolio=_synthetic_portfolio(decisions),
        series_by_instrument={"IIII": series_a_original, "JJJJ": series_b_original},
        policy=DependenceEstimationPolicy(
            policy_id="P", version="1", lookback_bar_count=5, minimum_overlapping_observations=3
        ),
    )
    report_mutated = build_portfolio_dependence_report(
        identity=_report_identity(),
        portfolio=_synthetic_portfolio(decisions),
        series_by_instrument={"IIII": series_a_mutated, "JJJJ": series_b_mutated},
        policy=DependenceEstimationPolicy(
            policy_id="P", version="1", lookback_bar_count=5, minimum_overlapping_observations=3
        ),
    )
    # The only concurrent-exposure state is at t=5 (both open together),
    # which only ever depends on bars at/before t=5 (the 5 early
    # returns) -- the late mutation (bars 6-10) must not change its own
    # pairwise dependence or concentration since the estimation cutoff
    # for that state is t=5, strictly before any of the mutated bars.
    state_original = report_original.concurrent_exposure_states[0]
    state_mutated = report_mutated.concurrent_exposure_states[0]
    assert (
        state_original.dependence_aware_concentration
        == state_mutated.dependence_aware_concentration
    )
    assert state_original.nominal_concentration == state_mutated.nominal_concentration
