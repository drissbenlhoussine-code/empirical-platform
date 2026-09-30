"""MILESTONE-092 -- a deterministic, look-ahead-safe replay of the V2 research policy over
real historical minute bars. No broker write is reachable from this module.

MIRRORS `usecases.opportunity_engine_replay`'s OWN discipline exactly (same docstring
claims, same look-ahead structure: `_decide_at` reads only `bars[:index+1]`,
`_resolve_outcome` reads only `bars[index+1:]`), but calls the V2 domain functions in
`decision_candidate.opportunity_engine_v2` instead of V1's. V1's own replay module is never
imported or modified here -- these are two structurally independent, parallel harnesses.

THE SAME ONE DOCUMENTED SIMPLIFICATION AS V1: each bar's own close stands in for both sides
of a zero-spread synthetic quote. Never presented as a real bid/ask or a real fill price.

SAME-BAR STOP/TARGET AMBIGUITY: resolved STOP FIRST, exactly as V1's own replay does --
never the favorable outcome when intrabar ordering is unknowable (Phase 16).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime, time
from decimal import Decimal
from enum import StrEnum
from zoneinfo import ZoneInfo

from empirical_platform.decision_candidate.market_data import (
    Bar,
    BarInterval,
    Instrument,
    ObservationWindow,
)
from empirical_platform.decision_candidate.operator_trading_configuration import (
    OperatorTradingConfiguration,
)
from empirical_platform.decision_candidate.opportunity_engine_repositories import IntradayBarsPort
from empirical_platform.decision_candidate.opportunity_engine_v2 import (
    OpportunityEnginePolicyV2,
    RejectionReasonV2,
    StructureMeasurementsV2,
    TradePlanGeometryV2,
    bar_evidence_refusal_v2,
    build_trade_plan_geometry_v2,
    entry_quality_refusal,
    evaluate_structure_v2,
    liquidity_refusal_v2,
    position_size_v2,
    reward_risk_refusal_v2,
    time_to_target_refusal,
)

__all__ = [
    "ReplayDecisionV2",
    "ReplayOutcomeV2",
    "ReplaySessionResultV2",
    "fetch_session_bars_v2",
    "replay_session_v2",
]


def fetch_session_bars_v2(
    bars_port: IntradayBarsPort,
    symbol: str,
    session_date: date,
    *,
    session_start: time,
    session_end: time,
    operator_timezone: str,
) -> tuple[Bar, ...]:
    """Identical to V1's own `fetch_session_bars` -- duplicated here (not imported) so this
    module has no dependency on V1's replay file at all, matching the architecture-boundary
    tests' own parallel-module discipline."""
    zone = ZoneInfo(operator_timezone)
    start = datetime.combine(session_date, session_start, tzinfo=zone).astimezone(ZoneInfo("UTC"))
    end = datetime.combine(session_date, session_end, tzinfo=zone).astimezone(ZoneInfo("UTC"))
    raw = bars_port.fetch_minute_bars(symbol, start=start, end=end, limit=1000)
    instrument = Instrument(symbol)
    bars = [
        Bar(
            instrument=instrument,
            interval=BarInterval.ONE_MINUTE,
            timestamp=view.timestamp,
            open=Decimal(view.open),
            high=Decimal(view.high),
            low=Decimal(view.low),
            close=Decimal(view.close),
            volume=view.volume,
        )
        for view in raw
    ]
    bars.sort(key=lambda bar: bar.timestamp)
    deduped: list[Bar] = []
    for bar in bars:
        if deduped and deduped[-1].timestamp == bar.timestamp:
            continue
        deduped.append(bar)
    return tuple(deduped)


class ReplayOutcomeV2(StrEnum):
    TARGET_HIT = "TARGET_HIT"
    STOP_HIT = "STOP_HIT"
    MANDATORY_EXIT = "MANDATORY_EXIT"
    UNRESOLVED_END_OF_DATA = "UNRESOLVED_END_OF_DATA"


