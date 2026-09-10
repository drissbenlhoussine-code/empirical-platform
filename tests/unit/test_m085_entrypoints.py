"""MILESTONE-085 operator CLI surfaces: argument handling, output, exit codes.

Every one of the twelve modules under test documents the same promise -- "`run_X`
is split out from `main()` so that argument handling and output formatting can be
unit-tested by monkeypatching this one function" -- and this file is that promise
being kept. `run_X` is replaced, so no test here opens a socket, a database
connection or a credential.

WHY THIS LAYER NEEDS ITS OWN TESTS. The M084 walkthrough found that fourteen of
fifteen commands answered an operator's typo with a traceback, and the note in
`_operator_cli.py` records why that was invisible: every path was covered by tests
calling handlers directly, and a handler that raises is what those tests assert.
The traceback only existed at the boundary those tests did not cross. So the
boundary is crossed here -- `main()` is CALLED, and what an operator would actually
see on stdout, on stderr and in the exit code is what gets asserted.

Three properties are checked for each command, because each has been a real defect
in this repository at some point: a wrong argument count exits 2 with a usage line
rather than raising IndexError; a refusal prints `REFUSED: ...` to stderr and exits
1 rather than printing a traceback; and `--json` emits parseable JSON rather than
prose. The `--json` flag is deliberately tested as position-independent, since
every command filters it out of the positional list rather than parsing it.
"""

from __future__ import annotations

import json
import tomllib
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from tests.unit._m085_fakes import (
    _NOW,
    FakeAttempts,
    FakeAuthorizations,
    a_preview,
    an_account,
)

from empirical_platform.decision_candidate.paper_execution import (
    ExecutionAttempt,
    ExecutionAuthorization,
    PaperExecutionState,
    authorize_submission,
)
from empirical_platform.entrypoints import (
    activate_execution_kill_switch,
    authorize_paper_submission,
    cancel_paper_order,
    deactivate_execution_kill_switch,
    inspect_paper_account,
    list_paper_executions,
    paper_execution_status,
    preview_paper_submission,
    reconcile_paper_order,
    show_paper_execution,
    submit_authorized_paper_order,
    verify_paper_environment,
)
from empirical_platform.usecases.decision_to_approval import NotFoundError
from empirical_platform.usecases.paper_execution import (
    PaperExecutionRefusedError,
    PaperExecutionStatus,
    PaperSubmissionResult,
    VerifyPaperEnvironmentResult,
)

# The twelve M085 console scripts, each paired with the single function its
# module docstring promises is the seam. If a module is ever added without a
# seam, or renames one, these tables are what fails.
_MODULES: dict[str, tuple[Any, str]] = {
    "verify-paper-environment": (verify_paper_environment, "run_verify_paper_environment"),
    "inspect-paper-account": (inspect_paper_account, "run_inspect_paper_account"),
    "preview-paper-submission": (preview_paper_submission, "run_preview_paper_submission"),
    "authorize-paper-submission": (authorize_paper_submission, "run_authorize_paper_submission"),
    "submit-authorized-paper-order": (
        submit_authorized_paper_order,
        "run_submit_authorized_paper_order",
    ),
    "reconcile-paper-order": (reconcile_paper_order, "run_reconcile_paper_order"),
    "cancel-paper-order": (cancel_paper_order, "run_cancel_paper_order"),
    "paper-execution-status": (paper_execution_status, "run_paper_execution_status"),
    "show-paper-execution": (show_paper_execution, "run_show_paper_execution"),
    "list-paper-executions": (list_paper_executions, "run_list_paper_executions"),
    "activate-execution-kill-switch": (
        activate_execution_kill_switch,
        "run_activate_execution_kill_switch",
    ),
    "deactivate-execution-kill-switch": (
        deactivate_execution_kill_switch,
        "run_deactivate_execution_kill_switch",
    ),
}

