"""MILESTONE-085 paper execution status CLI.

One word, for an operator or a script that wants the state and nothing else.
NOT_DISPATCHED, AUTHORIZATION_PENDING and AUTHORIZED are derived from the absence
of an attempt rather than stored, so an intent nobody has touched answers
NOT_DISPATCHED rather than erroring.

`run_paper_execution_status` is split out from `main()` so that argument handling
and output formatting can be unit-tested by monkeypatching this one function.
"""

from __future__ import annotations

import json
import sys

from empirical_platform.entrypoints._operator_cli import operator_command
from empirical_platform.entrypoints._paper_composition import paper_execution_runtime
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.usecases.paper_execution import (
    PaperExecutionState,
    PaperExecutionStatusHandler,
    PaperExecutionStatusQuery,
)

_USAGE = "usage: empirical-platform-paper-execution-status [--json] <intent_governance_id>"


def run_paper_execution_status(
    *, intent_governance_id: str, config: PostgreSQLConfigSnapshot | None = None
) -> PaperExecutionState:
    with paper_execution_runtime(config) as context:
        handler = PaperExecutionStatusHandler(
            attempts=context.paper.execution_attempts,
            authorizations=context.paper.execution_authorizations,
            previews=context.paper.submission_previews,
        )
        return handler.handle(PaperExecutionStatusQuery(intent_governance_id=intent_governance_id))


def _main() -> None:
    args = sys.argv[1:]
    as_json = "--json" in args
    positional = [argument for argument in args if argument != "--json"]
    if len(positional) != 1:
        raise SystemExit(_USAGE)

    state = run_paper_execution_status(intent_governance_id=positional[0])
    if as_json:
        print(
            json.dumps(
                {"intent_governance_id": positional[0], "state": state.value}, sort_keys=True
            )
        )
    else:
        print(state.value)


main = operator_command(_main)


if __name__ == "__main__":
    main()
