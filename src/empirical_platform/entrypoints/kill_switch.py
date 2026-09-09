"""MILESTONE-084 kill-switch CLI.

`status`, `on`, `off`.

MOVING THE SWITCH WRITES A NEW CONFIGURATION VERSION. The kill switch is a
field of a versioned, immutable configuration, so engaging it is not an edit --
it is a new version stored alongside the one it supersedes. That is deliberate:
a reader can afterwards see exactly when the switch moved and what policy was
in force on either side of it, which an in-place flag would destroy.

Moving the switch to the state it is already in writes nothing. A governance
record of a change that did not happen is worse than no record.

WHAT ENGAGING THE SWITCH DOES AND DOES NOT DO. A new evaluation under an
ENGAGED configuration returns NO_TRADE with KILL_SWITCH_ENGAGED, which is the
first rule the engine checks. It does NOT retract proposals that were already
prepared under a DISENGAGED configuration -- those become INVALIDATED by
`invalidate-stale-proposals`, because a newer configuration version now exists.
Run that command after engaging the switch if the queue must be cleared.

`run_kill_switch` is split out from `main()` so that `main()`'s argument
handling and output formatting can be unit-tested by monkeypatching this one
function -- without touching real persistence.
"""

from __future__ import annotations

import json
import sys

from empirical_platform.application.command import CommandEntryPoint
from empirical_platform.entrypoints._composition import postgres_repository_runtime
from empirical_platform.entrypoints._operator_cli import operator_command
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.usecases.decision_to_approval import (
    GetOperatorTradingConfigurationHandler,
    GetOperatorTradingConfigurationQuery,
    OperatorTradingConfiguration,
    SetKillSwitchCommand,
    SetKillSwitchHandler,
)
from empirical_platform.usecases.decision_to_approval_io import InputError

_USAGE = (
    "usage: empirical-platform-kill-switch [--json] <status|on|off> <configuration_governance_id>"
)


def run_kill_switch(
    *,
    action: str,
    configuration_governance_id: str,
    config: PostgreSQLConfigSnapshot | None = None,
) -> OperatorTradingConfiguration:
    with postgres_repository_runtime(config) as runtime:
        if action == "status":
            reader = GetOperatorTradingConfigurationHandler(
                configuration_repository=runtime.operator_trading_configurations
            )
            return reader.handle(
                GetOperatorTradingConfigurationQuery(
                    configuration_governance_id=configuration_governance_id
                )
            )
        handler = SetKillSwitchHandler(
            configuration_repository=runtime.operator_trading_configurations
        )
        entry_point = CommandEntryPoint(handler)
        return entry_point(
            SetKillSwitchCommand(
                configuration_governance_id=configuration_governance_id,
                engaged=action == "on",
            )
        )


def _main() -> None:
    args = sys.argv[1:]
    as_json = "--json" in args
    positional = [argument for argument in args if argument != "--json"]
    if len(positional) != 2:
        raise SystemExit(_USAGE)

    action, governance_id = positional
    if action not in {"status", "on", "off"}:
        raise InputError(f"action must be one of status, on, off; got {action!r}")

    configuration = run_kill_switch(action=action, configuration_governance_id=governance_id)

    if as_json:
        print(
            json.dumps(
                {
                    "configuration_governance_id": configuration.configuration_governance_id,
                    "configuration_version": configuration.configuration_version,
                    "kill_switch": configuration.kill_switch.value,
                    "trading_permitted": configuration.is_trading_permitted,
                },
                sort_keys=True,
            )
        )
    else:
        permitted = "permitted" if configuration.is_trading_permitted else "STOPPED"
        print(
            f"kill switch {configuration.kill_switch.value} "
            f"({configuration.configuration_governance_id} "
            f"v{configuration.configuration_version}) -> trading {permitted}"
        )


main = operator_command(_main)


if __name__ == "__main__":
    main()
