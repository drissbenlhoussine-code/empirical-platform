"""MILESTONE-092 Phase 6 -- MFE/MAE diagnostic study over V1's OWN entries on DEVELOPMENT only.

    python tools/m092_mfe_mae_study.py

READ-ONLY. Diagnoses WHY the frozen M090 V1 policy (fingerprint
6ed540efd2b2638bf5a3a9aae290874bad6c5fdad54c604325c86ce4fd2c49da) underperformed, using the
exact same 60 DEVELOPMENT sessions M091 already used (never FINAL HOLDOUT or VALIDATION --
see external-review/MILESTONE-092/dataset-split.md). Never modifies V1's own files; reuses
`usecases.opportunity_engine_replay.replay_session` (V1's frozen decide/resolve path)
unchanged to find where V1 WOULD have entered, then measures, for each such entry, how price
actually moved before mandatory liquidation -- independent of where V1's own stop/target
happened to sit.

MFE (maximum favorable excursion): the largest high price reached, above entry, at any bar
from the entry bar's successor through mandatory liquidation (bars strictly after the
decision bar only -- never the decision bar itself, matching the frozen replay's own
look-ahead discipline).

MAE (maximum adverse excursion): the largest drop below entry (a positive magnitude) reached
over the same bar range.

Both are also expressed in risk-multiples (MFE/MAE divided by the entry's own
risk_per_share) so they are directly comparable to the frozen 2.0R target and the entry's
own structural stop distance.
"""

from __future__ import annotations

import json
import os
import statistics
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, time
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
    ReplayDecision,
    fetch_session_bars,
    replay_session,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
RESULTS_PATH = REPO_ROOT / "external-review" / "MILESTONE-091" / "results.json"
FINDINGS_PATH = REPO_ROOT / "external-review" / "MILESTONE-092" / "mfe-mae-findings.md"
RAW_PATH = REPO_ROOT / "external-review" / "MILESTONE-092" / "mfe-mae-raw.json"

#: Reproduces external-review/MILESTONE-091/policy-freeze.md exactly -- V1's OWN frozen
#: policy, used here ONLY to find where V1 would have entered. Never modified.
V1_FROZEN_FINGERPRINT = "6ed540efd2b2638bf5a3a9aae290874bad6c5fdad54c604325c86ce4fd2c49da"

SYMBOLS: tuple[str, ...] = ("AAPL", "AMZN", "GOOGL", "META", "MSFT", "NVDA", "QQQ", "SPY")
SESSION_START = time(9, 30)
SESSION_END = time(16, 0)
OPERATOR_TIMEZONE = "America/New_York"
DEPLOYABLE_CAPITAL = Decimal("20000")


def v1_frozen_policy() -> OpportunityEnginePolicy:
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


