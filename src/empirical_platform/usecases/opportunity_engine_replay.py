"""MILESTONE-090 Phase 19 -- a deterministic, look-ahead-safe replay of the Opportunity Engine
over real historical minute bars. No broker write is reachable from this module.

WHY THIS DOES NOT CALL `_evaluate_symbol` DIRECTLY. That function performs live I/O (asks a
broker for the asset, the quote, the bars); a replay walks forward over an ALREADY-FETCHED bar
array with no live broker to ask. This module reproduces the SAME gate sequence, in the SAME
order, using the SAME domain functions (`bar_evidence_refusal`, `liquidity_refusal`,
`evaluate_structure`, `build_trade_plan_geometry`, `reward_risk_refusal`, `position_size`) --
never a parallel or looser implementation of any of them. The two gates a replay cannot honestly
perform are named explicitly and skipped, never faked: asset eligibility (tradable/active/
exchange -- a historical bar carries none of that) and the live market-session gate (a replay
assumes REGULAR_SESSION throughout, since it is by definition replaying regular-hours bars).

THE ONE DOCUMENTED SIMPLIFICATION: THE SYNTHETIC QUOTE. A replay has no real bid/ask -- only a
bar's OHLC. Each bar's own CLOSE is used as BOTH the synthetic bid and the synthetic ask
(`_synthetic_quote`), so the spread is always exactly zero and `quote_quality_refusal`'s spread
check never binds in a replay. This is evidence a replay never claims to be a fill price or a
real market spread; every report generated from this module says so. Freshness is also trivially
satisfied (the synthetic quote's `captured_at` is the SAME bar's own timestamp -- the evaluation
instant `T`), which is honest: whatever a live quote's real staleness risk is, this module makes
no claim about it either way.

NO LOOK-AHEAD, STRUCTURALLY. `_decide_at` builds the SAME `ObservationWindow` type
(`decision_candidate.market_data`) M057 already uses, from a BOUNDED slice of bars ending at
(and including) index `i` -- `bars[i - lookback : i + 1]` -- and never reads `bars[i + 1:]`.
Outcome resolution (`_resolve_outcome`) is the exact mirror: it reads ONLY `bars[i + 1:]`, never
`bars[: i + 1]`. Nothing in this module holds a reference to the full array inside the function
that makes the decision, and nothing in the function that resolves the outcome can see the
evaluation bar's own future neighbors before they occur in the walk -- see
`tests/unit/test_usecases_opportunity_engine_replay.py`'s look-ahead audit for the proof.
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
from empirical_platform.decision_candidate.opportunity_engine import (
    OpportunityEnginePolicy,
    QuoteEvidence,
    RejectionReason,
    StructureMeasurements,
    TradePlanGeometry,
    bar_evidence_refusal,
    build_trade_plan_geometry,
    evaluate_structure,
    liquidity_refusal,
    opportunity_quality,
    position_size,
    price_bounds_refusal,
    reward_risk_refusal,
)
from empirical_platform.decision_candidate.opportunity_engine_repositories import IntradayBarsPort
from empirical_platform.decision_candidate.paper_execution import (
    execution_policy_from_configuration,
    quote_refusal,
)
from empirical_platform.shared.brokerage.paper_time import BoundedInstant

__all__ = [
    "ReplayDecision",
    "ReplayOutcome",
    "ReplaySessionResult",
    "fetch_session_bars",
    "replay_session",
]

#: A replay never claims a real spread; a synthetic zero-spread quote is documented, not hidden.
_SYNTHETIC_QUOTE_SOURCE = "replay-synthetic-close"


def fetch_session_bars(
    bars_port: IntradayBarsPort,
    symbol: str,
    session_date: date,
    *,
    session_start: time,
    session_end: time,
    operator_timezone: str,
) -> tuple[Bar, ...]:
    """One real `fetch_minute_bars` call for one session, converted, sorted, and validated.

    `AlpacaPaperMarketDataClient.fetch_minute_bars` already requests `sort=asc` and is bounded
    to `MAXIMUM_BARS_PER_REQUEST` (1000) -- more than a ~390-bar regular session needs in one
    unpaginated page -- but a caller-side sort is applied anyway: trusting an upstream feed's
    ordering silently is exactly the kind of assumption `ObservationWindow.__post_init__`
    (M057) already refuses to make, and a sort here turns "merely out of order" into a
    harmless no-op instead of a raised exception mid-replay.
    """
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
    # De-duplicate a feed that (rarely) repeats a timestamp -- ObservationWindow refuses a
    # non-strictly-increasing sequence, and a duplicate is evidence quality, not a bug to hide.
    deduped: list[Bar] = []
    for bar in bars:
        if deduped and deduped[-1].timestamp == bar.timestamp:
            continue
        deduped.append(bar)
    return tuple(deduped)


class ReplayOutcome(StrEnum):
    """What happened to an ACTIONABLE decision, resolved using ONLY later bars."""

    TARGET_HIT = "TARGET_HIT"
    STOP_HIT = "STOP_HIT"
    #: The session's own mandatory-liquidation instant was reached before either the stop or
    #: the target -- exactly Phase 12's "no overnight position" rule, replayed honestly: the
    #: plan would have been flattened here, not left to keep working.
    MANDATORY_EXIT = "MANDATORY_EXIT"
    #: The bar sequence ran out (end of the fetched session) before stop, target or the
    #: mandatory exit instant was reached. Never silently treated as a win or a loss.
    UNRESOLVED_END_OF_DATA = "UNRESOLVED_END_OF_DATA"


@dataclass(frozen=True, slots=True)
class ReplayDecision:
    """One bar's evaluation, whether it became an actionable plan or was rejected."""

    bar_index: int
    decided_at: datetime
    symbol: str
    rejection_reasons: tuple[RejectionReason, ...]
    entry_price: Decimal | None
    stop_price: Decimal | None
    target_price: Decimal | None
    risk_per_share: Decimal | None
    reward_per_share: Decimal | None
    reward_risk_ratio: Decimal | None
    quantity: int | None
    quality_score: Decimal | None
    outcome: ReplayOutcome | None
    outcome_at: datetime | None
    outcome_price: Decimal | None
    realized_pnl_per_share: Decimal | None


