"""CLI behavior tests for MILESTONE-061 historical backtest entrypoints."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from empirical_platform.entrypoints import get_historical_backtest_run as get_module
from empirical_platform.entrypoints import run_historical_backtest as run_module
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import BacktestRunId, DatasetId
from empirical_platform.shared.identifiers import RuntimeIdentifier

_FIXTURE_PATH = str(
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "m061_historical_backtest"
    / "synthetic_6instrument_historical_backtest_dataset.json"
)


def test_run_historical_backtest_main_rejects_wrong_argument_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("sys.argv", ["empirical-platform-run-historical-backtest", "BTRUN-6101"])
    with pytest.raises(SystemExit, match="usage: empirical-platform-run-historical-backtest"):
        run_module.main()


def test_run_historical_backtest_main_calls_run_with_exact_parsed_arguments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    def fake_run(**kwargs: object) -> object:
        calls.append(kwargs)
        return _StubRun()

    monkeypatch.setattr(run_module, "run_historical_backtest", fake_run)
    monkeypatch.setattr(
        "sys.argv",
        [
            "empirical-platform-run-historical-backtest",
            "BTRUN-6101",
            _FIXTURE_PATH,
            "10000",
            "0.01",
            "5",
            "3",
            "5",
            "5",
        ],
    )
    run_module.main()
    assert calls == [
        {
            "run_governance_id": "BTRUN-6101",
            "dataset_file": _FIXTURE_PATH,
            "account_equity": Decimal("10000"),
            "risk_percent": Decimal("0.01"),
            "reference_window_size": 5,
            "holding_horizon_bars": 3,
            "entry_slippage_bps": Decimal("5"),
            "exit_slippage_bps": Decimal("5"),
        }
    ]


def test_get_historical_backtest_main_rejects_wrong_argument_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("sys.argv", ["empirical-platform-get-historical-backtest-run"])
    with pytest.raises(SystemExit, match="usage: empirical-platform-get-historical-backtest-run"):
        get_module.main()


def test_get_historical_backtest_main_calls_run_with_exact_parsed_arguments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    def fake_run(**kwargs: object) -> object:
        calls.append(kwargs)
        return _StubRun()

    monkeypatch.setattr(get_module, "run_get_historical_backtest_run", fake_run)
    monkeypatch.setattr(
        "sys.argv",
        [
            "empirical-platform-get-historical-backtest-run",
            "BTRUN-6101",
            "40000002-0000-4000-8000-000000000001",
        ],
    )
    get_module.main()
    assert calls == [
        {
            "backtest_run_governance_id": "BTRUN-6101",
            "backtest_run_runtime_id": "40000002-0000-4000-8000-000000000001",
        }
    ]


def test_entrypoints_print_json_payloads(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(run_module, "run_historical_backtest", lambda **_: _StubRun())
    monkeypatch.setattr(
        "sys.argv",
        [
            "empirical-platform-run-historical-backtest",
            "BTRUN-6101",
            _FIXTURE_PATH,
            "10000",
            "0.01",
        ],
    )
    run_module.main()
    run_payload = json.loads(capsys.readouterr().out)
    assert run_payload["dataset_id"] == "DATASET-6101"
    assert run_payload["simulated_trade_count"] == 1

    monkeypatch.setattr(get_module, "run_get_historical_backtest_run", lambda **_: _StubRun())
    monkeypatch.setattr(
        "sys.argv",
        [
            "empirical-platform-get-historical-backtest-run",
            "BTRUN-6101",
            "40000002-0000-4000-8000-000000000001",
        ],
    )
    get_module.main()
    get_payload = json.loads(capsys.readouterr().out)
    assert get_payload["governance_id"] == "BTRUN-6101"


class _StubTrade:
    trade_sequence = 1
    instrument = "AAPL"
    evaluation_cutoff = type("T", (), {"isoformat": lambda self: "2026-08-10T13:45:00+00:00"})()
    source_scan_reference = "SCAN-0001"
    source_decision_candidate_reference = "DCAND-0001"
    source_trade_plan_reference = "PLAN-0001"
    source_position_plan_reference = "POS-0001"
    scan_rank = 1
    ranking_score = Decimal("1.5")
    entry_timestamp = type("T", (), {"isoformat": lambda self: "2026-08-10T13:46:00+00:00"})()
    planned_entry_price = Decimal("101.0")
    simulated_entry_price = Decimal("101.0")
    planned_stop_price = Decimal("100.5")
    planned_target_price = Decimal("102.5")
    exit_timestamp = type("T", (), {"isoformat": lambda self: "2026-08-10T13:47:00+00:00"})()
    exit_price = Decimal("102.5")
    outcome = type("S", (), {"value": "TARGET_HIT"})()
    ambiguity_policy = type("S", (), {"value": "STOP_FIRST"})()
    ambiguity_triggered = False
    quantity = 24
    gross_pnl = Decimal("36.0")
    transaction_costs = Decimal("2.2")
    net_pnl = Decimal("33.8")
    risk_amount = Decimal("12.0")
    r_multiple = Decimal("2.8")
    holding_bars = 2


class _StubRun:
    identity = DomainIdentity(
        governance_id=BacktestRunId("BTRUN-6101"),
        runtime_id=RuntimeIdentifier("40000002-0000-4000-8000-000000000001"),
    )
    dataset_id = DatasetId("DATASET-6101")
    dataset_version = "1"
    dataset_source_kind = "FIXED_TEST_UNIVERSE"
    dataset_sha256 = "0" * 64
    interval = type("S", (), {"value": "ONE_MINUTE"})()
    universe = ("AAPL",)
    dataset_start_timestamp = type(
        "T",
        (),
        {"isoformat": lambda self: "2026-08-10T13:40:00+00:00"},
    )()
    dataset_end_timestamp = type(
        "T",
        (),
        {"isoformat": lambda self: "2026-08-10T13:51:00+00:00"},
    )()
    dataset_total_bars = 12
    reference_window_size = 5
    decision_cadence = "BAR_CLOSE"
    strategy_id = "PRIOR_WINDOW_BREAKOUT_VOLUME_CONFIRMATION"
    strategy_version = "1"
    ranking_model_id = "BREAKOUT_VOLUME_STRENGTH_SUM"
    ranking_model_version = "1"
    risk_policy_id = "REFERENCE_HIGH_BREAKOUT_RISK_GATE"
    risk_policy_version = "1"
    risk_policy_target_projection_percent = Decimal("0.02")
    risk_policy_minimum_reward_risk_ratio = Decimal("2.0")
    sizing_policy_id = "EQUITY_PERCENT_RISK_SIZING_GATE"
    sizing_policy_version = "1"
    sizing_policy_maximum_risk_percent = Decimal("0.02")
    sizing_policy_maximum_notional_percent = Decimal("0.25")
    sizing_policy_allow_fractional_shares = False
    supplied_account_equity = Decimal("10000")
    supplied_risk_percent = Decimal("0.01")
    execution_assumption_id = "NEXT_BAR_OPEN_ENTRY"
    execution_assumption_version = "1"
    outcome_model_id = "STOP_TARGET_TIME_EXIT"
    outcome_model_version = "1"
    outcome_model_no_overnight = True
    cost_model_id = "BPS_SLIPPAGE_WITH_OPTIONAL_FIXED_COMMISSION"
    cost_model_version = "1"
    cost_model_entry_slippage_bps = Decimal("5")
    cost_model_exit_slippage_bps = Decimal("5")
    cost_model_fixed_commission_per_side = Decimal("0")
    ambiguity_policy = type("S", (), {"value": "STOP_FIRST"})()
    holding_horizon_bars = 3
    status = type("S", (), {"value": "COMPLETED"})()
    product_classification = type(
        "S",
        (),
        {"value": "VALIDATION_ENGINE_PROVEN_FIXTURE_RESULTS_RECORDED"},
    )()
    evaluated_cutoff_count = 4
    evaluated_opportunity_count = 24
    approved_trade_plan_count = 5
    approved_position_plan_count = 5
    simulated_trade_count = 1
    executed_trade_count = 1
    win_count = 1
    loss_count = 0
    flat_count = 0
    time_exit_count = 0
    no_entry_count = 0
    gross_pnl = Decimal("36.0")
    net_pnl = Decimal("33.8")
    average_net_pnl = Decimal("33.8")
    average_r = Decimal("2.8")
    total_r = Decimal("2.8")
    win_rate = Decimal("1")
    profit_factor = None
    maximum_realized_pnl_drawdown = Decimal("0")
    trades = (_StubTrade(),)
