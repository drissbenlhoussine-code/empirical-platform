"""MILESTONE-086 -- loading one deterministic SIMULATION day into the real engine.

The Operator Console shows what the engine holds. To have something to show without a
network, this module stages a day: it saves the simulation trading configuration, captures
an evidence watermark, opens an evaluation context, and asks the REAL MILESTONE-084
paper-bound proposal handler to evaluate one candidate per staged symbol from fixture
market inputs. Whatever M084 refuses is refused (a NO_TRADE is reported, not forced), and
whatever it proposes is a genuine proposal with genuine risk checks, deadlines and a content
fingerprint -- the same rows a research pipeline would leave behind.

The fixture quotes are OPERATOR-ASSERTED SIMULATION INPUTS. They are not market
observations and the console labels them as such; the proposal's own `provider_id` says
`SIMULATION`.

Idempotent: every identifier is derived from the day and the symbol, so loading the same
day twice creates nothing new.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from datetime import time as clock_time
from decimal import Decimal

from empirical_platform.decision_candidate.evaluation_context import build_evaluation_context
from empirical_platform.decision_candidate.evaluation_evidence_watermark_repository import (
    EvaluationEvidenceWatermarkRepository,
)
from empirical_platform.decision_candidate.operator_trading_configuration import (
    AccountMode,
    KillSwitchState,
    LimitPricePolicy,
    OperatorTradingConfiguration,
    OrderType,
    TradingSession,
)
from empirical_platform.decision_candidate.paper_execution_repositories import PaperBrokerPort
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
from empirical_platform.shared.brokerage.paper_time import PaperTimeSource
from empirical_platform.usecases.operator_console import ConsoleRepositories
from empirical_platform.usecases.paper_execution import (
    PreparePaperBoundTradeProposalCommand,
    PreparePaperBoundTradeProposalHandler,
)

__all__ = [
    "EvaluationEvidenceWatermarkRepository",
    "SIMULATION_CONFIGURATION_ID",
    "SIMULATION_QUOTES",
    "SimulationDayReport",
    "load_simulation_day",
    "simulation_configuration",
    "simulation_timezone_for",
]

SIMULATION_CONFIGURATION_ID = "CFG-086-SIM"
_PROVIDER = "SIMULATION"

#: Staged bid/ask per symbol. Asserted inputs for a deterministic day, not observations.
SIMULATION_QUOTES: Mapping[str, tuple[str, str]] = {
    "AAPL": ("227.40", "227.50"),
    "MSFT": ("418.10", "418.30"),
    "NVDA": ("121.90", "122.00"),
    "AMZN": ("186.20", "186.30"),
    "GOOGL": ("164.70", "164.80"),
    "META": ("512.40", "512.70"),
    "JPM": ("208.10", "208.20"),
    "V": ("284.30", "284.45"),
    "JNJ": ("161.20", "161.30"),
    "PG": ("168.50", "168.60"),
    "XOM": ("117.80", "117.90"),
    "KO": ("70.10", "70.15"),
}


def simulation_timezone_for(now: datetime) -> str:
    """A fixed-offset zone in which `now` reads about ten in the morning.

    The simulation day is opened whenever the Owner opens the console. The engine's entry
    window, expiry and mandatory liquidation are times of the operator's day, and a proposal
    made late in that day is rightly refused (LIQUIDATION_DEADLINE_UNREACHABLE). Rather than
    weaken those rules, the simulation places its operator's day so that the current instant is
    mid-morning with a full session ahead. `Etc/GMT±N` names carry the inverted POSIX sign.
    """
    offset = (10 - now.astimezone(UTC).hour) % 24
    if offset > 14:
        offset -= 24
    if offset == 0:
        return "Etc/GMT"
    return f"Etc/GMT{'-' if offset > 0 else '+'}{abs(offset)}"


def simulation_configuration(
    *, watchlist: tuple[str, ...], operator_timezone: str = "UTC", version: int = 1
) -> OperatorTradingConfiguration:
    """The simulation day's trading rules. Displayed on Safety from this same record."""
    return OperatorTradingConfiguration(
        configuration_governance_id=SIMULATION_CONFIGURATION_ID,
        configuration_version=version,
        base_currency="USD",
        permitted_markets=("XNAS",),
        watchlist=watchlist,
        prohibited_instruments=("PENNY",),
        maximum_deployable_capital=Decimal("100000"),
        maximum_capital_per_trade=Decimal("2000"),
        maximum_percent_per_trade=Decimal("5"),
        minimum_cash_reserve=Decimal("10000"),
        maximum_simultaneous_positions=12,
        maximum_daily_loss=Decimal("1000"),
        maximum_daily_order_count=20,
        minimum_price=Decimal("5"),
        maximum_price=Decimal("5000"),
        minimum_liquidity_shares=100_000,
        maximum_spread_percent=Decimal("1"),
        maximum_estimated_slippage_percent=Decimal("1"),
        maximum_evidence_age_seconds=86_400,
        maximum_market_data_age_seconds=60,
        permitted_session=TradingSession.REGULAR,
        # The simulation runs whenever the Owner opens the console, so the entry window is
        # the whole operator day in a zone chosen so that "now" is mid-morning (see
        # `simulation_timezone_for`). A Paper configuration would carry the real session window.
        earliest_entry_time=clock_time(0, 1),
        latest_entry_time=clock_time(23, 58),
        mandatory_liquidation_time=clock_time(23, 59),
        operator_timezone=operator_timezone,
        exchange_calendar_policy="XNAS-REGULAR-2026",
        proposal_expiry_seconds=3600,
        approval_expiry_seconds=900,
        default_order_type=OrderType.LIMIT,
        permitted_order_types=(OrderType.LIMIT,),
        limit_price_policy=LimitPricePolicy.ASK,
        stop_loss_percent=Decimal("2"),
        profit_exit_percent=Decimal("4"),
        maximum_leverage=Decimal("1"),
        short_selling_permitted=False,
        overnight_positions_permitted=False,
        account_mode=AccountMode.PREPARATION,
        kill_switch=KillSwitchState.DISENGAGED,
    )


