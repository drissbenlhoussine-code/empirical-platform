"""MILESTONE-090 -- commands for the Opportunity Engine: generate, review, approve, ignore.

THE UNIVERSE, ONE SYMBOL AT A TIME, NEVER LET ONE BAD SYMBOL STOP THE BATCH. Each symbol in
`OperatorTradingConfiguration.watchlist` is evaluated independently; a broker error fetching
ONE symbol's asset/quote/bars is caught and recorded as that symbol's own
`INSUFFICIENT_EVIDENCE` rejection, never raised out of `GenerateOpportunitiesHandler.handle`,
so a single flaky lookup cannot blank the whole Today page.

RE-VERIFICATION, NEVER REPRICING (Phase 16). `ReviewOpportunityHandler` and
`ApproveOpportunityHandler` both re-run the FULL evaluation pipeline against fresh evidence
before permitting anything -- exactly M085/M087's "re-verify at confirm, never trust an
earlier check alone" doctrine. When the fresh evaluation still agrees (within
`entry_tolerance_percent`), the ORIGINAL, Owner-reviewed terms are what gets approved --
never a silently updated price.

THE APPROVAL BOUNDARY IS STRUCTURAL, NOT JUST A DOCSTRING (Phase 17-18).
`ApproveOpportunityHandler` durably records OWNER_APPROVED and returns the approved
`TradingOpportunity` -- which already carries every field (symbol, quantity, entry/stop/target,
mandatory_liquidation_at) a later milestone would need to construct a paper order. Nothing in
this module imports `submit_order`, `submit_close_order`, or any M085 dispatch handler; an
architecture test proves it (see `tests/architecture/test_m090_opportunity_engine_boundaries.py`).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
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
    AssetEvidence,
    MarketSessionState,
    OpportunityDecision,
    OpportunityEnginePolicy,
    OpportunityStatus,
    OwnerOpportunityAction,
    QuoteEvidence,
    RejectionReason,
    StructureEvaluation,
    TradePlanGeometry,
    TradingOpportunity,
    asset_eligibility_refusal,
    bar_evidence_refusal,
    build_trade_plan_geometry,
    entry_moved_refusal,
    evaluate_structure,
    liquidity_refusal,
    market_session_state,
    opportunity_quality,
    opportunity_valid_until,
    position_size,
    price_bounds_refusal,
    quote_quality_refusal,
    rank_sort_key,
    reward_risk_refusal,
    session_permits_actionable,
)
from empirical_platform.decision_candidate.opportunity_engine import (
    mandatory_liquidation_at as compute_mandatory_liquidation_at,
)
from empirical_platform.decision_candidate.opportunity_engine_repositories import (
    IntradayBarsPort,
    OpportunityDecisionRepository,
    OpportunityRepository,
)
from empirical_platform.decision_candidate.paper_execution import (
    execution_policy_from_configuration,
)
from empirical_platform.decision_candidate.paper_execution_repositories import (
    PaperBrokerPort,
    PaperMarketDataPort,
)
from empirical_platform.decision_candidate.product_repositories import (
    OperatorTradingConfigurationRepository,
)
from empirical_platform.shared.brokerage.alpaca_paper import BrokerResponseInvalidError
from empirical_platform.shared.brokerage.paper_time import BoundedInstant

__all__ = [
    "ApproveOpportunityCommand",
    "ApproveOpportunityHandler",
    "GenerateOpportunitiesCommand",
    "GenerateOpportunitiesHandler",
    "IgnoreOpportunityCommand",
    "IgnoreOpportunityHandler",
    "OperatorTradingConfiguration",
    "OperatorTradingConfigurationRepository",
    "OpportunityEngineRefusedError",
    "OpportunityEnginePolicy",
    "OpportunityStatus",
    "ReviewOpportunityHandler",
    "SymbolEvaluation",
    "TradingOpportunity",
    "select_top_actionable",
]

_MAXIMUM_BAR_LOOKBACK_MULTIPLE = 3  # ask for 3x the lookback so thin/gappy feeds still fill it


class OpportunityEngineRefusedError(ValueError):
    """An action this engine will not take, with the reason. Nothing was sent to any broker."""


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _opportunity_id(symbol: str, session_date: str, generated_at: datetime) -> str:
    material = f"{symbol}|{session_date}|{generated_at.isoformat()}"
    return "OPP-" + _digest(material)[:32]


def _decimal_or_none(value: str | None) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def _account_deployable_capital(
    broker: PaperBrokerPort, configuration: OperatorTradingConfiguration
) -> Decimal:
    """The real evidence a size cap is measured against -- never a caller-asserted number."""
    status, payload = broker.fetch_account()
    if status != 200:
        raise OpportunityEngineRefusedError(
            f"the account could not be read (HTTP {status}); nothing was generated"
        )
    equity = _decimal_or_none(str(payload.get("equity"))) if "equity" in payload else None
    if equity is None or equity <= 0:
        raise OpportunityEngineRefusedError(
            "the account payload carries no usable equity figure; nothing was generated"
        )
    return min(equity, configuration.maximum_deployable_capital)


def _window_from_bars(bars: tuple[object, ...], symbol: str) -> ObservationWindow | None:
    instrument = Instrument(symbol)
    built: list[Bar] = []
    for raw in bars:
        try:
            built.append(
                Bar(
                    instrument=instrument,
                    interval=BarInterval.ONE_MINUTE,
                    timestamp=raw.timestamp,  # type: ignore[attr-defined]
                    open=Decimal(raw.open),  # type: ignore[attr-defined]
                    high=Decimal(raw.high),  # type: ignore[attr-defined]
                    low=Decimal(raw.low),  # type: ignore[attr-defined]
                    close=Decimal(raw.close),  # type: ignore[attr-defined]
                    volume=raw.volume,  # type: ignore[attr-defined]
                )
            )
        except (ValueError, TypeError, InvalidOperation):
            # A malformed bar is evidence the feed is unusable for THIS symbol right now --
            # fail closed on the whole window rather than silently dropping one bar and
            # shifting the reference calculation under it.
            return None
    if len(built) < 2:
        return None
    try:
        return ObservationWindow(bars=tuple(built))
    except ValueError:
        return None


@dataclass(frozen=True, slots=True)
class SymbolEvaluation:
    """Everything one symbol's evaluation produced, whether it ended eligible or not."""

    symbol: str
    session: MarketSessionState
    asset: AssetEvidence | None
    quote: QuoteEvidence | None
    window: ObservationWindow | None
    structure: StructureEvaluation | None
    geometry: TradePlanGeometry | None
    quantity: int | None
    rejection_reasons: tuple[RejectionReason, ...]
    evidence: tuple[str, ...]


