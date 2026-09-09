"""MILESTONE-084 evaluation context CLI.

Binds one evaluation to the exact inputs it will consume, including exactly one
MILESTONE-083 evidence watermark. The watermark is NAMED here, not supplied:
the handler loads it, reads its stored receipt set, and refuses if it was never
captured. A context cannot be opened against evidence that does not exist, and
the receipt count and digest it records cannot be dictated by the caller.

`run_open_evaluation_context` is split out from `main()` so that `main()`'s
argument handling and output formatting can be unit-tested by monkeypatching
this one function -- without touching real persistence.
"""

from __future__ import annotations

import json
import sys

from empirical_platform.application.command import CommandEntryPoint
from empirical_platform.entrypoints._composition import postgres_repository_runtime
from empirical_platform.entrypoints._operator_cli import operator_command
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.usecases.decision_to_approval import (
    EvaluationContext,
    OpenEvaluationContextCommand,
    OpenEvaluationContextHandler,
)
from empirical_platform.usecases.decision_to_approval_io import (
    load_json_file,
    read_context_request,
    render_context_json,
    render_context_text,
)

_USAGE = "usage: empirical-platform-open-evaluation-context [--json] <context.json>"


def run_open_evaluation_context(
    *,
    command: OpenEvaluationContextCommand,
    config: PostgreSQLConfigSnapshot | None = None,
) -> EvaluationContext:
    with postgres_repository_runtime(config) as runtime:
        handler = OpenEvaluationContextHandler(
            configuration_repository=runtime.operator_trading_configurations,
            evaluation_context_repository=runtime.evaluation_contexts,
            evaluation_evidence_watermark_repository=runtime.evaluation_evidence_watermarks,
        )
        entry_point = CommandEntryPoint(handler)
        return entry_point(command)


def _main() -> None:
    args = sys.argv[1:]
    as_json = "--json" in args
    positional = [argument for argument in args if argument != "--json"]
    if len(positional) != 1:
        raise SystemExit(_USAGE)

    command = read_context_request(load_json_file(positional[0]))
    context = run_open_evaluation_context(command=command)

    if as_json:
        print(json.dumps(render_context_json(context), sort_keys=True))
    else:
        print(render_context_text(context), end="")


main = operator_command(_main)


if __name__ == "__main__":
    main()
