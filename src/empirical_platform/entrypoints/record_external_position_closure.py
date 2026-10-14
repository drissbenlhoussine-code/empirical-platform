"""RELEASE v1 -- PAPER external position closure reconciliation CLI.

    empirical-platform-record-external-position-closure <entry_intent_governance_id> \\
        <client_order_id> <recorded_by>

Verifies, then durably records, that an entry's position was closed by a broker order this
platform never dispatched (e.g. a manual sale on the Alpaca PAPER dashboard), so the
automatic Plan Manager stops retrying a trigger that can never succeed. See
`usecases.record_external_position_closure` for the full gating this performs -- every
safety-relevant fact (symbol, quantity, price, and that the broker's CURRENT position is
zero) is read fresh from the broker; only WHICH order to check and WHO is recording it are
taken from the command line. Reuses the SAME verified Store B + Store C composition the
PAPER-with-exit console uses (`paper_operator_console_with_exit_runtime`); never opens a
second connection, never starts a console, never submits or cancels an order.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime

from empirical_platform.entrypoints._operator_cli import operator_command
from empirical_platform.entrypoints._paper_position_exit_composition import (
    paper_operator_console_with_exit_runtime,
)
from empirical_platform.usecases.record_external_position_closure import (
    ExternalPositionClosure,
    RecordExternalPositionClosureCommand,
    RecordExternalPositionClosureHandler,
)

_USAGE = (
    "usage: empirical-platform-record-external-position-closure [--json] "
    "<entry_intent_governance_id> <client_order_id> <recorded_by>"
)


def run_record_external_position_closure(
    *, entry_intent_governance_id: str, client_order_id: str, recorded_by: str
) -> ExternalPositionClosure:
    with paper_operator_console_with_exit_runtime() as backend:
        assert backend._exits is not None  # always set by this composition
        assert backend._external_closures is not None  # always set by this composition
        handler = RecordExternalPositionClosureHandler(
            intents=backend._repositories.intents,
            entry_attempts=backend._repositories.attempts,
            exit_attempts=backend._exits.attempts,
            closures=backend._external_closures,
            events=backend._exits.events,
            broker=backend._broker,
        )
        return handler.handle(
            RecordExternalPositionClosureCommand(
                entry_intent_governance_id=entry_intent_governance_id,
                client_order_id=client_order_id,
                recorded_by=recorded_by,
                at=datetime.now(UTC),
            )
        )


def _render(closure: ExternalPositionClosure) -> str:
    return (
        f"Recorded external closure {closure.closure_id} for "
        f"{closure.entry_intent_governance_id}: SELL {closure.quantity} {closure.symbol} @ "
        f"{closure.filled_avg_price} (broker order {closure.broker_order_id}, by "
        f"{closure.recorded_by} at {closure.recorded_at.isoformat()}).\n"
    )


def _main() -> None:
    args = sys.argv[1:]
    as_json = "--json" in args
    positional = [argument for argument in args if argument != "--json"]
    if len(positional) != 3:
        raise SystemExit(_USAGE)
    entry_intent_governance_id, client_order_id, recorded_by = positional

    closure = run_record_external_position_closure(
        entry_intent_governance_id=entry_intent_governance_id,
        client_order_id=client_order_id,
        recorded_by=recorded_by,
    )
    if as_json:
        print(
            json.dumps(
                {
                    "closure_id": closure.closure_id,
                    "entry_intent_governance_id": closure.entry_intent_governance_id,
                    "symbol": closure.symbol,
                    "quantity": closure.quantity,
                    "broker_order_id": closure.broker_order_id,
                    "client_order_id": closure.client_order_id,
                    "filled_avg_price": str(closure.filled_avg_price),
                    "recorded_by": closure.recorded_by,
                    "recorded_at": closure.recorded_at.isoformat(),
                },
                sort_keys=True,
            )
        )
    else:
        print(_render(closure), end="")


main = operator_command(_main)


if __name__ == "__main__":
    main()
