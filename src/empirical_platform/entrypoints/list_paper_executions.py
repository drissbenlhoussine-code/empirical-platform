"""MILESTONE-085 paper execution queue CLI.

Lists the most recently claimed dispatch attempts, newest first. Touches no
broker: this is what the database holds, not what the venue currently thinks, and
an attempt whose state looks stale should be reconciled rather than believed.

`run_list_paper_executions` is split out from `main()` so that argument handling
and output formatting can be unit-tested by monkeypatching this one function.
"""

from __future__ import annotations

import json
import sys

from empirical_platform.entrypoints._operator_cli import operator_command
from empirical_platform.entrypoints._paper_composition import paper_execution_runtime
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.usecases.decision_to_approval_io import InputError
from empirical_platform.usecases.paper_execution import (
    ExecutionAttempt,
    ListPaperExecutionsHandler,
    ListPaperExecutionsQuery,
)
from empirical_platform.usecases.paper_execution_io import render_attempt_json

_USAGE = "usage: empirical-platform-list-paper-executions [--json] [<limit>]"
_DEFAULT_LIMIT = 20


def run_list_paper_executions(
    *, limit: int, config: PostgreSQLConfigSnapshot | None = None
) -> tuple[ExecutionAttempt, ...]:
    with paper_execution_runtime(config) as context:
        handler = ListPaperExecutionsHandler(attempts=context.paper.execution_attempts)
        return handler.handle(ListPaperExecutionsQuery(limit=limit))


def _main() -> None:
    args = sys.argv[1:]
    as_json = "--json" in args
    positional = [argument for argument in args if argument != "--json"]
    if len(positional) > 1:
        raise SystemExit(_USAGE)
    limit = _DEFAULT_LIMIT
    if positional:
        if not positional[0].isdigit() or int(positional[0]) < 1:
            raise InputError(f"limit {positional[0]!r} must be a positive whole number")
        limit = int(positional[0])

    attempts = run_list_paper_executions(limit=limit)
    if as_json:
        print(json.dumps([render_attempt_json(attempt) for attempt in attempts], sort_keys=True))
    elif not attempts:
        print("no paper dispatch attempts recorded")
    else:
        for attempt in attempts:
            print(
                f"{attempt.claimed_at.isoformat()}  {attempt.state.value:22s} "
                f"{attempt.intent_governance_id:24s} {attempt.client_order_id}"
            )


main = operator_command(_main)


if __name__ == "__main__":
    main()