#: One valid argument vector per command, so the happy path of each can be run.
_VALID_ARGUMENTS: dict[str, list[str]] = {
    "verify-paper-environment": [],
    "inspect-paper-account": ["SNP-1"],
    "preview-paper-submission": ["INT-1", "PVW-1", "SNP-1", "5", "60", "AAPL"],
    "authorize-paper-submission": ["AUT-1", "PVW-1", "f" * 64, "owner", "300"],
    "submit-authorized-paper-order": ["INT-1", "ATT-1", "SNP-2", "5", "60", "AAPL"],
    "reconcile-paper-order": ["INT-1"],
    "cancel-paper-order": ["INT-1"],
    "paper-execution-status": ["INT-1"],
    "show-paper-execution": ["INT-1"],
    "list-paper-executions": ["5"],
    "activate-execution-kill-switch": ["owner", "a stated reason"],
    "deactivate-execution-kill-switch": ["owner", "a stated reason"],
}

#: Argument vectors that must be refused with a usage message.
_WRONG_ARITY: dict[str, list[str]] = {
    "verify-paper-environment": ["unexpected"],
    "inspect-paper-account": [],
    "preview-paper-submission": ["INT-1"],
    "authorize-paper-submission": ["AUT-1"],
    "submit-authorized-paper-order": ["INT-1"],
    "reconcile-paper-order": [],
    "cancel-paper-order": ["INT-1", "extra"],
    "paper-execution-status": [],
    "show-paper-execution": ["INT-1", "extra"],
    "list-paper-executions": ["5", "extra"],
    "activate-execution-kill-switch": ["owner"],
    "deactivate-execution-kill-switch": ["owner"],
}


def _declared_m085_commands() -> set[str]:
    """The M085 console scripts declared in pyproject.toml, read from the file.

    Parsed rather than imported so the source of truth is the packaging metadata a
    wheel is built from, which is what an operator actually gets.
    """
    text = (Path(__file__).resolve().parents[2] / "pyproject.toml").read_text(encoding="utf-8")
    scripts = tomllib.loads(text)["project"]["scripts"]
    prefix = "empirical-platform-"
    return {
        name.removeprefix(prefix)
        for name, target in scripts.items()
        if name.startswith(prefix)
        and (".paper_" in target or "_paper_" in target or "execution_kill_switch" in target)
    }


def _an_attempt() -> ExecutionAttempt:
    attempts, _ = _dispatched_attempt()
    return attempts.rows["ATT-1"]


def _dispatched_attempt() -> tuple[FakeAttempts, ExecutionAuthorization]:
    authorizations = FakeAuthorizations()
    authorization = authorizations.save(
        authorize_submission(
            authorization_id="AUT-1",
            preview=a_preview(),
            authorized_by="owner",
            authorized_at=_NOW,
            validity_seconds=300,
        )
    )
    attempts = FakeAttempts()
    attempts.claim_dispatch(
        attempt_id="ATT-1",
        authorization=authorization,
        request_fingerprint_now=authorization.request_fingerprint,
        account_reference_now=authorization.account_reference,
        claimed_at=_NOW,
    )
    return attempts, authorization


def _an_authorization() -> ExecutionAuthorization:
    _, authorization = _dispatched_attempt()
    return authorization


def _a_status() -> PaperExecutionStatus:
    return PaperExecutionStatus(
        intent_governance_id="INT-1",
        state=PaperExecutionState.NOT_DISPATCHED,
        preview=None,
        authorization=None,
        attempt=None,
        acknowledgements=(),
        events=(),
    )


def _a_submission_result() -> PaperSubmissionResult:
    return PaperSubmissionResult(
        attempt=_an_attempt(),
        dispatched=False,
        http_status=None,
        broker_status=None,
        note="this intent has already been dispatched exactly once",
    )


def _an_environment_report() -> VerifyPaperEnvironmentResult:
    return VerifyPaperEnvironmentResult(
        endpoint_host="paper-api.alpaca.markets",
        is_the_pinned_paper_host=True,
        account_reachable=True,
        account_status="ACTIVE",
        account_reference="ref:" + "0" * 32,
        market_data_host="data.alpaca.markets",
    )


