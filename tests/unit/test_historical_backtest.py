from __future__ import annotations

import copy
import json
from decimal import Decimal
from pathlib import Path

import pytest

from empirical_platform.decision_candidate.historical_backtest import (
    HistoricalTradeOutcome,
    build_historical_backtest_run,
)
from empirical_platform.decision_candidate.position_plan import PositionSizingContext
from empirical_platform.entrypoints.run_historical_backtest import _parse_dataset_file
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import BacktestRunId
from empirical_platform.shared.identifiers import (
    DeterministicRuntimeIdentifierGenerator,
    RuntimeIdentifier,
)

_FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "m061_historical_backtest"
    / "synthetic_6instrument_historical_backtest_dataset.json"
)


def _id_generator() -> DeterministicRuntimeIdentifierGenerator:
    values = [f"00000000-0000-4000-8000-{index:012d}" for index in range(1, 400)]
    return DeterministicRuntimeIdentifierGenerator(values)


def _build_run() -> object:
    dataset = _parse_dataset_file(str(_FIXTURE_PATH))
    return build_historical_backtest_run(
        identity=DomainIdentity(
            governance_id=BacktestRunId("BTRUN-6101"),
            runtime_id=RuntimeIdentifier("11111111-1111-4111-8111-111111111111"),
        ),
        dataset=dataset,
        sizing_context=PositionSizingContext(
            account_equity=Decimal("10000"),
            risk_percent=Decimal("0.01"),
        ),
        runtime_identifier_generator=_id_generator(),
    )


def test_historical_backtest_fixture_produces_expected_trade_outcomes() -> None:
    run = _build_run()

    assert run.dataset_id.value == "DATASET-6101"
    assert run.dataset_version == "1"
    assert run.evaluated_cutoff_count == 4
    assert run.evaluated_opportunity_count == 24
    assert run.approved_trade_plan_count == 5
    assert run.approved_position_plan_count == 5
    assert run.simulated_trade_count == 5
    assert run.executed_trade_count == 4
    assert run.win_count == 2
    assert run.loss_count == 2
    assert run.time_exit_count == 1
    assert run.no_entry_count == 1
    assert run.gross_pnl == Decimal("19.440")
    assert run.net_pnl == Decimal("9.7342800")
    assert run.total_r == Decimal("0.945156666666666666666666667")
    assert run.maximum_realized_pnl_drawdown == Decimal("31.2348000")

    outcomes_by_instrument = {str(trade.instrument): trade for trade in run.trades}
    assert outcomes_by_instrument["AAPL"].outcome is HistoricalTradeOutcome.TARGET_HIT
    assert outcomes_by_instrument["AMZN"].outcome is HistoricalTradeOutcome.STOP_HIT
    assert outcomes_by_instrument["NVDA"].outcome is HistoricalTradeOutcome.STOP_HIT
    assert outcomes_by_instrument["NVDA"].ambiguity_triggered is True
    assert outcomes_by_instrument["GOOG"].outcome is HistoricalTradeOutcome.NO_ENTRY
    assert outcomes_by_instrument["TSLA"].outcome is HistoricalTradeOutcome.TIME_EXIT


def test_future_bar_mutation_outside_consumed_horizon_does_not_change_earlier_trades(
    tmp_path: Path,
) -> None:
    original_run = _build_run()
    raw = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
    mutated = copy.deepcopy(raw)
    # Mutate one bar that is outside every consumed horizon for the first
    # three trades; this should not change their historical decisions or
    # outcomes if M061 remains free of accidental look-ahead.
    mutated["instruments"][0]["bars"][11]["high"] = "500.0"
    mutated["instruments"][0]["bars"][11]["close"] = "499.9"
    mutated_path = tmp_path / "mutated_dataset.json"
    mutated_path.write_text(json.dumps(mutated, indent=2), encoding="utf-8")

    mutated_dataset = _parse_dataset_file(str(mutated_path))
    mutated_run = build_historical_backtest_run(
        identity=DomainIdentity(
            governance_id=BacktestRunId("BTRUN-6102"),
            runtime_id=RuntimeIdentifier("22222222-2222-4222-8222-222222222222"),
        ),
        dataset=mutated_dataset,
        sizing_context=PositionSizingContext(
            account_equity=Decimal("10000"),
            risk_percent=Decimal("0.01"),
        ),
        runtime_identifier_generator=_id_generator(),
    )

    for original_trade, mutated_trade in zip(
        original_run.trades[:3],
        mutated_run.trades[:3],
        strict=True,
    ):
        assert original_trade.instrument == mutated_trade.instrument
        assert original_trade.outcome == mutated_trade.outcome
        assert original_trade.net_pnl == mutated_trade.net_pnl
        assert (
            original_trade.source_trade_plan_reference == mutated_trade.source_trade_plan_reference
        )


def test_historical_dataset_requires_one_shared_timestamp_grid(tmp_path: Path) -> None:
    raw = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
    raw["instruments"][1]["bars"].pop()
    malformed_path = tmp_path / "malformed_dataset.json"
    malformed_path.write_text(json.dumps(raw, indent=2), encoding="utf-8")

    with pytest.raises(
        ValueError,
        match="all historical instrument series must share one canonical timestamp grid",
    ):
        _parse_dataset_file(str(malformed_path))
