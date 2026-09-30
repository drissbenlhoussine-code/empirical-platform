"""MILESTONE-090 Phase 19/20 -- replay the Opportunity Engine over REAL historical minute bars.

    python tools/m090_replay.py --symbols AAPL,MSFT,SPY,QQQ --sessions 5
    python tools/m090_replay.py --symbols AAPL --sessions 3 --report-path external-review/x.md

READ-ONLY, ALWAYS. The only network capability this script touches is
`AlpacaPaperMarketDataClient.fetch_minute_bars` (real IEX-feed 1-minute bars, GET only). No
object reachable from this module can place, modify or cancel an order -- the same client class
`entrypoints/_paper_composition.py` already pins to the data host and nothing broader. Credentials
are read once, from the process environment, via the SAME `credentials_from_environment` helper
M085's composition already uses -- no new credential-loading path is invented here.

A BOUNDED SAMPLE, NOT A BACKTEST. `--sessions` defaults to a small number of recent, already-
COMPLETED regular trading sessions (never today, so a session already fully happened). This is
deliberately small per the M090 mission's Phase 20 instruction: report honestly, do not optimize
until it looks profitable, and make no claim of expected profitability from a small sample.

THE REPORT SEPARATES TWO DIFFERENT CLAIMS, ALWAYS. ENGINE SIGNAL QUALITY (did the deterministic,
look-ahead-safe rules behave as designed: gate counts, rejection reasons, reward/risk and
maximum-loss distributions, time-of-day distribution of ACTIONABLE decisions) is never conflated
with HYPOTHETICAL HISTORICAL OUTCOME (what the replay's stop/target/mandatory-exit resolution
says WOULD have happened, under the replay harness's one documented simplification: a
zero-spread synthetic quote, each bar's own close standing in for both bid and ask -- see
`usecases.opportunity_engine_replay`'s own module docstring).
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from statistics import median
from zoneinfo import ZoneInfo

from empirical_platform.decision_candidate.operator_trading_configuration import (
    AccountMode,
    KillSwitchState,
    LimitPricePolicy,
    OperatorTradingConfiguration,
    OrderType,
    TradingSession,
)
from empirical_platform.decision_candidate.opportunity_engine import (
    OPPORTUNITY_ENGINE_POLICY_VERSION,
    OpportunityEnginePolicy,
)
from empirical_platform.decision_candidate.opportunity_engine_repositories import IntradayBarsPort
from empirical_platform.shared.brokerage.alpaca_paper import (
    AlpacaPaperMarketDataClient,
    credentials_from_environment,
)
from empirical_platform.usecases.opportunity_engine_replay import (
    ReplayDecision,
    ReplaySessionResult,
    fetch_session_bars,
    replay_session,
)

__all__ = [
    "DEFAULT_SYMBOLS",
    "build_report",
    "collect_results",
    "default_configuration",
    "default_policy",
    "recent_completed_session_dates",
]

REPO_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_SYMBOLS: tuple[str, ...] = ("AAPL", "MSFT", "QQQ", "SPY")
_SESSION_START = time(9, 30)
_SESSION_END = time(16, 0)
_OPERATOR_TIMEZONE = "America/New_York"
_DEPLOYABLE_CAPITAL = Decimal("10000")


def default_configuration(symbols: tuple[str, ...]) -> OperatorTradingConfiguration:
    """This CLI's own defaults -- a research run, not a durable production configuration.

    `watchlist` is sorted: `OperatorTradingConfiguration` requires every symbol list in
    canonical ascending order, and the CLI's own `--symbols` argument makes no such promise.
    """
    return OperatorTradingConfiguration(
        configuration_governance_id="CFG-M090-REPLAY-CLI",
        configuration_version=1,
        base_currency="USD",
        permitted_markets=("ARCA", "NASDAQ", "NYSE"),
        watchlist=tuple(sorted(symbols)),
        prohibited_instruments=(),
        maximum_deployable_capital=_DEPLOYABLE_CAPITAL,
        maximum_capital_per_trade=Decimal("2000"),
        maximum_percent_per_trade=Decimal("50"),
        minimum_cash_reserve=Decimal("1000"),
        maximum_simultaneous_positions=3,
        maximum_daily_loss=Decimal("500"),
        maximum_daily_order_count=10,
        minimum_price=Decimal("5"),
        maximum_price=Decimal("5000"),
        minimum_liquidity_shares=100_000,
        maximum_spread_percent=Decimal("1"),
        maximum_estimated_slippage_percent=Decimal("1"),
        maximum_evidence_age_seconds=86_400,
        maximum_market_data_age_seconds=60,
        permitted_session=TradingSession.REGULAR,
        earliest_entry_time=time(10, 0),
        latest_entry_time=time(15, 30),
        mandatory_liquidation_time=time(15, 45),
        operator_timezone=_OPERATOR_TIMEZONE,
        exchange_calendar_policy="XNAS-REGULAR-2026",
        proposal_expiry_seconds=300,
        approval_expiry_seconds=120,
        default_order_type=OrderType.LIMIT,
        permitted_order_types=(OrderType.LIMIT, OrderType.MARKET),
        limit_price_policy=LimitPricePolicy.ASK,
        stop_loss_percent=Decimal("2"),
        profit_exit_percent=Decimal("4"),
        maximum_leverage=Decimal("1"),
        short_selling_permitted=False,
        overnight_positions_permitted=False,
        account_mode=AccountMode.PREPARATION,
        kill_switch=KillSwitchState.DISENGAGED,
    )


def default_policy() -> OpportunityEnginePolicy:
    return OpportunityEnginePolicy(
        policy_version=OPPORTUNITY_ENGINE_POLICY_VERSION,
        structure_lookback_bars=5,
        minimum_recent_share_volume=1000,
        minimum_reward_risk_ratio=Decimal("2"),
        maximum_loss_per_trade=Decimal("100"),
        top_n=5,
        entry_tolerance_percent=Decimal("0.5"),
        opportunity_validity_seconds=300,
    )


def recent_completed_session_dates(count: int, *, before: date) -> tuple[date, ...]:
    """The `count` most recent weekdays strictly before `before`, oldest first.

    A calendar approximation, not the real exchange calendar: a market holiday in the window
    simply yields zero bars for that date (`fetch_session_bars` returns `()`, `collect_results`
    skips it) rather than crashing -- reported as fewer observed sessions, never faked.
    """
    if count < 1:
        raise ValueError("count must be at least 1")
    found: list[date] = []
    cursor = before - timedelta(days=1)
    while len(found) < count:
        if cursor.weekday() < 5:
            found.append(cursor)
        cursor -= timedelta(days=1)
    return tuple(reversed(found))


def _mandatory_liquidation_instant(
    session_date: date, configuration: OperatorTradingConfiguration
) -> datetime:
    zone = ZoneInfo(configuration.operator_timezone)
    local = datetime.combine(session_date, configuration.mandatory_liquidation_time, tzinfo=zone)
    return local.astimezone(UTC)


def collect_results(
    bars_port: IntradayBarsPort,
    symbols: Sequence[str],
    session_dates: Sequence[date],
    *,
    policy: OpportunityEnginePolicy,
    configuration: OperatorTradingConfiguration,
    deployable_capital: Decimal = _DEPLOYABLE_CAPITAL,
) -> tuple[ReplaySessionResult, ...]:
    """One `fetch_session_bars` + `replay_session` per (session date, symbol) pair.

    A session/symbol with no returned bars (holiday, no data, feed gap) is silently skipped --
    it contributes zero observations, never a fabricated one.
    """
    results: list[ReplaySessionResult] = []
    for session_date in session_dates:
        liquidation_at = _mandatory_liquidation_instant(session_date, configuration)
        for symbol in symbols:
            bars = fetch_session_bars(
                bars_port,
                symbol,
                session_date,
                session_start=_SESSION_START,
                session_end=_SESSION_END,
                operator_timezone=configuration.operator_timezone,
            )
            if not bars:
                continue
            results.append(
                replay_session(
                    symbol=symbol,
                    session_date=session_date,
                    bars=bars,
                    policy=policy,
                    configuration=configuration,
                    deployable_capital=deployable_capital,
                    mandatory_liquidation_at=liquidation_at,
                )
            )
    return tuple(results)


@dataclass(frozen=True, slots=True)
class _Aggregate:
    total_observations: int
    actionable: tuple[ReplayDecision, ...]
    rejected_count: int
    rejection_reason_counts: Counter[str]
    outcome_counts: Counter[str]


def _aggregate(results: Sequence[ReplaySessionResult]) -> _Aggregate:
    all_decisions = [d for result in results for d in result.decisions]
    actionable = tuple(d for d in all_decisions if not d.rejection_reasons)
    rejected = [d for d in all_decisions if d.rejection_reasons]
    reason_counts: Counter[str] = Counter(
        d.rejection_reasons[0].value for d in rejected if d.rejection_reasons
    )
    outcome_counts: Counter[str] = Counter(
        d.outcome.value for d in actionable if d.outcome is not None
    )
    return _Aggregate(
        total_observations=len(all_decisions),
        actionable=actionable,
        rejected_count=len(rejected),
        rejection_reason_counts=reason_counts,
        outcome_counts=outcome_counts,
    )


def _decimal_distribution(values: Sequence[Decimal]) -> str:
    if not values:
        return "n/a (no ACTIONABLE decisions)"
    ordered = sorted(values)
    return f"min={ordered[0]}, median={median(ordered)}, max={ordered[-1]}, n={len(ordered)}"


def build_report(
    results: Sequence[ReplaySessionResult],
    *,
    symbols: Sequence[str],
    session_dates: Sequence[date],
    generated_at: datetime,
) -> str:
    """Pure aggregation over already-computed `ReplaySessionResult`s -- no I/O, fully testable."""
    agg = _aggregate(results)
    sessions_observed = sorted({r.session_date for r in results})
    reward_risk_values = [
        d.reward_risk_ratio for d in agg.actionable if d.reward_risk_ratio is not None
    ]
    maximum_loss_values = [
        d.risk_per_share * Decimal(d.quantity)
        for d in agg.actionable
        if d.risk_per_share is not None and d.quantity is not None
    ]
    hour_counts: Counter[int] = Counter(d.decided_at.hour for d in agg.actionable)
    time_of_day = (
        ", ".join(f"{hour:02d}:00 UTC x{count}" for hour, count in sorted(hour_counts.items()))
        or "n/a (no ACTIONABLE decisions)"
    )
    reason_lines = (
        "\n".join(
            f"- {reason}: {count}"
            for reason, count in sorted(agg.rejection_reason_counts.items(), key=lambda kv: -kv[1])
        )
        or "- (no rejections)"
    )
    outcome_lines = (
        "\n".join(
            f"- {outcome}: {count}"
            for outcome, count in sorted(agg.outcome_counts.items(), key=lambda kv: -kv[1])
        )
        or "- (no ACTIONABLE decisions to resolve)"
    )

    observed_dates = ", ".join(d.isoformat() for d in sessions_observed) or "(none)"
    return f"""# MILESTONE-090 Phase 20 -- Initial Research Report

