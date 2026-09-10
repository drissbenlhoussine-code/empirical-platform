"""MILESTONE-085 execution kill-switch deactivation CLI.

Lifts the dispatch stop by writing a NEW append-only version, so the history of
who lifted it and when survives. Disengaging a switch that is already disengaged
writes nothing.

LIFTING THIS SWITCH AUTHORIZES NOTHING. It removes one refusal; it does not create
an authorization, revive an expired one, or make an already-consumed one usable
again. A dispatch still needs a fresh human authorization bound to the exact order.

`run_deactivate_execution_kill_switch` is split out from `main()` so that argument
handling and output formatting can be unit-tested by monkeypatching this one
function.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime

from empirical_platform.entrypoints._operator_cli import operator_command
from empirical_platform.entrypoints._paper_composition import paper_execution_runtime
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.usecases.decision_to_approval_io import InputError
from empirical_platform.usecases.paper_execution import (
    SetExecutionKillSwitchCommand,
    SetExecutionKillSwitchHandler,
)

_USAGE = "usage: empirical-platform-deactivate-execution-kill-switch [--json] <changed_by> <reason>"


def run_deactivate_execution_kill_switch(
    *, changed_by: str, reason: str, config: PostgreSQLConfigSnapshot | None = None
) -> bool:
    with paper_execution_runtime(config) as context:
        handler = SetExecutionKillSwitchHandler(kill_switch=context.paper.execution_kill_switch)
        return handler.handle(
            SetExecutionKillSwitchCommand(
                engaged=False,
                changed_by=changed_by,
                changed_at=datetime.now(UTC),
                reason=reason,
            )
        )


def _main() -> None:
    args = sys.argv[1:]
    as_json = "--json" in args
    positional = [argument for argument in args if argument != "--json"]
    if len(positional) != 2:
        raise SystemExit(_USAGE)
    changed_by, reason = positional
    if not reason.strip():
        raise InputError("a reason is required: lifting a stop is a governance act")

    changed = run_deactivate_execution_kill_switch(changed_by=changed_by, reason=reason)
    if as_json:
        print(json.dumps({"engaged": False, "changed": changed}, sort_keys=True))
    elif changed:
        print(
            "execution kill switch DISENGAGED -- dispatch is permitted again, but every "
            "dispatch still requires a fresh human authorization"
        )
    else:
        print("execution kill switch was already DISENGAGED -- nothing written")


main = operator_command(_main)


if __name__ == "__main__":
    main()