@dataclass(frozen=True, slots=True)
class ReplaySessionResult:
    symbol: str
    session_date: date
    bar_count: int
    decisions: tuple[ReplayDecision, ...]


def _synthetic_quote(bar: Bar) -> QuoteEvidence:
    """Phase 19's one documented simplification: the bar's own close, as both sides of a
    zero-spread quote. Never presented as a real bid/ask or a real fill price."""
    return QuoteEvidence(
        bid=bar.close, ask=bar.close, captured_at=bar.timestamp, source=_SYNTHETIC_QUOTE_SOURCE
    )


def _decide_at(
    bars: Sequence[Bar],
    index: int,
    *,
    symbol: str,
    policy: OpportunityEnginePolicy,
    configuration: OperatorTradingConfiguration,
    deployable_capital: Decimal,
) -> ReplayDecision:
    """Evaluate the bar at `index` using ONLY `bars[: index + 1]` -- never `bars[index + 1 :]`.

    Mirrors `usecases.opportunity_engine._evaluate_symbol`'s gate order exactly, skipping only
    the two gates a bar array cannot honestly answer (asset eligibility, live session state --
    see the module docstring): quote quality -> price bounds -> bar evidence -> liquidity ->
    structure -> geometry -> reward/risk -> size.
    """
    current = bars[index]
    lookback = policy.structure_lookback_bars
    window_start = max(0, index - lookback)
    window_bars = tuple(bars[window_start : index + 1])

    quote = _synthetic_quote(current)
    broker_now = BoundedInstant(earliest=current.timestamp, latest=current.timestamp)
    execution_policy = execution_policy_from_configuration(configuration)
    refusal = quote_refusal(
        bid=quote.bid,
        ask=quote.ask,
        captured_at=quote.captured_at,
        policy=execution_policy,
        broker_now=broker_now,
    )
    reasons: tuple[RejectionReason, ...] | None = None
    if refusal is not None:
        reasons = (RejectionReason.QUOTE_STALE_OR_INVALID,)
    else:
        # `_synthetic_quote` always sets `ask=bar.close`, a Decimal; `quote_refusal` having
        # already passed proves it is usable, but the type stays `Decimal | None` on
        # `QuoteEvidence` for the live path, so this is asserted, not silently coerced.
        assert quote.ask is not None
        price_refusal = price_bounds_refusal(
            price=quote.ask,
            minimum_price=configuration.minimum_price,
            maximum_price=configuration.maximum_price,
        )
        if price_refusal is not None:
            reasons = (price_refusal,)

    if reasons is None and len(window_bars) < 2:
        reasons = (RejectionReason.STALE_OR_MISSING_BARS,)

    window: ObservationWindow | None = None
    if reasons is None:
        window = ObservationWindow(bars=window_bars)
        bar_refusal = bar_evidence_refusal(window, policy=policy)
        if bar_refusal is not None:
            reasons = (bar_refusal,)

    if reasons is None:
        assert window is not None
        liquidity = liquidity_refusal(window, policy=policy)
        if liquidity is not None:
            reasons = (liquidity,)

    structure_measurements: StructureMeasurements | None = None
    if reasons is None:
        assert window is not None
        structure = evaluate_structure(window, lookback_bars=lookback)
        structure_measurements = structure.measurements
        if not structure.is_long_candidate:
            reasons = (RejectionReason.NO_BREAKOUT_STRUCTURE,)

    geometry: TradePlanGeometry | None = None
    if reasons is None:
        assert structure_measurements is not None and quote.ask is not None
        geometry = build_trade_plan_geometry(
            entry_price=quote.ask, structure=structure_measurements, policy=policy
        )
        if geometry is None:
            reasons = (RejectionReason.STOP_INVALID,)

    if reasons is None:
        assert geometry is not None
        rr_refusal = reward_risk_refusal(
            geometry, minimum_reward_risk_ratio=policy.minimum_reward_risk_ratio
        )
        if rr_refusal is not None:
            reasons = (rr_refusal,)

    quantity: int | None = None
    if reasons is None:
        assert geometry is not None
        quantity = position_size(
            entry_price=geometry.entry_price,
            stop_price=geometry.stop_price,
            maximum_loss=policy.maximum_loss_per_trade,
            maximum_capital_per_trade=configuration.maximum_capital_per_trade,
            maximum_percent_per_trade=configuration.maximum_percent_per_trade,
            deployable_capital=deployable_capital,
        )
        if quantity < 1:
            reasons = (RejectionReason.QUANTITY_LESS_THAN_ONE,)

    if reasons is not None:
        return ReplayDecision(
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
            quality_score=None,
            outcome=None,
            outcome_at=None,
            outcome_price=None,
            realized_pnl_per_share=None,
        )

    assert geometry is not None and quantity is not None and structure_measurements is not None
    quality = opportunity_quality(
        spread_percent=Decimal("0"),
        maximum_spread_percent=execution_policy.maximum_spread_percent,
        recent_volume=current.volume,
        minimum_recent_share_volume=policy.minimum_recent_share_volume,
        structure=structure_measurements,
        geometry=geometry,
        minimum_reward_risk_ratio=policy.minimum_reward_risk_ratio,
        quote_age_seconds=Decimal("0"),
        maximum_quote_age_seconds=300,
    )
    return ReplayDecision(
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
        quality_score=quality,
        outcome=None,
        outcome_at=None,
        outcome_price=None,
        realized_pnl_per_share=None,
    )