def _evaluate_symbol(
    *,
    symbol: str,
    configuration: OperatorTradingConfiguration,
    policy: OpportunityEnginePolicy,
    broker: PaperBrokerPort,
    market_data: PaperMarketDataPort,
    bars_port: IntradayBarsPort,
    session: MarketSessionState,
    broker_now: BoundedInstant,
    deployable_capital: Decimal,
) -> SymbolEvaluation:
    """The single-symbol pipeline Phases 3-11 describe, run once, fail closed at the first gate
    that refuses. Every branch returns a `SymbolEvaluation` -- never raises for an ordinary
    ineligibility, only for a genuinely unexpected broker answer, which the caller catches."""
    reasons: list[RejectionReason] = []
    evidence: list[str] = []

    try:
        raw_asset = broker.fetch_asset(symbol)
        asset = AssetEvidence(
            symbol=raw_asset.symbol,
            tradable=raw_asset.tradable,
            status=raw_asset.status,
            exchange=raw_asset.exchange,
        )
    except BrokerResponseInvalidError:
        asset = None

    refusal = asset_eligibility_refusal(
        asset=asset,
        symbol=symbol,
        watchlist=configuration.watchlist,
        prohibited_instruments=configuration.prohibited_instruments,
        permitted_markets=configuration.permitted_markets,
    )
    if refusal is not None:
        return SymbolEvaluation(
            symbol=symbol,
            session=session,
            asset=asset,
            quote=None,
            window=None,
            structure=None,
            geometry=None,
            quantity=None,
            rejection_reasons=(refusal,),
            evidence=(),
        )

    raw_quote = market_data.fetch_quote(symbol)
    quote = QuoteEvidence(
        bid=_decimal_or_none(None if raw_quote is None else raw_quote.bid),
        ask=_decimal_or_none(None if raw_quote is None else raw_quote.ask),
        captured_at=None if raw_quote is None else raw_quote.captured_at,
        source="" if raw_quote is None else raw_quote.source,
    )
    execution_policy = execution_policy_from_configuration(configuration)
    refusal = quote_quality_refusal(
        quote=quote, execution_policy=execution_policy, broker_now=broker_now
    )
    if refusal is None and quote.ask is not None:
        refusal = price_bounds_refusal(
            price=quote.ask,
            minimum_price=configuration.minimum_price,
            maximum_price=configuration.maximum_price,
        )
    if refusal is not None:
        reasons.append(refusal)
        return SymbolEvaluation(
            symbol=symbol,
            session=session,
            asset=asset,
            quote=quote,
            window=None,
            structure=None,
            geometry=None,
            quantity=None,
            rejection_reasons=tuple(reasons),
            evidence=(),
        )
    assert quote.ask is not None and quote.bid is not None
    spread_percent = (quote.ask - quote.bid) / ((quote.ask + quote.bid) / Decimal(2)) * Decimal(100)
    evidence.append(
        f"quote {quote.bid}/{quote.ask} (spread {spread_percent.quantize(Decimal('0.01'))}%)"
    )

    lookback = policy.structure_lookback_bars
    end = broker_now.latest
    start = end - timedelta(minutes=lookback * _MAXIMUM_BAR_LOOKBACK_MULTIPLE + 5)
    try:
        raw_bars = bars_port.fetch_minute_bars(symbol, start=start, end=end, limit=200)
    except BrokerResponseInvalidError:
        raw_bars = ()
    window = _window_from_bars(raw_bars, symbol)
    refusal = bar_evidence_refusal(window, policy=policy)
    if refusal is not None:
        return SymbolEvaluation(
            symbol=symbol,
            session=session,
            asset=asset,
            quote=quote,
            window=window,
            structure=None,
            geometry=None,
            quantity=None,
            rejection_reasons=(refusal,),
            evidence=tuple(evidence),
        )
    assert window is not None
    refusal = liquidity_refusal(window, policy=policy)
    if refusal is not None:
        return SymbolEvaluation(
            symbol=symbol,
            session=session,
            asset=asset,
            quote=quote,
            window=window,
            structure=None,
            geometry=None,
            quantity=None,
            rejection_reasons=(refusal,),
            evidence=tuple(evidence),
        )
    evidence.append(
        f"recent bar volume {window.evaluation_bar.volume:,} shares "
        f"(policy floor {policy.minimum_recent_share_volume:,})"
    )

    structure = evaluate_structure(window, lookback_bars=lookback)
    if not structure.is_long_candidate:
        return SymbolEvaluation(
            symbol=symbol,
            session=session,
            asset=asset,
            quote=quote,
            window=window,
            structure=structure,
            geometry=None,
            quantity=None,
            rejection_reasons=(RejectionReason.NO_BREAKOUT_STRUCTURE,),
            evidence=tuple(evidence),
        )
    evidence.append(
        f"close {structure.measurements.current_close} broke above the "
        f"{lookback}-bar range high {structure.measurements.range_high}"
    )
    evidence.append(f"low held above the prior swing low {structure.measurements.prior_swing_low}")
    evidence.append(
        f"volume {structure.measurements.current_volume:,} exceeded the "
        f"{lookback}-bar average {structure.measurements.reference_average_volume:,.0f}"
    )

    geometry = build_trade_plan_geometry(
        entry_price=quote.ask, structure=structure.measurements, policy=policy
    )
    if geometry is None:
        return SymbolEvaluation(
            symbol=symbol,
            session=session,
            asset=asset,
            quote=quote,
            window=window,
            structure=structure,
            geometry=None,
            quantity=None,
            rejection_reasons=(RejectionReason.STOP_INVALID,),
            evidence=tuple(evidence),
        )
    refusal = reward_risk_refusal(
        geometry, minimum_reward_risk_ratio=policy.minimum_reward_risk_ratio
    )
    if refusal is not None:
        return SymbolEvaluation(
            symbol=symbol,
            session=session,
            asset=asset,
            quote=quote,
            window=window,
            structure=structure,
            geometry=geometry,
            quantity=None,
            rejection_reasons=(refusal,),
            evidence=tuple(evidence),
        )

    quantity = position_size(
        entry_price=geometry.entry_price,
        stop_price=geometry.stop_price,
        maximum_loss=policy.maximum_loss_per_trade,
        maximum_capital_per_trade=configuration.maximum_capital_per_trade,
        maximum_percent_per_trade=configuration.maximum_percent_per_trade,
        deployable_capital=deployable_capital,
    )
    if quantity < 1:
        return SymbolEvaluation(
            symbol=symbol,
            session=session,
            asset=asset,
            quote=quote,
            window=window,
            structure=structure,
            geometry=geometry,
            quantity=quantity,
            rejection_reasons=(RejectionReason.QUANTITY_LESS_THAN_ONE,),
            evidence=tuple(evidence),
        )
    evidence.append(
        f"sized to {quantity} share(s): risk {geometry.risk_per_share}/share within the "
        f"{policy.maximum_loss_per_trade} maximum-loss budget"
    )

    return SymbolEvaluation(
        symbol=symbol,
        session=session,
        asset=asset,
        quote=quote,
        window=window,
        structure=structure,
        geometry=geometry,
        quantity=quantity,
        rejection_reasons=(),
        evidence=tuple(evidence),
    )


