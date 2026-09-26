"""MILESTONE-085 Paper-bound human decision CLI.

WHY A SECOND WAY TO DECIDE. MILESTONE-084's `decide-trade-proposal` is frozen and
stays exactly as it is. An approval it records carries an `expires_at` written on
this host's clock at the moment of decision, and M084 checks it again when the
intent is issued -- on the host clock. A host clock that falls back between the
decision and issuance makes an expired approval look current. Only a basis measured
at THIS moment can place that expiry on the broker's clock, so an approval recorded
through M084 alone cannot lead to a paper dispatch, and no basis is derived later.

This command reads the broker's clock (`GET /v2/clock`, read-only), refuses to
approve a proposal that has no proposal-time basis or that might already have
expired on the broker's clock, then records the decision through MILESTONE-084's own
handler, unchanged, with the measured host reading as `decided_at`. There is
deliberately no `decided_at` argument. `operator_identity` is required, exactly as in
M084. A rejection or cancellation is recorded the same way and needs no basis.

`run_decide_paper_bound_trade_proposal` is split out from `main()` so that argument
handling and output formatting can be unit-tested by monkeypatching this one
function -- without touching a real broker or a real database.
"""

from __future__ import annotations

import json
import sys

from empirical_platform.entrypoints._operator_cli import operator_command
from empirical_platform.entrypoints._paper_composition import paper_execution_runtime
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.usecases.decision_to_approval import OperatorAction
from empirical_platform.usecases.decision_to_approval_io import InputError
from empirical_platform.usecases.paper_execution import (
    DecidePaperBoundTradeProposalCommand,
    DecidePaperBoundTradeProposalHandler,
    PaperBoundDecision,
)
from empirical_platform.usecases.paper_execution_io import (
    render_paper_bound_decision_json,
    render_paper_bound_decision_text,
)

_USAGE = (
    "usage: empirical-platform-decide-paper-bound-trade-proposal [--json] "
    "<proposal_governance_id> <decision_governance_id> <APPROVE|REJECT|CANCEL> "
    "<operator_identity>"
)


def run_decide_paper_bound_trade_proposal(
    *,
    command: DecidePaperBoundTradeProposalCommand,
    config: PostgreSQLConfigSnapshot | None = None,
) -> PaperBoundDecision:
    with paper_execution_runtime(config) as context:
        handler = DecidePaperBoundTradeProposalHandler(
            configurations=context.m084.operator_trading_configurations,
            decisions=context.m084.approval_decisions,
            proposals=context.m084.trade_proposals,
            time_bases=context.paper.time_bases,
            # Read-only `GET /v2/clock`. This command places no order.
            broker=context.broker,
            time_source=context.time_source,
        )
        return handler.handle(command)


def _action(raw: str) -> OperatorAction:
    try:
        return OperatorAction(raw)
    except ValueError as error:
        permitted = ", ".join(sorted(member.value for member in OperatorAction))
        raise InputError(f"action must be one of {permitted}; got {raw!r}") from error


def _main() -> None:
    args = sys.argv[1:]
    as_json = "--json" in args
    positional = [argument for argument in args if argument != "--json"]
    # No `decided_at`, deliberately: the decision instant is the measured reading.
    if len(positional) != 4:
        raise SystemExit(_USAGE)

    proposal_id, decision_id, action_raw, operator = positional
    decided = run_decide_paper_bound_trade_proposal(
        command=DecidePaperBoundTradeProposalCommand(
            proposal_governance_id=proposal_id,
            decision_governance_id=decision_id,
            action=_action(action_raw),
            operator_identity=operator,
        )
    )
    if as_json:
        print(json.dumps(render_paper_bound_decision_json(decided), sort_keys=True))
    else:
        print(render_paper_bound_decision_text(decided), end="")


main = operator_command(_main)


if __name__ == "__main__":
    main()
