"""Real end-to-end historical validation study composition root.

MILESTONE-062. A caller supplies one fixed local multi-period dataset
bundle file, its own declared SHA-256 (tamper detection happens before any
parsing), three segment backtest-run governance IDs, and explicit
sizing inputs, and receives one structured, persisted, deterministic
cross-period validation result -- one DEVELOPMENT_REFERENCE segment plus
two independent HOLDOUT segments, each executed through the unmodified
M061 engine.
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
from empirical_platform.usecases.run_historical_validation_study import (
    RunHistoricalValidationStudyHandler,
    build_run_historical_validation_study_command,
)
from empirical_platform.usecases.validation_study_io import (
    historical_validation_study_payload,
)
from empirical_platform.usecases.validation_study_io import (
    parse_validation_dataset_bundle_file as _parse_bundle_file,
)


def run_run_historical_validation_study(
    *,
    study_governance_id: str,
    dataset_bundle_file: str,
    expected_dataset_sha256: str,
    development_backtest_run_governance_id: str,
    holdout_1_backtest_run_governance_id: str,
    holdout_2_backtest_run_governance_id: str,
    account_equity: Decimal,
    risk_percent: Decimal,
    reference_window_size: int = 5,
    holding_horizon_bars: int = 3,
    identifier_generator: RuntimeIdentifierGenerator | None = None,
    config: PostgreSQLConfigSnapshot | None = None,
) -> object:
    """Run one deterministic multi-period validation study end-to-end
    against real PostgreSQL."""
    resolved_generator = identifier_generator or UuidRuntimeIdentifierGenerator()
    bundle = _parse_bundle_file(dataset_bundle_file, expected_sha256=expected_dataset_sha256)
    with postgres_repository_runtime(config) as runtime:
        handler = RunHistoricalValidationStudyHandler(
            historical_backtest_run_repository=runtime.historical_backtests,
            validation_study_repository=runtime.validation_studies,
        )
        entry_point = CommandEntryPoint(handler)
        return entry_point(
            build_run_historical_validation_study_command(
                study_governance_id=study_governance_id,
                bundle=bundle,
                development_backtest_run_governance_id=development_backtest_run_governance_id,
                holdout_1_backtest_run_governance_id=holdout_1_backtest_run_governance_id,
                holdout_2_backtest_run_governance_id=holdout_2_backtest_run_governance_id,
                account_equity=account_equity,
                risk_percent=risk_percent,
                runtime_identifier_generator=resolved_generator,
                reference_window_size=reference_window_size,
                holding_horizon_bars=holding_horizon_bars,
            )
        )


def _study_payload(study: object) -> dict[str, object]:
    return historical_validation_study_payload(study)


def main() -> None:
    if len(sys.argv) not in (9, 10, 11):
        raise SystemExit(
            "usage: empirical-platform-run-historical-validation-study "
            "<study_governance_id> <dataset_bundle_file> <expected_dataset_sha256> "
            "<development_backtest_run_governance_id> <holdout_1_backtest_run_governance_id> "
            "<holdout_2_backtest_run_governance_id> <account_equity> <risk_percent> "
            "[reference_window_size] [holding_horizon_bars]"
        )
    study = run_run_historical_validation_study(
        study_governance_id=sys.argv[1],
        dataset_bundle_file=sys.argv[2],
        expected_dataset_sha256=sys.argv[3],
        development_backtest_run_governance_id=sys.argv[4],
        holdout_1_backtest_run_governance_id=sys.argv[5],
        holdout_2_backtest_run_governance_id=sys.argv[6],
        account_equity=Decimal(sys.argv[7]),
        risk_percent=Decimal(sys.argv[8]),
        reference_window_size=int(sys.argv[9]) if len(sys.argv) > 9 else 5,
        holding_horizon_bars=int(sys.argv[10]) if len(sys.argv) > 10 else 3,
    )
    print(json.dumps(_study_payload(study), sort_keys=True))


if __name__ == "__main__":
    main()