def _opportunity_from_evaluation(
    *,
    evaluation: SymbolEvaluation,
    session_date: str,
    generated_at: datetime,
    policy: OpportunityEnginePolicy,
    configuration_liquidation_time: time,
    operator_timezone: str,
    session_calendar_date: date,
) -> TradingOpportunity:
    opportunity_id = _opportunity_id(evaluation.symbol, session_date, generated_at)
    expires_at = generated_at + timedelta(seconds=policy.opportunity_validity_seconds)
    evidence_as_of = (
        evaluation.quote.captured_at
        if evaluation.quote and evaluation.quote.captured_at
        else generated_at
    )

    if evaluation.rejection_reasons:
        return TradingOpportunity(
            opportunity_id=opportunity_id,
            policy_fingerprint=policy.fingerprint,
            symbol=evaluation.symbol,
            generated_at=generated_at,
            expires_at=expires_at,
            evidence_as_of=evidence_as_of,
            session=evaluation.session,
            bid=evaluation.quote.bid if evaluation.quote else None,
            ask=evaluation.quote.ask if evaluation.quote else None,
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
            structure_model_id="",
            structure_model_version="",
            evidence=evaluation.evidence,
            quality_score=None,
            quality_model_id="",
            quality_model_version="",
            rejection_reasons=evaluation.rejection_reasons,
            status=OpportunityStatus.REJECTED,
        )

    assert evaluation.geometry is not None and evaluation.quantity is not None
    assert evaluation.structure is not None and evaluation.quote is not None
    geometry = evaluation.geometry
    liquidation_at = compute_mandatory_liquidation_at(
        session_date=session_calendar_date,
        liquidation_time=configuration_liquidation_time,
        operator_timezone=operator_timezone,
    )
    valid_until = opportunity_valid_until(
        generated_at=generated_at, policy=policy, liquidation_at=liquidation_at
    )
    bid, ask = evaluation.quote.bid, evaluation.quote.ask
    assert bid is not None and ask is not None
    spread_percent = (ask - bid) / ((ask + bid) / Decimal(2)) * Decimal(100)
    # `quote_quality_refusal` already required a non-None `captured_at` to reach this point.
    assert evaluation.quote.captured_at is not None
    quote_age_seconds = Decimal(
        max((generated_at - evaluation.quote.captured_at).total_seconds(), 0)
    )
    quality_score = opportunity_quality(
        spread_percent=spread_percent,
        maximum_spread_percent=Decimal("1"),
        recent_volume=evaluation.structure.measurements.current_volume,
        minimum_recent_share_volume=policy.minimum_recent_share_volume,
        structure=evaluation.structure.measurements,
        geometry=geometry,
        minimum_reward_risk_ratio=policy.minimum_reward_risk_ratio,
        quote_age_seconds=quote_age_seconds,
        maximum_quote_age_seconds=300,
    )
    status = (
        OpportunityStatus.ACTIONABLE
        if session_permits_actionable(evaluation.session)
        else OpportunityStatus.CANDIDATE
    )
    return TradingOpportunity(
        opportunity_id=opportunity_id,
        policy_fingerprint=policy.fingerprint,
        symbol=evaluation.symbol,
        generated_at=generated_at,
        expires_at=valid_until,
        evidence_as_of=evidence_as_of,
        session=evaluation.session,
        bid=bid,
        ask=ask,
        spread_percent=spread_percent.quantize(Decimal("0.01")),
        entry_price=geometry.entry_price,
        stop_price=geometry.stop_price,
        target_price=geometry.target_price,
        risk_per_share=geometry.risk_per_share,
        reward_per_share=geometry.reward_per_share,
        reward_risk_ratio=geometry.reward_risk_ratio,
        quantity=evaluation.quantity,
        notional=(geometry.entry_price * Decimal(evaluation.quantity)).quantize(Decimal("0.01")),
        maximum_loss=(geometry.risk_per_share * Decimal(evaluation.quantity)).quantize(
            Decimal("0.01")
        ),
        mandatory_liquidation_at=liquidation_at,
        structure_model_id="BOUNDED_RANGE_BREAKOUT_HIGHER_LOW_VOLUME",
        structure_model_version="1",
        evidence=evaluation.evidence,
        quality_score=quality_score,
        quality_model_id="SPREAD_LIQUIDITY_TREND_REWARD_RISK_FRESHNESS_WEIGHTED_SUM",
        quality_model_version="1",
        rejection_reasons=(),
        status=status,
    )