Generated {generated_at.isoformat()}. Produced by `tools/m090_replay.py`, a read-only
historical replay -- no broker write of any kind was made to generate this report.

## Sample

- Symbols requested: {", ".join(symbols)}
- Session dates requested: {", ".join(d.isoformat() for d in session_dates)}
- Session dates with at least one observed bar: {observed_dates}
- Policy version: {OPPORTUNITY_ENGINE_POLICY_VERSION}

This is a SMALL, BOUNDED sample. No claim of expected profitability is made or implied by
anything below -- that would require a far larger, statistically meaningful sample this run
does not attempt.

## ENGINE SIGNAL QUALITY

Whether the deterministic, look-ahead-safe rules behaved as designed over this sample --
NOT a claim about future returns.

- Total observations (bar-evaluations with enough reference history): {agg.total_observations}
- ACTIONABLE (opportunities generated): {len(agg.actionable)}
- REJECTED: {agg.rejected_count}

### Rejection reasons
{reason_lines}

### Reward/risk ratio distribution (ACTIONABLE only)
{_decimal_distribution(reward_risk_values)}

### Maximum-loss distribution (ACTIONABLE only, risk_per_share * quantity)
{_decimal_distribution(maximum_loss_values)}

### Time-of-day distribution of ACTIONABLE decisions (decision hour, UTC)
{time_of_day}

