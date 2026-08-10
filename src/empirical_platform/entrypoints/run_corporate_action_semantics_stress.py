"""Real end-to-end CORPORATE_ACTION_SEMANTICS_STRESS composition root.

MILESTONE-065. A caller supplies the dataset governance identity of two
already-imported and already-persisted dataset snapshots (one
`SPLIT_ADJUSTED`, one `RAW_UNADJUSTED`) plus the on-disk M061-compatible
artifact file for each, and receives one structured, persisted diagnostic
comparison -- built by calling the real, unmodified M061
`build_historical_backtest_run()` twice.
"""

from __future__ import annotations

import json
import sys
from decimal import Decimal

from empirical_platform.application.command import CommandEntryPoint
from empirical_platform.entrypoints._composition import postgres_repository_runtime
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.shared.identifiers import (
    RuntimeIdentifierGenerator,
    UuidRuntimeIdentifierGenerator,
)
from empirical_platform.usecases.historical_backtest_io import (
    parse_historical_backtest_dataset_file,
)
from empirical_platform.usecases.historical_import_io import (
    corporate_action_semantics_stress_payload,
)
from empirical_platform.usecases.run_corporate_action_semantics_stress import (
    RunCorporateActionSemanticsStressHandler,
    build_run_corporate_action_semantics_stress_command,
)


def run_run_corporate_action_semantics_stress(
    *,
    stress_governance_id: str,
    dataset_id: str,
    correct_dataset_version: str,
    correct_dataset_file: str,
    naive_dataset_version: str,
    naive_dataset_file: str,
    correct_run_governance_id: str,
    naive_run_governance_id: str,
    account_equity: Decimal,
    risk_percent: Decimal,
    reference_window_size: int = 5,
    identifier_generator: RuntimeIdentifierGenerator | None = None,
    config: PostgreSQLConfigSnapshot | None = None,
) -> object:
    """Run one deterministic corporate-action semantics stress diagnostic
    end-to-end against real PostgreSQL."""
    resolved_generator = identifier_generator or UuidRuntimeIdentifierGenerator()
    correct_dataset = parse_historical_backtest_dataset_file(correct_dataset_file)
    naive_dataset = parse_historical_backtest_dataset_file(naive_dataset_file)
    with postgres_repository_runtime(config) as runtime:
        handler = RunCorporateActionSemanticsStressHandler(
            historical_backtest_run_repository=runtime.historical_backtests,
            dataset_snapshot_repository=runtime.dataset_snapshots,
            stress_repository=runtime.corporate_action_semantics_stresses,
        )
        entry_point = CommandEntryPoint(handler)
        return entry_point(
            build_run_corporate_action_semantics_stress_command(
                stress_governance_id=stress_governance_id,
                dataset_id=dataset_id,
                correct_dataset_version=correct_dataset_version,
                correct_dataset=correct_dataset,
                naive_dataset_version=naive_dataset_version,
                naive_dataset=naive_dataset,
                correct_run_governance_id=correct_run_governance_id,
                naive_run_governance_id=naive_run_governance_id,
                account_equity=account_equity,
                risk_percent=risk_percent,
                runtime_identifier_generator=resolved_generator,
                reference_window_size=reference_window_size,
            )
        )


def _stress_payload(result: object) -> dict[str, object]:
    return corporate_action_semantics_stress_payload(result)


def main() -> None:
    if len(sys.argv) not in (11, 12):
        raise SystemExit(
            "usage: empirical-platform-run-corporate-action-semantics-stress "
            "<stress_governance_id> <dataset_id> <correct_dataset_version> "
            "<correct_dataset_file> <naive_dataset_version> <naive_dataset_file> "
            "<correct_run_governance_id> <naive_run_governance_id> <account_equity> "
            "<risk_percent> [reference_window_size]"
        )
    result = run_run_corporate_action_semantics_stress(
        stress_governance_id=sys.argv[1],
        dataset_id=sys.argv[2],
        correct_dataset_version=sys.argv[3],
        correct_dataset_file=sys.argv[4],
        naive_dataset_version=sys.argv[5],
        naive_dataset_file=sys.argv[6],
        correct_run_governance_id=sys.argv[7],
        naive_run_governance_id=sys.argv[8],
        account_equity=Decimal(sys.argv[9]),
        risk_percent=Decimal(sys.argv[10]),
        reference_window_size=int(sys.argv[11]) if len(sys.argv) > 11 else 5,
    )
    print(json.dumps(_stress_payload(result), sort_keys=True))


if __name__ == "__main__":
    main()
