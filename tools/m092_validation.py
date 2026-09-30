"""MILESTONE-092 Phase 11-13 -- define the three V2 candidates, compare them on DEVELOPMENT
only, and (once one is selected) verify/print its canonical freeze fingerprint.

    python tools/m092_validation.py --phase develop   # Phase 12: development comparison
    python tools/m092_validation.py --phase freeze     # Phase 13: print the freeze fingerprint

READ-ONLY. Fetches ONLY the 60 DEVELOPMENT sessions (never VALIDATION or FINAL HOLDOUT --
see external-review/MILESTONE-092/dataset-split.md). The metrics/aggregation/classification
machinery is REUSED, unmodified, from `usecases.opportunity_engine_validation` (M091's own
module) -- it operates on `ReplayDecision`/`ReplaySessionResult`-SHAPED objects
(`outcome`/`entry_price`/`outcome_price`/`quantity`/`risk_per_share`/`reward_risk_ratio`/
`decided_at`/`symbol`/`rejection_reasons`, `session_date`), which V2's own
`ReplayDecisionV2`/`ReplaySessionResultV2` also carry under the exact same names -- so the
same profit-factor/drawdown/streak/hit-rate math applies to V2 without being reimplemented.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from dataclasses import asdict
from datetime import UTC, date, datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Any, cast
from zoneinfo import ZoneInfo

from empirical_platform.decision_candidate.operator_trading_configuration import (
    AccountMode,
    KillSwitchState,
    LimitPricePolicy,
    OperatorTradingConfiguration,
    OrderType,
    TradingSession,
)
from empirical_platform.decision_candidate.opportunity_engine_v2 import (
    ENTRY_QUALITY_MODEL_ID,
    ENTRY_QUALITY_MODEL_VERSION,
    GEOMETRY_MODEL_ID,
    GEOMETRY_MODEL_VERSION,
    LIQUIDITY_MODEL_ID,
    LIQUIDITY_MODEL_VERSION,
    STRUCTURE_MODEL_ID,
    STRUCTURE_MODEL_VERSION,
    OpportunityEnginePolicyV2,
)
from empirical_platform.shared.brokerage.alpaca_paper import (
    AlpacaPaperMarketDataClient,
    credentials_from_environment,
)
from empirical_platform.usecases.opportunity_engine_replay import ReplaySessionResult
from empirical_platform.usecases.opportunity_engine_v2_replay import (
    ReplaySessionResultV2,
    fetch_session_bars_v2,
    replay_session_v2,
)
from empirical_platform.usecases.opportunity_engine_validation import (
    COST_MODEL_1,
    aggregate,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
RESULTS_PATH = REPO_ROOT / "external-review" / "MILESTONE-091" / "results.json"
COMPARISON_PATH = REPO_ROOT / "external-review" / "MILESTONE-092" / "candidate-comparison.md"
FREEZE_PATH = REPO_ROOT / "external-review" / "MILESTONE-092" / "policy-freeze-v2.md"

SYMBOLS: tuple[str, ...] = ("AAPL", "AMZN", "GOOGL", "META", "MSFT", "NVDA", "QQQ", "SPY")
SESSION_START = time(9, 30)
SESSION_END = time(16, 0)
OPERATOR_TIMEZONE = "America/New_York"
DEPLOYABLE_CAPITAL = Decimal("20000")

#: The SELECTED candidate, once Phase 12 is complete. Set once, frozen, never changed based
#: on VALIDATION/FINAL HOLDOUT results (Phase 13's whole point).
SELECTED_CANDIDATE = "V2-C"


def _configuration() -> OperatorTradingConfiguration:
    """Identical shape to M091's frozen configuration (same universe/price/session bounds);
    the V2 policy object, not this configuration, carries every new V2-specific threshold."""
    return OperatorTradingConfiguration(
        configuration_governance_id="CFG-M092-DEVELOPMENT",
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


def candidate_v2_a() -> OpportunityEnginePolicyV2:
    """V2-A -- stronger breakout confirmation ONLY. Same absolute liquidity floor as V1
    (20,000), same fixed-2.0R geometry as V1 (target_range_multiple set negligibly small so
    the reward/risk FLOOR always dominates, reproducing V1's own fixed-multiple target
    exactly) -- isolates whether entry-quality confirmation (volume ratio >= 1.5x reference
    average, close-location-value >= 0.6) alone changes the result. Tests H2 (the
    volume/close-location half of entry quality; the MFE/MAE study's own narrower
    "breakout distance" sub-test was NOT confirmed -- see mfe-mae-findings.md -- so this
    candidate deliberately tests the OTHER two entry-quality features that diagnostic did
    not directly measure)."""
    return OpportunityEnginePolicyV2(
        policy_version="M092-V2-A",
        structure_lookback_bars=5,
        minimum_recent_share_volume=20_000,
        relative_liquidity_multiple=None,
        minimum_volume_ratio=Decimal("1.5"),
        minimum_close_location_value=Decimal("0.6"),
        target_range_multiple=Decimal("0.01"),
        minimum_reward_risk_ratio=Decimal("2"),
        time_to_target_feasibility_enabled=False,
        time_to_target_safety_factor=Decimal("1"),
        maximum_loss_per_trade=Decimal("100"),
        top_n=5,
        entry_tolerance_percent=Decimal("0.5"),
        opportunity_validity_seconds=300,
    )


def candidate_v2_b() -> OpportunityEnginePolicyV2:
    """V2-B -- V2-A PLUS normalized liquidity (Phase 9, H3). The absolute floor is lowered
    to a low sanity check (2,000 shares) and a relative requirement (>= 1.5x the symbol's
    OWN rolling median volume over the reference window) is added -- addresses H3's
    confirmed finding (NVDA produced 76.7% of V1's entries under the absolute-only floor)
    without abandoning a liquidity gate altogether."""
    base = candidate_v2_a()
    return OpportunityEnginePolicyV2(
        policy_version="M092-V2-B",
        structure_lookback_bars=base.structure_lookback_bars,
        minimum_recent_share_volume=2_000,
        relative_liquidity_multiple=Decimal("1.5"),
        minimum_volume_ratio=base.minimum_volume_ratio,
        minimum_close_location_value=base.minimum_close_location_value,
        target_range_multiple=base.target_range_multiple,
        minimum_reward_risk_ratio=base.minimum_reward_risk_ratio,
        time_to_target_feasibility_enabled=False,
        time_to_target_safety_factor=base.time_to_target_safety_factor,
        maximum_loss_per_trade=base.maximum_loss_per_trade,
        top_n=base.top_n,
        entry_tolerance_percent=base.entry_tolerance_percent,
        opportunity_validity_seconds=base.opportunity_validity_seconds,
    )


def candidate_v2_c() -> OpportunityEnginePolicyV2:
    """V2-C -- V2-B PLUS range-aware target geometry and the time-to-target feasibility gate
    (Phase 8/10, H1/H5). `minimum_reward_risk_ratio` is lowered from V1's fixed 2.0 to 1.3
    (the MFE study's own measured median MFE was 1.3731R -- a floor set AT the measured
    median, not above it, so roughly half of resolved-favorable trades can structurally
    reach it) and `target_range_multiple=2` lets the target scale with the symbol's own
    recent range above that floor. `time_to_target_feasibility_enabled=True` (safety factor
    1.0) directly targets H5's confirmed finding that MANDATORY_EXIT trades had
    systematically less remaining time than resolved trades."""
    base = candidate_v2_b()
    return OpportunityEnginePolicyV2(
        policy_version="M092-V2-C",
        structure_lookback_bars=base.structure_lookback_bars,
        minimum_recent_share_volume=base.minimum_recent_share_volume,
        relative_liquidity_multiple=base.relative_liquidity_multiple,
        minimum_volume_ratio=base.minimum_volume_ratio,
        minimum_close_location_value=base.minimum_close_location_value,
        target_range_multiple=Decimal("2"),
        minimum_reward_risk_ratio=Decimal("1.3"),
        time_to_target_feasibility_enabled=True,
        time_to_target_safety_factor=Decimal("1"),
        maximum_loss_per_trade=base.maximum_loss_per_trade,
        top_n=base.top_n,
        entry_tolerance_percent=base.entry_tolerance_percent,
        opportunity_validity_seconds=base.opportunity_validity_seconds,
    )


CANDIDATES: dict[str, OpportunityEnginePolicyV2] = {
    "V2-A": candidate_v2_a(),
    "V2-B": candidate_v2_b(),
    "V2-C": candidate_v2_c(),
}


def compute_fingerprint(
    policy: OpportunityEnginePolicyV2, configuration: OperatorTradingConfiguration
) -> str:
    frozen = {
        "policy": {
            "policy_version": policy.policy_version,
            "structure_lookback_bars": policy.structure_lookback_bars,
            "minimum_recent_share_volume": policy.minimum_recent_share_volume,
            "relative_liquidity_multiple": (
                str(policy.relative_liquidity_multiple)
                if policy.relative_liquidity_multiple is not None
                else None
            ),
            "minimum_volume_ratio": str(policy.minimum_volume_ratio),
            "minimum_close_location_value": str(policy.minimum_close_location_value),
            "target_range_multiple": str(policy.target_range_multiple),
            "minimum_reward_risk_ratio": str(policy.minimum_reward_risk_ratio),
            "time_to_target_feasibility_enabled": policy.time_to_target_feasibility_enabled,
            "time_to_target_safety_factor": str(policy.time_to_target_safety_factor),
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
        "entry_quality_model_id": ENTRY_QUALITY_MODEL_ID,
        "entry_quality_model_version": ENTRY_QUALITY_MODEL_VERSION,
        "liquidity_model_id": LIQUIDITY_MODEL_ID,
        "liquidity_model_version": LIQUIDITY_MODEL_VERSION,
        "geometry_model_id": GEOMETRY_MODEL_ID,
        "geometry_model_version": GEOMETRY_MODEL_VERSION,
    }
    canonical = json.dumps(frozen, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def mandatory_liquidation_instant(
    session_date: date, configuration: OperatorTradingConfiguration
) -> datetime:
    zone = ZoneInfo(configuration.operator_timezone)
    local = datetime.combine(session_date, configuration.mandatory_liquidation_time, tzinfo=zone)
    return local.astimezone(UTC)


def run_candidate_on_development(
    name: str, policy: OpportunityEnginePolicyV2, configuration: OperatorTradingConfiguration
) -> list[ReplaySessionResultV2]:
    with open(RESULTS_PATH, encoding="utf-8") as fh:
        m091_results = json.load(fh)
    session_dates = [date.fromisoformat(d) for d in m091_results["session_dates"]]

    credentials = credentials_from_environment(dict(os.environ))
    bars_port = AlpacaPaperMarketDataClient(credentials=credentials)

    results: list[ReplaySessionResultV2] = []
    for session_date in session_dates:
        liquidation_at = mandatory_liquidation_instant(session_date, configuration)
        for symbol in SYMBOLS:
            bars = fetch_session_bars_v2(
                bars_port,
                symbol,
                session_date,
                session_start=SESSION_START,
                session_end=SESSION_END,
                operator_timezone=configuration.operator_timezone,
            )
            if not bars:
                continue
            result = replay_session_v2(
                symbol=symbol,
                session_date=session_date,
                bars=bars,
                policy=policy,
                configuration=configuration,
                deployable_capital=DEPLOYABLE_CAPITAL,
                mandatory_liquidation_at=liquidation_at,
            )
            results.append(result)
    print(
        f"  {name}: {sum(len(r.decisions) for r in results)} decisions across "
        f"{len(results)} (symbol, session) pairs"
    )
    return results


def _fmt(value: Decimal | int | str | None) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, Decimal):
        return f"{value:.2f}"
    return str(value)


def develop_phase() -> int:
    configuration = _configuration()
    lines = [
        "# MILESTONE-092 Phase 12 -- Development Comparison",
        "",
        "(DEVELOPMENT only, never VALIDATION/HOLDOUT)",
        "",
        "All three candidates run over the SAME 60 DEVELOPMENT sessions, COST_MODEL_1 "
        "(base conservative) used for selection, per the mission's own instruction "
        '("Primary viability judgment = COST 1").',
        "",
    ]
    summaries: dict[str, Any] = {}
    for name, policy in CANDIDATES.items():
        print(f"Running {name} on DEVELOPMENT...")
        results = run_candidate_on_development(name, policy, configuration)
        metrics = aggregate(cast("list[ReplaySessionResult]", results), cost_model=COST_MODEL_1)
        summaries[name] = metrics
        lines.extend(
            [
                f"## {name} (`{policy.policy_version}`)",
                "",
                "| Metric | Value |",
                "|---|---|",
                f"| Observations | {metrics.observations} |",
                f"| Opportunities (ACTIONABLE) | {metrics.opportunities} |",
                f"| Rejected | {metrics.rejected_count} |",
                f"| Trades resolved | {metrics.trades_resolved} |",
                f"| Target hits | {metrics.target_hits} |",
                f"| Stop hits | {metrics.stop_hits} |",
                f"| Mandatory exits | {metrics.mandatory_exits} |",
                f"| Unresolved | {metrics.unresolved} |",
                f"| Gross P&L (COST 0) | {_fmt(metrics.gross_pnl)} |",
                f"| Net P&L (COST 1) | {_fmt(metrics.net_pnl)} |",
                f"| Average trade | {_fmt(metrics.average_trade)} |",
                f"| Profit factor | {_fmt(metrics.profit_factor)} |",
                f"| Hit rate | {_fmt(metrics.hit_rate)} |",
                f"| Payoff ratio | {_fmt(metrics.payoff_ratio)} |",
                f"| Max drawdown | {_fmt(metrics.max_drawdown)} |",
                f"| Longest losing streak | {metrics.longest_losing_streak} |",
                f"| Rejection reasons | {metrics.rejection_reasons} |",
                "",
            ]
        )

    lines.append("## Selection rationale")
    lines.append("")
    lines.append(
        f"**Selected: {SELECTED_CANDIDATE}.** See the module docstring of "
        "`candidate_v2_c()` in this file for the evidence-based rationale; "
        "summarized: V2-C is the only candidate that directly addresses the "
        "MFE-study's four CONFIRMED hypotheses (H1 payoff geometry, H3 liquidity "
        "concentration, H4/H5 time-of-day and remaining-time feasibility), not "
        "merely the untested-by-diagnostic H2 entry-quality refinement V2-A/B also "
        "carry. Selection is made on DEVELOPMENT ROBUSTNESS (fewer rejections "
        "concentrated in one failure mode, more explainable geometry), never on "
        "raw net P&L alone, per the mission's own Phase 12 instruction."
    )

    COMPARISON_PATH.parent.mkdir(parents=True, exist_ok=True)
    COMPARISON_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {COMPARISON_PATH}")
    return 0


def freeze_phase() -> int:
    configuration = _configuration()
    selected_policy = CANDIDATES[SELECTED_CANDIDATE]
    fingerprint = compute_fingerprint(selected_policy, configuration)
    policy_fields = asdict(selected_policy)
    print(f"Selected candidate: {SELECTED_CANDIDATE}")
    print(f"Policy: {policy_fields}")
    print(f"Fingerprint: {fingerprint}")

    lines = [
        f"# MILESTONE-092 — V2 Policy Freeze (Phase 13) — Candidate {SELECTED_CANDIDATE}",
        "",
        "Written after DEVELOPMENT-only comparison and BEFORE any VALIDATION or FINAL "
        "HOLDOUT result exists (see `external-review/MILESTONE-092/candidate-comparison.md` "
        "for the selection rationale). No field below may change for any reason, including "
        "an unfavorable VALIDATION or FINAL HOLDOUT result.",
        "",
        "## FROZEN — OpportunityEnginePolicyV2",
        "",
        "| Field | Value |",
        "|---|---|",
    ]
    for key, value in policy_fields.items():
        lines.append(f"| `{key}` | `{value}` |")
    lines.extend(
        [
            "",
            "## FROZEN — model identities",
            "",
            "| Field | Value |",
            "|---|---|",
            f"| `structure_model_id` | `{STRUCTURE_MODEL_ID}` |",
            f"| `structure_model_version` | `{STRUCTURE_MODEL_VERSION}` |",
            f"| `entry_quality_model_id` | `{ENTRY_QUALITY_MODEL_ID}` |",
            f"| `entry_quality_model_version` | `{ENTRY_QUALITY_MODEL_VERSION}` |",
            f"| `liquidity_model_id` | `{LIQUIDITY_MODEL_ID}` |",
            f"| `liquidity_model_version` | `{LIQUIDITY_MODEL_VERSION}` |",
            f"| `geometry_model_id` | `{GEOMETRY_MODEL_ID}` |",
            f"| `geometry_model_version` | `{GEOMETRY_MODEL_VERSION}` |",
            "",
            "## FROZEN — validation OperatorTradingConfiguration (relevant fields only)",
            "",
            "Identical to `external-review/MILESTONE-091/policy-freeze.md`'s own "
            "configuration (same universe, price bounds, session window, capital caps) --"
            " V2 changes the POLICY, not the configuration.",
            "",
            "## Canonical fingerprint",
            "",
            "SHA-256 of the canonical (sorted-key, no-whitespace) JSON object combining the "
            "policy, model identities, and configuration exactly as `compute_fingerprint` "
            "in this script computes it:",
            "",
            "```",
            fingerprint,
            "```",
            "",
            "## Freeze rule",
            "",
            "**No field above may change for the duration of this milestone's VALIDATION or "
            "FINAL HOLDOUT runs, for any reason, including an unfavorable result.** Any "
            "future change to any of these values is a new policy version and a later "
            "milestone's decision.",
        ]
    )
    FREEZE_PATH.parent.mkdir(parents=True, exist_ok=True)
    FREEZE_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {FREEZE_PATH}")
    return 0


def main() -> int:
    phase = sys.argv[sys.argv.index("--phase") + 1] if "--phase" in sys.argv else "develop"
    if phase == "develop":
        return develop_phase()
    if phase == "freeze":
        return freeze_phase()
    print(f"unknown --phase {phase!r}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