@dataclass(frozen=True, slots=True)
class GenerateOpportunitiesCommand:
    session_date: str  # "YYYY-MM-DD"
    generated_at: datetime


class GenerateOpportunitiesHandler:
    """Evaluate the whole watchlist once and persist one opportunity per symbol.

    Reads only: no order-shaped broker call exists on `PaperBrokerPort`/`PaperMarketDataPort`/
    `IntradayBarsPort` this handler could reach even by mistake (see the Protocol definitions).
    """

    __slots__ = (
        "_configuration",
        "_policy",
        "_broker",
        "_market_data",
        "_bars",
        "_opportunities",
    )

    def __init__(
        self,
        *,
        configuration: OperatorTradingConfiguration,
        policy: OpportunityEnginePolicy,
        broker: PaperBrokerPort,
        market_data: PaperMarketDataPort,
        bars: IntradayBarsPort,
        opportunities: OpportunityRepository,
    ) -> None:
        self._configuration = configuration
        self._policy = policy
        self._broker = broker
        self._market_data = market_data
        self._bars = bars
        self._opportunities = opportunities

    def handle(self, command: GenerateOpportunitiesCommand) -> tuple[TradingOpportunity, ...]:
        clock = self._broker.fetch_clock()
        broker_now = BoundedInstant(earliest=clock.timestamp, latest=clock.timestamp)
        session = market_session_state(
            is_open=clock.is_open,
            broker_now=broker_now,
            earliest_entry_time=self._configuration.earliest_entry_time,
            latest_entry_time=self._configuration.latest_entry_time,
            operator_timezone=self._configuration.operator_timezone,
        )
        deployable_capital = _account_deployable_capital(self._broker, self._configuration)
        session_calendar_date = clock.timestamp.astimezone(
            ZoneInfo(self._configuration.operator_timezone)
        ).date()

        results: list[TradingOpportunity] = []
        for symbol in self._configuration.watchlist:
            try:
                evaluation = _evaluate_symbol(
                    symbol=symbol,
                    configuration=self._configuration,
                    policy=self._policy,
                    broker=self._broker,
                    market_data=self._market_data,
                    bars_port=self._bars,
                    session=session,
                    broker_now=broker_now,
                    deployable_capital=deployable_capital,
                )
            except BrokerResponseInvalidError:
                evaluation = SymbolEvaluation(
                    symbol=symbol,
                    session=session,
                    asset=None,
                    quote=None,
                    window=None,
                    structure=None,
                    geometry=None,
                    quantity=None,
                    rejection_reasons=(RejectionReason.INSUFFICIENT_EVIDENCE,),
                    evidence=(),
                )
            opportunity = _opportunity_from_evaluation(
                evaluation=evaluation,
                session_date=command.session_date,
                generated_at=command.generated_at,
                policy=self._policy,
                configuration_liquidation_time=self._configuration.mandatory_liquidation_time,
                operator_timezone=self._configuration.operator_timezone,
                session_calendar_date=session_calendar_date,
            )
            results.append(self._opportunities.save(opportunity))
        return tuple(results)


