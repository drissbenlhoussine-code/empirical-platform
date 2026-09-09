"""MILESTONE-084 human approval CLI.

THE ONE COMMAND A HUMAN MUST RUN. Nothing in this milestone approves anything
on its own: there is no timeout that approves, no default that approves, and no
path where the absence of a rejection becomes an approval. An order intent
exists only downstream of one explicit invocation of this command by a named
operator.

`operator_identity` is a required argument with no default. An approval filed
under "system" or under nothing is an approval nobody made.

The decision is recorded before the proposal's status moves. That order is the
safe one: the database admits a decision only while its proposal is still
PREPARED and only with that proposal's current fingerprint, so moving the
status first would leave a proposal APPROVED with nobody named as having
approved it.

`run_decide_trade_proposal` is split out from `main()` so that `main()`'s
argument handling and output formatting can be unit-tested by monkeypatching
this one function -- without touching real persistence.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime

from empirical_platform.application.command import CommandEntryPoint
from empirical_platform.entrypoints._composition import postgres_repository_runtime
from empirical_platform.entrypoints._operator_cli import operator_command
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.usecases.decision_to_approval import (
    DecideTradeProposalCommand,
    DecideTradeProposalHandler,
    DecisionOutcome,
    OperatorAction,
)
from empirical_platform.usecases.decision_to_approval_io import (
    InputError,
    render_decision_json,
    render_decision_text,
    render_proposal_json,
)

_USAGE = (
    "usage: empirical-platform-decide-trade-proposal [--json] <proposal_governance_id> "
    "<decision_governance_id> <APPROVE|REJECT|CANCEL> <operator_identity> [decided_at]"
)


def run_decide_trade_proposal(
    *,
    command: DecideTradeProposalCommand,
    config: PostgreSQLConfigSnapshot | None = None,
) -> DecisionOutcome:
    with postgres_repository_runtime(config) as runtime:
        handler = DecideTradeProposalHandler(
            configuration_repository=runtime.operator_trading_configurations,
            approval_decision_repository=runtime.approval_decisions,
            trade_proposal_repository=runtime.trade_proposals,
        )
        entry_point = CommandEntryPoint(handler)
        return entry_point(command)


def _action(raw: str) -> OperatorAction:
    try:
        return OperatorAction(raw)
    except ValueError as error:
        permitted = ", ".join(sorted(member.value for member in OperatorAction))
        raise InputError(f"action must be one of {permitted}; got {raw!r}") from error


def _decided_at(raw: str | None) -> datetime:
    """The decision instant, defaulting to now.

    This is the one clock read in MILESTONE-084's decision path, and it is
    here at the edge rather than inside the domain: a human is deciding at
    this moment, and the record should say so. An explicit value may be given
    for a decision being recorded after the fact.
    """
    if raw is None:
        return datetime.now(UTC)
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as error:
        raise InputError(f"decided_at is not an ISO-8601 instant: {raw!r}") from error
    if parsed.tzinfo is None:
        raise InputError("decided_at must carry a UTC offset")
    return parsed


def _main() -> None:
    args = sys.argv[1:]
    as_json = "--json" in args
    positional = [argument for argument in args if argument != "--json"]
    if len(positional) not in (4, 5):
        raise SystemExit(_USAGE)

    proposal_id, decision_id, action_raw, operator = positional[:4]
    decided_at = _decided_at(positional[4] if len(positional) == 5 else None)

    outcome = run_decide_trade_proposal(
        command=DecideTradeProposalCommand(
            proposal_governance_id=proposal_id,
            decision_governance_id=decision_id,
            action=_action(action_raw),
            operator_identity=operator,
            decided_at=decided_at,
        )
    )

    if as_json:
        print(
            json.dumps(
                {
                    "decision": render_decision_json(outcome.decision),
                    "proposal": render_proposal_json(outcome.proposal),
                },
                sort_keys=True,
            )
        )
    else:
        print(render_decision_text(outcome.decision), end="")


main = operator_command(_main)


if __name__ == "__main__":
    main()
