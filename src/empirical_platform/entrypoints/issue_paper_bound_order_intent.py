"""MILESTONE-085 Paper-bound order intent issuance CLI.

WHY A SECOND WAY TO ISSUE AN INTENT. MILESTONE-084's `issue-order-intent` is frozen
and stays exactly as it is. An intent issued through it carries no record of how
this host's clock related to the broker's at the moment it was issued, and without
that its deadlines cannot be placed on the broker's clock once the host clock moves.
Such an intent is therefore NOT dispatchable by MILESTONE-085, and no basis is
derived for it afterwards.

This command issues the intent through MILESTONE-084's own handler, unchanged, in
the same act as reading the broker's clock (`GET /v2/clock`, read-only): the
conservative host reading taken after that response IS the intent's `created_at`,
and the measured interval is stored beside it as M085-owned evidence. It places no
order and sends nothing but that one read.

`run_issue_paper_bound_order_intent` is split out from `main()` so that argument
handling and output formatting can be unit-tested by monkeypatching this one
function -- without touching a real broker or a real database.
"""

from __future__ import annotations

import json
import sys

from empirical_platform.entrypoints._operator_cli import operator_command
from empirical_platform.entrypoints._paper_composition import paper_execution_runtime
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.usecases.paper_execution import (
    IssuePaperBoundOrderIntentCommand,
    IssuePaperBoundOrderIntentHandler,
    PaperBoundIntent,
)
from empirical_platform.usecases.paper_execution_io import (
    render_paper_bound_intent_json,
    render_paper_bound_intent_text,
)

_USAGE = (
    "usage: empirical-platform-issue-paper-bound-order-intent [--json] "
    "<intent_governance_id> <proposal_governance_id> <idempotency_key>"
)


def run_issue_paper_bound_order_intent(
    *,
    intent_governance_id: str,
    proposal_governance_id: str,
    idempotency_key: str,
    config: PostgreSQLConfigSnapshot | None = None,
) -> PaperBoundIntent:
    with paper_execution_runtime(config) as context:
        handler = IssuePaperBoundOrderIntentHandler(
            approval_decisions=context.m084.approval_decisions,
            intents=context.m084.approved_order_intents,
            proposals=context.m084.trade_proposals,
            time_bases=context.paper.time_bases,
            # Read-only `GET /v2/clock`. This command places no order.
            broker=context.broker,
            time_source=context.time_source,
        )
        return handler.handle(
            IssuePaperBoundOrderIntentCommand(
                intent_governance_id=intent_governance_id,
                proposal_governance_id=proposal_governance_id,
                idempotency_key=idempotency_key,
            )
        )


def _main() -> None:
    args = sys.argv[1:]
    as_json = "--json" in args
    positional = [argument for argument in args if argument != "--json"]
    # No `created_at` argument, deliberately: the issuance instant is the measured
    # host reading, and letting an operator supply one would let a basis describe
    # an instant it was not measured at.
    if len(positional) != 3:
        raise SystemExit(_USAGE)

    intent_id, proposal_id, idempotency_key = positional
    issued = run_issue_paper_bound_order_intent(
        intent_governance_id=intent_id,
        proposal_governance_id=proposal_id,
        idempotency_key=idempotency_key,
    )
    if as_json:
        print(json.dumps(render_paper_bound_intent_json(issued), sort_keys=True))
    else:
        print(render_paper_bound_intent_text(issued), end="")


main = operator_command(_main)


if __name__ == "__main__":
    main()
