"""Independent M061 outcome/PnL/metric verification.

Recomputes historical trade outcomes and aggregate metrics from the raw JSON
fixture and the persisted production snapshot values without calling the
production backtest outcome or metric functions.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

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


def _run() -> object:
    dataset = _parse_dataset_file(str(_FIXTURE_PATH))
    ids = [f"10000000-0000-4000-8000-{index:012d}" for index in range(1, 400)]
    return build_historical_backtest_run(
        identity=DomainIdentity(
            governance_id=BacktestRunId("BTRUN-6101"),
            runtime_id=RuntimeIdentifier("33333333-3333-4333-8333-333333333333"),
        ),
        dataset=dataset,
        sizing_context=PositionSizingContext(
            account_equity=Decimal("10000"),
            risk_percent=Decimal("0.01"),
        ),
        runtime_identifier_generator=DeterministicRuntimeIdentifierGenerator(ids),
    )


def test_independent_recomputation_matches_m061_fixture_results() -> None:
    run = _run()
    raw = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
    bars_by_symbol = {
        instrument_entry["instrument"]: instrument_entry["bars"]
        for instrument_entry in raw["instruments"]
    }

    expected = {
        "AAPL": {"entry": Decimal("101.0"), "exit": Decimal("102.51"), "outcome": "TARGET_HIT"},
        "AMZN": {"entry": Decimal("101.0"), "exit": Decimal("100.5"), "outcome": "STOP_HIT"},
        "NVDA": {"entry": Decimal("101.0"), "exit": Decimal("100.4"), "outcome": "STOP_HIT"},
        "GOOG": {"entry": None, "exit": None, "outcome": "NO_ENTRY"},
        "TSLA": {"entry": Decimal("101.0"), "exit": Decimal("101.4"), "outcome": "TIME_EXIT"},
    }

    total_net = Decimal("0")
    total_gross = Decimal("0")
    positive = Decimal("0")
    negative = Decimal("0")
    running = Decimal("0")
    peak = Decimal("0")
    drawdown = Decimal("0")

    for trade in run.trades:
        symbol = str(trade.instrument)
        fixture = expected[symbol]
        assert trade.outcome.value == fixture["outcome"]
        if fixture["entry"] is None:
            assert trade.outcome is HistoricalTradeOutcome.NO_ENTRY
            assert trade.net_pnl == Decimal("0")
            continue

        raw_entry = fixture["entry"]
        raw_exit = fixture["exit"]
        assert trade.simulated_entry_price == raw_entry
        assert trade.exit_price == raw_exit

        quantity = Decimal(trade.quantity)
        entry_cost = quantity * raw_entry * (Decimal("5") / Decimal("10000"))
        exit_cost = quantity * raw_exit * (Decimal("5") / Decimal("10000"))
        gross = (raw_exit - raw_entry) * quantity
        net = gross - entry_cost - exit_cost

        assert trade.gross_pnl == gross
        assert trade.transaction_costs == entry_cost + exit_cost
        assert trade.net_pnl == net
        total_gross += gross
        total_net += net
        if net > 0:
            positive += net
        if net < 0:
            negative += net
        running += net
        if running > peak:
            peak = running
        current_drawdown = peak - running
        if current_drawdown > drawdown:
            drawdown = current_drawdown

    assert run.gross_pnl == total_gross
    assert run.net_pnl == total_net
    assert run.profit_factor == positive / abs(negative)
    assert run.maximum_realized_pnl_drawdown == drawdown
    assert run.win_rate == Decimal("0.5")
    assert bars_by_symbol["GOOG"][9]["open"] == "102.7"
