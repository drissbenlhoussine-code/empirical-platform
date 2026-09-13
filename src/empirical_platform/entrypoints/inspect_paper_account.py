"""MILESTONE-085 paper account inspection CLI.

Reads the paper account and stores one immutable snapshot of it. The account
identifier is stored as a stable digest, never as a broker account number, and
every balance printed is SIMULATED.

`run_inspect_paper_account` is split out from `main()` so that argument handling
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
    InspectPaperAccountCommand,
    InspectPaperAccountHandler,
    PaperAccountSnapshot,
)
from empirical_platform.usecases.paper_execution_io import (
    render_account_json,
    render_account_text,
)

_USAGE = "usage: empirical-platform-inspect-paper-account [--json] <snapshot_id>"


def run_inspect_paper_account(
    *, snapshot_id: str, config: PostgreSQLConfigSnapshot | None = None
) -> PaperAccountSnapshot:
    with paper_execution_runtime(config) as context:
        handler = InspectPaperAccountHandler(
            broker=context.broker, snapshots=context.paper.paper_account_snapshots
        )
        return handler.handle(
            InspectPaperAccountCommand(snapshot_id=snapshot_id, captured_at=datetime.now(UTC))
        )


def _main() -> None:
    args = sys.argv[1:]
    as_json = "--json" in args
    positional = [argument for argument in args if argument != "--json"]
    if len(positional) != 1:
        raise SystemExit(_USAGE)

    account = run_inspect_paper_account(snapshot_id=positional[0])
    if as_json:
        print(json.dumps(render_account_json(account), sort_keys=True))
    else:
        print(render_account_text(account), end="")


main = operator_command(_main)


if __name__ == "__main__":
    main()