def select_top_actionable(
    opportunities: tuple[TradingOpportunity, ...], *, top_n: int
) -> tuple[TradingOpportunity, ...]:
    """Phase 14: hard fail first (already done -- only ACTIONABLE rows are eligible here),
    rank survivors second, return only the top N."""
    actionable = tuple(o for o in opportunities if o.status is OpportunityStatus.ACTIONABLE)
    ranked = sorted(actionable, key=rank_sort_key)
    return tuple(ranked[:top_n])


def _reverify(
    stored: TradingOpportunity,
    *,
    configuration: OperatorTradingConfiguration,
    policy: OpportunityEnginePolicy,
    broker: PaperBrokerPort,
    market_data: PaperMarketDataPort,
    bars: IntradayBarsPort,
) -> SymbolEvaluation:
    clock = broker.fetch_clock()
    broker_now = BoundedInstant(earliest=clock.timestamp, latest=clock.timestamp)
    session = market_session_state(
        is_open=clock.is_open,
        broker_now=broker_now,
        earliest_entry_time=configuration.earliest_entry_time,
        latest_entry_time=configuration.latest_entry_time,
        operator_timezone=configuration.operator_timezone,
    )
    deployable_capital = _account_deployable_capital(broker, configuration)
    return _evaluate_symbol(
        symbol=stored.symbol,
        configuration=configuration,
        policy=policy,
        broker=broker,
        market_data=market_data,
        bars_port=bars,
        session=session,
        broker_now=broker_now,
        deployable_capital=deployable_capital,
    )


