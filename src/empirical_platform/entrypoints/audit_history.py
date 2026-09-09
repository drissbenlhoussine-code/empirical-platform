"""MILESTONE-084 audit history CLI.

Prints the whole chain behind one proposal: the configuration that governed it,
the evaluation context and the M083 watermark it consumed, the proposal's exact
order terms and the risk checks it passed, the human decision, and the order
intent -- in the order they happened.

Each link is reported as `(missing)` rather than raising when it cannot be
read. A chain broken by something outside this milestone's enforcement boundary
should be shown as broken; refusing to print anything would tell the operator
less about a database that has been tampered with, not more.

`run_audit_history` is split out from `main()` so that `main()`'s argument
handling and output formatting can be unit-tested by monkeypatching this one
function -- without touching real persistence.
"""

from __future__ import annotations

import json
import sys

from empirical_platform.entrypoints._composition import postgres_repository_runtime
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.usecases.decision_to_approval import (
    AuditHistory,
    GetAuditHistoryHandler,
    GetAuditHistoryQuery,
)
from empirical_platform.usecases.decision_to_approval_io import (
    render_audit_history_json,
    render_audit_history_text,
)

_USAGE = "usage: empirical-platform-audit-history [--json] <proposal_governance_id>"


def run_audit_history(
    *,
    proposal_governance_id: str,
    config: PostgreSQLConfigSnapshot | None = None,
) -> AuditHistory:
    with postgres_repository_runtime(config) as runtime:
        handler = GetAuditHistoryHandler(
            configuration_repository=runtime.operator_trading_configurations,
            evaluation_context_repository=runtime.evaluation_contexts,
            approval_decision_repository=runtime.approval_decisions,
            approved_order_intent_repository=runtime.approved_order_intents,
            trade_proposal_repository=runtime.trade_proposals,
        )
        return handler.handle(GetAuditHistoryQuery(proposal_governance_id=proposal_governance_id))


def main() -> None:
    args = sys.argv[1:]
    as_json = "--json" in args
    positional = [argument for argument in args if argument != "--json"]
    if len(positional) != 1:
        raise SystemExit(_USAGE)

    history = run_audit_history(proposal_governance_id=positional[0])

    if as_json:
        print(json.dumps(render_audit_history_json(history), sort_keys=True))
    else:
        print(render_audit_history_text(history), end="")


if __name__ == "__main__":
    main()
