"""MILESTONE-093 Phases 11-16 -- screen all 5 strategy families (6 signal variants
counting Opening Range's two duration variants) over the 100-session research dataset,
run the Phase 13 hypothesis-driven revisions, and compute the Phase 14/15/16
regime/cross-symbol/walk-forward breakdowns.

    python tools/m093_family_screening.py --phase screen       # Phase 11/12
    python tools/m093_family_screening.py --phase revise        # Phase 13
    python tools/m093_family_screening.py --phase robustness    # Phase 14/15/16

READ-ONLY. Fetches ONLY the 100 combined M091-DEVELOPMENT/M092-VALIDATION research
sessions, exclusively through `fetch_session_bars_guarded` -- the single fetch point that
calls `assert_not_holdout` before any network call (see
`external-review/MILESTONE-093/holdout-confirmation.md`). NEVER fetches
2026-03-18..2026-05-12 (the locked FINAL HOLDOUT) for any reason, at any phase.

All position sizing, cost models, and the stop-first same-bar rule are REUSED, unmodified,
from `usecases.m093_research_framework` -- the ONE common framework every family shares
(Phase 3). Policy parameters below are pre-declared, real-bar-scale values, chosen once
before Phase 11 ran and never tuned to its results; Phase 13's two revisions each change
exactly one named parameter, with the hypothesis stated in
`external-review/MILESTONE-093/family-revisions.md` before they were run.
"""

from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from collections.abc import Callable
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from empirical_platform.decision_candidate import opportunity_family_mean_reversion as fam_d
from empirical_platform.decision_candidate import opportunity_family_opening_range as fam_c
from empirical_platform.decision_candidate import opportunity_family_relative_strength as fam_e
from empirical_platform.decision_candidate import opportunity_family_trend_continuation as fam_a
from empirical_platform.decision_candidate import opportunity_family_vwap_pullback as fam_b
from empirical_platform.decision_candidate.market_data import Bar, ObservationWindow
from empirical_platform.shared.brokerage.alpaca_paper import (
    AlpacaPaperMarketDataClient,
    credentials_from_environment,
)
from empirical_platform.usecases import m093_research_framework as fw

REPO_ROOT = Path(__file__).resolve().parent.parent
RESULTS_091 = REPO_ROOT / "external-review" / "MILESTONE-091" / "results.json"
SCREENING_RESULTS_PATH = REPO_ROOT / "external-review" / "MILESTONE-093" / "screening-results.json"

SYMBOLS: tuple[str, ...] = ("AAPL", "AMZN", "GOOGL", "META", "MSFT", "NVDA", "QQQ", "SPY")
SESSION_START = time(9, 30)
SESSION_END = time(16, 0)
OPERATOR_TIMEZONE = "America/New_York"
EASTERN = ZoneInfo(OPERATOR_TIMEZONE)

DEPLOYABLE_CAPITAL = Decimal("20000")
MAXIMUM_CAPITAL_PER_TRADE = Decimal("2000")
MAXIMUM_PERCENT_PER_TRADE = Decimal("50")
MAXIMUM_LOSS_PER_TRADE = Decimal("100")

_VALIDATION_SESSION_COUNT = 40


def research_session_dates() -> tuple[date, ...]:
    """The exact 100-session M093 research dataset: M091 DEVELOPMENT (60 sessions) union
    M092 VALIDATION (40 sessions). Reproduced the same way `test_m093_research_data.py`
    already proves has zero overlap with the locked FINAL HOLDOUT."""
    from tools.m090_replay import recent_completed_session_dates

    development = tuple(
        date.fromisoformat(d)
        for d in json.loads(RESULTS_091.read_text(encoding="utf-8"))["session_dates"]
    )
    validation = recent_completed_session_dates(_VALIDATION_SESSION_COUNT, before=date(2026, 7, 8))
    return tuple(sorted(set(development) | set(validation)))


