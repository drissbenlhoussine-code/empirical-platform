"""MILESTONE-085 paper execution history CLI.

The whole chain behind one intent in one answer: the latest preview, the latest
authorization, the single attempt, every broker acknowledgement in the order it
arrived, and every audit event. Touches no broker.

`run_show_paper_execution` is split out from `main()` so that argument handling
and output formatting can be unit-tested by monkeypatching this one function.
"""

from __future__ import annotations

import json
import sys

from empirical_platform.entrypoints._operator_cli import operator_command
from empirical_platform.entrypoints._paper_composition import paper_execution_runtime
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.usecases.paper_execution import (
    PaperExecutionStatus,
    ShowPaperExecutionHandler,
    ShowPaperExecutionQuery,
)
from empirical_platform.usecases.paper_execution_io import (
    render_status_json,
    render_status_text,
)

_USAGE = "usage: empirical-platform-show-paper-execution [--json] <intent_governance_id>"


def run_show_paper_execution(
    *, intent_governance_id: str, config: PostgreSQLConfigSnapshot | None = None
) -> PaperExecutionStatus:
    with paper_execution_runtime(config) as context:
        handler = ShowPaperExecutionHandler(
            attempts=context.paper.execution_attempts,
            authorizations=context.paper.execution_authorizations,
            previews=context.paper.submission_previews,
            acknowledgements=context.paper.broker_acknowledgements,
            events=context.paper.paper_execution_events,
        )
        return handler.handle(ShowPaperExecutionQuery(intent_governance_id=intent_governance_id))


def _main() -> None:
    args = sys.argv[1:]
    as_json = "--json" in args
    positional = [argument for argument in args if argument != "--json"]
    if len(positional) != 1:
        raise SystemExit(_USAGE)

    status = run_show_paper_execution(intent_governance_id=positional[0])
    if as_json:
        print(json.dumps(render_status_json(status), sort_keys=True))
    else:
        print(render_status_text(status), end="")


main = operator_command(_main)


if __name__ == "__main__":
    main()
