"""MILESTONE-084 -- CLI argument handling, output, and operator-input reading.

Each entrypoint's `run_*` function is monkeypatched, following the precedent in
`entrypoints.capture_evaluation_evidence_watermark`: this file exercises
argument parsing and formatting without touching real persistence. The real
composition is proven separately by the PostgreSQL integration tests.
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from tests.unit.test_m084_domain_core import (
    EVALUATED_AT,
    a_configuration,
    a_proposal,
    evaluate,
)

from empirical_platform.decision_candidate.operator_trading_configuration import (
    AccountMode,
    OrderType,
)
from empirical_platform.decision_candidate.product_market_inputs import DataFeedKind, MarketStatus
from empirical_platform.decision_candidate.trade_approval import (
    OperatorAction,
    build_approved_order_intent,
    record_operator_decision,
)
from empirical_platform.decision_candidate.trade_proposal import ProposalStatus
from empirical_platform.entrypoints import (
    decide_trade_proposal,
    get_order_intent,
    get_trade_proposal,
    issue_order_intent,
    list_trade_proposals,
    open_evaluation_context,
    prepare_trade_proposal,
    save_trading_configuration,
)
from empirical_platform.usecases.decision_to_approval import DecisionOutcome
from empirical_platform.usecases.decision_to_approval_io import (
    InputError,
    load_json_file,
    read_configuration,
    read_context_request,
    read_market_inputs,
    render_intent_text,
    render_money,
    render_outcome_json,
    render_outcome_text,
    render_proposal_text,
)

CONFIGURATION_DOCUMENT: dict[str, Any] = {
    "configuration_governance_id": "CFG-0001",
    "configuration_version": 1,
    "base_currency": "USD",
    "permitted_markets": ["XNAS"],
    "watchlist": ["AAPL", "MSFT"],
    "prohibited_instruments": ["PENNY"],
    "maximum_deployable_capital": "10000",
    "maximum_capital_per_trade": "2000",
    "maximum_percent_per_trade": "20",
    "minimum_cash_reserve": "1000",
    "maximum_simultaneous_positions": 3,
    "maximum_daily_loss": "500",
    "maximum_daily_order_count": 10,
    "minimum_price": "5",
    "maximum_price": "1000",
    "minimum_liquidity_shares": 100000,
    "maximum_spread_percent": "1",
    "maximum_estimated_slippage_percent": "1",
    "maximum_evidence_age_seconds": 86400,
    "maximum_market_data_age_seconds": 60,
    "permitted_session": "REGULAR",
    "earliest_entry_time": "10:00:00",
    "latest_entry_time": "15:30:00",
    "mandatory_liquidation_time": "15:45:00",
    "operator_timezone": "Europe/Helsinki",
    "exchange_calendar_policy": "XNAS-REGULAR-2026",
    "proposal_expiry_seconds": 300,
    "approval_expiry_seconds": 120,
    "default_order_type": "LIMIT",
    "permitted_order_types": ["LIMIT", "MARKET"],
    "limit_price_policy": "ASK",
    "stop_loss_percent": "2",
    "profit_exit_percent": "4",
    "maximum_leverage": "1",
    "short_selling_permitted": False,
    "overnight_positions_permitted": False,
    "account_mode": "PREPARATION",
    "kill_switch": "DISENGAGED",
}

OBSERVED_AT = (EVALUATED_AT - timedelta(seconds=5)).isoformat()

INPUTS_DOCUMENT: dict[str, Any] = {
    "quote": {
        "quote_id": "QTE-0001",
        "provider_id": "OPERATOR-ASSERTED",
        "symbol": "AAPL",
        "bid": "199.95",
        "ask": "200.10",
        "last_trade": "200.00",
        "observed_at": OBSERVED_AT,
        "feed_kind": "REAL_TIME",
    },
    "account": {
        "account_snapshot_id": "ACC-0001",
        "provider_id": "OPERATOR-ASSERTED",
        "account_reference": "PREP-1",
        "base_currency": "USD",
        "cash_available": "5000",
        "equity_total": "10000",
        "realized_pnl_today": "0",
        "orders_submitted_today": 0,
        "observed_at": OBSERVED_AT,
    },
    "session": {
        "session_id": "SES-0001",
        "provider_id": "OPERATOR-ASSERTED",
        "market": "XNAS",
        "status": "OPEN",
        "observed_at": OBSERVED_AT,
    },
    "instrument": {
        "symbol": "AAPL",
        "market": "XNAS",
        "currency": "USD",
        "is_fractionable": False,
        "lot_size": 1,
    },
    "liquidity": {
        "symbol": "AAPL",
        "average_daily_volume_shares": 50000000,
        "observed_at": OBSERVED_AT,
    },
    "cost_estimate": {
        "estimate_id": "CST-0001",
        "provider_id": "OPERATOR-ASSERTED",
        "symbol": "AAPL",
        "commission": "1.00",
        "estimated_slippage_percent": "0.1",
        "observed_at": OBSERVED_AT,
    },
    "positions": [],
    "open_orders": [],
    "evidence_age_seconds": "60",
}

CONTEXT_DOCUMENT: dict[str, Any] = {
    "evaluation_context_id": "ECX-0001",
    "configuration_governance_id": "CFG-0001",
    "configuration_version": 1,
    "watermark_governance_id": "WM-0001",
    "quote_id": "QTE-0001",
    "account_snapshot_id": "ACC-0001",
    "session_id": "SES-0001",
    "cost_estimate_id": "CST-0001",
    "instrument_universe_version": "UNIVERSE-2026-06",
    "strategy_version": "STRATEGY-0001",
    "created_at": EVALUATED_AT.isoformat(),
}


class TestReadingAConfiguration:
    def test_a_complete_document_reads_into_a_configuration(self) -> None:
        configuration = read_configuration(CONFIGURATION_DOCUMENT)
        assert configuration.configuration_governance_id == "CFG-0001"
        assert configuration.account_mode is AccountMode.PREPARATION
        assert configuration.maximum_capital_per_trade == Decimal("2000")

    def test_an_amount_written_as_a_json_number_is_refused(self) -> None:
        # A JSON number is a float. 200.10 read through a float is no longer
        # the amount that was written, so it is refused rather than rounded.
        document = {**CONFIGURATION_DOCUMENT, "maximum_capital_per_trade": 2000.0}
        with pytest.raises(InputError, match="not a JSON number"):
            read_configuration(document)

    def test_a_missing_key_is_named_rather_than_defaulted(self) -> None:
        document = {k: v for k, v in CONFIGURATION_DOCUMENT.items() if k != "base_currency"}
        with pytest.raises(InputError, match="missing 'base_currency'"):
            read_configuration(document)

    def test_a_value_outside_a_closed_enumeration_lists_the_permitted_ones(self) -> None:
        document = {**CONFIGURATION_DOCUMENT, "account_mode": "PAPER_TRADING"}
        with pytest.raises(InputError, match="must be one of LIVE, PAPER, PREPARATION"):
            read_configuration(document)

    def test_a_forbidden_policy_is_still_refused_by_the_type(self) -> None:
        # The reader reads; the type refuses a policy this product will not hold.
        document = {**CONFIGURATION_DOCUMENT, "account_mode": "LIVE"}
        with pytest.raises(ValueError, match="account_mode must be PREPARATION"):
            read_configuration(document)

    def test_an_entry_time_carrying_an_offset_is_refused(self) -> None:
        document = {**CONFIGURATION_DOCUMENT, "earliest_entry_time": "10:00:00+03:00"}
        with pytest.raises(InputError, match="must be a local time with no offset"):
            read_configuration(document)

    def test_a_non_object_document_is_refused(self) -> None:
        with pytest.raises(InputError, match="must be a JSON object"):
            read_configuration([1, 2, 3])

    def test_a_boolean_where_a_count_belongs_is_refused(self) -> None:
        document = {**CONFIGURATION_DOCUMENT, "maximum_daily_order_count": True}
        with pytest.raises(InputError, match="not a boolean"):
            read_configuration(document)


class TestReadingMarketInputs:
    def test_a_complete_document_reads_into_snapshots(self) -> None:
        inputs = read_market_inputs(INPUTS_DOCUMENT)
        assert inputs.quote.ask == Decimal("200.10")
        assert inputs.quote.feed_kind is DataFeedKind.REAL_TIME
        assert inputs.session.status is MarketStatus.OPEN
        assert inputs.cost_estimate is not None
        assert inputs.evidence_age_seconds == Decimal("60")

    def test_a_cost_estimate_may_be_absent(self) -> None:
        document = {**INPUTS_DOCUMENT, "cost_estimate": None}
        assert read_market_inputs(document).cost_estimate is None

    def test_an_instant_without_an_offset_is_refused(self) -> None:
        quote = {**INPUTS_DOCUMENT["quote"], "observed_at": "2026-06-10T11:59:55"}
        with pytest.raises(InputError, match="must carry a UTC offset"):
            read_market_inputs({**INPUTS_DOCUMENT, "quote": quote})

    def test_positions_and_open_orders_default_to_empty(self) -> None:
        document = {
            k: v for k, v in INPUTS_DOCUMENT.items() if k not in {"positions", "open_orders"}
        }
        inputs = read_market_inputs(document)
        assert inputs.positions == ()
        assert inputs.open_orders == ()

    def test_a_position_entry_is_read(self) -> None:
        document = {
            **INPUTS_DOCUMENT,
            "positions": [{"symbol": "AAPL", "quantity": 5, "average_price": "190.00"}],
        }
        inputs = read_market_inputs(document)
        assert inputs.positions[0].symbol == "AAPL"
        assert inputs.positions[0].average_price == Decimal("190.00")


class TestReadingAContextRequest:
    def test_a_complete_document_reads_into_a_command(self) -> None:
        command = read_context_request(CONTEXT_DOCUMENT)
        assert command.evaluation_context_id == "ECX-0001"
        assert command.watermark_governance_id == "WM-0001"
        assert command.research_session_id is None

    def test_optional_identities_are_read_when_present(self) -> None:
        command = read_context_request({**CONTEXT_DOCUMENT, "research_session_id": "RS-0001"})
        assert command.research_session_id == "RS-0001"

    def test_a_missing_watermark_identity_is_refused(self) -> None:
        document = {k: v for k, v in CONTEXT_DOCUMENT.items() if k != "watermark_governance_id"}
        with pytest.raises(InputError, match="missing 'watermark_governance_id'"):
            read_context_request(document)


class TestLoadingAFile:
    def test_a_missing_file_is_named(self, tmp_path: Path) -> None:
        with pytest.raises(InputError, match="cannot read"):
            load_json_file(str(tmp_path / "absent.json"))

    def test_malformed_json_is_named(self, tmp_path: Path) -> None:
        path = tmp_path / "broken.json"
        path.write_text("{not json", encoding="utf-8")
        with pytest.raises(InputError, match="not valid JSON"):
            load_json_file(str(path))

    def test_a_valid_file_round_trips(self, tmp_path: Path) -> None:
        path = tmp_path / "configuration.json"
        path.write_text(json.dumps(CONFIGURATION_DOCUMENT), encoding="utf-8")
        assert read_configuration(load_json_file(str(path))).configuration_version == 1


class TestRendering:
    def test_money_is_shown_in_cents_not_in_the_column_scale(self) -> None:
        # NUMERIC(20,8) returns 200.10000000; a person reading a price wants
        # 200.10, and normalizing alone would give 200.1.
        assert render_money(Decimal("200.10000000")) == "200.10"
        assert render_money(Decimal("1")) == "1.00"
        assert render_money(Decimal("1803.70")) == "1803.70"

    def test_sub_cent_precision_is_shown_rather_than_rounded_away(self) -> None:
        assert render_money(Decimal("0.12345")) == "0.12345"

    def test_a_proposal_renders_its_terms_and_fingerprint(self) -> None:
        text = render_proposal_text(a_proposal())
        assert "BUY 9 AAPL" in text
        assert "limit 200.10" in text
        # 25, not 26: FIND-M-01 removed the `notional_limit` check, which could
        # never report FAILED because sizing already clips the budget to the cap.
        # The literal is the canary -- a check appearing or disappearing must be
        # a deliberate edit here -- and the second assertion keeps the rendered
        # figure tied to the engine rather than to this expectation.
        assert "risk checks passed: 25" in text
        assert f"risk checks passed: {len(a_proposal().risk_checks)}" in text

    def test_a_no_trade_names_its_reason_and_the_checks_that_did_not_pass(self) -> None:
        outcome = evaluate(cost_estimate=None)
        text = render_outcome_text(outcome)
        assert "NO_TRADE: COST_ESTIMATE_MISSING" in text
        assert "cost_estimate" in text

    def test_an_intent_says_out_loud_that_it_cannot_be_sent(self) -> None:
        prepared = a_proposal()
        decision = record_operator_decision(
            proposal=prepared,
            decision_governance_id="DEC-0001",
            action=OperatorAction.APPROVE,
            operator_identity="alice",
            decided_at=EVALUATED_AT + timedelta(seconds=10),
            approval_expiry_seconds=120,
        )
        intent = build_approved_order_intent(
            intent_governance_id="INT-0001",
            proposal=replace(prepared, status=ProposalStatus.APPROVED),
            decision=decision,
            created_at=EVALUATED_AT + timedelta(seconds=20),
            idempotency_key="IDEM-0001",
        )
        text = render_intent_text(intent)
        assert "NOT_SUBMITTED" in text
        assert "no way to send this to a broker" in text


class TestEntrypointArguments:
    """`main()` refuses a wrong argument count before touching persistence."""

    @pytest.mark.parametrize(
        ("module", "argv"),
        [
            (save_trading_configuration, []),
            (save_trading_configuration, ["a", "b"]),
            (open_evaluation_context, []),
            (prepare_trade_proposal, ["one", "two"]),
            (get_trade_proposal, []),
            (get_trade_proposal, ["a", "b"]),
            (decide_trade_proposal, ["a", "b", "APPROVE"]),
            (decide_trade_proposal, ["a", "b", "APPROVE", "alice", "t", "extra"]),
            (issue_order_intent, ["a", "b"]),
            (get_order_intent, []),
            (list_trade_proposals, ["PREPARED", "APPROVED"]),
        ],
    )
    def test_a_wrong_argument_count_exits_with_usage(
        self, monkeypatch: pytest.MonkeyPatch, module: ModuleType, argv: list[str]
    ) -> None:
        monkeypatch.setattr("sys.argv", ["prog", *argv])
        with pytest.raises(SystemExit, match="usage:"):
            module.main()


class TestEntrypointOutput:
    def test_save_trading_configuration_prints_what_it_stored(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        path = tmp_path / "configuration.json"
        path.write_text(json.dumps(CONFIGURATION_DOCUMENT), encoding="utf-8")
        monkeypatch.setattr(
            save_trading_configuration,
            "run_save_trading_configuration",
            lambda **_: a_configuration(),
        )
        monkeypatch.setattr("sys.argv", ["prog", str(path)])
        save_trading_configuration.main()
        assert "stored configuration CFG-084-0001 v1 [PREPARATION" in capsys.readouterr().out

    def test_save_trading_configuration_json_output_is_sorted(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        path = tmp_path / "configuration.json"
        path.write_text(json.dumps(CONFIGURATION_DOCUMENT), encoding="utf-8")
        monkeypatch.setattr(
            save_trading_configuration,
            "run_save_trading_configuration",
            lambda **_: a_configuration(),
        )
        monkeypatch.setattr("sys.argv", ["prog", "--json", str(path)])
        save_trading_configuration.main()
        payload = json.loads(capsys.readouterr().out)
        assert payload["account_mode"] == "PREPARATION"
        assert list(payload) == sorted(payload)

    def test_prepare_trade_proposal_prints_a_no_trade_as_a_no_trade(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        path = tmp_path / "inputs.json"
        path.write_text(json.dumps(INPUTS_DOCUMENT), encoding="utf-8")
        refusal = evaluate(cost_estimate=None)
        monkeypatch.setattr(
            prepare_trade_proposal, "run_prepare_trade_proposal", lambda **_: refusal
        )
        monkeypatch.setattr(
            "sys.argv",
            ["prog", "PRP-1", "ECX-1", "AAPL", EVALUATED_AT.isoformat(), str(path)],
        )
        prepare_trade_proposal.main()
        assert "NO_TRADE: COST_ESTIMATE_MISSING" in capsys.readouterr().out

    def test_prepare_trade_proposal_refuses_a_naive_evaluation_instant(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        path = tmp_path / "inputs.json"
        path.write_text(json.dumps(INPUTS_DOCUMENT), encoding="utf-8")
        monkeypatch.setattr(
            "sys.argv", ["prog", "PRP-1", "ECX-1", "AAPL", "2026-06-10T12:00:00", str(path)]
        )
        with pytest.raises(InputError, match="must carry a UTC offset"):
            prepare_trade_proposal.main()

    def test_decide_trade_proposal_refuses_an_unknown_action(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("sys.argv", ["prog", "PRP-1", "DEC-1", "AUTO_APPROVE", "alice"])
        with pytest.raises(InputError, match="must be one of APPROVE, CANCEL, REJECT"):
            decide_trade_proposal.main()

    def test_decide_trade_proposal_prints_who_decided(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        prepared = a_proposal()
        decision = record_operator_decision(
            proposal=prepared,
            decision_governance_id="DEC-0001",
            action=OperatorAction.APPROVE,
            operator_identity="alice",
            decided_at=EVALUATED_AT + timedelta(seconds=10),
            approval_expiry_seconds=120,
        )
        outcome = DecisionOutcome(
            decision=decision, proposal=replace(prepared, status=ProposalStatus.APPROVED)
        )
        monkeypatch.setattr(decide_trade_proposal, "run_decide_trade_proposal", lambda **_: outcome)
        monkeypatch.setattr(
            "sys.argv",
            ["prog", "PRP-0001", "DEC-0001", "APPROVE", "alice", (EVALUATED_AT).isoformat()],
        )
        decide_trade_proposal.main()
        assert "by alice at" in capsys.readouterr().out

    def test_list_trade_proposals_says_so_when_the_queue_is_empty(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(list_trade_proposals, "run_list_trade_proposals", lambda **_: ())
        monkeypatch.setattr("sys.argv", ["prog"])
        list_trade_proposals.main()
        assert "no proposals in PREPARED" in capsys.readouterr().out

    def test_list_trade_proposals_refuses_an_unknown_status(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("sys.argv", ["prog", "SUBMITTED"])
        with pytest.raises(InputError, match="status must be one of"):
            list_trade_proposals.main()

    def test_get_trade_proposal_renders_json_on_request(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        proposal = a_proposal()
        monkeypatch.setattr(get_trade_proposal, "run_get_trade_proposal", lambda **_: proposal)
        monkeypatch.setattr("sys.argv", ["prog", "--json", "PRP-0001"])
        get_trade_proposal.main()
        payload = json.loads(capsys.readouterr().out)
        assert payload["quantity"] == 9
        assert payload["order_type"] == OrderType.LIMIT.value
        assert payload["content_fingerprint"] == proposal.content_fingerprint


class TestOutcomeJsonShape:
    def test_a_proposal_outcome_names_itself_a_proposal(self) -> None:
        payload = render_outcome_json(evaluate())
        assert payload["decision"] == "PROPOSAL"
        assert payload["no_trade_reason"] is None
        assert payload["proposal"] is not None

    def test_a_refusal_names_itself_a_no_trade(self) -> None:
        payload = render_outcome_json(evaluate(cost_estimate=None))
        assert payload["decision"] == "NO_TRADE"
        assert payload["no_trade_reason"] == "COST_ESTIMATE_MISSING"
        assert payload["proposal"] is None