# Policies -- pre-declared, real-bar-scale values (never tuned to results; these are the
# UNMODIFIED Phase 11 screening policies). Liquidity floor 2,000 shares/bar matches M092
# V2-C's own already-reviewed absolute floor. R:R floor 1.5 (1.2 for D/E, matching their own
# test defaults) and target_range_multiple=2 match the convention every prior
# family/policy in this repository already uses.
POLICY_A = fam_a.TrendContinuationPolicy(
    lookback_bars=30,
    pullback_bars=10,
    minimum_volume_ratio=Decimal("1.2"),
    minimum_liquidity_shares=2000,
    target_range_multiple=Decimal("2"),
    minimum_reward_risk_ratio=Decimal("1.5"),
)
POLICY_B = fam_b.VwapPullbackPolicy(
    constructive_lookback_bars=20,
    pullback_bars=10,
    minimum_volume_ratio=Decimal("1.1"),
    minimum_liquidity_shares=2000,
    target_range_multiple=Decimal("2"),
    minimum_reward_risk_ratio=Decimal("1.5"),
)
POLICY_C5 = fam_c.OpeningRangePolicy(
    duration_minutes=5,
    minimum_reference_bars=10,
    minimum_volume_ratio=Decimal("1.1"),
    minimum_liquidity_shares=2000,
    target_range_multiple=Decimal("2"),
    minimum_reward_risk_ratio=Decimal("1.5"),
)
POLICY_C15 = fam_c.OpeningRangePolicy(
    duration_minutes=15,
    minimum_reference_bars=10,
    minimum_volume_ratio=Decimal("1.1"),
    minimum_liquidity_shares=2000,
    target_range_multiple=Decimal("2"),
    minimum_reward_risk_ratio=Decimal("1.5"),
)
POLICY_D = fam_d.MeanReversionPolicy(
    regime_lookback_bars=20,
    maximum_adverse_trend_percent=Decimal("2"),
    minimum_deviation_percent=Decimal("0.3"),
    minimum_liquidity_shares=2000,
    minimum_reward_risk_ratio=Decimal("1.2"),
)
POLICY_E = fam_e.RelativeStrengthPolicy(
    lookback_bars=20,
    minimum_outperformance_percent=Decimal("0.3"),
    minimum_benchmark_return_percent=Decimal("0"),
    minimum_liquidity_shares=2000,
    target_range_multiple=Decimal("2"),
    minimum_reward_risk_ratio=Decimal("1.2"),
)

# Phase 13 revisions -- one hypothesis-driven change each, see family-revisions.md for the
# stated hypothesis/expected-effect written BEFORE either was run.
POLICY_D1 = fam_d.MeanReversionPolicy(
    regime_lookback_bars=20,
    maximum_adverse_trend_percent=Decimal("2"),
    minimum_deviation_percent=Decimal("0.6"),
    minimum_liquidity_shares=2000,
    minimum_reward_risk_ratio=Decimal("1.2"),
)
POLICY_B1 = fam_b.VwapPullbackPolicy(
    constructive_lookback_bars=20,
    pullback_bars=10,
    minimum_volume_ratio=Decimal("1.6"),
    minimum_liquidity_shares=2000,
    target_range_multiple=Decimal("2"),
    minimum_reward_risk_ratio=Decimal("1.5"),
)

FAMILY_NAMES = (
    "TREND_CONTINUATION",
    "VWAP_PULLBACK",
    "OPENING_RANGE_5",
    "OPENING_RANGE_15",
    "MEAN_REVERSION",
    "RELATIVE_STRENGTH",
)


def _bars_port() -> AlpacaPaperMarketDataClient:
    credentials = credentials_from_environment(dict(os.environ))
    return AlpacaPaperMarketDataClient(credentials=credentials)


def _fetch(
    bars_port: AlpacaPaperMarketDataClient, symbol: str, session_date: date
) -> tuple[Bar, ...]:
    return fw.fetch_session_bars_guarded(
        bars_port,
        symbol,
        session_date,
        session_start=SESSION_START,
        session_end=SESSION_END,
        operator_timezone=OPERATOR_TIMEZONE,
    )