class ReviewOpportunityHandler:
    """Re-verify a stored ACTIONABLE opportunity against fresh evidence. Sends nothing."""

    __slots__ = ("_configuration", "_policy", "_broker", "_market_data", "_bars", "_opportunities")

    def __init__(
        self,
        *,
        configuration: OperatorTradingConfiguration,
        policy: OpportunityEnginePolicy,
        broker: PaperBrokerPort,
        market_data: PaperMarketDataPort,
        bars: IntradayBarsPort,
        opportunities: OpportunityRepository,
    ) -> None:
        self._configuration = configuration
        self._policy = policy
        self._broker = broker
        self._market_data = market_data
        self._bars = bars
        self._opportunities = opportunities

    def handle(self, opportunity_id: str, *, at: datetime) -> TradingOpportunity:
        stored = self._opportunities.get(opportunity_id)
        if stored is None:
            raise OpportunityEngineRefusedError(f"no opportunity {opportunity_id!r} exists")
        if stored.status is not OpportunityStatus.ACTIONABLE:
            raise OpportunityEngineRefusedError(
                f"opportunity {opportunity_id!r} is {stored.status.value}, not ACTIONABLE"
            )
        if at >= stored.expires_at:
            self._opportunities.transition(
                opportunity_id=opportunity_id, target=OpportunityStatus.EXPIRED, at=at
            )
            raise OpportunityEngineRefusedError(
                "this opportunity expired before it could be reviewed. Nothing was sent."
            )
        fresh = _reverify(
            stored,
            configuration=self._configuration,
            policy=self._policy,
            broker=self._broker,
            market_data=self._market_data,
            bars=self._bars,
        )
        if (
            fresh.rejection_reasons
            or fresh.geometry is None
            or fresh.quantity is None
            or fresh.quantity < 1
        ):
            self._opportunities.transition(
                opportunity_id=opportunity_id, target=OpportunityStatus.INVALIDATED, at=at
            )
            reasons = (
                ", ".join(r.value for r in fresh.rejection_reasons) or "conditions deteriorated"
            )
            raise OpportunityEngineRefusedError(
                f"OPPORTUNITY INVALIDATED: {reasons}. Nothing was sent; review the watchlist again."
            )
        assert stored.entry_price is not None
        moved = entry_moved_refusal(
            evidence_entry_price=stored.entry_price,
            current_price=fresh.geometry.entry_price,
            policy=self._policy,
        )
        if moved is not None:
            self._opportunities.transition(
                opportunity_id=opportunity_id, target=OpportunityStatus.INVALIDATED, at=at
            )
            raise OpportunityEngineRefusedError(
                f"OPPORTUNITY INVALIDATED: {moved.value}. The plan was not silently repriced; "
                "review the watchlist again for current terms."
            )
        return stored


