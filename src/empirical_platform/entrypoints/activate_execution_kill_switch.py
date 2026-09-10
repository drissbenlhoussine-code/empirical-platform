"""MILESTONE-085 execution kill-switch activation CLI.

STOPS DISPATCH, NOT PROPOSAL. This is a different switch from M084's configuration
kill switch: that one makes a new evaluation return NO_TRADE, this one refuses to
send anything to the paper broker. Both are checked before a dispatch, because an
intent approved before either was engaged would otherwise still be dispatchable.

MOVING THE SWITCH WRITES A NEW VERSION. Engaging it is not an edit -- it is a new
append-only row alongside the one it supersedes, so a reader can afterwards see
exactly when it moved and who moved it. Engaging a switch that is already engaged
writes nothing, because a governance record of a change that did not happen is
worse than no record.

WHAT IT DOES NOT DO. It does not cancel or reconcile orders that are already at the
broker. Those need `empirical-platform-cancel-paper-order` and
`empirical-platform-reconcile-paper-order`.

`run_activate_execution_kill_switch` is split out from `main()` so that argument handling and output
formatting can be unit-tested by monkeypatching this one function.
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

_USAGE = "usage: empirical-platform-activate-execution-kill-switch [--json] <changed_by> <reason>"


def run_activate_execution_kill_switch(
    *, changed_by: str, reason: str, config: PostgreSQLConfigSnapshot | None = None
) -> bool:
    with paper_execution_runtime(config) as context:
        handler = SetExecutionKillSwitchHandler(kill_switch=context.paper.execution_kill_switch)
        return handler.handle(
            SetExecutionKillSwitchCommand(
                engaged=True,
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
        raise InputError("a reason is required: a stop nobody explained is a stop nobody can lift")

    changed = run_activate_execution_kill_switch(changed_by=changed_by, reason=reason)
    if as_json:
        print(json.dumps({"engaged": True, "changed": changed}, sort_keys=True))
    elif changed:
        print("execution kill switch ENGAGED -- no paper order may be dispatched")
    else:
        print("execution kill switch was already ENGAGED -- nothing written")


main = operator_command(_main)


if __name__ == "__main__":
    main()
