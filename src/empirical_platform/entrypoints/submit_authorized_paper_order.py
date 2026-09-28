"""MILESTONE-085 authorized paper order submission CLI -- the only command that sends.

WHAT IT WILL NOT DO. It will not create an authorization, will not accept a
fingerprint, will not take an endpoint, and has no `--force`. If no valid human
authorization exists for the intent, it refuses; the way to get one is to run
`empirical-platform-authorize-paper-submission`, which means reading a preview
first.

WHAT HAPPENS BEFORE THE NETWORK. The kill switch is read, all broker evidence is
refreshed, the request fingerprint is recomputed from that fresh evidence, the
authorization is required to still match it, and the dispatch is claimed in the
database. Only then is anything sent.

IF THE OUTCOME IS AMBIGUOUS. The attempt is recorded as SUBMISSION_UNKNOWN and the
printed note says to reconcile using the same client order id. Running this
command again will NOT send a second order: it finds the existing attempt and
returns it.

`run_submit_authorized_paper_order` is split out from `main()` so that argument
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
from empirical_platform.usecases.paper_execution import (
    PaperSubmissionResult,
    SubmitAuthorizedPaperOrderCommand,
    SubmitAuthorizedPaperOrderHandler,
)
from empirical_platform.usecases.paper_execution_io import (
    render_submission_json,
    render_submission_text,
)

#: CORRECTIVE PASS (D1). This command takes NO limit. The notional cap, freshness
#: limit, watchlist, spread limit and entry window are the configuration's, bound to
#: the authorization by its policy fingerprint; an argument could only weaken them.
_USAGE = (
    "usage: empirical-platform-submit-authorized-paper-order [--json] "
    "<intent_governance_id> <attempt_id> <snapshot_id>"
)


def run_submit_authorized_paper_order(
    *,
    intent_governance_id: str,
    attempt_id: str,
    snapshot_id: str,
    config: PostgreSQLConfigSnapshot | None = None,
) -> PaperSubmissionResult:
    with paper_execution_runtime(config) as context:
        handler = SubmitAuthorizedPaperOrderHandler(
            intents=context.m084.approved_order_intents,
            configurations=context.m084.operator_trading_configurations,
            time_bases=context.paper.time_bases,
            previews=context.paper.submission_previews,
            authorizations=context.paper.execution_authorizations,
            attempts=context.paper.execution_attempts,
            acknowledgements=context.paper.broker_acknowledgements,
            events=context.paper.paper_execution_events,
            snapshots=context.paper.paper_account_snapshots,
            broker=context.broker,
            market_data=context.market_data,
            kill_switch=context.paper.execution_kill_switch,
            time_source=context.time_source,
        )
        return handler.handle(
            SubmitAuthorizedPaperOrderCommand(
                intent_governance_id=intent_governance_id,
                attempt_id=attempt_id,
                account_snapshot_id=snapshot_id,
                at=datetime.now(UTC),
            )
        )


def _main() -> None:
    args = sys.argv[1:]
    as_json = "--json" in args
    positional = [argument for argument in args if argument != "--json"]
    if len(positional) != 3:
        raise SystemExit(_USAGE)

    intent_id, attempt_id, snapshot_id = positional
    result = run_submit_authorized_paper_order(
        intent_governance_id=intent_id,
        attempt_id=attempt_id,
        snapshot_id=snapshot_id,
    )
    if as_json:
        print(json.dumps(render_submission_json(result), sort_keys=True))
    else:
        print(render_submission_text(result), end="")


main = operator_command(_main)


if __name__ == "__main__":
    main()
