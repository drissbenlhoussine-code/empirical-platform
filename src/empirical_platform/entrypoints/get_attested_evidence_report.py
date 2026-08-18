"""MILESTONE-082 receipt-label-cutoff view CLI.

Read-only: no attestation path is reachable from here.

RENAMED by Owner review finding 2: the flag is `--receipt-label-cutoff`, and
the old `--attested-as-of` no longer exists, because "as of" claimed a
point-in-time knowledge stance the label cannot support.

 This module emits a VIEW, never a snapshot, and it reads the
receipt store alone -- the M076 ledger is not a dependency of this entry point
(owner review findings 7 and 10).
"""

from __future__ import annotations

import json
import sys
from datetime import datetime

from empirical_platform.application.query import QueryEntryPoint
from empirical_platform.entrypoints._composition import postgres_repository_runtime
from empirical_platform.shared.config.settings import resolve_foundation_config
from empirical_platform.usecases.attest_operator_event_receipt import (
    GetAttestedEvidenceReportHandler,
    GetAttestedEvidenceReportQuery,
)
from empirical_platform.usecases.attested_evidence_io import (
    render_attested_evidence_report_json,
    render_attested_evidence_report_text,
)

_USAGE = (
    "usage: empirical-platform-receipt-label-cutoff-view [--json] "
    "--receipt-label-cutoff <ISO-8601 with offset>"
)


def _argument(args: list[str], flag: str) -> str | None:
    if flag not in args:
        return None
    index = args.index(flag)
    if index + 1 >= len(args):
        raise SystemExit(_USAGE)
    return args[index + 1]


def _cutoff(raw: str | None, label: str) -> datetime:
    # Required. Defaulting it would silently choose an epistemic stance on the
    # caller's behalf, exactly as M079 through M081 refuse to do.
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
    cutoff = _cutoff(_argument(args, "--receipt-label-cutoff"), "--receipt-label-cutoff")

    config = resolve_foundation_config().postgresql
    with postgres_repository_runtime(config) as runtime:
        handler = GetAttestedEvidenceReportHandler(
            operator_event_receipt_repository=runtime.operator_event_receipts,
        )
        entry_point = QueryEntryPoint(handler)
        report = entry_point(GetAttestedEvidenceReportQuery(receipt_label_cutoff=cutoff))

    if as_json:
        print(json.dumps(render_attested_evidence_report_json(report), sort_keys=True))
    else:
        print(render_attested_evidence_report_text(report), end="")
