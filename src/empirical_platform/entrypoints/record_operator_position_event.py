"""MILESTONE-076 CLI: record one operator-asserted position event.

The operator is asserting what THEY did. This command does not place, route,
or confirm anything, and nothing here is a broker record or a verified fill.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

from empirical_platform.entrypoints._composition import postgres_repository_runtime
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.shared.identifiers import UuidRuntimeIdentifierGenerator
from empirical_platform.usecases.record_operator_position_event import (
    OPERATOR_LEDGER_BANNER,
    LedgerRejectionError,
    RecordedOperatorEventView,
    RecordOperatorPositionEventCommand,
    RecordOperatorPositionEventHandler,
    build_operator_position_event,
)

_USAGE = (
    "usage: empirical-platform-record-position-event [--json] "
    "--event-id ID --position-id ID --symbol SYM --kind OPENED|REDUCED|CLOSED "
    "--quantity N --price X --at ISO8601 [--source-position-plan ID] [--note TEXT]"
)


def _require(args: list[str], flag: str) -> str:
    if flag not in args:
        raise SystemExit(f"{_USAGE}\nmissing required option: {flag}")
    index = args.index(flag)
    if index + 1 >= len(args):
        raise SystemExit(f"{_USAGE}\noption {flag} requires a value")
    return args[index + 1]


def _optional(args: list[str], flag: str) -> str | None:
    return args[args.index(flag) + 1] if flag in args else None


def run_record_operator_position_event(
    *,
    governance_id: str,
    position_governance_id: str,
    instrument_symbol: str,
    kind: str,
    quantity: int,
    asserted_price: Decimal,
    event_timestamp: datetime,
    source_position_plan_governance_id: str | None = None,
    note: str | None = None,
    config: PostgreSQLConfigSnapshot | None = None,
) -> RecordedOperatorEventView:
    """Primitives in, primitive view out. No domain object crosses this
    boundary, because `entrypoints` may not import `decision_candidate`."""
    event = build_operator_position_event(
        governance_id=governance_id,
        runtime_id=str(UuidRuntimeIdentifierGenerator().generate()),
        position_governance_id=position_governance_id,
        instrument_symbol=instrument_symbol,
        kind=kind,
        quantity=quantity,
        asserted_price=asserted_price,
        event_timestamp=event_timestamp,
        recorded_at=datetime.now(UTC),
        source_position_plan_governance_id=source_position_plan_governance_id,
        note=note,
    )
    with postgres_repository_runtime(config) as runtime:
        handler = RecordOperatorPositionEventHandler(
            ledger_repository=runtime.operator_position_ledger
        )
        return RecordedOperatorEventView.of(
            handler.handle(RecordOperatorPositionEventCommand(event=event))
        )


def main() -> None:
    args = sys.argv[1:]
    as_json = "--json" in args
    try:
        kind = _require(args, "--kind")
        quantity = int(_require(args, "--quantity"))
        price = Decimal(_require(args, "--price"))
        at = datetime.fromisoformat(_require(args, "--at"))
    except (ValueError, InvalidOperation) as exc:
        raise SystemExit(f"{_USAGE}\n{exc}") from exc
    if at.tzinfo is None:
        raise SystemExit(f"{_USAGE}\n--at must carry an explicit timezone offset")

    try:
        recorded = run_record_operator_position_event(
            governance_id=_require(args, "--event-id"),
            position_governance_id=_require(args, "--position-id"),
            instrument_symbol=_require(args, "--symbol"),
            kind=kind,
            quantity=quantity,
            asserted_price=price,
            event_timestamp=at,
            source_position_plan_governance_id=_optional(args, "--source-position-plan"),
            note=_optional(args, "--note"),
        )
    except LedgerRejectionError as exc:
        raise SystemExit(f"rejected: {exc}") from exc

    if as_json:
        print(
            json.dumps(
                {
                    "honesty_banner": OPERATOR_LEDGER_BANNER,
                    "recorded_event_governance_id": recorded.governance_id,
                    "position_governance_id": recorded.position_governance_id,
                    "instrument_symbol": recorded.instrument_symbol,
                    "event_kind": recorded.event_kind,
                    "quantity": recorded.quantity,
                    "event_timestamp": recorded.event_timestamp,
                },
                sort_keys=True,
            )
        )
    else:
        print(f"recorded operator assertion {recorded.governance_id}")
        print(
            f"  {recorded.event_kind} {recorded.quantity} {recorded.instrument_symbol} "
            f"[{recorded.position_governance_id}] at {recorded.event_timestamp}"
        )
        print(f"  {OPERATOR_LEDGER_BANNER}")