def _resolve_outcome(
    bars: Sequence[Bar], index: int, decision: ReplayDecision, *, mandatory_liquidation_at: datetime
) -> ReplayDecision:
    """Resolve `decision` using ONLY `bars[index + 1 :]` -- never `bars[: index + 1]`.

    Same-bar stop-and-target ambiguity resolves STOP FIRST -- the conservative assumption,
    named explicitly here and in every report this module's output feeds.
    """
    if decision.stop_price is None or decision.target_price is None:
        return decision
    for later in bars[index + 1 :]:
        if later.timestamp >= mandatory_liquidation_at:
            return _with_outcome(
                decision, ReplayOutcome.MANDATORY_EXIT, later.timestamp, later.close
            )
        stop_touched = later.low <= decision.stop_price
        target_touched = later.high >= decision.target_price
        if stop_touched:
            return _with_outcome(
                decision, ReplayOutcome.STOP_HIT, later.timestamp, decision.stop_price
            )
        if target_touched:
            return _with_outcome(
                decision, ReplayOutcome.TARGET_HIT, later.timestamp, decision.target_price
            )
    return _with_outcome(decision, ReplayOutcome.UNRESOLVED_END_OF_DATA, None, None)


def _with_outcome(
    decision: ReplayDecision, outcome: ReplayOutcome, at: datetime | None, price: Decimal | None
) -> ReplayDecision:
    pnl = None if price is None or decision.entry_price is None else (price - decision.entry_price)
    return replace(
        decision,
        outcome=outcome,
        outcome_at=at,
        outcome_price=price,
        realized_pnl_per_share=pnl,
    )


def replay_session(
    *,
    symbol: str,
    session_date: date,
    bars: tuple[Bar, ...],
    policy: OpportunityEnginePolicy,
    configuration: OperatorTradingConfiguration,
    deployable_capital: Decimal,
    mandatory_liquidation_at: datetime,
) -> ReplaySessionResult:
    """Walk `bars` forward once. At each bar with enough reference history, decide using only
    bars up to and including it, then resolve the outcome using only later bars.
    """
    decisions: list[ReplayDecision] = []
    lookback = policy.structure_lookback_bars
    for index in range(lookback, len(bars)):
        decision = _decide_at(
            bars,
            index,
            symbol=symbol,
            policy=policy,
            configuration=configuration,
            deployable_capital=deployable_capital,
        )
        if not decision.rejection_reasons:
            decision = _resolve_outcome(
                bars, index, decision, mandatory_liquidation_at=mandatory_liquidation_at
            )
        decisions.append(decision)
    return ReplaySessionResult(
        symbol=symbol,
        session_date=session_date,
        bar_count=len(bars),
        decisions=tuple(decisions),
    )
