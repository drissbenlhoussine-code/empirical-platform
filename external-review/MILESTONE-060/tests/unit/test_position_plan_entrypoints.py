"""CLI behavior tests for MILESTONE-060 position-plan entrypoints."""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

from empirical_platform.entrypoints import build_position_plan as build_module
from empirical_platform.entrypoints import get_position_plan as get_module
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import PositionPlanId, TradePlanId
from empirical_platform.shared.identifiers import RuntimeIdentifier


def _position_plan() -> object:
    return build_module.run_build_position_plan(
        position_plan_governance_id="POS-0001",
        source_trade_plan_governance_id="PLAN-0001",
        source_trade_plan_runtime_id="40000001-0000-4000-8000-000000000001",
        account_equity=Decimal("10000"),
        risk_percent=Decimal("0.01"),
    )


def test_build_position_plan_main_rejects_wrong_argument_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("sys.argv", ["empirical-platform-build-position-plan", "POS-0001"])
    with pytest.raises(SystemExit, match="usage: empirical-platform-build-position-plan"):
        build_module.main()


def test_build_position_plan_main_calls_run_with_exact_parsed_arguments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    def fake_run(**kwargs: object) -> object:
        calls.append(kwargs)
        return _StubPlan()

    monkeypatch.setattr(build_module, "run_build_position_plan", fake_run)
    monkeypatch.setattr(
        "sys.argv",
        [
            "empirical-platform-build-position-plan",
            "POS-0001",
            "PLAN-0001",
            "40000001-0000-4000-8000-000000000001",
            "10000",
            "0.01",
        ],
    )
    build_module.main()
    assert calls == [
        {
            "position_plan_governance_id": "POS-0001",
            "source_trade_plan_governance_id": "PLAN-0001",
            "source_trade_plan_runtime_id": "40000001-0000-4000-8000-000000000001",
            "account_equity": Decimal("10000"),
            "risk_percent": Decimal("0.01"),
        }
    ]


def test_get_position_plan_main_rejects_wrong_argument_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("sys.argv", ["empirical-platform-get-position-plan"])
    with pytest.raises(SystemExit, match="usage: empirical-platform-get-position-plan"):
        get_module.main()


def test_get_position_plan_main_calls_run_with_exact_parsed_arguments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    def fake_run(**kwargs: object) -> object:
        calls.append(kwargs)
        return _StubPlan()

    monkeypatch.setattr(get_module, "run_get_position_plan", fake_run)
    monkeypatch.setattr(
        "sys.argv",
        [
            "empirical-platform-get-position-plan",
            "POS-0001",
            "40000002-0000-4000-8000-000000000001",
        ],
    )
    get_module.main()
    assert calls == [
        {
            "position_plan_governance_id": "POS-0001",
            "position_plan_runtime_id": "40000002-0000-4000-8000-000000000001",
        }
    ]


def test_entrypoints_print_json_payloads(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(build_module, "run_build_position_plan", lambda **_: _StubPlan())
    monkeypatch.setattr(
        "sys.argv",
        [
            "empirical-platform-build-position-plan",
            "POS-0001",
            "PLAN-0001",
            "40000001-0000-4000-8000-000000000001",
            "10000",
            "0.01",
        ],
    )
    build_module.main()
    build_payload = json.loads(capsys.readouterr().out)
    assert build_payload["status"] == "APPROVED_POSITION_PLAN"
    assert build_payload["sizing"]["quantity"] == 20

    monkeypatch.setattr(get_module, "run_get_position_plan", lambda **_: _StubPlan())
    monkeypatch.setattr(
        "sys.argv",
        [
            "empirical-platform-get-position-plan",
            "POS-0001",
            "40000002-0000-4000-8000-000000000001",
        ],
    )
    get_module.main()
    get_payload = json.loads(capsys.readouterr().out)
    assert get_payload["governance_id"] == "POS-0001"


class _StubSizing:
    entry_price = Decimal("100.00")
    stop_price = Decimal("95.00")
    risk_per_unit = Decimal("5.00")
    allowed_risk_amount = Decimal("100.00")
    maximum_notional = Decimal("2000.00")
    risk_based_quantity = 20
    capital_based_quantity = 20
    quantity = 20
    position_notional = Decimal("2000.00")
    actual_risk = Decimal("100.00")


class _StubPlan:
    identity = DomainIdentity(
        governance_id=PositionPlanId("POS-0001"),
        runtime_id=RuntimeIdentifier("40000002-0000-4000-8000-000000000001"),
    )
    source_trade_plan_id = TradePlanId("PLAN-0001")
    instrument = "AAPL"
    policy_id = "EQUITY_PERCENT_RISK_SIZING_GATE"
    policy_version = "1"
    policy_maximum_risk_percent = Decimal("0.02")
    policy_maximum_notional_percent = Decimal("0.25")
    policy_allow_fractional_shares = False
    supplied_account_equity = Decimal("10000")
    supplied_risk_percent = Decimal("0.01")
    status = type("S", (), {"value": "APPROVED_POSITION_PLAN"})()
    reasons = ()
    sizing = _StubSizing()