#: What each seam should return on a happy path.
_RETURNS: dict[str, Any] = {
    "verify-paper-environment": _an_environment_report,
    "inspect-paper-account": an_account,
    "preview-paper-submission": a_preview,
    "authorize-paper-submission": _an_authorization,
    "submit-authorized-paper-order": _a_submission_result,
    "reconcile-paper-order": _an_attempt,
    "cancel-paper-order": _an_attempt,
    "paper-execution-status": lambda: PaperExecutionState.NOT_DISPATCHED,
    "show-paper-execution": _a_status,
    "list-paper-executions": lambda: (_an_attempt(),),
    "activate-execution-kill-switch": lambda: True,
    "deactivate-execution-kill-switch": lambda: True,
}


def _install(
    monkeypatch: pytest.MonkeyPatch,
    command: str,
    *,
    arguments: list[str],
    result: object | None = None,
    raises: BaseException | None = None,
) -> list[dict[str, object]]:
    """Replace the command's seam and its argv. Returns the recorded calls."""
    module, seam = _MODULES[command]
    calls: list[dict[str, object]] = []

    def replacement(**kwargs: object) -> object:
        calls.append(kwargs)
        if raises is not None:
            raise raises
        return _RETURNS[command]() if result is None else result

    monkeypatch.setattr(module, seam, replacement)
    monkeypatch.setattr("sys.argv", ["command", *arguments])
    return calls


class TestTheTableCoversEveryConsoleScript:
    """A thirteenth M085 command must not be able to arrive untested.

    `_MODULES` is hand-written, so on its own it proves nothing about completeness:
    a new console script added to `pyproject.toml` without a row here would simply
    not be tested, silently. This reads the declared scripts and requires the two
    to agree, which turns every test in this file into a test of ALL the commands
    rather than of the ones somebody remembered.
    """

    def test_every_declared_m085_script_has_a_row(self) -> None:
        declared = _declared_m085_commands()
        assert declared, "no M085 console scripts were found in pyproject.toml"
        assert declared == set(_MODULES), (
            f"declared but untested: {sorted(declared - set(_MODULES))}; "
            f"tested but not declared: {sorted(set(_MODULES) - declared)}"
        )

    def test_there_are_exactly_twelve(self) -> None:
        assert len(_MODULES) == 12

    def test_each_row_names_a_function_the_module_actually_has(self) -> None:
        # A renamed seam would otherwise be caught only as a confusing
        # monkeypatch failure inside an unrelated test.
        for command, (module, seam) in _MODULES.items():
            assert hasattr(module, seam), f"{command}: {module.__name__} has no {seam}"

    def test_each_module_documents_the_seam_it_exposes(self) -> None:
        # The promise this whole file rests on is written in each docstring; if a
        # module stops making it, the test strategy needs revisiting.
        for command, (module, seam) in _MODULES.items():
            docstring = module.__doc__ or ""
            assert seam in docstring, f"{command}: {seam} is not named in the module docstring"


