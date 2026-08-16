"""MILESTONE-080 CLI. Read-only: no append path is reachable from here."""

from __future__ import annotations

import json
import sys
from datetime import datetime

from empirical_platform.application.query import QueryEntryPoint
from empirical_platform.entrypoints._composition import postgres_repository_runtime
from empirical_platform.shared.config.settings import resolve_foundation_config
from empirical_platform.usecases.asserted_round_trip_io import (
    render_round_trip_report_json,
    render_round_trip_report_text,
)
from empirical_platform.usecases.get_asserted_round_trip_report import (
    GetAssertedRoundTripReportHandler,
    GetAssertedRoundTripReportQuery,
)

_USAGE = (
    "usage: empirical-platform-asserted-round-trip [--json] "
    "--effective-as-of <ISO-8601 with offset> --knowledge-as-of <ISO-8601 with offset>"
)


def _argument(args: list[str], flag: str) -> str | None:
    if flag not in args:
        return None
    index = args.index(flag)
    if index + 1 >= len(args):
        raise SystemExit(_USAGE)
    return args[index + 1]


def _cutoff(raw: str | None, label: str) -> datetime:
    # Both cutoffs are required. Defaulting either one would silently choose an
    # epistemic stance on the caller's behalf.
    if raw is None:
        raise SystemExit(f"{_USAGE}\n  {label} is required")
    try:
        moment = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise SystemExit(f"{_USAGE}\n  {label} is not a valid ISO-8601 timestamp") from exc
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise SystemExit(
            f"{_USAGE}\n  {label} must carry a UTC offset, e.g. 2026-08-10T16:00:00+00:00"
        )
    return moment


def main() -> None:
    args = sys.argv[1:]
    as_json = "--json" in args
    effective = _cutoff(_argument(args, "--effective-as-of"), "--effective-as-of")
    knowledge = _cutoff(_argument(args, "--knowledge-as-of"), "--knowledge-as-of")

    config = resolve_foundation_config().postgresql
    with postgres_repository_runtime(config) as runtime:
        handler = GetAssertedRoundTripReportHandler(
            operator_position_ledger_repository=runtime.operator_position_ledger
        )
        entry_point = QueryEntryPoint(handler)
        report = entry_point(
            GetAssertedRoundTripReportQuery(effective_as_of=effective, knowledge_as_of=knowledge)
        )

    if as_json:
        print(json.dumps(render_round_trip_report_json(report), sort_keys=True))
    else:
        print(render_round_trip_report_text(report), end="")
