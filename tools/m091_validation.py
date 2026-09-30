"""MILESTONE-091 -- the large, honest, out-of-sample validation run for the FROZEN M090 V1
policy over 60 real historical sessions and 8 predeclared symbols.

    python tools/m091_validation.py

READ-ONLY, ALWAYS. The only network capability this script touches is
`AlpacaPaperMarketDataClient.fetch_minute_bars` (real IEX-feed 1-minute bars, GET only) --
the SAME, unmodified adapter `tools/m090_replay.py` already uses. No object reachable from
this module can place, modify or cancel an order.

FROZEN, NOT TUNABLE. `frozen_policy()`/`frozen_configuration()` below reproduce EXACTLY the
values recorded in `external-review/MILESTONE-091/policy-freeze.md`
(fingerprint `6ed540efd2b2638bf5a3a9aae290874bad6c5fdad54c604325c86ce4fd2c49da`) -- this
script asserts its own computed fingerprint matches that recorded one at startup, and
refuses to run if it does not (a hard proof this run used the frozen values, not a silently
adjusted copy). Nothing here may be changed because a result looks unfavorable; a change to
either function below is a new policy version and a new milestone's decision, never a
same-run reaction to this script's own output.

THIS SCRIPT NEVER TUNES ANY PARAMETER BASED ON A RESULT: it is written, reviewed, and run
exactly once per invocation, top to bottom, with no branch conditioned on an intermediate
P&L figure.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from dataclasses import asdict
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from empirical_platform.decision_candidate.market_data import Bar
from empirical_platform.decision_candidate.operator_trading_configuration import (
    AccountMode,
    KillSwitchState,
    LimitPricePolicy,
    OperatorTradingConfiguration,
    OrderType,
    TradingSession,
)
from empirical_platform.decision_candidate.opportunity_engine import OpportunityEnginePolicy
from empirical_platform.shared.brokerage.alpaca_paper import (
    AlpacaPaperMarketDataClient,
    credentials_from_environment,
)
from empirical_platform.usecases.opportunity_engine_replay import (
    ReplaySessionResult,
    fetch_session_bars,
    replay_session,
)
from empirical_platform.usecases.opportunity_engine_validation import (
    COST_MODEL_0,
    COST_MODEL_1,
    COST_MODEL_2,
    aggregate,
    classify,
    concentration_report,
    extract_trade_records,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
RESULTS_PATH = REPO_ROOT / "external-review" / "MILESTONE-091" / "results.json"
REPORT_PATH = REPO_ROOT / "external-review" / "MILESTONE-091" / "owner-report.md"

FROZEN_FINGERPRINT = "6ed540efd2b2638bf5a3a9aae290874bad6c5fdad54c604325c86ce4fd2c49da"

#: Phase 4: the predeclared, non-performance-selected universe. Canonical ascending order.
SYMBOLS: tuple[str, ...] = ("AAPL", "AMZN", "GOOGL", "META", "MSFT", "NVDA", "QQQ", "SPY")
SESSION_COUNT = 60
SESSION_START = time(9, 30)
SESSION_END = time(16, 0)
OPERATOR_TIMEZONE = "America/New_York"
DEPLOYABLE_CAPITAL = Decimal("20000")


def frozen_policy() -> OpportunityEnginePolicy:
    """Reproduces `external-review/MILESTONE-091/policy-freeze.md` exactly."""
    return OpportunityEnginePolicy(
        policy_version="M090-V1",
        structure_lookback_bars=5,
        minimum_recent_share_volume=20_000,
        minimum_reward_risk_ratio=Decimal("2"),
        maximum_loss_per_trade=Decimal("100"),
        top_n=5,
        entry_tolerance_percent=Decimal("0.5"),
        opportunity_validity_seconds=300,
    )


def frozen_configuration() -> OperatorTradingConfiguration:
    """Reproduces `external-review/MILESTONE-091/policy-freeze.md` exactly."""
    return OperatorTradingConfiguration(
        configuration_governance_id="CFG-M091-VALIDATION",
        configuration_version=1,
        base_currency="USD",
        permitted_markets=("ARCA", "NASDAQ", "NYSE"),
        watchlist=tuple(sorted(SYMBOLS)),
        prohibited_instruments=(),
        maximum_deployable_capital=DEPLOYABLE_CAPITAL,
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
        operator_timezone=OPERATOR_TIMEZONE,
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


def compute_fingerprint(
    policy: OpportunityEnginePolicy, configuration: OperatorTradingConfiguration
) -> str:
    """The SAME canonical construction `policy-freeze.md` documents -- sorted-key JSON over
    the policy, the model identities, and the validation-relevant configuration fields."""
    from empirical_platform.decision_candidate.opportunity_engine import (
        QUALITY_MODEL_ID,
        QUALITY_MODEL_VERSION,
        STRUCTURE_MODEL_ID,
        STRUCTURE_MODEL_VERSION,
    )

    frozen = {
        "policy": {
            "policy_version": policy.policy_version,
            "structure_lookback_bars": policy.structure_lookback_bars,
            "minimum_recent_share_volume": policy.minimum_recent_share_volume,
            "minimum_reward_risk_ratio": str(policy.minimum_reward_risk_ratio),
            "maximum_loss_per_trade": str(policy.maximum_loss_per_trade),
            "top_n": policy.top_n,
            "entry_tolerance_percent": str(policy.entry_tolerance_percent),
            "opportunity_validity_seconds": policy.opportunity_validity_seconds,
        },
        "configuration": {
            "watchlist": list(configuration.watchlist),
            "permitted_markets": list(configuration.permitted_markets),
            "maximum_spread_percent": str(configuration.maximum_spread_percent),
            "minimum_liquidity_shares": configuration.minimum_liquidity_shares,
            "minimum_price": str(configuration.minimum_price),
            "maximum_price": str(configuration.maximum_price),
            "permitted_session": configuration.permitted_session.value,
            "earliest_entry_time": configuration.earliest_entry_time.isoformat(),
            "latest_entry_time": configuration.latest_entry_time.isoformat(),
            "mandatory_liquidation_time": configuration.mandatory_liquidation_time.isoformat(),
            "operator_timezone": configuration.operator_timezone,
            "maximum_capital_per_trade": str(configuration.maximum_capital_per_trade),
            "maximum_percent_per_trade": str(configuration.maximum_percent_per_trade),
            "maximum_deployable_capital": str(configuration.maximum_deployable_capital),
            "default_order_type": configuration.default_order_type.value,
            "limit_price_policy": configuration.limit_price_policy.value,
            "maximum_leverage": str(configuration.maximum_leverage),
            "short_selling_permitted": configuration.short_selling_permitted,
            "overnight_positions_permitted": configuration.overnight_positions_permitted,
        },
        "structure_model_id": STRUCTURE_MODEL_ID,
        "structure_model_version": STRUCTURE_MODEL_VERSION,
        "quality_model_id": QUALITY_MODEL_ID,
        "quality_model_version": QUALITY_MODEL_VERSION,
    }
    canonical = json.dumps(frozen, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def recent_completed_session_dates(count: int, *, before: date) -> tuple[date, ...]:
    """The `count` most recent weekdays strictly before `before`, oldest first. A calendar
    approximation (not the real exchange calendar): a holiday simply yields zero observed
    bars for that date, reported as an excluded pair, never faked."""
    if count < 1:
        raise ValueError("count must be at least 1")
    found: list[date] = []
    cursor = before - timedelta(days=1)
    while len(found) < count:
        if cursor.weekday() < 5:
            found.append(cursor)
        cursor -= timedelta(days=1)
    return tuple(reversed(found))


def mandatory_liquidation_instant(
    session_date: date, configuration: OperatorTradingConfiguration
) -> datetime:
    zone = ZoneInfo(configuration.operator_timezone)
    local = datetime.combine(session_date, configuration.mandatory_liquidation_time, tzinfo=zone)
    return local.astimezone(UTC)


class DataIntegrityError(ValueError):
    """One (symbol, session) pair failed a Phase 6 data-quality check. Caught by the
    caller and recorded as an EXCLUSION with this exact reason -- never silently skipped
    and never fabricated evidence in its place."""


def fetch_and_validate_session_bars(
    bars_port: AlpacaPaperMarketDataClient,
    symbol: str,
    session_date: date,
    configuration: OperatorTradingConfiguration,
) -> tuple[Bar, ...]:
    """`fetch_session_bars` already sorts, de-duplicates, and (via `Bar.__post_init__`)
    refuses non-positive prices, inverted OHLC, and negative volume by raising -- this
    function additionally verifies session-boundary containment and a minimum bar count,
    and translates ANY failure into one `DataIntegrityError` with an explicit reason."""
    zone = ZoneInfo(configuration.operator_timezone)
    start = datetime.combine(session_date, SESSION_START, tzinfo=zone).astimezone(UTC)
    end = datetime.combine(session_date, SESSION_END, tzinfo=zone).astimezone(UTC)
    try:
        bars = fetch_session_bars(
            bars_port,
            symbol,
            session_date,
            session_start=SESSION_START,
            session_end=SESSION_END,
            operator_timezone=configuration.operator_timezone,
        )
    except (ValueError, TypeError) as error:
        raise DataIntegrityError(f"bar construction refused: {error}") from error
    if not bars:
        raise DataIntegrityError("no bars returned (holiday, feed gap, or no data)")
    # Session-boundary containment: defense in depth on top of the query's own start/end
    # bounds -- no premarket/after-hours bar may be present. Alpaca's `end` is INCLUSIVE
    # (verified: the regular session's last bar is timestamped exactly at `end`, e.g.
    # 20:00:00 UTC for a 16:00 ET close) -- both bounds are therefore closed here.
    out_of_bounds = [b for b in bars if not (start <= b.timestamp <= end)]
    if out_of_bounds:
        raise DataIntegrityError(
            f"{len(out_of_bounds)} bar(s) outside the regular session window "
            f"[{start.isoformat()}, {end.isoformat()}]"
        )
    # Strictly chronological, strictly increasing: fetch_session_bars already sorts and
    # de-duplicates, so this re-verifies rather than trusts that silently held.
    for earlier, later in zip(bars, bars[1:], strict=False):
        if later.timestamp <= earlier.timestamp:
            raise DataIntegrityError("bars are not strictly chronological after de-duplication")
    # A regular session is ~390 one-minute bars; a suspiciously thin count (well under half)
    # is evidence of a partial/short session or a feed gap, not silently trusted as complete.
    if len(bars) < 100:
        raise DataIntegrityError(
            f"only {len(bars)} bars returned, suspiciously few for a regular session"
        )
    return bars


def main() -> int:  # noqa: PLR0915 - one linear, auditable run; splitting it would obscure the order
    policy = frozen_policy()
    configuration = frozen_configuration()
    computed_fingerprint = compute_fingerprint(policy, configuration)
    if computed_fingerprint != FROZEN_FINGERPRINT:
        print(
            f"REFUSED: computed fingerprint {computed_fingerprint} does not match the "
            f"recorded freeze {FROZEN_FINGERPRINT}. The frozen policy/configuration in this "
            "script no longer matches external-review/MILESTONE-091/policy-freeze.md. "
            "Nothing was fetched or computed.",
            file=sys.stderr,
        )
        return 2
    print(f"Fingerprint verified: {computed_fingerprint}")

    credentials = credentials_from_environment(dict(os.environ))
    bars_port = AlpacaPaperMarketDataClient(credentials=credentials)

    session_dates = recent_completed_session_dates(SESSION_COUNT, before=date.today())  # noqa: DTZ011
    block_a_dates = frozenset(session_dates[:30])
    block_b_dates = frozenset(session_dates[30:])
    print(f"Session dates ({len(session_dates)}): {session_dates[0]} .. {session_dates[-1]}")

    results: list[ReplaySessionResult] = []
    excluded: list[dict[str, str]] = []
    total_pairs = len(SYMBOLS) * len(session_dates)
    for session_date in session_dates:
        liquidation_at = mandatory_liquidation_instant(session_date, configuration)
        for symbol in SYMBOLS:
            try:
                bars = fetch_and_validate_session_bars(
                    bars_port, symbol, session_date, configuration
                )
            except DataIntegrityError as error:
                excluded.append(
                    {
                        "symbol": symbol,
                        "session_date": session_date.isoformat(),
                        "reason": str(error),
                    }
                )
                continue
            results.append(
                replay_session(
                    symbol=symbol,
                    session_date=session_date,
                    bars=bars,
                    policy=policy,
                    configuration=configuration,
                    deployable_capital=DEPLOYABLE_CAPITAL,
                    mandatory_liquidation_at=liquidation_at,
                )
            )
    print(
        f"Fetched {len(results)}/{total_pairs} (symbol, session) pairs; {len(excluded)} excluded."
    )

    excluded_fraction = (
        Decimal(len(excluded)) / Decimal(total_pairs) if total_pairs else Decimal("0")
    )

    block_a_results = [r for r in results if r.session_date in block_a_dates]
    block_b_results = [r for r in results if r.session_date in block_b_dates]

    full_cost0 = aggregate(results, cost_model=COST_MODEL_0)
    full_cost1 = aggregate(results, cost_model=COST_MODEL_1)
    full_cost2 = aggregate(results, cost_model=COST_MODEL_2)
    block_a_cost1 = aggregate(block_a_results, cost_model=COST_MODEL_1)
    block_b_cost1 = aggregate(block_b_results, cost_model=COST_MODEL_1)

    per_symbol_cost1 = {
        symbol: aggregate([r for r in results if r.symbol == symbol], cost_model=COST_MODEL_1)
        for symbol in SYMBOLS
    }
    hours = sorted(
        {d.decided_at.hour for r in results for d in r.decisions if not d.rejection_reasons}
    )
    per_hour_cost1 = {
        hour: aggregate(
            [
                ReplaySessionResult(
                    symbol=r.symbol,
                    session_date=r.session_date,
                    bar_count=r.bar_count,
                    decisions=tuple(d for d in r.decisions if d.decided_at.hour == hour),
                )
                for r in results
            ],
            cost_model=COST_MODEL_1,
        )
        for hour in hours
    }

    all_records = extract_trade_records(results)
    concentration = concentration_report(
        all_records,
        cost_model=COST_MODEL_1,
        block_a_dates=block_a_dates,
        block_b_dates=block_b_dates,
    )

    classification = classify(
        full_metrics_cost1=full_cost1,
        block_a_metrics_cost1=block_a_cost1,
        block_b_metrics_cost1=block_b_cost1,
        concentration=concentration,
        excluded_fraction=excluded_fraction,
    )
    print(f"CLASSIFICATION: {classification.classification} -- {classification.rationale}")

    def _decimalize(obj: object) -> object:
        if isinstance(obj, Decimal):
            return str(obj)
        if isinstance(obj, date):
            return obj.isoformat()
        if isinstance(obj, dict):
            return {k: _decimalize(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [_decimalize(v) for v in obj]
        return obj

    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "fingerprint": computed_fingerprint,
        "symbols": list(SYMBOLS),
        "session_dates": [d.isoformat() for d in session_dates],
        "block_a_dates": [d.isoformat() for d in sorted(block_a_dates)],
        "block_b_dates": [d.isoformat() for d in sorted(block_b_dates)],
        "total_pairs_requested": total_pairs,
        "pairs_fetched": len(results),
        "pairs_excluded": len(excluded),
        "excluded_fraction": str(excluded_fraction),
        "excluded_pairs": excluded,
        "cost_models": {
            m.name: {
                "entry_cost_percent": str(m.entry_cost_percent),
                "exit_cost_percent": str(m.exit_cost_percent),
                "description": m.description,
            }
            for m in (COST_MODEL_0, COST_MODEL_1, COST_MODEL_2)
        },
        "full_sample": {
            "cost_model_0": _decimalize(asdict(full_cost0)),
            "cost_model_1": _decimalize(asdict(full_cost1)),
            "cost_model_2": _decimalize(asdict(full_cost2)),
        },
        "block_a_cost_model_1": _decimalize(asdict(block_a_cost1)),
        "block_b_cost_model_1": _decimalize(asdict(block_b_cost1)),
        "per_symbol_cost_model_1": {s: _decimalize(asdict(m)) for s, m in per_symbol_cost1.items()},
        "per_hour_utc_cost_model_1": {
            str(h): _decimalize(asdict(m)) for h, m in per_hour_cost1.items()
        },
        "concentration_cost_model_1": _decimalize(asdict(concentration)),
        "classification": {
            "classification": classification.classification,
            "criteria": classification.criteria,
            "rationale": classification.rationale,
        },
    }

    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {RESULTS_PATH.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
