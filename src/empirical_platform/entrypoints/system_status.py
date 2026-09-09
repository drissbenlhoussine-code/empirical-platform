"""MILESTONE-084 system status CLI.

Answers the two questions an operator asks before doing anything: what is in
the queue, and is the product allowed to act.

It also states, every time, what this product CANNOT do. That line is not
decoration: "submission capability: NONE" is a constant rather than a probe,
because there is nothing to probe -- no broker client may be imported anywhere
in this package, and no intent can leave NOT_SUBMITTED. An operator should
never have to infer that from an absence.

`run_system_status` is split out from `main()` so that `main()`'s argument
handling and output formatting can be unit-tested by monkeypatching this one
function -- without touching real persistence.
"""

from __future__ import annotations

import json
import sys

from empirical_platform.entrypoints._composition import postgres_repository_runtime
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.usecases.decision_to_approval import (
    GetSystemStatusHandler,
    GetSystemStatusQuery,
    SystemStatus,
)
from empirical_platform.usecases.decision_to_approval_io import (
    render_system_status_json,
    render_system_status_text,
)

_USAGE = "usage: empirical-platform-system-status [--json] [configuration_governance_id]"


def run_system_status(
    *,
    configuration_governance_id: str | None = None,
    config: PostgreSQLConfigSnapshot | None = None,
) -> SystemStatus:
    with postgres_repository_runtime(config) as runtime:
        handler = GetSystemStatusHandler(
            configuration_repository=runtime.operator_trading_configurations,
            trade_proposal_repository=runtime.trade_proposals,
        )
        return handler.handle(
            GetSystemStatusQuery(configuration_governance_id=configuration_governance_id)
        )


def main() -> None:
    args = sys.argv[1:]
    as_json = "--json" in args
    positional = [argument for argument in args if argument != "--json"]
    if len(positional) > 1:
        raise SystemExit(_USAGE)

    status = run_system_status(configuration_governance_id=positional[0] if positional else None)

    if as_json:
        print(json.dumps(render_system_status_json(status), sort_keys=True))
    else:
        print(render_system_status_text(status), end="")


if __name__ == "__main__":
    main()