@dataclass(frozen=True, slots=True)
class SimulationDayReport:
    day: str
    configuration_version: int
    evaluation_context_id: str
    proposed: tuple[str, ...]
    already_present: tuple[str, ...]
    refused: tuple[tuple[str, str], ...]


def load_simulation_day(
    *,
    repositories: ConsoleRepositories,
    watermarks: EvaluationEvidenceWatermarkRepository,
    broker: PaperBrokerPort,
    time_source: PaperTimeSource,
    clock: Callable[[], datetime],
    symbols: tuple[str, ...],
    quotes: Mapping[str, tuple[str, str]] = SIMULATION_QUOTES,
    day: date | None = None,
) -> SimulationDayReport:
    now = clock()
    the_day = day or now.date()
    stamp = the_day.strftime("%Y%m%d")
    configurations = repositories.configurations
    zone = simulation_timezone_for(now)
    configuration = configurations.latest(SIMULATION_CONFIGURATION_ID)
    if configuration is None or configuration.operator_timezone != zone:
        # A new VERSION, never an edit: earlier proposals keep the version they were judged under.
        configuration = configurations.save(
            simulation_configuration(
                watchlist=tuple(sorted(symbols)),
                operator_timezone=zone,
                version=1 if configuration is None else configuration.configuration_version + 1,
            )
        )

    context_id = f"ECX-086-{stamp}"
    context = repositories.contexts.get(context_id)
    if context is None:
        watermark = watermarks.capture(watermark_governance_id=f"WM-086-{stamp}")
        context = repositories.contexts.save(
            build_evaluation_context(
                evaluation_context_id=context_id,
                configuration=configuration,
                watermark=watermark,
                quote_id=f"QTE-086-{stamp}",
                account_snapshot_id=f"ACC-086-{stamp}",
                session_id=f"SES-086-{stamp}",
                cost_estimate_id=f"CST-086-{stamp}",
                instrument_universe_version="SIMULATION-UNIVERSE-2026",
                strategy_version="M086-SIMULATION-DAY",
                created_at=now,
            )
        )

    handler = PreparePaperBoundTradeProposalHandler(
        configurations=configurations,
        contexts=repositories.contexts,
        proposals=repositories.proposals,
        time_bases=repositories.time_bases,
        broker=broker,
        time_source=time_source,
    )
    proposed: list[str] = []
    present: list[str] = []
    refused: list[tuple[str, str]] = []
    observed_at = now - timedelta(seconds=5)
    for symbol in symbols:
        proposal_id = f"PRP-086-{stamp}-{symbol}"
        if repositories.proposals.get(proposal_id) is not None:
            present.append(symbol)
            continue
        quote = quotes.get(symbol)
        if quote is None:
            refused.append((symbol, "no staged quote"))
            continue
        bid, ask = Decimal(quote[0]), Decimal(quote[1])
        result = handler.handle(
            PreparePaperBoundTradeProposalCommand(
                proposal_governance_id=proposal_id,
                evaluation_context_id=context.evaluation_context_id,
                symbol=symbol,
                quote=QuoteSnapshot(
                    quote_id=f"QTE-086-{stamp}-{symbol}",
                    provider_id=_PROVIDER,
                    symbol=symbol,
                    bid=bid,
                    ask=ask,
                    last_trade=ask,
                    observed_at=observed_at,
                    feed_kind=DataFeedKind.REAL_TIME,
                ),
                account=AccountSnapshot(
                    account_snapshot_id=f"ACC-086-{stamp}",
                    provider_id=_PROVIDER,
                    account_reference="SIMULATION-ACCOUNT",
                    base_currency="USD",
                    cash_available=Decimal("100000"),
                    equity_total=Decimal("100000"),
                    realized_pnl_today=Decimal("0"),
                    orders_submitted_today=0,
                    observed_at=observed_at,
                ),
                session=SessionSnapshot(
                    session_id=f"SES-086-{stamp}",
                    provider_id=_PROVIDER,
                    market="XNAS",
                    status=MarketStatus.OPEN,
                    observed_at=observed_at,
                ),
                instrument=InstrumentMetadata(
                    symbol=symbol, market="XNAS", currency="USD", is_fractionable=False, lot_size=1
                ),
                liquidity=LiquiditySnapshot(
                    symbol=symbol, average_daily_volume_shares=50_000_000, observed_at=observed_at
                ),
                cost_estimate=TradingCostEstimate(
                    estimate_id=f"CST-086-{stamp}",
                    provider_id=_PROVIDER,
                    symbol=symbol,
                    commission=Decimal("0.00"),
                    estimated_slippage_percent=Decimal("0.1"),
                    observed_at=observed_at,
                ),
                positions=(),
                open_orders=(),
                evidence_age_seconds=Decimal("5"),
            )
        )
        if result.outcome.proposal is None:
            reason = result.outcome.no_trade_reason
            refused.append((symbol, reason.value if reason is not None else "refused"))
        else:
            proposed.append(symbol)
    return SimulationDayReport(
        day=the_day.isoformat(),
        configuration_version=configuration.configuration_version,
        evaluation_context_id=context.evaluation_context_id,
        proposed=tuple(proposed),
        already_present=tuple(present),
        refused=tuple(refused),
    )


def utc_now() -> datetime:
    return datetime.now(UTC)
