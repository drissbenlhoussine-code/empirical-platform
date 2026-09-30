"""MILESTONE-092 Phase 14-15 -- run the FROZEN V2-C policy exactly once against VALIDATION,
then (only if VALIDATION clears its own bar) exactly once against FINAL HOLDOUT.

    python tools/m092_validate_holdout.py

READ-ONLY. Fetches ONLY the 40 VALIDATION sessions (2026-05-13 -> 2026-07-07), and -- only if
triggered -- the 40 FINAL HOLDOUT sessions (2026-03-18 -> 2026-05-12). Never re-fetches or
re-evaluates DEVELOPMENT. The frozen candidate (`candidate_v2_c` from `tools.m092_validation`,
the EXACT same function that produced fingerprint `2fcd41e...` in
`external-review/MILESTONE-092/policy-freeze-v2.md`) is imported, never redefined here, so
there is no possibility of drift between what was frozen and what is run.

THE HOLDOUT TRIGGER IS MECHANICAL, NOT A JUDGMENT CALL (Phase 15's own "only if VALIDATION
shows credible improvement" is operationalized here EXACTLY as Phase 19's own VALIDATION-side
CANDIDATE_EDGE_V2 requirement: COST_MODEL_1 net > 0 AND profit factor > 1 AND average trade >
0). If VALIDATION does not clear this bar, FINAL HOLDOUT is never fetched or evaluated at all
-- this script does not even construct the date list for it in that case, so there is no
code path by which holdout bars could be read without the trigger firing.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

sys.path.insert(0, str(Path(__file__).resolve().parent))

from empirical_platform.shared.brokerage.alpaca_paper import (  # noqa: E402
    AlpacaPaperMarketDataClient,
    credentials_from_environment,
)
from empirical_platform.usecases.opportunity_engine_replay import ReplaySessionResult  # noqa: E402
from empirical_platform.usecases.opportunity_engine_v2_replay import (  # noqa: E402
    ReplaySessionResultV2,
    fetch_session_bars_v2,
    replay_session_v2,
)
from empirical_platform.usecases.opportunity_engine_v2_validation import (  # noqa: E402
    ConcentrationReportV2,
    classify_v2,
    concentration_report_v2,
)
from empirical_platform.usecases.opportunity_engine_validation import (  # noqa: E402
    COST_MODEL_0,
    COST_MODEL_1,
    COST_MODEL_2,
    MetricsSummary,
    aggregate,
    extract_trade_records,
)
from m092_validation import (  # noqa: E402 - sys.path must be extended first
    DEPLOYABLE_CAPITAL,
    SESSION_END,
    SESSION_START,
    SYMBOLS,
    _configuration,
    candidate_v2_c,
    compute_fingerprint,
    mandatory_liquidation_instant,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
RESULTS_PATH = REPO_ROOT / "external-review" / "MILESTONE-091" / "results.json"
VALIDATION_RESULTS_MD = REPO_ROOT / "external-review" / "MILESTONE-092" / "validation-results.md"
HOLDOUT_RESULTS_MD = REPO_ROOT / "external-review" / "MILESTONE-092" / "holdout-results.md"
COMBINED_JSON = REPO_ROOT / "external-review" / "MILESTONE-092" / "results-v2.json"

#: Frozen V2-C fingerprint -- must equal what policy-freeze-v2.md already recorded. Checked,
#: not merely asserted, before anything is fetched.
EXPECTED_FROZEN_FINGERPRINT_V2 = "2fcd41e03da2a9a20ee5b617bab02f49e97077eb9ed8ff8b59966a7ac3c8e604"


def _recent_completed_session_dates(count: int, *, before: date) -> tuple[date, ...]:
    """Identical to `tools/m090_replay.py`'s own helper and to
    `tests/unit/test_m092_dataset_split.py`'s own duplicate -- reproduced here (not
    imported) so this script has no import-time dependency on either."""
    found: list[date] = []
    cursor = before - timedelta(days=1)
    while len(found) < count:
        if cursor.weekday() < 5:
            found.append(cursor)
        cursor -= timedelta(days=1)
    return tuple(reversed(found))


def _development_dates() -> tuple[date, ...]:
    with open(RESULTS_PATH, encoding="utf-8") as fh:
        m091_results = json.load(fh)
    return tuple(date.fromisoformat(d) for d in m091_results["session_dates"])


def run_period(name: str, session_dates: tuple[date, ...]) -> list[ReplaySessionResultV2]:
    configuration = _configuration()
    policy = candidate_v2_c()
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


def _fmt(value: Decimal | int | float | None) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, Decimal):
        return f"{value:.2f}"
    if isinstance(value, float):
        return f"{value:.1f}"
    return str(value)


def _concentration_lines(report: ConcentrationReportV2) -> list[str]:
    count_share = _fmt(report.top_symbol_trade_count_share_percent)
    profit_share = _fmt(report.top_symbol_gross_profit_share_percent)
    day_share = _fmt(report.top_day_gross_profit_share_percent)
    return [
        f"- Total net P&L: {_fmt(report.total_net_pnl)}",
        f"- Total gross profit: {_fmt(report.total_gross_profit)}",
        f"- Top symbol by trade count: {report.top_symbol_by_trade_count} "
        f"({report.top_symbol_trade_count} trades, {count_share}% of all trades)",
        f"- Top symbol by gross profit: {report.top_symbol_by_gross_profit} "
        f"({profit_share}% of gross profit)",
        f"- Top day by gross profit: {report.top_day_by_gross_profit} "
        f"({day_share}% of gross profit)",
        "- Net P&L excluding top-trade-count symbol: "
        f"{_fmt(report.net_pnl_excluding_top_trade_count_symbol)}",
        "- Net P&L excluding top-gross-profit day: "
        f"{_fmt(report.net_pnl_excluding_top_gross_profit_day)}",
    ]


def _metrics_table(metrics: MetricsSummary) -> list[str]:
    return [
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
        f"| Average trade | {_fmt(metrics.average_trade)} |",
        f"| Median trade | {_fmt(metrics.median_trade)} |",
        f"| Hit rate | {_fmt(metrics.hit_rate)} |",
        f"| Average winner | {_fmt(metrics.average_winner)} |",
        f"| Average loser | {_fmt(metrics.average_loser)} |",
        f"| Payoff ratio | {_fmt(metrics.payoff_ratio)} |",
        f"| Profit factor | {_fmt(metrics.profit_factor)} |",
        f"| Max drawdown | {_fmt(metrics.max_drawdown)} |",
        f"| Longest losing streak | {metrics.longest_losing_streak} |",
        f"| Average holding (s) | {_fmt(metrics.average_holding_seconds)} |",
        f"| Rejection reasons | {metrics.rejection_reasons} |",
    ]


def main() -> int:
    policy = candidate_v2_c()
    configuration = _configuration()
    fingerprint = compute_fingerprint(policy, configuration)
    if fingerprint != EXPECTED_FROZEN_FINGERPRINT_V2:
        print(
            f"REFUSED: the frozen candidate's live fingerprint ({fingerprint}) does not match "
            f"the recorded freeze ({EXPECTED_FROZEN_FINGERPRINT_V2}) -- the policy has drifted "
            "since the freeze. Nothing was fetched or evaluated.",
            file=sys.stderr,
        )
        return 2
    print(f"Frozen fingerprint verified: {fingerprint}")

    development_dates = _development_dates()
    validation_dates = _recent_completed_session_dates(40, before=min(development_dates))
    print(
        f"VALIDATION: {len(validation_dates)} sessions, {min(validation_dates)} -> "
        f"{max(validation_dates)}"
    )

    print("Running VALIDATION (frozen V2-C, exactly once)...")
    validation_results = run_period("VALIDATION", validation_dates)
    validation_typed = cast("list[ReplaySessionResult]", validation_results)
    validation_metrics_0 = aggregate(validation_typed, cost_model=COST_MODEL_0)
    validation_metrics_1 = aggregate(validation_typed, cost_model=COST_MODEL_1)
    validation_metrics_2 = aggregate(validation_typed, cost_model=COST_MODEL_2)
    validation_records = extract_trade_records(validation_typed)
    validation_concentration = concentration_report_v2(validation_records, cost_model=COST_MODEL_1)

    validation_lines = [
        "# MILESTONE-092 Phase 14 -- VALIDATION Result (frozen V2-C, run exactly once)",
        "",
        f"Sessions: {len(validation_dates)} ({min(validation_dates)} -> "
        f"{max(validation_dates)}). Fingerprint verified: `{fingerprint}`.",
        "",
        "## COST_MODEL_0 (idealized)",
        "",
        *_metrics_table(validation_metrics_0),
        "",
        "## COST_MODEL_1 (base conservative) -- primary viability judgment",
        "",
        *_metrics_table(validation_metrics_1),
        "",
        "## COST_MODEL_2 (stress)",
        "",
        *_metrics_table(validation_metrics_2),
        "",
        "## Concentration (COST_MODEL_1, share-of-gross-profit formula)",
        "",
        *_concentration_lines(validation_concentration),
        "",
    ]

    validation_passed = (
        validation_metrics_1.net_pnl > 0
        and validation_metrics_1.profit_factor is not None
        and validation_metrics_1.profit_factor > 1
        and validation_metrics_1.average_trade is not None
        and validation_metrics_1.average_trade > 0
    )
    trigger_outcome = "PASS, proceeding to FINAL HOLDOUT" if validation_passed else "FAIL, stopping"
    print(
        f"VALIDATION trigger check: net={validation_metrics_1.net_pnl} "
        f"pf={validation_metrics_1.profit_factor} avg={validation_metrics_1.average_trade} "
        f"-> {trigger_outcome}"
    )
    validation_lines.append(
        f"## Holdout trigger: {'TRIGGERED' if validation_passed else 'NOT TRIGGERED'}"
    )
    validation_lines.append("")
    if validation_passed:
        validation_lines.append(
            "VALIDATION cleared all three required conditions (COST_MODEL_1 net > 0, profit "
            "factor > 1, average trade > 0) -- proceeding to FINAL HOLDOUT."
        )
    else:
        validation_lines.append(
            "VALIDATION did NOT clear the required bar -- per Phase 14's own instruction, "
            "classified NO_EDGE_V2 and FINAL HOLDOUT was never fetched or evaluated. The "
            "40-session FINAL HOLDOUT block (2026-03-18 -> 2026-05-12) remains genuinely "
            "unseen by any V2 candidate evaluation."
        )
    VALIDATION_RESULTS_MD.parent.mkdir(parents=True, exist_ok=True)
    VALIDATION_RESULTS_MD.write_text("\n".join(validation_lines) + "\n", encoding="utf-8")
    print(f"Wrote {VALIDATION_RESULTS_MD}")

    holdout_metrics_0 = holdout_metrics_1 = holdout_metrics_2 = None
    holdout_concentration = None
    holdout_dates: tuple[date, ...] | None = None

    if validation_passed:
        holdout_dates = _recent_completed_session_dates(40, before=min(validation_dates))
        print(
            f"FINAL HOLDOUT: {len(holdout_dates)} sessions, {min(holdout_dates)} -> "
            f"{max(holdout_dates)}"
        )
        print("Running FINAL HOLDOUT (frozen V2-C, exactly once)...")
        holdout_results = run_period("FINAL HOLDOUT", holdout_dates)
        holdout_typed = cast("list[ReplaySessionResult]", holdout_results)
        holdout_metrics_0 = aggregate(holdout_typed, cost_model=COST_MODEL_0)
        holdout_metrics_1 = aggregate(holdout_typed, cost_model=COST_MODEL_1)
        holdout_metrics_2 = aggregate(holdout_typed, cost_model=COST_MODEL_2)
        holdout_records = extract_trade_records(holdout_typed)
        holdout_concentration = concentration_report_v2(holdout_records, cost_model=COST_MODEL_1)

        holdout_lines = [
            "# MILESTONE-092 Phase 15 -- FINAL HOLDOUT Result (frozen V2-C, run exactly once)",
            "",
            f"Sessions: {len(holdout_dates)} ({min(holdout_dates)} -> {max(holdout_dates)}). "
            f"Fingerprint verified: `{fingerprint}`. This is the primary launch evidence.",
            "",
            "## COST_MODEL_0 (idealized)",
            "",
            *_metrics_table(holdout_metrics_0),
            "",
            "## COST_MODEL_1 (base conservative) -- primary viability judgment",
            "",
            *_metrics_table(holdout_metrics_1),
            "",
            "## COST_MODEL_2 (stress)",
            "",
            *_metrics_table(holdout_metrics_2),
            "",
            "## Concentration (COST_MODEL_1, share-of-gross-profit formula)",
            "",
            *_concentration_lines(holdout_concentration),
            "",
        ]
        HOLDOUT_RESULTS_MD.write_text("\n".join(holdout_lines) + "\n", encoding="utf-8")
        print(f"Wrote {HOLDOUT_RESULTS_MD}")
    else:
        HOLDOUT_RESULTS_MD.write_text(
            "# MILESTONE-092 Phase 15 -- FINAL HOLDOUT — NOT RUN\n\n"
            "VALIDATION did not clear the required bar (COST_MODEL_1 net > 0, profit factor "
            "> 1, average trade > 0). Per the mission's own Phase 14 instruction, this "
            "milestone stopped at VALIDATION and classified NO_EDGE_V2. The FINAL HOLDOUT "
            "block (2026-03-18 -> 2026-05-12, 40 sessions) was never fetched and no bar from "
            "it was ever read by any V2 candidate evaluation -- it remains genuinely unseen.\n",
            encoding="utf-8",
        )
        print(f"Wrote {HOLDOUT_RESULTS_MD} (not-run notice)")

    classification = classify_v2(
        validation_metrics=validation_metrics_1,
        validation_concentration=validation_concentration,
        holdout_metrics=holdout_metrics_1,
        holdout_concentration=holdout_concentration,
    )
    print(f"CLASSIFICATION: {classification.classification}")
    print(f"Rationale: {classification.rationale}")

    def _metrics_dict(metrics: MetricsSummary | None) -> dict[str, Any] | None:
        if metrics is None:
            return None
        return {k: (str(v) if isinstance(v, Decimal) else v) for k, v in asdict(metrics).items()}

    def _concentration_dict(report: ConcentrationReportV2 | None) -> dict[str, Any] | None:
        if report is None:
            return None
        return {k: (str(v) if isinstance(v, Decimal) else v) for k, v in asdict(report).items()}

    combined: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "frozen_fingerprint": fingerprint,
        "selected_candidate": "V2-C",
        "development_dates": [d.isoformat() for d in development_dates],
        "validation_dates": [d.isoformat() for d in validation_dates],
        "holdout_dates": [d.isoformat() for d in holdout_dates] if holdout_dates else None,
        "validation": {
            "cost_model_0": _metrics_dict(validation_metrics_0),
            "cost_model_1": _metrics_dict(validation_metrics_1),
            "cost_model_2": _metrics_dict(validation_metrics_2),
            "concentration_cost_model_1": _concentration_dict(validation_concentration),
        },
        "holdout": {
            "cost_model_0": _metrics_dict(holdout_metrics_0),
            "cost_model_1": _metrics_dict(holdout_metrics_1),
            "cost_model_2": _metrics_dict(holdout_metrics_2),
            "concentration_cost_model_1": _concentration_dict(holdout_concentration),
        }
        if validation_passed
        else None,
        "classification": {
            "classification": classification.classification,
            "criteria": classification.criteria,
            "rationale": classification.rationale,
        },
    }
    COMBINED_JSON.write_text(json.dumps(combined, indent=2, sort_keys=True), encoding="utf-8")
    print(f"Wrote {COMBINED_JSON}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