@dataclass(frozen=True, slots=True)
class ReplayDecisionV2:
    bar_index: int
    decided_at: datetime
    symbol: str
    rejection_reasons: tuple[RejectionReasonV2, ...]
    entry_price: Decimal | None
    stop_price: Decimal | None
    target_price: Decimal | None
    risk_per_share: Decimal | None
    reward_per_share: Decimal | None
    reward_risk_ratio: Decimal | None
    quantity: int | None
    outcome: ReplayOutcomeV2 | None
    outcome_at: datetime | None
    outcome_price: Decimal | None
    realized_pnl_per_share: Decimal | None


@dataclass(frozen=True, slots=True)
class ReplaySessionResultV2:
    symbol: str
    session_date: date
    bar_count: int
    decisions: tuple[ReplayDecisionV2, ...]


def _decide_at(
    bars: Sequence[Bar],
    index: int,
    *,
    symbol: str,
    policy: OpportunityEnginePolicyV2,
    configuration: OperatorTradingConfiguration,
    deployable_capital: Decimal,
    mandatory_liquidation_at: datetime,
) -> ReplayDecisionV2:
    """Evaluate the bar at `index` using ONLY `bars[:index+1]`. Gate order: bar evidence ->
    price bounds (reused as a plain range check, no quote-freshness concept needed for a
    same-bar synthetic quote) -> liquidity -> structure -> entry quality -> geometry ->
    time-to-target feasibility -> reward/risk -> size.
    """
    current = bars[index]
    lookback = policy.structure_lookback_bars
    window_start = max(0, index - lookback)
    window_bars = tuple(bars[window_start : index + 1])

    reasons: tuple[RejectionReasonV2, ...] | None = None
    if current.close < configuration.minimum_price or (
        configuration.maximum_price is not None and current.close > configuration.maximum_price
    ):
        reasons = (RejectionReasonV2.STALE_OR_MISSING_BARS,)

    if reasons is None and len(window_bars) < 2:
        reasons = (RejectionReasonV2.STALE_OR_MISSING_BARS,)

    window: ObservationWindow | None = None
    if reasons is None:
        window = ObservationWindow(bars=window_bars)
        bar_refusal = bar_evidence_refusal_v2(window, policy=policy)
        if bar_refusal is not None:
            reasons = (bar_refusal,)

    measurements: StructureMeasurementsV2 | None = None
    is_candidate = False
    if reasons is None:
        assert window is not None
        is_candidate, measurements = evaluate_structure_v2(window, lookback_bars=lookback)

    if reasons is None:
        assert measurements is not None
        liquidity = liquidity_refusal_v2(window, measurements, policy=policy)  # type: ignore[arg-type]
        if liquidity is not None:
            reasons = (liquidity,)

    if reasons is None:
        assert measurements is not None
        if not is_candidate:
            reasons = (RejectionReasonV2.NO_BREAKOUT_STRUCTURE,)

    if reasons is None:
        assert measurements is not None
        quality = entry_quality_refusal(measurements, policy=policy)
        if quality is not None:
            reasons = (quality,)

    geometry: TradePlanGeometryV2 | None = None
    if reasons is None:
        assert measurements is not None
        geometry = build_trade_plan_geometry_v2(
            entry_price=current.close, measurements=measurements, policy=policy
        )
        if geometry is None:
            reasons = (RejectionReasonV2.STOP_INVALID,)

    if reasons is None:
        assert geometry is not None and measurements is not None
        remaining_bars = max(0, len(bars) - index - 1)
        feasibility = time_to_target_refusal(
            geometry=geometry,
            measurements=measurements,
            remaining_bars_to_mandatory_exit=remaining_bars,
            policy=policy,
        )
        if feasibility is not None:
            reasons = (feasibility,)

    if reasons is None:
        assert geometry is not None
        rr_refusal = reward_risk_refusal_v2(
            geometry, minimum_reward_risk_ratio=policy.minimum_reward_risk_ratio
        )
        if rr_refusal is not None:
            reasons = (rr_refusal,)

    quantity: int | None = None
    if reasons is None:
        assert geometry is not None
        quantity = position_size_v2(
            entry_price=geometry.entry_price,
            stop_price=geometry.stop_price,
            maximum_loss=policy.maximum_loss_per_trade,
            maximum_capital_per_trade=configuration.maximum_capital_per_trade,
            maximum_percent_per_trade=configuration.maximum_percent_per_trade,
            deployable_capital=deployable_capital,
        )
        if quantity < 1:
            reasons = (RejectionReasonV2.QUANTITY_LESS_THAN_ONE,)

    if reasons is not None:
        return ReplayDecisionV2(
            bar_index=index,
            decided_at=current.timestamp,
            symbol=symbol,
            rejection_reasons=reasons,
            entry_price=None,
            stop_price=None,
            target_price=None,
            risk_per_share=None,
            reward_per_share=None,
            reward_risk_ratio=None,
            quantity=None,
            outcome=None,
            outcome_at=None,
            outcome_price=None,
            realized_pnl_per_share=None,
        )

    assert geometry is not None and quantity is not None
    return ReplayDecisionV2(
        bar_index=index,
        decided_at=current.timestamp,
        symbol=symbol,
        rejection_reasons=(),
        entry_price=geometry.entry_price,
        stop_price=geometry.stop_price,
        target_price=geometry.target_price,
        risk_per_share=geometry.risk_per_share,
        reward_per_share=geometry.reward_per_share,
        reward_risk_ratio=geometry.reward_risk_ratio,
        quantity=quantity,
        outcome=None,
        outcome_at=None,
        outcome_price=None,
        realized_pnl_per_share=None,
    )


