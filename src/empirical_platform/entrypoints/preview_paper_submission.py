"""MILESTONE-085 paper submission preview CLI.

SENDS NOTHING. Refreshes the account, clock, asset, quote, position and kill
switch, then freezes exactly what a human would authorize -- including every
reason it cannot be authorized. Print this, read it, and only then authorize.

`run_preview_paper_submission` is split out from `main()` so that argument
handling and output formatting can be unit-tested by monkeypatching this one
function -- without touching a real broker or a real database.
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
    PreviewPaperSubmissionCommand,
    PreviewPaperSubmissionHandler,
    SubmissionPreview,
)
from empirical_platform.usecases.paper_execution_io import (
    render_preview_json,
    render_preview_text,
)

_USAGE = (
    "usage: empirical-platform-preview-paper-submission [--json] <intent_governance_id> "
    "<preview_id> <snapshot_id> <maximum_notional> <quote_max_age_seconds> "
    "<watchlist_symbol>[,<symbol>...]"
)


def run_preview_paper_submission(
    *,
    intent_governance_id: str,
    preview_id: str,
    snapshot_id: str,
    maximum_notional: Decimal,
    quote_maximum_age_seconds: int,
    approved_watchlist: frozenset[str],
    config: PostgreSQLConfigSnapshot | None = None,
) -> SubmissionPreview:
    with paper_execution_runtime(config) as context:
        handler = PreviewPaperSubmissionHandler(
            intents=context.m084.approved_order_intents,
            snapshots=context.paper.paper_account_snapshots,
            previews=context.paper.submission_previews,
            events=context.paper.paper_execution_events,
            broker=context.broker,
            market_data=context.market_data,
            kill_switch=context.paper.execution_kill_switch,
            time_source=context.time_source,
        )
        return handler.handle(
            PreviewPaperSubmissionCommand(
                intent_governance_id=intent_governance_id,
                preview_id=preview_id,
                account_snapshot_id=snapshot_id,
                approved_watchlist=approved_watchlist,
                maximum_notional=maximum_notional,
                quote_maximum_age_seconds=quote_maximum_age_seconds,
                created_at=datetime.now(UTC),
            )
        )


def _amount(raw: str) -> Decimal:
    # Read from a string, never through float: a ceiling typed as 5.00 must mean
    # exactly five.
    try:
        return Decimal(raw)
    except InvalidOperation as error:
        raise InputError(f"maximum_notional {raw!r} is not a decimal") from error


def _whole(raw: str, *, field: str) -> int:
    if not raw.isdigit():
        raise InputError(f"{field} {raw!r} is not a non-negative whole number")
    return int(raw)


def _main() -> None:
    args = sys.argv[1:]
    as_json = "--json" in args
    positional = [argument for argument in args if argument != "--json"]
    if len(positional) != 6:
        raise SystemExit(_USAGE)

    intent_id, preview_id, snapshot_id, notional, age, watchlist = positional
    symbols = frozenset(symbol.strip().upper() for symbol in watchlist.split(",") if symbol.strip())
    if not symbols:
        raise InputError("the approved watchlist must name at least one symbol")

    preview = run_preview_paper_submission(
        intent_governance_id=intent_id,
        preview_id=preview_id,
        snapshot_id=snapshot_id,
        maximum_notional=_amount(notional),
        quote_maximum_age_seconds=_whole(age, field="quote_max_age_seconds"),
        approved_watchlist=symbols,
    )
    if as_json:
        print(json.dumps(render_preview_json(preview), sort_keys=True))
    else:
        print(render_preview_text(preview), end="")


main = operator_command(_main)


if __name__ == "__main__":
    main()