@dataclass(frozen=True, slots=True)
class ApproveOpportunityCommand:
    opportunity_id: str
    decision_id: str
    approved_by: str
    at: datetime


class ApproveOpportunityHandler:
    """Record the Owner's APPROVE decision, after re-verifying everything once more.

    Durably records OWNER_APPROVED and returns the approved plan. THIS IS WHERE THIS
    MILESTONE STOPS (Phase 17-18): nothing here calls a broker submission method, and none
    exists to call from this module (see the module docstring and the architecture test).
    """

    __slots__ = ("_review", "_configuration", "_opportunities", "_decisions")

    def __init__(
        self,
        *,
        configuration: OperatorTradingConfiguration,
        policy: OpportunityEnginePolicy,
        broker: PaperBrokerPort,
        market_data: PaperMarketDataPort,
        bars: IntradayBarsPort,
        opportunities: OpportunityRepository,
        decisions: OpportunityDecisionRepository,
    ) -> None:
        self._review = ReviewOpportunityHandler(
            configuration=configuration,
            policy=policy,
            broker=broker,
            market_data=market_data,
            bars=bars,
            opportunities=opportunities,
        )
        self._configuration = configuration
        self._opportunities = opportunities
        self._decisions = decisions

    def handle(self, command: ApproveOpportunityCommand) -> TradingOpportunity:
        existing = self._decisions.for_opportunity(command.opportunity_id)
        if existing is not None:
            raise OpportunityEngineRefusedError(
                f"opportunity {command.opportunity_id!r} already has a recorded decision "
                f"({existing.action.value}); nothing was done"
            )
        reverified = self._review.handle(command.opportunity_id, at=command.at)
        approved = self._opportunities.transition(
            opportunity_id=command.opportunity_id,
            target=OpportunityStatus.OWNER_APPROVED,
            at=command.at,
        )
        self._decisions.save(
            OpportunityDecision(
                decision_id=command.decision_id,
                opportunity_id=command.opportunity_id,
                action=OwnerOpportunityAction.APPROVE,
                decided_by=command.approved_by,
                decided_at=command.at,
            )
        )
        del reverified  # confirmed identical to `approved`'s pre-transition terms; not reused
        return approved


@dataclass(frozen=True, slots=True)
class IgnoreOpportunityCommand:
    opportunity_id: str
    decision_id: str
    ignored_by: str
    at: datetime


class IgnoreOpportunityHandler:
    """Record the Owner's IGNORE decision. No re-verification needed: ignoring commits to
    nothing and cannot be made unsafe by stale evidence.

    Only an ACTIONABLE opportunity can be ignored, matching
    `ALLOWED_OPPORTUNITY_TRANSITIONS`: a CANDIDATE row (one the Owner was shown only as
    research, never as something to act on) has nothing to "ignore" yet -- it simply expires
    or is superseded by a later generation."""

    __slots__ = ("_opportunities", "_decisions")

    def __init__(
        self, *, opportunities: OpportunityRepository, decisions: OpportunityDecisionRepository
    ) -> None:
        self._opportunities = opportunities
        self._decisions = decisions

    def handle(self, command: IgnoreOpportunityCommand) -> TradingOpportunity:
        existing = self._decisions.for_opportunity(command.opportunity_id)
        if existing is not None:
            raise OpportunityEngineRefusedError(
                f"opportunity {command.opportunity_id!r} already has a recorded decision "
                f"({existing.action.value}); nothing was done"
            )
        stored = self._opportunities.get(command.opportunity_id)
        if stored is None:
            raise OpportunityEngineRefusedError(f"no opportunity {command.opportunity_id!r} exists")
        if stored.status is not OpportunityStatus.ACTIONABLE:
            raise OpportunityEngineRefusedError(
                f"opportunity {command.opportunity_id!r} is {stored.status.value}, not "
                "ACTIONABLE; nothing to ignore"
            )
        ignored = self._opportunities.transition(
            opportunity_id=command.opportunity_id,
            target=OpportunityStatus.OWNER_IGNORED,
            at=command.at,
        )
        self._decisions.save(
            OpportunityDecision(
                decision_id=command.decision_id,
                opportunity_id=command.opportunity_id,
                action=OwnerOpportunityAction.IGNORE,
                decided_by=command.ignored_by,
                decided_at=command.at,
            )
        )
        return ignored
