"""MILESTONE-084 operator trading configuration CLI (read).

Prints one stored configuration version, or the latest if none is named. The
JSON form is deliberately the same shape `save-trading-configuration` accepts:
an operator who wants to change one limit should be able to write this out,
edit it, bump the version and store it back, rather than reconstruct the file
from documentation.

`run_show_trading_configuration` is split out from `main()` so that `main()`'s
argument handling and output formatting can be unit-tested by monkeypatching
this one function -- without touching real persistence.
"""

from __future__ import annotations

import json
import sys

from empirical_platform.entrypoints._composition import postgres_repository_runtime
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.usecases.decision_to_approval import (
    GetOperatorTradingConfigurationHandler,
    GetOperatorTradingConfigurationQuery,
    OperatorTradingConfiguration,
)
from empirical_platform.usecases.decision_to_approval_io import (
    InputError,
    render_configuration_json,
    render_configuration_text,
)

_USAGE = (
    "usage: empirical-platform-show-trading-configuration [--json] "
    "<configuration_governance_id> [version]"
)


def run_show_trading_configuration(
    *,
    configuration_governance_id: str,
    configuration_version: int | None = None,
    config: PostgreSQLConfigSnapshot | None = None,
) -> OperatorTradingConfiguration:
    with postgres_repository_runtime(config) as runtime:
        handler = GetOperatorTradingConfigurationHandler(
            configuration_repository=runtime.operator_trading_configurations
        )
        return handler.handle(
            GetOperatorTradingConfigurationQuery(
                configuration_governance_id=configuration_governance_id,
                configuration_version=configuration_version,
            )
        )


def _version(raw: str) -> int:
    try:
        parsed = int(raw)
    except ValueError as error:
        raise InputError(f"version must be a whole number; got {raw!r}") from error
    if parsed < 1:
        raise InputError("version must start at 1")
    return parsed


def main() -> None:
    args = sys.argv[1:]
    as_json = "--json" in args
    positional = [argument for argument in args if argument != "--json"]
    if len(positional) not in (1, 2):
        raise SystemExit(_USAGE)

    configuration = run_show_trading_configuration(
        configuration_governance_id=positional[0],
        configuration_version=_version(positional[1]) if len(positional) == 2 else None,
    )

    if as_json:
        print(json.dumps(render_configuration_json(configuration), sort_keys=True))
    else:
        print(render_configuration_text(configuration), end="")


if __name__ == "__main__":
    main()
