"""MILESTONE-063 independent verification path.

This module does not import `_median()`, `_classify_regimes()`,
`regime_breakdown()`, or any other M063 study-level metric helper.
Instead, it loads the real fixture, uses production only to obtain the
window-level outcomes, and then independently recomputes the study-level
metrics from those raw window results.
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from pathlib import Path
from statistics import median
from typing import Any

from empirical_platform.decision_candidate.position_plan import PositionSizingContext
from empirical_platform.decision_candidate.robustness_study import (
    HistoricalRobustnessStudy,
    RobustnessDatasetBundle,
    build_robustness_study,
)
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import BacktestRunId, RobustnessStudyId
from empirical_platform.shared.identifiers import (
    DeterministicRuntimeIdentifierGenerator,
    RuntimeIdentifier,
)

_FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "m063_robustness_study"
    / "synthetic_broad_robustness_dataset_bundle.json"
)
_EXPECTED_SHA256 = "765601962773a215aa483538f467632de6780c8510b4a82b823f77bd132db2dd"


def _load_bundle() -> RobustnessDatasetBundle:
    from empirical_platform.usecases.robustness_study_io import (
        parse_robustness_dataset_bundle_file,
    )

    return parse_robustness_dataset_bundle_file(
        str(_FIXTURE_PATH), expected_sha256=_EXPECTED_SHA256
    )


def _generator() -> DeterministicRuntimeIdentifierGenerator:
    return DeterministicRuntimeIdentifierGenerator(
        [f"{i:08d}-0000-4000-8000-000000000001" for i in range(94000001, 94001000)]
    )


def _backtest_run_identity_for(window_id: str) -> DomainIdentity[BacktestRunId]:
    sequence = int(window_id[1:])
    return DomainIdentity(
        governance_id=BacktestRunId(f"BTRUN-94{sequence:02d}"),
        runtime_id=RuntimeIdentifier(f"94{sequence:06d}-0000-4000-8000-000000000001"),
    )


def _study() -> HistoricalRobustnessStudy:
    return build_robustness_study(
        identity=DomainIdentity(
            governance_id=RobustnessStudyId("ROBUST-9401"),
            runtime_id=RuntimeIdentifier("94000000-0000-4000-8000-000000000001"),
        ),
        bundle=_load_bundle(),
        sizing_context=PositionSizingContext(
            account_equity=Decimal("100000"), risk_percent=Decimal("0.01")
        ),
        runtime_identifier_generator=_generator(),
        backtest_run_identity_for=_backtest_run_identity_for,
    )[0]


def _raw_fixture() -> dict[str, Any]:
    return json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))


def _independent_window_ranges(windows: list[dict[str, Any]]) -> list[tuple[str, int, int, int]]:
    ranges = []
    cursor = 0
    for entry in sorted(windows, key=lambda item: int(item["sequence_index"])):
        total = (
            int(entry["warmup_bar_count"])
            + int(entry["scoring_bar_count"])
            + int(entry["buffer_bar_count"])
        )
        start = cursor
        end = cursor + total
        ranges.append((str(entry["window_id"]), int(entry["sequence_index"]), start, end))
        cursor = end
    return ranges


def test_independent_sha256_matches_declared_value() -> None:
    assert hashlib.sha256(_FIXTURE_PATH.read_bytes()).hexdigest() == _EXPECTED_SHA256


def test_independent_window_ranges_never_overlap_and_cover_the_fixture() -> None:
    raw = _raw_fixture()
    ranges = _independent_window_ranges(raw["windows"])
    seen: set[int] = set()
    for window_id, _sequence, start, end in ranges:
        indices = set(range(start, end))
        assert not (indices & seen), f"window {window_id} overlaps a prior window"
        seen |= indices
    assert len(ranges) == 10
    assert seen == set(range(160))


def test_independent_recomputation_matches_production_study_metrics() -> None:
    study = _study()
    results = study.window_results

    positive_net = [result for result in results if result.net_pnl > 0]
    negative_net = [result for result in results if result.net_pnl < 0]
    positive_r = [result for result in results if result.total_r > 0]
    negative_r = [result for result in results if result.total_r < 0]

    independent_best_net = max(results, key=lambda result: result.net_pnl)
    independent_worst_net = min(results, key=lambda result: result.net_pnl)
    independent_best_r = max(results, key=lambda result: result.total_r)
    independent_worst_r = min(results, key=lambda result: result.total_r)

    all_net = sum((result.net_pnl for result in results), Decimal("0"))
    all_r = sum((result.total_r for result in results), Decimal("0"))
    positive_sum = sum((result.net_pnl for result in positive_net), Decimal("0"))
    negative_abs_sum = sum((abs(result.net_pnl) for result in negative_net), Decimal("0"))

    breakdown: dict[str, dict[str, Decimal | int]] = {}
    for result in results:
        key = result.regime_label.value
        bucket = breakdown.setdefault(
            key,
            {
                "window_count": 0,
                "executed_trade_count": 0,
                "net_pnl_total": Decimal("0"),
                "total_r_total": Decimal("0"),
                "positive_window_count": 0,
                "negative_window_count": 0,
            },
        )
        bucket["window_count"] += 1
        bucket["executed_trade_count"] += result.executed_trade_count
        bucket["net_pnl_total"] += result.net_pnl
        bucket["total_r_total"] += result.total_r
        if result.net_pnl > 0:
            bucket["positive_window_count"] += 1
        if result.net_pnl < 0:
            bucket["negative_window_count"] += 1

    assert study.window_count == len(results)
    assert study.total_evaluated_cutoff_count == sum(
        result.evaluated_cutoff_count for result in results
    )
    assert study.total_simulated_trade_count == sum(
        result.simulated_trade_count for result in results
    )
    assert study.total_executed_trade_count == sum(
        result.executed_trade_count for result in results
    )
    assert study.positive_net_pnl_window_count == len(positive_net)
    assert study.negative_net_pnl_window_count == len(negative_net)
    assert study.positive_total_r_window_count == len(positive_r)
    assert study.negative_total_r_window_count == len(negative_r)
    assert study.median_window_net_pnl == Decimal(
        str(median([result.net_pnl for result in results]))
    )
    assert study.median_window_total_r == Decimal(
        str(median([result.total_r for result in results]))
    )
    assert study.best_window_by_net_pnl.window_id == independent_best_net.window.window_id
    assert study.best_window_by_net_pnl.value == independent_best_net.net_pnl
    assert study.worst_window_by_net_pnl.window_id == independent_worst_net.window.window_id
    assert study.worst_window_by_net_pnl.value == independent_worst_net.net_pnl
    assert study.best_window_by_total_r.window_id == independent_best_r.window.window_id
    assert study.best_window_by_total_r.value == independent_best_r.total_r
    assert study.worst_window_by_total_r.window_id == independent_worst_r.window.window_id
    assert study.worst_window_by_total_r.value == independent_worst_r.total_r
    assert study.all_window_net_pnl_total == all_net
    assert study.all_window_total_r_total == all_r
    assert study.excluding_best_window_net_pnl_total == all_net - independent_best_net.net_pnl
    assert study.excluding_best_window_total_r_total == all_r - independent_best_r.total_r
    assert study.largest_positive_window_share_of_positive_pnl == (
        max(result.net_pnl for result in positive_net) / positive_sum
    )
    assert study.largest_negative_window_share_of_absolute_negative_pnl == (
        max(abs(result.net_pnl) for result in negative_net) / negative_abs_sum
    )

    assert set(breakdown) == {"HIGH_VOLATILITY", "NORMAL_VOLATILITY", "LOW_VOLATILITY"}
    assert breakdown["HIGH_VOLATILITY"]["window_count"] == 4
    assert breakdown["HIGH_VOLATILITY"]["executed_trade_count"] == 24
    assert breakdown["HIGH_VOLATILITY"]["net_pnl_total"] == Decimal("1763.01930780")
    assert breakdown["NORMAL_VOLATILITY"]["window_count"] == 3
    assert breakdown["NORMAL_VOLATILITY"]["negative_window_count"] == 2
    assert breakdown["LOW_VOLATILITY"]["window_count"] == 3
    assert breakdown["LOW_VOLATILITY"]["positive_window_count"] == 3
