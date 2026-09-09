"""MILESTONE-084 approved order intent CLI (read).

Prints one stored intent. Its submission state is always NOT_SUBMITTED, and the
printed output says so explicitly rather than leaving a reader to infer from a
field they might not look at.

`run_get_order_intent` is split out from `main()` so that `main()`'s argument
handling and output formatting can be unit-tested by monkeypatching this one
function -- without touching real persistence.
"""

from __future__ import annotations

import json
import sys

from empirical_platform.entrypoints._composition import postgres_repository_runtime
from empirical_platform.entrypoints._operator_cli import operator_command
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.usecases.decision_to_approval import (
    ApprovedOrderIntent,
    GetApprovedOrderIntentHandler,
    GetApprovedOrderIntentQuery,
)
from empirical_platform.usecases.decision_to_approval_io import (
    render_intent_json,
    render_intent_text,
)

_USAGE = "usage: empirical-platform-get-order-intent [--json] <intent_governance_id>"


def run_get_order_intent(
    *,
    intent_governance_id: str,
    config: PostgreSQLConfigSnapshot | None = None,
) -> ApprovedOrderIntent:
    with postgres_repository_runtime(config) as runtime:
        handler = GetApprovedOrderIntentHandler(
            approved_order_intent_repository=runtime.approved_order_intents
        )
        return handler.handle(
            GetApprovedOrderIntentQuery(intent_governance_id=intent_governance_id)
        )


def _main() -> None:
    args = sys.argv[1:]
    as_json = "--json" in args
    positional = [argument for argument in args if argument != "--json"]
    if len(positional) != 1:
        raise SystemExit(_USAGE)

    intent = run_get_order_intent(intent_governance_id=positional[0])

    if as_json:
        print(json.dumps(render_intent_json(intent), sort_keys=True))
    else:
        print(render_intent_text(intent), end="")


main = operator_command(_main)


if __name__ == "__main__":
    main()
