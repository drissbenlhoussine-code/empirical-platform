"""MILESTONE-084 approved order intent CLI.

WHAT THIS COMMAND DOES NOT DO. It does not place an order, contact a broker,
open a network connection, or make the intent submittable by anything. It
writes one record whose submission state is NOT_SUBMITTED and for which
MILESTONE-084 provides no transition away from NOT_SUBMITTED -- neither in
code, where no method exists, nor in the database, where a CHECK constraint and
an append-only trigger both refuse it.

The intent is DERIVED, never described by the caller: symbol, quantity, order
type, price and expiry all come from the approved proposal. The only arguments
are identities and the moment of issue.

`run_issue_order_intent` is split out from `main()` so that `main()`'s argument
handling and output formatting can be unit-tested by monkeypatching this one
function -- without touching real persistence.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime

from empirical_platform.application.command import CommandEntryPoint
from empirical_platform.entrypoints._composition import postgres_repository_runtime
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.usecases.decision_to_approval import (
    ApprovedOrderIntent,
    IssueApprovedOrderIntentCommand,
    IssueApprovedOrderIntentHandler,
)
from empirical_platform.usecases.decision_to_approval_io import (
    InputError,
    render_intent_json,
    render_intent_text,
)

_USAGE = (
    "usage: empirical-platform-issue-order-intent [--json] <intent_governance_id> "
    "<proposal_governance_id> <idempotency_key> [created_at]"
)


def run_issue_order_intent(
    *,
    command: IssueApprovedOrderIntentCommand,
    config: PostgreSQLConfigSnapshot | None = None,
) -> ApprovedOrderIntent:
    with postgres_repository_runtime(config) as runtime:
        handler = IssueApprovedOrderIntentHandler(
            approval_decision_repository=runtime.approval_decisions,
            approved_order_intent_repository=runtime.approved_order_intents,
            trade_proposal_repository=runtime.trade_proposals,
        )
        entry_point = CommandEntryPoint(handler)
        return entry_point(command)


def _created_at(raw: str | None) -> datetime:
    if raw is None:
        return datetime.now(UTC)
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as error:
        raise InputError(f"created_at is not an ISO-8601 instant: {raw!r}") from error
    if parsed.tzinfo is None:
        raise InputError("created_at must carry a UTC offset")
    return parsed


def main() -> None:
    args = sys.argv[1:]
    as_json = "--json" in args
    positional = [argument for argument in args if argument != "--json"]
    if len(positional) not in (3, 4):
        raise SystemExit(_USAGE)

    intent_id, proposal_id, idempotency_key = positional[:3]
    intent = run_issue_order_intent(
        command=IssueApprovedOrderIntentCommand(
            intent_governance_id=intent_id,
            proposal_governance_id=proposal_id,
            idempotency_key=idempotency_key,
            created_at=_created_at(positional[3] if len(positional) == 4 else None),
        )
    )

    if as_json:
        print(json.dumps(render_intent_json(intent), sort_keys=True))
    else:
        print(render_intent_text(intent), end="")


if __name__ == "__main__":
    main()