def _resolve_outcome(
    bars: Sequence[Bar],
    index: int,
    decision: ReplayDecisionV2,
    *,
    mandatory_liquidation_at: datetime,
) -> ReplayDecisionV2:
    """Resolve `decision` using ONLY `bars[index+1:]`. Same-bar stop/target ambiguity
    resolves STOP FIRST -- the conservative assumption, matching V1's own rule exactly."""
    if decision.stop_price is None or decision.target_price is None:
        return decision
    for later in bars[index + 1 :]:
        if later.timestamp >= mandatory_liquidation_at:
            return _with_outcome(
                decision, ReplayOutcomeV2.MANDATORY_EXIT, later.timestamp, later.close
            )
        stop_touched = later.low <= decision.stop_price
        target_touched = later.high >= decision.target_price
        if stop_touched:
            return _with_outcome(
                decision, ReplayOutcomeV2.STOP_HIT, later.timestamp, decision.stop_price
            )
        if target_touched:
            return _with_outcome(
                decision, ReplayOutcomeV2.TARGET_HIT, later.timestamp, decision.target_price
            )
    return _with_outcome(decision, ReplayOutcomeV2.UNRESOLVED_END_OF_DATA, None, None)


def _with_outcome(
    decision: ReplayDecisionV2,
    outcome: ReplayOutcomeV2,
    at: datetime | None,
    price: Decimal | None,
) -> ReplayDecisionV2:
    pnl = None if price is None or decision.entry_price is None else (price - decision.entry_price)
    return replace(
        decision, outcome=outcome, outcome_at=at, outcome_price=price, realized_pnl_per_share=pnl
    )


def replay_session_v2(
    *,
    symbol: str,
    session_date: date,
    bars: tuple[Bar, ...],
    policy: OpportunityEnginePolicyV2,
    configuration: OperatorTradingConfiguration,
    deployable_capital: Decimal,
    mandatory_liquidation_at: datetime,
) -> ReplaySessionResultV2:
    decisions: list[ReplayDecisionV2] = []
    lookback = policy.structure_lookback_bars
    for index in range(lookback, len(bars)):
        decision = _decide_at(
            bars,
            index,
            symbol=symbol,
            policy=policy,
            configuration=configuration,
            deployable_capital=deployable_capital,
            mandatory_liquidation_at=mandatory_liquidation_at,
        )
        if not decision.rejection_reasons:
            decision = _resolve_outcome(
                bars, index, decision, mandatory_liquidation_at=mandatory_liquidation_at
            )
        decisions.append(decision)
    return ReplaySessionResultV2(
        symbol=symbol, session_date=session_date, bar_count=len(bars), decisions=tuple(decisions)
    )
