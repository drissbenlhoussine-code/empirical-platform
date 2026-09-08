"""MILESTONE-084 operator trading configuration CLI (write).

Stores one configuration VERSION. Versions are never edited: changing policy
means writing a new file with the next version number, so that every proposal
can name the exact policy text that governed it.

The file is refused rather than repaired. A configuration this product will not
hold -- leveraged, short-selling, overnight, or a PAPER/LIVE account mode --
fails here and again at the database, and no partial version is stored.

`run_save_trading_configuration` is split out from `main()`, mirroring
`entrypoints.capture_evaluation_evidence_watermark`'s precedent, so that
`main()`'s argument handling and output formatting can be unit-tested by
monkeypatching this one function -- without touching real persistence.
"""

from __future__ import annotations

import json
import sys

from empirical_platform.application.command import CommandEntryPoint
from empirical_platform.entrypoints._composition import postgres_repository_runtime
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.usecases.decision_to_approval import (
    OperatorTradingConfiguration,
    SaveOperatorTradingConfigurationCommand,
    SaveOperatorTradingConfigurationHandler,
)
from empirical_platform.usecases.decision_to_approval_io import (
    load_json_file,
    read_configuration,
)

_USAGE = "usage: empirical-platform-save-trading-configuration [--json] <configuration.json>"


def run_save_trading_configuration(
    *,
    configuration: OperatorTradingConfiguration,
    config: PostgreSQLConfigSnapshot | None = None,
) -> OperatorTradingConfiguration:
    with postgres_repository_runtime(config) as runtime:
        handler = SaveOperatorTradingConfigurationHandler(
            configuration_repository=runtime.operator_trading_configurations
        )
        entry_point = CommandEntryPoint(handler)
        return entry_point(SaveOperatorTradingConfigurationCommand(configuration=configuration))


def main() -> None:
    args = sys.argv[1:]
    as_json = "--json" in args
    positional = [argument for argument in args if argument != "--json"]
    if len(positional) != 1:
        raise SystemExit(_USAGE)

    configuration = read_configuration(load_json_file(positional[0]))
    stored = run_save_trading_configuration(configuration=configuration)

    if as_json:
        print(
            json.dumps(
                {
                    "configuration_governance_id": stored.configuration_governance_id,
                    "configuration_version": stored.configuration_version,
                    "account_mode": stored.account_mode.value,
                    "kill_switch": stored.kill_switch.value,
                },
                sort_keys=True,
            )
        )
    else:
        print(
            f"stored configuration {stored.configuration_governance_id} "
            f"v{stored.configuration_version} "
            f"[{stored.account_mode.value}, kill switch {stored.kill_switch.value}]"
        )


if __name__ == "__main__":
    main()
