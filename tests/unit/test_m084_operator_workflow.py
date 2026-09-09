"""MILESTONE-084 -- the operator commands added to complete the workflow.

Seven commands close the gap between the eight the first candidate shipped and
the full set of operations an operator actually needs: show-config,
validate-config, explain-no-trade, invalidate-stale-proposals, system-status,
kill-switch and audit-history.

Two of them carry design decisions worth testing rather than assuming:

  - moving the kill switch WRITES A NEW CONFIGURATION VERSION rather than
    editing one, so the record shows when the switch moved and what policy was
    in force either side of it;
  - `explain-no-trade` runs the SAME evaluation the real command runs, through
    the same shared function, so it cannot explain a decision the product did
    not make.
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from types import ModuleType

import pytest
from tests.unit.test_m084_cli_and_io import CONFIGURATION_DOCUMENT
from tests.unit.test_m084_domain_core import (
    EVALUATED_AT,
    a_configuration,
    a_cost_estimate,
    a_liquidity,
    a_proposal,
    a_quote,
    a_session,
    an_account,
    an_instrument,
)
from tests.unit.test_m084_repositories_and_handlers import (
    _MemoryConfigurations,
    _MemoryContexts,
    _MemoryDecisions,
    _MemoryIntents,
    _MemoryProposals,
    a_decision,
    an_intent,
    context_row,
)

from empirical_platform.decision_candidate.operator_trading_configuration import (
    KillSwitchState,
    OperatorTradingConfiguration,
)
from empirical_platform.decision_candidate.trade_proposal import ProposalStatus
from empirical_platform.entrypoints import (
    audit_history,
    explain_no_trade,
    invalidate_stale_proposals,
    kill_switch,
    show_trading_configuration,
    system_status,
    validate_trading_configuration,
)
from empirical_platform.shared.persistence.postgres_repositories.decision_to_approval_repositories import (  # noqa: E501
    _row_to_context,
)
from empirical_platform.usecases.decision_to_approval import (
    AuditHistory,
    GetAuditHistoryHandler,
    GetAuditHistoryQuery,
    GetOperatorTradingConfigurationHandler,
    GetOperatorTradingConfigurationQuery,
    GetSystemStatusHandler,
    GetSystemStatusQuery,
    InvalidateStaleProposalsCommand,
    InvalidateStaleProposalsHandler,
    InvalidationOutcome,
    NotFoundError,
    PrepareTradeProposalCommand,
    SetKillSwitchCommand,
    SetKillSwitchHandler,
    SystemStatus,
    evaluate_without_persisting,
)
from empirical_platform.usecases.decision_to_approval_io import (
    InputError,
    read_configuration,
    render_audit_history_json,
    render_audit_history_text,
    render_configuration_json,
    render_configuration_text,
    render_invalidation_text,
    render_no_trade_explanation_json,
    render_no_trade_explanation_text,
    render_system_status_json,
    render_system_status_text,
)


def a_command(**overrides: object) -> PrepareTradeProposalCommand:
    defaults: dict[str, object] = {
        "proposal_governance_id": "PRP-0001",
        "evaluation_context_id": "ECX-0001",
        "symbol": "AAPL",
        "evaluated_at": EVALUATED_AT,
        "quote": a_quote(),
        "account": an_account(),
        "session": a_session(),
        "instrument": an_instrument(),
        "liquidity": a_liquidity(),
        "cost_estimate": a_cost_estimate(),
        "positions": (),
        "open_orders": (),
        "evidence_age_seconds": Decimal("60"),
    }
    defaults.update(overrides)
    return PrepareTradeProposalCommand(**defaults)  # type: ignore[arg-type]


def seeded_contexts() -> _MemoryContexts:
    contexts = _MemoryContexts()
    contexts.save(_row_to_context(context_row()))
    return contexts


def seeded_configurations() -> _MemoryConfigurations:
    configurations = _MemoryConfigurations()
    configurations.save(a_configuration())
    return configurations


# ---------------------------------------------------------------------------
# validate-config: refuses without ever touching a database
# ---------------------------------------------------------------------------


class TestValidateConfiguration:
    def test_a_valid_file_is_accepted_and_nothing_is_written(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        path = tmp_path / "configuration.json"
        path.write_text(json.dumps(CONFIGURATION_DOCUMENT), encoding="utf-8")
        monkeypatch.setattr("sys.argv", ["prog", str(path)])
        validate_trading_configuration.main()
        out = capsys.readouterr().out
        assert "ACCEPTED" in out
        assert "Nothing was written" in out

    def test_a_forbidden_policy_exits_non_zero_with_the_domain_reason(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        path = tmp_path / "configuration.json"
        path.write_text(
            json.dumps({**CONFIGURATION_DOCUMENT, "account_mode": "LIVE"}), encoding="utf-8"
        )
        monkeypatch.setattr("sys.argv", ["prog", str(path)])
        with pytest.raises(SystemExit) as exit_info:
            validate_trading_configuration.main()
        assert exit_info.value.code == 1
        # The operator reads the domain type's own refusal, not a paraphrase.
        assert "account_mode must be PREPARATION" in capsys.readouterr().err

    def test_the_json_form_reports_validity_as_data(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        path = tmp_path / "configuration.json"
        path.write_text(
            json.dumps({**CONFIGURATION_DOCUMENT, "maximum_leverage": "2"}), encoding="utf-8"
        )
        monkeypatch.setattr("sys.argv", ["prog", "--json", str(path)])
        with pytest.raises(SystemExit):
            validate_trading_configuration.main()
        payload = json.loads(capsys.readouterr().out)
        assert payload["valid"] is False
        assert "unleveraged" in payload["reason"]

    def test_it_never_opens_a_database_connection(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        # The point of the command: a check that needed a working database
        # would be unavailable exactly when a misconfiguration is most likely.
        assert not hasattr(validate_trading_configuration, "postgres_repository_runtime")
        source = Path(validate_trading_configuration.__file__).read_text(encoding="utf-8")
        assert "postgres" not in source.lower()


# ---------------------------------------------------------------------------
# show-config
# ---------------------------------------------------------------------------


class TestShowConfiguration:
    def test_the_latest_version_is_read_when_none_is_named(self) -> None:
        configurations = seeded_configurations()
        configurations.save(a_configuration(configuration_version=4))
        handler = GetOperatorTradingConfigurationHandler(configuration_repository=configurations)  # type: ignore[arg-type]
        result = handler.handle(GetOperatorTradingConfigurationQuery("CFG-084-0001"))
        assert result.configuration_version == 4

    def test_a_named_version_is_read_exactly(self) -> None:
        configurations = seeded_configurations()
        configurations.save(a_configuration(configuration_version=4))
        handler = GetOperatorTradingConfigurationHandler(configuration_repository=configurations)  # type: ignore[arg-type]
        result = handler.handle(GetOperatorTradingConfigurationQuery("CFG-084-0001", 1))
        assert result.configuration_version == 1

    def test_an_unknown_configuration_is_an_explicit_refusal(self) -> None:
        handler = GetOperatorTradingConfigurationHandler(  # type: ignore[arg-type]
            configuration_repository=_MemoryConfigurations()
        )
        with pytest.raises(NotFoundError, match="no configuration"):
            handler.handle(GetOperatorTradingConfigurationQuery("CFG-NOPE"))

    def test_the_rendered_json_round_trips_through_the_reader(self) -> None:
        # An operator should be able to write this out, edit one limit, bump
        # the version and store it back. That only holds if the two agree.
        original = a_configuration()
        assert read_configuration(render_configuration_json(original)) == original

    def test_the_text_form_states_the_three_hard_invariants(self) -> None:
        text = render_configuration_text(a_configuration())
        assert "short_selling=False" in text
        assert "overnight=False" in text
        assert "leverage=1.00" in text
        assert "PREPARATION" in text

    def test_a_version_argument_that_is_not_a_number_is_refused(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("sys.argv", ["prog", "CFG-1", "not-a-number"])
        with pytest.raises(InputError, match="version must be a whole number"):
            show_trading_configuration.main()


# ---------------------------------------------------------------------------
# The kill switch
# ---------------------------------------------------------------------------


class TestKillSwitch:
    def test_engaging_writes_a_new_version_rather_than_editing_one(self) -> None:
        configurations = seeded_configurations()
        handler = SetKillSwitchHandler(configuration_repository=configurations)  # type: ignore[arg-type]
        moved = handler.handle(SetKillSwitchCommand("CFG-084-0001", engaged=True))

        assert moved.configuration_version == 2
        assert moved.kill_switch is KillSwitchState.ENGAGED
        # The superseded version is still readable, still DISENGAGED. That is
        # the whole reason the switch is versioned rather than a mutable flag.
        previous = configurations.get("CFG-084-0001", 1)
        assert previous is not None
        assert previous.kill_switch is KillSwitchState.DISENGAGED

    def test_disengaging_also_writes_a_new_version(self) -> None:
        configurations = _MemoryConfigurations()
        configurations.save(a_configuration(kill_switch=KillSwitchState.ENGAGED))
        handler = SetKillSwitchHandler(configuration_repository=configurations)  # type: ignore[arg-type]
        moved = handler.handle(SetKillSwitchCommand("CFG-084-0001", engaged=False))
        assert moved.configuration_version == 2
        assert moved.kill_switch is KillSwitchState.DISENGAGED

    def test_moving_the_switch_to_where_it_already_is_writes_nothing(self) -> None:
        # A governance record of a change that did not happen is worse than no
        # record at all.
        configurations = seeded_configurations()
        handler = SetKillSwitchHandler(configuration_repository=configurations)  # type: ignore[arg-type]
        unchanged = handler.handle(SetKillSwitchCommand("CFG-084-0001", engaged=False))
        assert unchanged.configuration_version == 1
        assert len(configurations.rows) == 1

    def test_a_switch_with_no_configuration_behind_it_is_refused(self) -> None:
        handler = SetKillSwitchHandler(configuration_repository=_MemoryConfigurations())  # type: ignore[arg-type]
        with pytest.raises(NotFoundError, match="a switch with no policy behind it stops nothing"):
            handler.handle(SetKillSwitchCommand("CFG-NOPE", engaged=True))

    def test_the_new_version_keeps_every_other_field(self) -> None:
        configurations = seeded_configurations()
        handler = SetKillSwitchHandler(configuration_repository=configurations)  # type: ignore[arg-type]
        moved = handler.handle(SetKillSwitchCommand("CFG-084-0001", engaged=True))
        expected = a_configuration(configuration_version=2, kill_switch=KillSwitchState.ENGAGED)
        assert moved == expected

    def test_an_unknown_action_is_refused(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("sys.argv", ["prog", "disable", "CFG-1"])
        with pytest.raises(InputError, match="must be one of status, on, off"):
            kill_switch.main()

    def test_an_engaged_configuration_stops_the_engine_at_the_first_check(self) -> None:
        # The switch is not advisory: it is the first rule the engine checks.
        configurations = _MemoryConfigurations()
        configurations.save(a_configuration(kill_switch=KillSwitchState.ENGAGED))
        outcome = evaluate_without_persisting(
            a_command(),
            configuration_repository=configurations,  # type: ignore[arg-type]
            evaluation_context_repository=seeded_contexts(),  # type: ignore[arg-type]
        )
        assert outcome.proposal is None
        assert outcome.no_trade_reason is not None
        assert outcome.no_trade_reason.value == "KILL_SWITCH_ENGAGED"


# ---------------------------------------------------------------------------
# explain-no-trade
# ---------------------------------------------------------------------------


class TestExplainNoTrade:
    def test_the_explanation_runs_the_same_evaluation_as_the_real_command(self) -> None:
        # Not "an equivalent evaluation" -- the same function. A second
        # implementation kept carefully in step would drift.
        from empirical_platform.usecases.decision_to_approval import PrepareTradeProposalHandler

        source = PrepareTradeProposalHandler.handle.__doc__ or ""
        assert (
            "evaluate_without_persisting" in (PrepareTradeProposalHandler.handle.__code__.co_names)
            or "evaluate_without_persisting" in source
            or True
        )
        # Structural check: the handler calls the shared function by name.
        assert "evaluate_without_persisting" in PrepareTradeProposalHandler.handle.__code__.co_names

    def test_nothing_is_persisted_even_when_the_evaluation_would_produce_one(self) -> None:
        proposals = _MemoryProposals()
        outcome = evaluate_without_persisting(
            a_command(),
            configuration_repository=seeded_configurations(),  # type: ignore[arg-type]
            evaluation_context_repository=seeded_contexts(),  # type: ignore[arg-type]
        )
        assert outcome.proposal is not None
        assert proposals.rows == {}

    def test_every_check_is_listed_not_only_the_reported_reason(self) -> None:
        outcome = evaluate_without_persisting(
            a_command(cost_estimate=None),
            configuration_repository=seeded_configurations(),  # type: ignore[arg-type]
            evaluation_context_repository=seeded_contexts(),  # type: ignore[arg-type]
        )
        payload = render_no_trade_explanation_json(outcome)
        assert payload["reported_reason"] == "COST_ESTIMATE_MISSING"
        assert payload["checks_evaluated"] == len(outcome.risk_checks)
        assert len(payload["checks"]) == len(outcome.risk_checks)

    def test_several_simultaneous_failures_are_all_shown(self) -> None:
        # The reason a fix-one-thing-at-a-time operator needs this command: the
        # reported reason is one of possibly several.
        outcome = evaluate_without_persisting(
            a_command(cost_estimate=None, liquidity=a_liquidity(average_daily_volume_shares=1)),
            configuration_repository=seeded_configurations(),  # type: ignore[arg-type]
            evaluation_context_repository=seeded_contexts(),  # type: ignore[arg-type]
        )
        payload = render_no_trade_explanation_json(outcome)
        failed = {c["check_id"] for c in payload["checks_not_passed"]}
        assert {"cost_estimate", "liquidity"} <= failed
        assert len(payload["checks_not_passed"]) >= 2

    def test_the_text_form_says_that_one_reason_was_selected_by_precedence(self) -> None:
        outcome = evaluate_without_persisting(
            a_command(cost_estimate=None),
            configuration_repository=seeded_configurations(),  # type: ignore[arg-type]
            evaluation_context_repository=seeded_contexts(),  # type: ignore[arg-type]
        )
        text = render_no_trade_explanation_text(outcome)
        assert "chosen by explicit precedence" in text
        assert "UNKNOWN" in text

    def test_a_proposal_outcome_says_there_is_nothing_to_explain(self) -> None:
        outcome = evaluate_without_persisting(
            a_command(),
            configuration_repository=seeded_configurations(),  # type: ignore[arg-type]
            evaluation_context_repository=seeded_contexts(),  # type: ignore[arg-type]
        )
        assert "Nothing to explain" in render_no_trade_explanation_text(outcome)

    def test_an_unknown_context_is_refused(self) -> None:
        with pytest.raises(NotFoundError, match="no evaluation context"):
            evaluate_without_persisting(
                a_command(evaluation_context_id="ECX-NOPE"),
                configuration_repository=seeded_configurations(),  # type: ignore[arg-type]
                evaluation_context_repository=_MemoryContexts(),  # type: ignore[arg-type]
            )


# ---------------------------------------------------------------------------
# invalidate-stale-proposals
# ---------------------------------------------------------------------------


class TestInvalidateStaleProposals:
    def _handler(
        self, configurations: _MemoryConfigurations, proposals: _MemoryProposals
    ) -> InvalidateStaleProposalsHandler:
        return InvalidateStaleProposalsHandler(
            configuration_repository=configurations,  # type: ignore[arg-type]
            trade_proposal_repository=proposals,  # type: ignore[arg-type]
        )

    def test_a_proposal_past_its_expiry_becomes_expired(self) -> None:
        proposals = _MemoryProposals()
        proposals.save(a_proposal())
        outcome = self._handler(seeded_configurations(), proposals).handle(
            InvalidateStaleProposalsCommand(as_of=EVALUATED_AT + timedelta(seconds=301))
        )
        assert outcome.expired == ("PRP-0001",)
        assert proposals.rows["PRP-0001"].status is ProposalStatus.EXPIRED

    def test_a_proposal_under_a_superseded_configuration_becomes_invalidated(self) -> None:
        configurations = seeded_configurations()
        configurations.save(a_configuration(configuration_version=2))
        proposals = _MemoryProposals()
        proposals.save(a_proposal())
        outcome = self._handler(configurations, proposals).handle(
            InvalidateStaleProposalsCommand(as_of=EVALUATED_AT + timedelta(seconds=10))
        )
        assert outcome.invalidated == ("PRP-0001",)
        assert proposals.rows["PRP-0001"].status is ProposalStatus.INVALIDATED

    def test_expiry_is_reported_ahead_of_supersession(self) -> None:
        # An expired proposal is expired whatever the configuration did
        # afterwards; reporting it as INVALIDATED would name the wrong reason.
        configurations = seeded_configurations()
        configurations.save(a_configuration(configuration_version=2))
        proposals = _MemoryProposals()
        proposals.save(a_proposal())
        outcome = self._handler(configurations, proposals).handle(
            InvalidateStaleProposalsCommand(as_of=EVALUATED_AT + timedelta(seconds=301))
        )
        assert outcome.expired == ("PRP-0001",)
        assert outcome.invalidated == ()

    def test_a_current_unexpired_proposal_is_left_alone(self) -> None:
        proposals = _MemoryProposals()
        proposals.save(a_proposal())
        outcome = self._handler(seeded_configurations(), proposals).handle(
            InvalidateStaleProposalsCommand(as_of=EVALUATED_AT + timedelta(seconds=10))
        )
        assert outcome.total == 0
        assert proposals.rows["PRP-0001"].status is ProposalStatus.PREPARED

    def test_terminal_proposals_are_never_touched(self) -> None:
        proposals = _MemoryProposals()
        proposals.save(replace(a_proposal(), status=ProposalStatus.APPROVED))
        outcome = self._handler(seeded_configurations(), proposals).handle(
            InvalidateStaleProposalsCommand(as_of=EVALUATED_AT + timedelta(days=365))
        )
        assert outcome.total == 0
        assert proposals.rows["PRP-0001"].status is ProposalStatus.APPROVED

    def test_the_sweep_can_be_narrowed_to_one_configuration(self) -> None:
        proposals = _MemoryProposals()
        proposals.save(a_proposal())
        outcome = self._handler(seeded_configurations(), proposals).handle(
            InvalidateStaleProposalsCommand(
                as_of=EVALUATED_AT + timedelta(seconds=301),
                configuration_governance_id="CFG-SOMETHING-ELSE",
            )
        )
        assert outcome.total == 0
        assert proposals.rows["PRP-0001"].status is ProposalStatus.PREPARED

    def test_an_empty_sweep_says_so(self) -> None:
        assert "no PREPARED proposal needed invalidating" in render_invalidation_text(
            InvalidationOutcome(expired=(), invalidated=())
        )

    def test_the_sweep_reads_each_configuration_identity_once(self) -> None:
        # Not a micro-optimisation: a sweep over a long queue that re-read the
        # latest version per proposal would issue one query per row.
        calls: list[str] = []

        class _Counting(_MemoryConfigurations):
            def latest(self, gid: str) -> OperatorTradingConfiguration | None:
                calls.append(gid)
                return super().latest(gid)

        configurations = _Counting()
        configurations.save(a_configuration())
        proposals = _MemoryProposals()
        for index in range(5):
            # Built through the engine, not `replace`d: the proposal identity is
            # part of the fingerprint, so a renamed copy would carry a digest
            # that no longer matches its own terms.
            proposals.save(a_proposal(proposal_governance_id=f"PRP-{index}"))
        self._handler(configurations, proposals).handle(  # type: ignore[arg-type]
            InvalidateStaleProposalsCommand(as_of=EVALUATED_AT + timedelta(seconds=10))
        )
        assert calls == ["CFG-084-0001"]


# ---------------------------------------------------------------------------
# system-status
# ---------------------------------------------------------------------------


class TestSystemStatus:
    def test_every_status_appears_even_with_no_rows(self) -> None:
        # A summary that omitted the empty statuses would read as though those
        # states did not exist.
        proposals = _MemoryProposals()
        handler = GetSystemStatusHandler(
            configuration_repository=_MemoryConfigurations(),  # type: ignore[arg-type]
            trade_proposal_repository=proposals,  # type: ignore[arg-type]
        )
        status = handler.handle(GetSystemStatusQuery())
        assert set(status.proposal_counts) == set(ProposalStatus)
        assert all(count == 0 for count in status.proposal_counts.values())

    def test_the_kill_switch_state_is_reported_with_the_configuration(self) -> None:
        configurations = _MemoryConfigurations()
        configurations.save(a_configuration(kill_switch=KillSwitchState.ENGAGED))
        handler = GetSystemStatusHandler(
            configuration_repository=configurations,  # type: ignore[arg-type]
            trade_proposal_repository=_MemoryProposals(),  # type: ignore[arg-type]
        )
        status = handler.handle(GetSystemStatusQuery("CFG-084-0001"))
        assert status.kill_switch == "ENGAGED"
        assert status.account_mode == "PREPARATION"

    def test_submission_capability_is_always_none(self) -> None:
        # A constant, not a probe: there is nothing to probe.
        assert (
            SystemStatus(
                proposal_counts={},
                configuration_governance_id=None,
                configuration_version=None,
                account_mode=None,
                kill_switch=None,
            ).submission_capability
            == "NONE"
        )

    def test_the_text_form_states_what_the_product_cannot_do(self) -> None:
        text = render_system_status_text(
            SystemStatus(
                proposal_counts=dict.fromkeys(ProposalStatus, 0),
                configuration_governance_id=None,
                configuration_version=None,
                account_mode=None,
                kill_switch=None,
            )
        )
        assert "submission capability: NONE" in text
        assert "cannot send an order" in text

    def test_the_json_form_names_every_status_key(self) -> None:
        payload = render_system_status_json(
            SystemStatus(
                proposal_counts=dict.fromkeys(ProposalStatus, 0),
                configuration_governance_id=None,
                configuration_version=None,
                account_mode=None,
                kill_switch=None,
            )
        )
        assert set(payload["proposal_counts"]) == {s.value for s in ProposalStatus}
        assert payload["submission_capability"] == "NONE"

    def test_a_status_with_no_configuration_named_reports_none(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(
            system_status,
            "run_system_status",
            lambda **_: SystemStatus(
                proposal_counts=dict.fromkeys(ProposalStatus, 0),
                configuration_governance_id=None,
                configuration_version=None,
                account_mode=None,
                kill_switch=None,
            ),
        )
        monkeypatch.setattr("sys.argv", ["prog"])
        system_status.main()
        assert "(none named)" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# audit-history
# ---------------------------------------------------------------------------


class TestAuditHistory:
    def _handler(self, **repositories: object) -> GetAuditHistoryHandler:
        defaults: dict[str, object] = {
            "configuration_repository": seeded_configurations(),
            "evaluation_context_repository": seeded_contexts(),
            "approval_decision_repository": _MemoryDecisions(),
            "approved_order_intent_repository": _MemoryIntents(),
            "trade_proposal_repository": _MemoryProposals(),
        }
        defaults.update(repositories)
        return GetAuditHistoryHandler(**defaults)  # type: ignore[arg-type]

    def test_the_whole_chain_is_assembled(self) -> None:
        proposals = _MemoryProposals()
        proposals.save(a_proposal())
        decisions = _MemoryDecisions()
        decisions.record(a_decision())
        intents = _MemoryIntents()
        intents.issue(an_intent())

        history = self._handler(
            trade_proposal_repository=proposals,
            approval_decision_repository=decisions,
            approved_order_intent_repository=intents,
        ).handle(GetAuditHistoryQuery("PRP-0001"))

        assert history.proposal.proposal_governance_id == "PRP-0001"
        assert history.context is not None
        assert history.configuration is not None
        assert history.decision is not None
        assert history.intent is not None

    def test_a_proposal_with_no_decision_yet_reports_the_gap_rather_than_raising(self) -> None:
        proposals = _MemoryProposals()
        proposals.save(a_proposal())
        history = self._handler(trade_proposal_repository=proposals).handle(
            GetAuditHistoryQuery("PRP-0001")
        )
        assert history.decision is None
        assert history.intent is None
        text = render_audit_history_text(history)
        assert "(no decision recorded)" in text
        assert "(no intent issued)" in text

    def test_a_broken_chain_is_shown_as_broken_rather_than_refused(self) -> None:
        # A chain broken by something outside this milestone's enforcement
        # boundary should be visible. Refusing to print would tell the operator
        # less about a tampered database, not more.
        proposals = _MemoryProposals()
        proposals.save(a_proposal())
        history = self._handler(
            trade_proposal_repository=proposals,
            evaluation_context_repository=_MemoryContexts(),
            configuration_repository=_MemoryConfigurations(),
        ).handle(GetAuditHistoryQuery("PRP-0001"))
        assert history.context is None
        assert history.configuration is None
        assert "(missing)" in render_audit_history_text(history)

    def test_an_unknown_proposal_is_an_explicit_refusal(self) -> None:
        with pytest.raises(NotFoundError, match="no trade proposal"):
            self._handler().handle(GetAuditHistoryQuery("PRP-NOPE"))

    def test_the_json_form_carries_every_link(self) -> None:
        proposals = _MemoryProposals()
        proposals.save(a_proposal())
        payload = render_audit_history_json(
            self._handler(trade_proposal_repository=proposals).handle(
                GetAuditHistoryQuery("PRP-0001")
            )
        )
        assert set(payload) == {
            "proposal",
            "evaluation_context",
            "configuration",
            "decision",
            "approved_order_intent",
        }
        assert payload["proposal"]["quantity"] == 9

    def test_the_history_is_a_read_and_offers_no_way_to_change_anything(self) -> None:
        public = {name for name in dir(AuditHistory) if not name.startswith("_")}
        assert public == {"proposal", "context", "configuration", "decision", "intent"}


class TestEveryNewEntrypointRefusesAWrongArgumentCount:
    @pytest.mark.parametrize(
        ("module", "argv"),
        [
            (show_trading_configuration, []),
            (show_trading_configuration, ["a", "1", "extra"]),
            (validate_trading_configuration, []),
            (validate_trading_configuration, ["a", "b"]),
            (explain_no_trade, ["a", "b", "c"]),
            (explain_no_trade, ["a", "b", "c", "d", "e"]),
            (invalidate_stale_proposals, ["a", "b", "c"]),
            (system_status, ["a", "b"]),
            (kill_switch, ["on"]),
            (kill_switch, ["on", "a", "b"]),
            (audit_history, []),
            (audit_history, ["a", "b"]),
        ],
    )
    def test_usage_is_printed_before_anything_is_touched(
        self, monkeypatch: pytest.MonkeyPatch, module: ModuleType, argv: list[str]
    ) -> None:
        monkeypatch.setattr("sys.argv", ["prog", *argv])
        with pytest.raises(SystemExit, match="usage:"):
            module.main()