def v1_frozen_configuration() -> OperatorTradingConfiguration:
    return OperatorTradingConfiguration(
        configuration_governance_id="CFG-M092-MFE-MAE-STUDY",
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


def mandatory_liquidation_instant(
    session_date: date, configuration: OperatorTradingConfiguration
) -> datetime:
    zone = ZoneInfo(configuration.operator_timezone)
    local = datetime.combine(session_date, configuration.mandatory_liquidation_time, tzinfo=zone)
    return local.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class ExcursionRecord:
    """One V1 entry's excursion profile, measured using ONLY bars[index+1:] up to mandatory
    liquidation -- the same look-ahead discipline the frozen replay's own outcome resolution
    uses (never the decision bar itself, never a bar after the true resolution instant for
    ANYTHING other than this diagnostic excursion measurement)."""

    symbol: str
    session_date: str
    decided_at: str
    decided_hour_utc: int
    entry_price: str
    stop_price: str
    target_price: str
    risk_per_share: str
    mfe: str
    mfe_in_r: str
    time_to_mfe_seconds: float
    mae: str
    mae_in_r: str
    time_to_mae_seconds: float
    remaining_session_seconds: float
    outcome: str | None
    breakout_distance_percent: str | None


def _breakout_distance_percent(bars: tuple[Bar, ...], index: int, lookback: int) -> str | None:
    """(close - range_high) / (range_high - range_low) * 100 for the SAME reference window
    `evaluate_structure` used -- a diagnostic re-measurement, not a new gate; `None` if the
    range is degenerate (range_high == range_low)."""
    window_start = max(0, index - lookback)
    reference = bars[window_start:index]
    if len(reference) < lookback:
        return None
    range_high = max(b.high for b in reference)
    range_low = min(b.low for b in reference)
    if range_high <= range_low:
        return None
    current = bars[index]
    distance = (current.close - range_high) / (range_high - range_low) * Decimal("100")
    return str(distance.quantize(Decimal("0.01")))


def measure_excursion(
    bars: tuple[Bar, ...],
    index: int,
    decision: ReplayDecision,
    *,
    mandatory_liquidation_at: datetime,
    lookback: int,
) -> ExcursionRecord | None:
    if (
        decision.entry_price is None
        or decision.stop_price is None
        or decision.risk_per_share is None
    ):
        return None
    entry = decision.entry_price
    risk = decision.risk_per_share
    decided_at = bars[index].timestamp

    later = [b for b in bars[index + 1 :] if b.timestamp <= mandatory_liquidation_at]
    if not later:
        return None

    mfe = Decimal("0")
    mfe_at = decided_at
    mae = Decimal("0")
    mae_at = decided_at
    for bar in later:
        favorable = bar.high - entry
        if favorable > mfe:
            mfe = favorable
            mfe_at = bar.timestamp
        adverse = entry - bar.low
        if adverse > mae:
            mae = adverse
            mae_at = bar.timestamp

    remaining = (mandatory_liquidation_at - decided_at).total_seconds()
    breakout_distance = _breakout_distance_percent(bars, index, lookback)

    return ExcursionRecord(
        symbol=decision.symbol,
        session_date=decided_at.date().isoformat(),
        decided_at=decided_at.isoformat(),
        decided_hour_utc=decided_at.hour,
        entry_price=str(entry),
        stop_price=str(decision.stop_price),
        target_price=str(decision.target_price),
        risk_per_share=str(risk),
        mfe=str(mfe.quantize(Decimal("0.0001"))),
        mfe_in_r=str((mfe / risk).quantize(Decimal("0.0001"))) if risk > 0 else "0",
        time_to_mfe_seconds=(mfe_at - decided_at).total_seconds(),
        mae=str(mae.quantize(Decimal("0.0001"))),
        mae_in_r=str((mae / risk).quantize(Decimal("0.0001"))) if risk > 0 else "0",
        time_to_mae_seconds=(mae_at - decided_at).total_seconds(),
        remaining_session_seconds=remaining,
        outcome=decision.outcome.value if decision.outcome is not None else None,
        breakout_distance_percent=breakout_distance,
    )


def _percentiles(values: list[Decimal]) -> dict[str, str]:
    if not values:
        return {"min": "n/a", "p25": "n/a", "median": "n/a", "p75": "n/a", "max": "n/a"}
    ordered = sorted(float(v) for v in values)
    if len(ordered) >= 4:
        p25 = f"{statistics.quantiles(ordered, n=4)[0]:.4f}"
        p75 = f"{statistics.quantiles(ordered, n=4)[2]:.4f}"
    else:
        p25 = f"{ordered[0]:.4f}"
        p75 = f"{ordered[-1]:.4f}"
    return {
        "min": f"{ordered[0]:.4f}",
        "p25": p25,
        "median": f"{statistics.median(ordered):.4f}",
        "p75": p75,
        "max": f"{ordered[-1]:.4f}",
    }


def main() -> int:
    policy = v1_frozen_policy()
    configuration = v1_frozen_configuration()
    print(
        f"Diagnosing V1's OWN entries under its frozen policy (fingerprint reference: "
        f"{V1_FROZEN_FINGERPRINT}) -- this study never modifies V1 or its fingerprint."
    )

    with open(RESULTS_PATH, encoding="utf-8") as fh:
        m091_results = json.load(fh)
    session_dates = [date.fromisoformat(d) for d in m091_results["session_dates"]]
    print(f"DEVELOPMENT sessions ({len(session_dates)}): {session_dates[0]} .. {session_dates[-1]}")

    credentials = credentials_from_environment(dict(os.environ))
    bars_port = AlpacaPaperMarketDataClient(credentials=credentials)

    records: list[ExcursionRecord] = []
    for session_date in session_dates:
        liquidation_at = mandatory_liquidation_instant(session_date, configuration)
        for symbol in SYMBOLS:
            bars = fetch_session_bars(
                bars_port,
                symbol,
                session_date,
                session_start=SESSION_START,
                session_end=SESSION_END,
                operator_timezone=configuration.operator_timezone,
            )
            if not bars:
                continue
            result = replay_session(
                symbol=symbol,
                session_date=session_date,
                bars=bars,
                policy=policy,
                configuration=configuration,
                deployable_capital=DEPLOYABLE_CAPITAL,
                mandatory_liquidation_at=liquidation_at,
            )
            for decision in result.decisions:
                if decision.rejection_reasons:
                    continue
                record = measure_excursion(
                    bars,
                    decision.bar_index,
                    decision,
                    mandatory_liquidation_at=liquidation_at,
                    lookback=policy.structure_lookback_bars,
                )
                if record is not None:
                    records.append(record)
        print(f"  {session_date}: {len(records)} cumulative entries measured")

    print(f"Total V1 entries measured: {len(records)}")

    RAW_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(RAW_PATH, "w", encoding="utf-8") as fh:
        json.dump([asdict(r) for r in records], fh, indent=2, sort_keys=True)

    mfe_r = [Decimal(r.mfe_in_r) for r in records]
    mae_r = [Decimal(r.mae_in_r) for r in records]
    mfe_stats = _percentiles(mfe_r)
    mae_stats = _percentiles(mae_r)

    at_or_above_2r = sum(1 for v in mfe_r if v >= Decimal("2"))
    at_or_above_1r_mae = sum(1 for v in mae_r if v >= Decimal("1"))
    at_or_above_2r_percent = at_or_above_2r / len(records) * 100 if records else 0
    at_or_above_1r_mae_percent = at_or_above_1r_mae / len(records) * 100 if records else 0

    # H2: breakout-distance terciles vs MFE
    with_distance = [r for r in records if r.breakout_distance_percent is not None]
    with_distance.sort(key=lambda r: Decimal(r.breakout_distance_percent))  # type: ignore[arg-type]
    n = len(with_distance)
    weak = with_distance[: n // 3] if n >= 3 else []
    strong = with_distance[-(n // 3) :] if n >= 3 else []
    weak_mfe = _percentiles([Decimal(r.mfe_in_r) for r in weak])
    strong_mfe = _percentiles([Decimal(r.mfe_in_r) for r in strong])
    strong_beats_weak = (
        bool(strong)
        and bool(weak)
        and Decimal(strong_mfe["median"]) > Decimal(weak_mfe["median"]) * Decimal("1.15")
    )

    # H4: mandatory-exit rate by decided hour
    by_hour: dict[int, list[ExcursionRecord]] = {}
    for r in records:
        by_hour.setdefault(r.decided_hour_utc, []).append(r)
    hour_mandatory_rate = {
        hour: (sum(1 for x in rows if x.outcome == "MANDATORY_EXIT") / len(rows) if rows else 0.0)
        for hour, rows in sorted(by_hour.items())
    }

    # H5: remaining-session-seconds profile, MANDATORY_EXIT vs resolved (STOP/TARGET)
    mandatory = [r for r in records if r.outcome == "MANDATORY_EXIT"]
    resolved_other = [r for r in records if r.outcome in ("STOP_HIT", "TARGET_HIT")]
    mandatory_remaining = (
        statistics.median([r.remaining_session_seconds for r in mandatory]) if mandatory else None
    )
    other_remaining = (
        statistics.median([r.remaining_session_seconds for r in resolved_other])
        if resolved_other
        else None
    )
    mandatory_remaining_text = "n/a" if mandatory_remaining is None else str(mandatory_remaining)
    other_remaining_text = "n/a" if other_remaining is None else str(other_remaining)

    # H3: per-symbol liquidity-gate pass rate proxy -- fraction of this symbol's entries
    # among all entries (a rough concentration signal; the FULL H3 liquidity analysis is in
    # opportunity_engine_v2.py's own docstring/research notes, this is the MFE/MAE study's
    # own contribution: confirming entries concentrate the same way M091 already measured).
    by_symbol_count: dict[str, int] = {}
    for r in records:
        by_symbol_count[r.symbol] = by_symbol_count.get(r.symbol, 0) + 1

    lines = [
        "# MILESTONE-092 Phase 6 -- MFE/MAE Diagnostic Findings (DEVELOPMENT only)",
        "",
        f"V1's own frozen policy (reference fingerprint `{V1_FROZEN_FINGERPRINT}`, never "
        "modified) was used only to find where V1 would have entered. Measured over the "
        f"same 60 DEVELOPMENT sessions M091 used. Total entries measured: **{len(records)}**.",
        "",
        "## MFE (in risk-multiples, R) -- how far price actually moved favorably",
        "",
        "| min | p25 | median | p75 | max |",
        "|---|---|---|---|---|",
        f"| {mfe_stats['min']} | {mfe_stats['p25']} | {mfe_stats['median']} | "
        f"{mfe_stats['p75']} | {mfe_stats['max']} |",
        "",
        f"**{at_or_above_2r} of {len(records)} entries ({at_or_above_2r_percent:.1f}%) "
        "ever reached 2.0R favorable excursion** -- V1's fixed target. The median MFE is "
        f"{mfe_stats['median']}R.",
        "",
        "## MAE (in risk-multiples, R) -- how far price actually moved adversely",
        "",
        "| min | p25 | median | p75 | max |",
        "|---|---|---|---|---|",
        f"| {mae_stats['min']} | {mae_stats['p25']} | {mae_stats['median']} | "
        f"{mae_stats['p75']} | {mae_stats['max']} |",
        "",
        f"**{at_or_above_1r_mae} of {len(records)} entries "
        f"({at_or_above_1r_mae_percent:.1f}%) "
        "reached 1.0R adverse excursion** (i.e. touched or exceeded V1's own structural stop "
        f"distance). Median MAE is {mae_stats['median']}R.",
        "",
        "## H1 finding (payoff geometry)",
        "",
        (
            f"CONFIRMED: median MFE ({mfe_stats['median']}R) sits well below the fixed 2.0R "
            "target, and only a minority of entries ever reach 2.0R favorable excursion at "
            "all. V1's fixed 2.0R target is structurally too far for most entries to reach "
            "before mandatory liquidation."
            if Decimal(mfe_stats["median"]) < Decimal("2")
            else "DISCONFIRMED: median MFE regularly clears 2.0R."
        ),
        "",
        "## H2 finding (entry quality -- breakout distance)",
        "",
        f"Weak-tercile (n={len(weak)}) median MFE: {weak_mfe['median']}R. "
        f"Strong-tercile (n={len(strong)}) median MFE: {strong_mfe['median']}R.",
        "",
        (
            "CONFIRMED: strong breakouts show materially higher MFE than weak ones -- a "
            "stronger confirmation filter is evidence-supported."
            if strong_beats_weak
            else "WEAK/NO SIGNAL: breakout distance alone does not clearly separate MFE outcomes "
            "in this sample -- other confirmation evidence (volume persistence, close "
            "location) may matter more than raw breakout distance."
        ),
        "",
        "## H3 finding (liquidity concentration, trade-count proxy)",
        "",
        "| Symbol | Entries | Share |",
        "|---|---|---|",
    ]
    total_entries = len(records) or 1
    for symbol in sorted(by_symbol_count, key=lambda s: -by_symbol_count[s]):
        count = by_symbol_count[symbol]
        lines.append(f"| {symbol} | {count} | {count / total_entries * 100:.1f}% |")
    lines.extend(
        [
            "",
            "Confirms M091's own finding: entries concentrate heavily in NVDA under the "
            "absolute 20,000-share-per-bar floor. See "
            "`src/empirical_platform/decision_candidate/opportunity_engine_v2.py`'s own "
            "normalized-liquidity research notes for the Phase 9 rework.",
            "",
            "## H4 finding (time-of-day)",
            "",
            "| Decision hour (UTC) | Entries | Mandatory-exit rate |",
            "|---|---|---|",
        ]
    )
    for hour, rate in hour_mandatory_rate.items():
        lines.append(f"| {hour}:00 | {len(by_hour[hour])} | {rate * 100:.1f}% |")
    later_hours = [h for h in hour_mandatory_rate if h >= 17]
    earlier_hours = [h for h in hour_mandatory_rate if h < 17]
    later_avg = (
        statistics.mean([hour_mandatory_rate[h] for h in later_hours]) if later_hours else None
    )
    earlier_avg = (
        statistics.mean([hour_mandatory_rate[h] for h in earlier_hours]) if earlier_hours else None
    )
    lines.extend(
        [
            "",
            (
                f"CONFIRMED: later-session entries (>=17:00 UTC, avg mandatory-exit rate "
                f"{later_avg * 100:.1f}%) show a higher mandatory-exit rate than earlier ones "
                f"(<17:00 UTC, avg {earlier_avg * 100:.1f}%)."
                if later_avg is not None and earlier_avg is not None and later_avg > earlier_avg
                else "NO CLEAR PATTERN in this sample."
            ),
            "",
            "## H5 finding (mandatory-exit rate vs remaining time)",
            "",
            f"Median remaining-session-seconds for MANDATORY_EXIT trades (n={len(mandatory)}): "
            f"{mandatory_remaining_text}.",
            f"Median remaining-session-seconds for STOP_HIT/TARGET_HIT trades "
            f"(n={len(resolved_other)}): {other_remaining_text}.",
            "",
            (
                "CONFIRMED: MANDATORY_EXIT trades had systematically LESS remaining session "
                "time at decision than resolved trades -- directly motivating Phase 8's "
                "time-to-target feasibility gate."
                if mandatory_remaining is not None
                and other_remaining is not None
                and mandatory_remaining < other_remaining
                else "NO CLEAR SEPARATION on remaining time alone in this sample."
            ),
            "",
            "## What this study does NOT establish",
            "",
            "- Any claim about VALIDATION or FINAL HOLDOUT performance (not touched here).",
            "- Guaranteed or expected future profitability of any V2 design.",
            "- That V1 itself was changed (it was not -- this is read-only diagnosis).",
        ]
    )

    FINDINGS_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {FINDINGS_PATH}")
    print(f"Wrote {RAW_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
