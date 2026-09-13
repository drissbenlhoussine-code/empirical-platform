"""MILESTONE-085 paper order reconciliation CLI.

Asks the broker about the SAME client order id the dispatch used, and records the
answer. This is how an UNKNOWN outcome becomes known -- and the only sanctioned
way. It never sends an order.

A "not found" answer is deliberately NOT read as proof that nothing was sent. The
bounded policy in the domain requires more than one such observation and a minimum
elapsed time before it will resolve an unknown, and until then this command leaves
the state alone and records why.

`run_reconcile_paper_order` is split out from `main()` so that argument handling
and output formatting can be unit-tested by monkeypatching this one function.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime

from empirical_platform.entrypoints._operator_cli import operator_command
from empirical_platform.entrypoints._paper_composition import paper_execution_runtime
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.usecases.paper_execution import (
    ExecutionAttempt,
    ReconcilePaperOrderCommand,
    ReconcilePaperOrderHandler,
)
from empirical_platform.usecases.paper_execution_io import (
    render_attempt_json,
    render_attempt_text,
)

_USAGE = "usage: empirical-platform-reconcile-paper-order [--json] <intent_governance_id>"


def run_reconcile_paper_order(
    *, intent_governance_id: str, config: PostgreSQLConfigSnapshot | None = None
) -> ExecutionAttempt:
    with paper_execution_runtime(config) as context:
        handler = ReconcilePaperOrderHandler(
            attempts=context.paper.execution_attempts,
            acknowledgements=context.paper.broker_acknowledgements,
            events=context.paper.paper_execution_events,
            broker=context.broker,
        )
        return handler.handle(
            ReconcilePaperOrderCommand(
                intent_governance_id=intent_governance_id, at=datetime.now(UTC)
            )
        )


def _main() -> None:
    args = sys.argv[1:]
    as_json = "--json" in args
    positional = [argument for argument in args if argument != "--json"]
    if len(positional) != 1:
        raise SystemExit(_USAGE)

    attempt = run_reconcile_paper_order(intent_governance_id=positional[0])
    if as_json:
        print(json.dumps(render_attempt_json(attempt), sort_keys=True))
    else:
        print(render_attempt_text(attempt), end="")


main = operator_command(_main)


if __name__ == "__main__":
    main()
