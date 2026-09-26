"""MILESTONE-085 paper environment verification CLI (read-only).

Sends no order. Confirms the trading endpoint is the pinned paper host, that the
credentials reach it, and which market-data host quotes would come from.

`run_verify_paper_environment` is split out from `main()` so that argument
handling and output formatting can be unit-tested by monkeypatching this one
function -- without touching a real broker.
"""

from __future__ import annotations

import json
import sys

from empirical_platform.entrypoints._operator_cli import operator_command
from empirical_platform.entrypoints._paper_composition import paper_execution_runtime
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.usecases.paper_execution import (
    VerifyPaperEnvironmentHandler,
    VerifyPaperEnvironmentQuery,
    VerifyPaperEnvironmentResult,
)
from empirical_platform.usecases.paper_execution_io import (
    render_environment_json,
    render_environment_text,
)

_USAGE = "usage: empirical-platform-verify-paper-environment [--json]"


def run_verify_paper_environment(
    *, config: PostgreSQLConfigSnapshot | None = None
) -> VerifyPaperEnvironmentResult:
    with paper_execution_runtime(config) as context:
        handler = VerifyPaperEnvironmentHandler(
            broker=context.broker, market_data=context.market_data
        )
        return handler.handle(VerifyPaperEnvironmentQuery())


def _main() -> None:
    args = sys.argv[1:]
    as_json = "--json" in args
    if [argument for argument in args if argument != "--json"]:
        raise SystemExit(_USAGE)

    result = run_verify_paper_environment()
    if as_json:
        print(json.dumps(render_environment_json(result), sort_keys=True))
    else:
        print(render_environment_text(result), end="")


main = operator_command(_main)


if __name__ == "__main__":
    main()
