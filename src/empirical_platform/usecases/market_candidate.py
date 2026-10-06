"""Route verified market evidence through the existing canonical v1 proposal engine."""

from collections.abc import Callable
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from empirical_platform.decision_candidate.helsinki_calendar import require_helsinki_open
from empirical_platform.decision_candidate.market_access_ports import (
    MarketCandidateDataPort,
    MarketJournal,
)
from empirical_platform.decision_candidate.market_identity import Currency, fingerprint
from empirical_platform.decision_candidate.market_plan import MarketPlan, OrderPurpose
from empirical_platform.decision_candidate.operator_trading_configuration import (
    KillSwitchState,
    OperatorTradingConfiguration,
)
from empirical_platform.decision_candidate.product_market_inputs import (
    AccountSnapshot,
    DataFeedKind,
    InstrumentMetadata,
    LiquiditySnapshot,
    MarketStatus,
    QuoteSnapshot,
    SessionSnapshot,
    TradingCostEstimate,
)
from empirical_platform.decision_candidate.trade_proposal import evaluate_trade_proposal
from empirical_platform.usecases.market_access import (
    bind_market_proposal,
    require_acceptance_policy,
)


def prepare_market_plan(
    *,
    broker: MarketCandidateDataPort,
    journal: MarketJournal,
    policy: OperatorTradingConfiguration,
    symbol: str,
    costs: TradingCostEstimate,
    cost_currency: Currency,
    now: Callable[[], datetime],
) -> MarketPlan:
    require_acceptance_policy(policy)
    if journal.kill_switch() or policy.kill_switch is KillSwitchState.ENGAGED:
        raise ValueError("kill switch blocks candidate preparation")
    if any(journal.dispatch(p.plan_id, OrderPurpose.ENTRY) for p in journal.active_plans()):
        raise ValueError("unclosed or UNKNOWN durable entry prevents a new candidate")
    if cost_currency is not Currency.EUR or costs.symbol != symbol:
        raise ValueError("explicit instrument-specific EUR cost evidence required")
    contract = broker.resolve(symbol)
    last, last_at = broker.last_trade(contract.instrument)
    volume, volume_at = broker.average_daily_volume(contract.instrument)
    account = broker.account()
    positions, orders = broker.positions(), broker.open_orders()
    quote = broker.quote(contract.instrument)
    at = now()
    quote.validate(contract.instrument, at, policy.maximum_market_data_age_seconds)
    for observed in (last_at, volume_at, account.observed_at, costs.observed_at):
        if not 0 <= (at - observed).total_seconds() <= policy.maximum_market_data_age_seconds:
            raise ValueError("all candidate evidence must be fresh, including the cost estimate")
    if account.identity != broker.identity or not account.ready or positions or orders:
        raise ValueError("verified flat ready account required")
    require_helsinki_open(
        at, broker_liquid_open=contract.liquid_open, broker_liquid_close=contract.liquid_close
    )
    digest = fingerprint(
        {
            "instrument": contract.instrument.fingerprint,
            "account": account.identity.reference,
            "at": at.isoformat(),
            "bid": str(quote.bid),
            "ask": str(quote.ask),
            "last": str(last),
            "volume": volume,
            "cost_id": costs.estimate_id,
            "commission": str(costs.commission),
            "slippage_percent": str(costs.estimated_slippage_percent),
        }
    )
    prefix = digest[:32]
    local = at.astimezone(ZoneInfo(policy.operator_timezone))
    outcome = evaluate_trade_proposal(
        configuration=policy,
        evaluation_context_id="MKT-" + prefix,
        proposal_governance_id="MPLAN-" + prefix,
        evaluated_at=at,
        symbol=symbol,
        quote=QuoteSnapshot(
            "Q-" + prefix,
            "IBKR_PAPER",
            symbol,
            quote.bid,
            quote.ask,
            last,
            min(quote.source_at, last_at),
            DataFeedKind.REAL_TIME,
        ),
        account=AccountSnapshot(
            "A-" + prefix,
            "IBKR_PAPER",
            account.identity.reference,
            "EUR",
            account.cash,
            account.equity,
            account.realized_pnl,
            journal.entry_count(local.replace(hour=0, minute=0, second=0, microsecond=0)),
            account.observed_at,
        ),
        session=SessionSnapshot("S-" + prefix, "NASDAQ-XHEL", "XHEL", MarketStatus.OPEN, at),
        instrument=InstrumentMetadata(symbol, "XHEL", "EUR", False, 1),
        liquidity=LiquiditySnapshot(symbol, volume, volume_at),
        cost_estimate=costs,
        positions=(),
        open_orders=(),
        evidence_age_seconds=Decimal(
            str(
                (
                    at
                    - min(
                        quote.source_at, last_at, volume_at, account.observed_at, costs.observed_at
                    )
                ).total_seconds()
            )
        ),
    )
    if outcome.proposal is None:
        raise ValueError("canonical proposal engine refused this evidence; no acceptance bypass")
    plan = bind_market_proposal(
        outcome.proposal,
        policy=policy,
        account=account.identity,
        contract=contract,
        quote=quote,
        now=at,
    )
    journal.save_plan(plan)
    return plan