@pytest.mark.parametrize("command", sorted(_MODULES))
class TestEveryCommand:
    """The three properties every one of the twelve must have."""

    def test_a_wrong_argument_count_prints_usage_and_exits_two(
        self, command: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        calls = _install(monkeypatch, command, arguments=_WRONG_ARITY[command])
        module, _ = _MODULES[command]
        with pytest.raises(SystemExit) as raised:
            module.main()
        # SystemExit carrying a string exits 2 and prints it: a usage message is a
        # finished answer, which is why operator_command re-raises SystemExit
        # untouched rather than reprinting it as "REFUSED: 2".
        assert "usage:" in str(raised.value)
        assert calls == [], "nothing may be executed after a usage refusal"

    def test_the_happy_path_prints_something_and_calls_the_seam_once(
        self, command: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        calls = _install(monkeypatch, command, arguments=_VALID_ARGUMENTS[command])
        module, _ = _MODULES[command]
        module.main()
        assert len(calls) == 1
        assert capsys.readouterr().out.strip() != ""

    def test_the_json_flag_emits_parseable_json(
        self, command: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _install(monkeypatch, command, arguments=["--json", *_VALID_ARGUMENTS[command]])
        module, _ = _MODULES[command]
        module.main()
        json.loads(capsys.readouterr().out)

    def test_the_json_flag_is_position_independent(
        self, command: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Every command filters --json out of the positional list rather than
        # requiring it first, so a trailing flag must behave identically.
        _install(monkeypatch, command, arguments=[*_VALID_ARGUMENTS[command], "--json"])
        module, _ = _MODULES[command]
        module.main()
        json.loads(capsys.readouterr().out)

    def test_a_refusal_prints_refused_and_exits_one(
        self, command: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _install(
            monkeypatch,
            command,
            arguments=_VALID_ARGUMENTS[command],
            raises=PaperExecutionRefusedError("the stated reason"),
        )
        module, _ = _MODULES[command]
        with pytest.raises(SystemExit) as raised:
            module.main()
        assert raised.value.code == 1
        captured = capsys.readouterr()
        assert captured.err.startswith("REFUSED: the stated reason")
        assert "Traceback" not in captured.err

    def test_a_missing_record_prints_refused_and_exits_one(
        self, command: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _install(
            monkeypatch,
            command,
            arguments=_VALID_ARGUMENTS[command],
            raises=NotFoundError("no such record"),
        )
        module, _ = _MODULES[command]
        with pytest.raises(SystemExit) as raised:
            module.main()
        assert raised.value.code == 1
        assert capsys.readouterr().err.startswith("REFUSED: no such record")

    def test_a_defect_is_not_swallowed(self, command: str, monkeypatch: pytest.MonkeyPatch) -> None:
        # The narrow rule in _operator_cli: only operator-fixable errors become
        # refusals. A RuntimeError is a bug in this software and must keep its
        # traceback rather than being dressed up as a considered answer.
        _install(
            monkeypatch,
            command,
            arguments=_VALID_ARGUMENTS[command],
            raises=RuntimeError("a defect"),
        )
        module, _ = _MODULES[command]
        with pytest.raises(RuntimeError, match="a defect"):
            module.main()


class TestArgumentParsingThatIsNotShared:
    """The per-command parsing, where the interesting refusals are."""

    def test_a_non_decimal_notional_is_refused_by_name(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        calls = _install(
            monkeypatch,
            "submit-authorized-paper-order",
            arguments=["INT-1", "ATT-1", "SNP-2", "not-a-number", "60", "AAPL"],
        )
        with pytest.raises(SystemExit):
            submit_authorized_paper_order.main()
        assert "maximum_notional" in capsys.readouterr().err
        assert calls == [], "nothing may be dispatched on a malformed argument"

    def test_a_negative_quote_age_is_refused(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        calls = _install(
            monkeypatch,
            "submit-authorized-paper-order",
            arguments=["INT-1", "ATT-1", "SNP-2", "5", "-1", "AAPL"],
        )
        with pytest.raises(SystemExit):
            submit_authorized_paper_order.main()
        assert "quote_max_age_seconds" in capsys.readouterr().err
        assert calls == []

    def test_an_empty_watchlist_is_refused(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        calls = _install(
            monkeypatch,
            "submit-authorized-paper-order",
            arguments=["INT-1", "ATT-1", "SNP-2", "5", "60", " , "],
        )
        with pytest.raises(SystemExit):
            submit_authorized_paper_order.main()
        assert "watchlist" in capsys.readouterr().err
        assert calls == []

    def test_the_watchlist_is_upper_cased_and_split(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls = _install(
            monkeypatch,
            "preview-paper-submission",
            arguments=["INT-1", "PVW-1", "SNP-1", "5", "60", "aapl, msft "],
        )
        preview_paper_submission.main()
        assert calls[0]["approved_watchlist"] == frozenset({"AAPL", "MSFT"})

    def test_the_notional_reaches_the_seam_as_a_decimal(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # As a Decimal, not a float: a float ceiling would silently change what
        # the operator typed.
        calls = _install(
            monkeypatch,
            "preview-paper-submission",
            arguments=["INT-1", "PVW-1", "SNP-1", "5.25", "60", "AAPL"],
        )
        preview_paper_submission.main()
        assert calls[0]["maximum_notional"] == Decimal("5.25")
        assert isinstance(calls[0]["maximum_notional"], Decimal)

    @pytest.mark.parametrize("validity", ["0", "-5", "abc", "1.5"])
    def test_a_non_positive_validity_is_refused(
        self,
        validity: str,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        # An authorization valid for zero seconds is not an authorization, and a
        # negative one is nonsense: both must be refused before anything is written.
        calls = _install(
            monkeypatch,
            "authorize-paper-submission",
            arguments=["AUT-1", "PVW-1", "f" * 64, "owner", validity],
        )
        with pytest.raises(SystemExit):
            authorize_paper_submission.main()
        assert "validity_seconds" in capsys.readouterr().err
        assert calls == []

    def test_a_valid_validity_reaches_the_seam_as_an_int(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls = _install(
            monkeypatch,
            "authorize-paper-submission",
            arguments=["AUT-1", "PVW-1", "f" * 64, "owner", "120"],
        )
        authorize_paper_submission.main()
        assert calls[0]["validity_seconds"] == 120

    @pytest.mark.parametrize("limit", ["0", "-1", "abc"])
    def test_a_non_positive_limit_is_refused(
        self, limit: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        calls = _install(monkeypatch, "list-paper-executions", arguments=[limit])
        with pytest.raises(SystemExit):
            list_paper_executions.main()
        assert "limit" in capsys.readouterr().err
        assert calls == []

    def test_the_limit_defaults_when_omitted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls = _install(monkeypatch, "list-paper-executions", arguments=[])
        list_paper_executions.main()
        assert calls[0]["limit"] == list_paper_executions._DEFAULT_LIMIT

    def test_an_empty_list_says_so_rather_than_printing_nothing(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Silence would be indistinguishable from a crash.
        _install(monkeypatch, "list-paper-executions", arguments=[], result=())
        list_paper_executions.main()
        assert "no paper dispatch attempts recorded" in capsys.readouterr().out

    def test_an_empty_list_is_an_empty_json_array(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _install(monkeypatch, "list-paper-executions", arguments=["--json"], result=())
        list_paper_executions.main()
        assert json.loads(capsys.readouterr().out) == []

    def test_the_listing_names_each_attempt_state_and_client_order_id(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        attempt = _an_attempt()
        _install(monkeypatch, "list-paper-executions", arguments=[], result=(attempt,))
        list_paper_executions.main()
        printed = capsys.readouterr().out
        assert attempt.state.value in printed
        assert attempt.client_order_id in printed

    @pytest.mark.parametrize(
        "command",
        ["activate-execution-kill-switch", "deactivate-execution-kill-switch"],
    )
    def test_a_blank_reason_is_refused(
        self, command: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # A stop nobody explained is a stop nobody can lift.
        calls = _install(monkeypatch, command, arguments=["owner", "   "])
        module, _ = _MODULES[command]
        with pytest.raises(SystemExit):
            module.main()
        assert "reason is required" in capsys.readouterr().err
        assert calls == []

    def test_an_already_engaged_switch_says_nothing_was_written(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _install(
            monkeypatch,
            "activate-execution-kill-switch",
            arguments=["owner", "because"],
            result=False,
        )
        activate_execution_kill_switch.main()
        printed = capsys.readouterr().out
        assert "already ENGAGED" in printed
        assert "nothing written" in printed

    def test_engaging_reports_that_no_dispatch_may_happen(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _install(
            monkeypatch,
            "activate-execution-kill-switch",
            arguments=["owner", "because"],
            result=True,
        )
        activate_execution_kill_switch.main()
        assert "ENGAGED" in capsys.readouterr().out

    def test_disengaging_still_says_an_authorization_is_required(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Lifting the stop must not read as "dispatch is now automatic".
        _install(
            monkeypatch,
            "deactivate-execution-kill-switch",
            arguments=["owner", "because"],
            result=True,
        )
        deactivate_execution_kill_switch.main()
        printed = capsys.readouterr().out
        assert "DISENGAGED" in printed
        assert "fresh human authorization" in printed

    def test_an_already_disengaged_switch_says_nothing_was_written(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _install(
            monkeypatch,
            "deactivate-execution-kill-switch",
            arguments=["owner", "because"],
            result=False,
        )
        deactivate_execution_kill_switch.main()
        assert "already DISENGAGED" in capsys.readouterr().out

    def test_the_status_command_prints_the_bare_state(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _install(
            monkeypatch,
            "paper-execution-status",
            arguments=["INT-1"],
            result=PaperExecutionState.SUBMISSION_UNKNOWN,
        )
        paper_execution_status.main()
        assert capsys.readouterr().out.strip() == "SUBMISSION_UNKNOWN"

    def test_the_status_json_names_the_intent_it_answered_about(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _install(
            monkeypatch,
            "paper-execution-status",
            arguments=["--json", "INT-7"],
            result=PaperExecutionState.FILLED,
        )
        paper_execution_status.main()
        document = json.loads(capsys.readouterr().out)
        assert document == {"intent_governance_id": "INT-7", "state": "FILLED"}

    def test_the_submit_command_passes_every_argument_through_unchanged(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls = _install(
            monkeypatch,
            "submit-authorized-paper-order",
            arguments=["INT-9", "ATT-9", "SNP-9", "12.50", "45", "AAPL,MSFT"],
        )
        submit_authorized_paper_order.main()
        assert calls[0]["intent_governance_id"] == "INT-9"
        assert calls[0]["attempt_id"] == "ATT-9"
        assert calls[0]["snapshot_id"] == "SNP-9"
        assert calls[0]["maximum_notional"] == Decimal("12.50")
        assert calls[0]["quote_maximum_age_seconds"] == 45
        assert calls[0]["approved_watchlist"] == frozenset({"AAPL", "MSFT"})

    def test_the_submit_command_has_no_force_and_no_endpoint_flag(self) -> None:
        # The absence is the product decision, so the absence is asserted. A
        # --force here would be a way to dispatch without a human authorization,
        # and an --endpoint would be a way to leave the paper host.
        source = submit_authorized_paper_order._USAGE
        assert "--force" not in source
        assert "--endpoint" not in source
        assert not hasattr(submit_authorized_paper_order, "run_submit_unauthorized_paper_order")

    def test_an_ambiguous_outcome_is_printed_with_its_warning(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # The one output an operator must not misread.
        attempts, _ = _dispatched_attempt()
        attempts.transition(
            attempt_id="ATT-1",
            target=PaperExecutionState.SUBMISSION_IN_PROGRESS,
            at=_NOW,
        )
        unknown = attempts.transition(
            attempt_id="ATT-1",
            target=PaperExecutionState.SUBMISSION_UNKNOWN,
            at=_NOW,
            failure_code="AMBIGUOUS",
        )
        _install(
            monkeypatch,
            "submit-authorized-paper-order",
            arguments=["INT-1", "ATT-1", "SNP-2", "5", "60", "AAPL"],
            result=PaperSubmissionResult(
                attempt=unknown,
                dispatched=True,
                http_status=None,
                broker_status=None,
                note="the outcome is unknown -- reconcile; do not send again",
            ),
        )
        submit_authorized_paper_order.main()
        printed = capsys.readouterr().out
        assert "do not send again" in printed
        assert unknown.client_order_id in printed
