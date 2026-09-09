"""MILESTONE-084 stale-proposal sweep CLI.

Moves PREPARED proposals that can no longer be approved out of the queue, for
two distinct reasons kept distinct in the output:

  - EXPIRED: the proposal's own expiry has passed.
  - INVALIDATED: a newer configuration version exists, so the policy the
    proposal was evaluated under is no longer the operator's policy.

Expiry is checked first. An expired proposal is expired whatever the
configuration did afterwards, and reporting it as INVALIDATED would name the
wrong reason.

`as_of` defaults to now and may be given explicitly. Nothing terminal is
touched: the database refuses a transition out of a terminal status anyway, and
this command never attempts one.

`run_invalidate_stale_proposals` is split out from `main()` so that `main()`'s
argument handling and output formatting can be unit-tested by monkeypatching
this one function -- without touching real persistence.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime

from empirical_platform.application.command import CommandEntryPoint
from empirical_platform.entrypoints._composition import postgres_repository_runtime
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.usecases.decision_to_approval import (
    InvalidateStaleProposalsCommand,
    InvalidateStaleProposalsHandler,
    InvalidationOutcome,
)
from empirical_platform.usecases.decision_to_approval_io import (
    InputError,
    render_invalidation_json,
    render_invalidation_text,
)

_USAGE = (
    "usage: empirical-platform-invalidate-stale-proposals [--json] "
    "[configuration_governance_id] [as_of]"
)


def run_invalidate_stale_proposals(
    *,
    command: InvalidateStaleProposalsCommand,
    config: PostgreSQLConfigSnapshot | None = None,
) -> InvalidationOutcome:
    with postgres_repository_runtime(config) as runtime:
        handler = InvalidateStaleProposalsHandler(
            configuration_repository=runtime.operator_trading_configurations,
            trade_proposal_repository=runtime.trade_proposals,
        )
        entry_point = CommandEntryPoint(handler)
        return entry_point(command)


def _as_of(raw: str | None) -> datetime:
    if raw is None:
        return datetime.now(UTC)
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as error:
        raise InputError(f"as_of is not an ISO-8601 instant: {raw!r}") from error
    if parsed.tzinfo is None:
        raise InputError("as_of must carry a UTC offset")
    return parsed


def main() -> None:
    args = sys.argv[1:]
    as_json = "--json" in args
    positional = [argument for argument in args if argument != "--json"]
    if len(positional) > 2:
        raise SystemExit(_USAGE)

    outcome = run_invalidate_stale_proposals(
        command=InvalidateStaleProposalsCommand(
            as_of=_as_of(positional[1] if len(positional) == 2 else None),
            configuration_governance_id=positional[0] if positional else None,
        )
    )

    if as_json:
        print(json.dumps(render_invalidation_json(outcome), sort_keys=True))
    else:
        print(render_invalidation_text(outcome), end="")


if __name__ == "__main__":
    main()