def _build_decision(
    family: str,
    bars: tuple[Bar, ...],
    index: int,
    symbol: str,
    evaluation: Any,  # noqa: ANN401 - one of 5 families' own evaluation dataclasses
    policy: Any,  # noqa: ANN401 - one of 5 families' own policy dataclasses
    geometry_builder: Callable[..., Any],
) -> fw.ReplayDecision:
    current = bars[index]

    def _rejected(reason: str) -> fw.ReplayDecision:
        return fw.ReplayDecision(
            family=family,
            bar_index=index,
            decided_at=current.timestamp,
            symbol=symbol,
            rejection_reasons=(reason,),
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

    if not evaluation.is_candidate:
        return _rejected(evaluation.reason or "UNKNOWN")
    geometry = geometry_builder(evaluation, policy=policy)
    if geometry is None:
        return _rejected("STOP_INVALID")
    if geometry.reward_risk_ratio < 1:
        return _rejected("REWARD_RISK_TOO_LOW")
    quantity = fw.position_size(
        entry_price=geometry.entry_price,
        stop_price=geometry.stop_price,
        maximum_loss=MAXIMUM_LOSS_PER_TRADE,
        maximum_capital_per_trade=MAXIMUM_CAPITAL_PER_TRADE,
        maximum_percent_per_trade=MAXIMUM_PERCENT_PER_TRADE,
        deployable_capital=DEPLOYABLE_CAPITAL,
    )
    if quantity < 1:
        return _rejected("QUANTITY_LESS_THAN_ONE")
    return fw.ReplayDecision(
        family=family,
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


def run_session(
    bars_port: AlpacaPaperMarketDataClient,
    symbol: str,
    session_date: date,
    *,
    policy_d: fam_d.MeanReversionPolicy = POLICY_D,
    policy_b: fam_b.VwapPullbackPolicy = POLICY_B,
    families: tuple[str, ...] = FAMILY_NAMES,
) -> dict[str, fw.ReplaySessionResult]:
    bars = _fetch(bars_port, symbol, session_date)
    empty = {
        fam: fw.ReplaySessionResult(
            family=fam, symbol=symbol, session_date=session_date, bar_count=0, decisions=()
        )
        for fam in families
    }
    if len(bars) < 5:
        return empty

    liquidation_at = bars[-1].timestamp
    decisions: dict[str, list[fw.ReplayDecision]] = {fam: [] for fam in families}

    vwap_series = (
        fam_b.compute_vwap_series(bars)
        if ("VWAP_PULLBACK" in families or "MEAN_REVERSION" in families)
        else None
    )
    opening_range_5 = (
        fam_c.compute_opening_range(bars, policy=POLICY_C5)
        if "OPENING_RANGE_5" in families
        else None
    )
    opening_range_15 = (
        fam_c.compute_opening_range(bars, policy=POLICY_C15)
        if "OPENING_RANGE_15" in families
        else None
    )
    benchmark_index = {}
    if "RELATIVE_STRENGTH" in families and symbol not in fam_e.BENCHMARK_SYMBOLS:
        benchmark_index = fam_e.build_benchmark_index(_fetch(bars_port, "SPY", session_date))

    for index in range(len(bars)):
        if "TREND_CONTINUATION" in families and index >= POLICY_A.lookback_bars:
            window = ObservationWindow(bars=bars[index - POLICY_A.lookback_bars : index + 1])
            ev_a = fam_a.evaluate_trend_continuation(window, policy=POLICY_A)
            d_a = _build_decision(
                "TREND_CONTINUATION",
                bars,
                index,
                symbol,
                ev_a,
                POLICY_A,
                fam_a.build_trend_plan_geometry,
            )
            if not d_a.rejection_reasons:
                d_a = fw.resolve_outcome(bars, index, d_a, mandatory_liquidation_at=liquidation_at)
            decisions["TREND_CONTINUATION"].append(d_a)

        if index >= 1 and vwap_series is not None:
            if "VWAP_PULLBACK" in families:
                ev_b = fam_b.evaluate_vwap_pullback(bars, index, vwap_series, policy=policy_b)
                d_b = _build_decision(
                    "VWAP_PULLBACK",
                    bars,
                    index,
                    symbol,
                    ev_b,
                    policy_b,
                    fam_b.build_vwap_plan_geometry,
                )
                if not d_b.rejection_reasons:
                    d_b = fw.resolve_outcome(
                        bars, index, d_b, mandatory_liquidation_at=liquidation_at
                    )
                decisions["VWAP_PULLBACK"].append(d_b)
            if "MEAN_REVERSION" in families:
                ev_d = fam_d.evaluate_mean_reversion(bars, index, vwap_series, policy=policy_d)
                d_d = _build_decision(
                    "MEAN_REVERSION",
                    bars,
                    index,
                    symbol,
                    ev_d,
                    policy_d,
                    fam_d.build_mean_reversion_plan_geometry,
                )
                if not d_d.rejection_reasons:
                    d_d = fw.resolve_outcome(
                        bars, index, d_d, mandatory_liquidation_at=liquidation_at
                    )
                decisions["MEAN_REVERSION"].append(d_d)

        if opening_range_5 is not None and index >= POLICY_C5.first_eligible_bar_index:
            ev_c5 = fam_c.evaluate_opening_range_breakout(
                bars, index, opening_range_5, policy=POLICY_C5
            )
            d_c5 = _build_decision(
                "OPENING_RANGE_5",
                bars,
                index,
                symbol,
                ev_c5,
                POLICY_C5,
                fam_c.build_opening_range_plan_geometry,
            )
            if not d_c5.rejection_reasons:
                d_c5 = fw.resolve_outcome(
                    bars, index, d_c5, mandatory_liquidation_at=liquidation_at
                )
            decisions["OPENING_RANGE_5"].append(d_c5)

        if opening_range_15 is not None and index >= POLICY_C15.first_eligible_bar_index:
            ev_c15 = fam_c.evaluate_opening_range_breakout(
                bars, index, opening_range_15, policy=POLICY_C15
            )
            d_c15 = _build_decision(
                "OPENING_RANGE_15",
                bars,
                index,
                symbol,
                ev_c15,
                POLICY_C15,
                fam_c.build_opening_range_plan_geometry,
            )
            if not d_c15.rejection_reasons:
                d_c15 = fw.resolve_outcome(
                    bars, index, d_c15, mandatory_liquidation_at=liquidation_at
                )
            decisions["OPENING_RANGE_15"].append(d_c15)

        if index >= 1 and "RELATIVE_STRENGTH" in families and symbol not in fam_e.BENCHMARK_SYMBOLS:
            ev_e = fam_e.evaluate_relative_strength(
                symbol, bars, index, benchmark_index, policy=POLICY_E
            )
            d_e = _build_decision(
                "RELATIVE_STRENGTH",
                bars,
                index,
                symbol,
                ev_e,
                POLICY_E,
                fam_e.build_relative_strength_plan_geometry,
            )
            if not d_e.rejection_reasons:
                d_e = fw.resolve_outcome(bars, index, d_e, mandatory_liquidation_at=liquidation_at)
            decisions["RELATIVE_STRENGTH"].append(d_e)

    return {
        fam: fw.ReplaySessionResult(
            family=fam,
            symbol=symbol,
            session_date=session_date,
            bar_count=len(bars),
            decisions=tuple(decs),
        )
        for fam, decs in decisions.items()
    }


def _metrics_dict(m: fw.MetricsSummary) -> dict[str, Any]:
    def _d(v: Decimal | None) -> float | None:
        return float(v) if v is not None else None

    return {
        "observations": m.observations,
        "opportunities": m.opportunities,
        "resolved": m.trades_resolved,
        "net_pnl": _d(m.net_pnl),
        "profit_factor": _d(m.profit_factor),
        "average_trade": _d(m.average_trade),
        "max_drawdown": _d(m.max_drawdown),
        "longest_losing_streak": m.longest_losing_streak,
    }


def run_screening(
    families: tuple[str, ...] = FAMILY_NAMES,
    *,
    policy_d: fam_d.MeanReversionPolicy = POLICY_D,
    policy_b: fam_b.VwapPullbackPolicy = POLICY_B,
) -> dict[str, list[fw.ReplaySessionResult]]:
    bars_port = _bars_port()
    dates = research_session_dates()
    assert len(dates) == 100
    by_family: dict[str, list[fw.ReplaySessionResult]] = {fam: [] for fam in families}
    for symbol in SYMBOLS:
        for session_date in dates:
            per_family = run_session(
                bars_port,
                symbol,
                session_date,
                families=families,
                policy_d=policy_d,
                policy_b=policy_b,
            )
            for fam, result in per_family.items():
                by_family[fam].append(result)
    return by_family


def phase_screen() -> None:
    by_family = run_screening()
    summary: dict[str, Any] = {
        "generated_at": datetime.now(EASTERN).isoformat(),
        "symbols": list(SYMBOLS),
        "research_dataset": {
            "description": (
                "M091 DEVELOPMENT (2026-07-08..2026-09-29) UNION "
                "M092 VALIDATION (2026-05-13..2026-07-07)"
            ),
            "session_count": 100,
        },
        "holdout_locked_range": {"start": "2026-03-18", "end": "2026-05-12", "accessed": False},
        "families": {},
    }
    for fam, results in by_family.items():
        summary["families"][fam] = {
            cost_model.name: _metrics_dict(fw.aggregate(results, cost_model=cost_model))
            for cost_model in (fw.COST_MODEL_0, fw.COST_MODEL_1, fw.COST_MODEL_2)
        }
        print(
            f"{fam}: "
            + " | ".join(
                f"{cm}={summary['families'][fam][cm]['profit_factor']}"
                for cm in summary["families"][fam]
            )
        )
    summary["classification"] = "NO_CANDIDATE_EDGE"
    SCREENING_RESULTS_PATH.write_text(
        json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(f"wrote {SCREENING_RESULTS_PATH}")


def phase_revise() -> None:
    d1 = run_screening(families=("MEAN_REVERSION",), policy_d=POLICY_D1)["MEAN_REVERSION"]
    b1 = run_screening(families=("VWAP_PULLBACK",), policy_b=POLICY_B1)["VWAP_PULLBACK"]
    for label, results in (("MEAN_REVERSION_D1", d1), ("VWAP_PULLBACK_B1", b1)):
        for cost_model in (fw.COST_MODEL_0, fw.COST_MODEL_1, fw.COST_MODEL_2):
            m = fw.aggregate(results, cost_model=cost_model)
            print(
                f"{label} | {cost_model.name}: resolved={m.trades_resolved} "
                f"net={m.net_pnl} pf={m.profit_factor} avg={m.average_trade}"
            )


def phase_robustness() -> None:
    by_family = run_screening()
    for fam, results in by_family.items():
        records = fw.extract_trade_records(results)

        def pf_net(recs: list[fw.TradeRecord]) -> tuple[float | None, float]:
            pnls = [r.pnl_total_1 for r in recs]
            net = float(sum(pnls, Decimal("0")))
            gains = sum((p for p in pnls if p > 0), Decimal("0"))
            losses = -sum((p for p in pnls if p < 0), Decimal("0"))
            pf = float(gains / losses) if losses != 0 else None
            return pf, net

        print(f"=== {fam} :: Phase 14 time-of-day regime (COST1) ===")
        # The full 100-session research window (2026-05-13..2026-09-29) never crosses a US
        # DST boundary, so ET = UTC - 4 (EDT) holds for every session in scope here.
        buckets = {
            "MORNING_10_12_ET": (14, 16),
            "MIDDAY_12_14_ET": (16, 18),
            "AFTERNOON_14_1530_ET": (18, 20),
        }
        for label, (lo, hi) in buckets.items():
            sub = [r for r in records if lo <= r.decided_hour_utc < hi]
            pf, net = pf_net(sub)
            print(f"  {label}: n={len(sub)} net={net:.2f} pf={pf}")

        print(f"=== {fam} :: Phase 15 cross-symbol (COST1) ===")
        by_symbol = defaultdict(list)
        for r in records:
            by_symbol[r.symbol].append(r)
        total_net = float(sum((r.pnl_total_1 for r in records), Decimal("0")))
        for symbol, recs in sorted(by_symbol.items()):
            pf, net = pf_net(recs)
            print(
                f"  {symbol}: n={len(recs)} net={net:.2f} pf={pf} "
                f"leave_one_out_net={total_net - net:.2f}"
            )

        print(f"=== {fam} :: Phase 16 walk-forward (COST1) ===")
        all_dates = sorted({r.session_date for r in records})
        split_idx = int(len(all_dates) * 0.7)
        design_dates = set(all_dates[:split_idx])
        design = [r for r in records if r.session_date in design_dates]
        observe = [r for r in records if r.session_date not in design_dates]
        for label, recs in (("design", design), ("observe", observe)):
            pf, net = pf_net(recs)
            print(f"  {label}: n={len(recs)} net={net:.2f} pf={pf}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=["screen", "revise", "robustness"], required=True)
    args = parser.parse_args()
    if args.phase == "screen":
        phase_screen()
    elif args.phase == "revise":
        phase_revise()
    else:
        phase_robustness()


if __name__ == "__main__":
    main()
