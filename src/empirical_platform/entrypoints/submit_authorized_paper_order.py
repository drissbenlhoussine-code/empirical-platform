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
from decimal import Decimal, InvalidOperation

from empirical_platform.entrypoints._operator_cli import operator_command
from empirical_platform.entrypoints._paper_composition import paper_execution_runtime
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.usecases.decision_to_approval_io import InputError
from empirical_platform.usecases.paper_execution import (
    PaperSubmissionResult,
    SubmitAuthorizedPaperOrderCommand,
    SubmitAuthorizedPaperOrderHandler,
)
from empirical_platform.usecases.paper_execution_io import (
    render_submission_json,
    render_submission_text,
)

_USAGE = (
    "usage: empirical-platform-submit-authorized-paper-order [--json] "
    "<intent_governance_id> <attempt_id> <snapshot_id> <maximum_notional> "
    "<quote_max_age_seconds> <watchlist_symbol>[,<symbol>...]"
)


def run_submit_authorized_paper_order(
    *,
    intent_governance_id: str,
    attempt_id: str,
    snapshot_id: str,
    maximum_notional: Decimal,
    quote_maximum_age_seconds: int,
    approved_watchlist: frozenset[str],
    config: PostgreSQLConfigSnapshot | None = None,
) -> PaperSubmissionResult:
    with paper_execution_runtime(config) as context:
        handler = SubmitAuthorizedPaperOrderHandler(
            intents=context.m084.approved_order_intents,
            previews=context.paper.submission_previews,
            authorizations=context.paper.execution_authorizations,
            attempts=context.paper.execution_attempts,
            acknowledgements=context.paper.broker_acknowledgements,
            events=context.paper.paper_execution_events,
            snapshots=context.paper.paper_account_snapshots,
            broker=context.broker,
            market_data=context.market_data,
            kill_switch=context.paper.execution_kill_switch,
        )
        return handler.handle(
            SubmitAuthorizedPaperOrderCommand(
                intent_governance_id=intent_governance_id,
                attempt_id=attempt_id,
                account_snapshot_id=snapshot_id,
                approved_watchlist=approved_watchlist,
                maximum_notional=maximum_notional,
                quote_maximum_age_seconds=quote_maximum_age_seconds,
                at=datetime.now(UTC),
            )
        )


def _main() -> None:
    args = sys.argv[1:]
    as_json = "--json" in args
    positional = [argument for argument in args if argument != "--json"]
    if len(positional) != 6:
        raise SystemExit(_USAGE)

    intent_id, attempt_id, snapshot_id, notional, age, watchlist = positional
    try:
        ceiling = Decimal(notional)
    except InvalidOperation as error:
        raise InputError(f"maximum_notional {notional!r} is not a decimal") from error
    if not age.isdigit():
        raise InputError(f"quote_max_age_seconds {age!r} is not a non-negative whole number")
    symbols = frozenset(symbol.strip().upper() for symbol in watchlist.split(",") if symbol.strip())
    if not symbols:
        raise InputError("the approved watchlist must name at least one symbol")

    result = run_submit_authorized_paper_order(
        intent_governance_id=intent_id,
        attempt_id=attempt_id,
        snapshot_id=snapshot_id,
        maximum_notional=ceiling,
        quote_maximum_age_seconds=int(age),
        approved_watchlist=symbols,
    )
    if as_json:
        print(json.dumps(render_submission_json(result), sort_keys=True))
    else:
        print(render_submission_text(result), end="")


main = operator_command(_main)


if __name__ == "__main__":
    main()