## HYPOTHETICAL HISTORICAL OUTCOME

What the replay's stop/target/mandatory-exit resolution says WOULD have happened to each
ACTIONABLE decision, under the replay harness's ONE documented simplification: each bar's own
close stands in for BOTH the synthetic bid and ask (zero spread), never a real fill price or a
real market spread. This section is a hypothetical, not a real trading result.

{outcome_lines}

No expected-value, win-rate or profitability claim is made from this sample. A handful of
sessions cannot separate genuine edge from noise.
"""


def _build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--symbols",
        type=str,
        default=",".join(DEFAULT_SYMBOLS),
        help="Comma-separated symbols (default: %(default)s)",
    )
    parser.add_argument(
        "--sessions",
        type=int,
        default=5,
        help="Number of recent, already-completed weekday sessions to replay (default: 5)",
    )
    parser.add_argument(
        "--report-path",
        type=str,
        default=None,
        help="If given, also write the report to this path (relative to the repo root)",
    )
    return parser


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = _build_argument_parser()
    args = parser.parse_args(argv)
    symbols = tuple(s.strip().upper() for s in args.symbols.split(",") if s.strip())
    if not symbols:
        parser.error("--symbols must name at least one symbol")
    if args.sessions < 1:
        parser.error("--sessions must be at least 1")
    args.symbols = symbols
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)

    credentials = credentials_from_environment(dict(os.environ))
    bars_port = AlpacaPaperMarketDataClient(credentials=credentials)

    configuration = default_configuration(args.symbols)
    policy = default_policy()
    session_dates = recent_completed_session_dates(args.sessions, before=date.today())  # noqa: DTZ011

    results = collect_results(
        bars_port, args.symbols, session_dates, policy=policy, configuration=configuration
    )
    report = build_report(
        results,
        symbols=args.symbols,
        session_dates=session_dates,
        generated_at=datetime.now(UTC),
    )
    print(report)
    if args.report_path:
        out_path = REPO_ROOT / args.report_path
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
