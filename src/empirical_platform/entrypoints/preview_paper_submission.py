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

from empirical_platform.entrypoints._operator_cli import operator_command
from empirical_platform.entrypoints._paper_composition import paper_execution_runtime
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.usecases.paper_execution import (
    PreviewPaperSubmissionCommand,
    PreviewPaperSubmissionHandler,
    SubmissionPreview,
)
from empirical_platform.usecases.paper_execution_io import (
    render_preview_json,
    render_preview_text,
)

#: CORRECTIVE PASS (D1). No notional, freshness or watchlist argument: those limits
#: are read from the configuration version the intent names, and a command-line value
#: could only ever have been a way to state looser ones.
_USAGE = (
    "usage: empirical-platform-preview-paper-submission [--json] <intent_governance_id> "
    "<preview_id> <snapshot_id>"
)


def run_preview_paper_submission(
    *,
    intent_governance_id: str,
    preview_id: str,
    snapshot_id: str,
    config: PostgreSQLConfigSnapshot | None = None,
) -> SubmissionPreview:
    with paper_execution_runtime(config) as context:
        handler = PreviewPaperSubmissionHandler(
            intents=context.m084.approved_order_intents,
            configurations=context.m084.operator_trading_configurations,
            time_bases=context.paper.time_bases,
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
                created_at=datetime.now(UTC),
            )
        )


def _main() -> None:
    args = sys.argv[1:]
    as_json = "--json" in args
    positional = [argument for argument in args if argument != "--json"]
    if len(positional) != 3:
        raise SystemExit(_USAGE)

    intent_id, preview_id, snapshot_id = positional
    preview = run_preview_paper_submission(
        intent_governance_id=intent_id,
        preview_id=preview_id,
        snapshot_id=snapshot_id,
    )
    if as_json:
        print(json.dumps(render_preview_json(preview), sort_keys=True))
    else:
        print(render_preview_text(preview), end="")


main = operator_command(_main)


if __name__ == "__main__":
    main()
