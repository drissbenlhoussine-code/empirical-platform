"""MILESTONE-083 watermark get CLI.

Read-only: reads the STORED set of one already-captured watermark. Never
consults the current receipt inventory, so this command's output for a given
identity is fixed the instant that watermark is captured.

`run_get_evaluation_evidence_watermark` is split out from `main()`, mirroring
`entrypoints.create_run`/`entrypoints.get_run`'s own precedent
(MILESTONE-053), so `main()`'s argument handling and output formatting can be
unit-tested by monkeypatching this one function -- without touching real
persistence. Real end-to-end composition is proven separately by this
milestone's own PostgreSQL integration test.
"""

from __future__ import annotations

import json
import sys

from empirical_platform.application.query import QueryEntryPoint
from empirical_platform.entrypoints._composition import postgres_repository_runtime
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.usecases.capture_evaluation_evidence_watermark import (
    EvaluationEvidenceWatermark,
    GetEvaluationEvidenceWatermarkHandler,
    GetEvaluationEvidenceWatermarkQuery,
)
from empirical_platform.usecases.evaluation_evidence_watermark_io import (
    render_evaluation_evidence_watermark_json,
    render_evaluation_evidence_watermark_text,
)

_USAGE = (
    "usage: empirical-platform-get-evaluation-evidence-watermark [--json] <watermark_governance_id>"  # noqa: E501
)


def run_get_evaluation_evidence_watermark(
    *,
    watermark_governance_id: str,
    config: PostgreSQLConfigSnapshot | None = None,
) -> EvaluationEvidenceWatermark:
    """Read one already-captured watermark end-to-end, against real PostgreSQL."""
    with postgres_repository_runtime(config) as runtime:
        handler = GetEvaluationEvidenceWatermarkHandler(
            evaluation_evidence_watermark_repository=runtime.evaluation_evidence_watermarks,
        )
        entry_point = QueryEntryPoint(handler)
        return entry_point(
            GetEvaluationEvidenceWatermarkQuery(watermark_governance_id=watermark_governance_id)
        )


def main() -> None:
    args = sys.argv[1:]
    as_json = "--json" in args
    positional = [a for a in args if a != "--json"]
    if len(positional) != 1:
        raise SystemExit(_USAGE)

    watermark = run_get_evaluation_evidence_watermark(watermark_governance_id=positional[0])

    if as_json:
        print(json.dumps(render_evaluation_evidence_watermark_json(watermark), sort_keys=True))
    else:
        print(render_evaluation_evidence_watermark_text(watermark), end="")


if __name__ == "__main__":
    main()
