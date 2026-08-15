"""MILESTONE-076 CLI: derived operator-asserted position state at an `as_of`."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime

from empirical_platform.entrypoints._composition import postgres_repository_runtime
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.usecases.get_operator_position_state import (
    GetOperatorPositionStateHandler,
    GetOperatorPositionStateQuery,
)
from empirical_platform.usecases.operator_position_ledger_io import (
    render_operator_position_state_json,
    render_operator_position_state_text,
)

_USAGE = "usage: empirical-platform-get-position-state [--json] [--as-of ISO8601]"


def run_get_operator_position_state(
    *,
    as_of: datetime,
    as_json: bool,
    config: PostgreSQLConfigSnapshot | None = None,
) -> str:
    """Return the finished rendering.

    `entrypoints` may not import `decision_candidate`, so no domain object
    crosses this boundary: the state is rendered inside the composition block
    and only a string comes back.
    """
    with postgres_repository_runtime(config) as runtime:
        handler = GetOperatorPositionStateHandler(
            ledger_repository=runtime.operator_position_ledger
        )
        state = handler.handle(GetOperatorPositionStateQuery(as_of=as_of))
        if as_json:
            return json.dumps(render_operator_position_state_json(state), sort_keys=True)
        return render_operator_position_state_text(state)


def main() -> None:
    args = sys.argv[1:]
    as_json = "--json" in args
    as_of = datetime.now(UTC)
    if "--as-of" in args:
        index = args.index("--as-of")
        if index + 1 >= len(args):
            raise SystemExit(_USAGE)
        try:
            as_of = datetime.fromisoformat(args[index + 1])
        except ValueError as exc:
            raise SystemExit(f"{_USAGE}\n{exc}") from exc
        if as_of.tzinfo is None:
            raise SystemExit(f"{_USAGE}\n--as-of must carry an explicit timezone offset")

    print(run_get_operator_position_state(as_of=as_of, as_json=as_json))
