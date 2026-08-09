"""Real end-to-end historical robustness study composition root.

MILESTONE-063. A caller supplies one fixed local broad multi-window dataset
bundle file, its own declared SHA-256 (tamper detection happens before any
parsing), a backtest-run governance-ID numeric base (each window's own
`BacktestRunId` is deterministically derived from it), and explicit sizing
inputs, and receives one structured, persisted, deterministic
cross-window robustness result -- N chronological windows, each executed
through the unmodified M061 engine, with a transparent, un-massaged
cross-window comparison.
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
from empirical_platform.usecases.robustness_study_io import (
    historical_robustness_study_payload,
)
from empirical_platform.usecases.robustness_study_io import (
    parse_robustness_dataset_bundle_file as _parse_bundle_file,
)
from empirical_platform.usecases.run_historical_robustness_study import (
    RunHistoricalRobustnessStudyHandler,
    build_run_historical_robustness_study_command,
)


def run_run_historical_robustness_study(
    *,
    study_governance_id: str,
    dataset_bundle_file: str,
    expected_dataset_sha256: str,
    backtest_run_governance_id_base: int,
    account_equity: Decimal,
    risk_percent: Decimal,
    reference_window_size: int = 5,
    holding_horizon_bars: int = 3,
    identifier_generator: RuntimeIdentifierGenerator | None = None,
    config: PostgreSQLConfigSnapshot | None = None,
) -> object:
    """Run one deterministic broad multi-window robustness study end-to-end
    against real PostgreSQL."""
    resolved_generator = identifier_generator or UuidRuntimeIdentifierGenerator()
    bundle = _parse_bundle_file(dataset_bundle_file, expected_sha256=expected_dataset_sha256)
    with postgres_repository_runtime(config) as runtime:
        handler = RunHistoricalRobustnessStudyHandler(
            historical_backtest_run_repository=runtime.historical_backtests,
            robustness_study_repository=runtime.robustness_studies,
        )
        entry_point = CommandEntryPoint(handler)
        return entry_point(
            build_run_historical_robustness_study_command(
                study_governance_id=study_governance_id,
                bundle=bundle,
                backtest_run_governance_id_base=backtest_run_governance_id_base,
                account_equity=account_equity,
                risk_percent=risk_percent,
                runtime_identifier_generator=resolved_generator,
                reference_window_size=reference_window_size,
                holding_horizon_bars=holding_horizon_bars,
            )
        )


def _study_payload(study: object) -> dict[str, object]:
    return historical_robustness_study_payload(study)


def main() -> None:
    if len(sys.argv) not in (7, 8, 9):
        raise SystemExit(
            "usage: empirical-platform-run-historical-robustness-study "
            "<study_governance_id> <dataset_bundle_file> <expected_dataset_sha256> "
            "<backtest_run_governance_id_base> <account_equity> <risk_percent> "
            "[reference_window_size] [holding_horizon_bars]"
        )
    study = run_run_historical_robustness_study(
        study_governance_id=sys.argv[1],
        dataset_bundle_file=sys.argv[2],
        expected_dataset_sha256=sys.argv[3],
        backtest_run_governance_id_base=int(sys.argv[4]),
        account_equity=Decimal(sys.argv[5]),
        risk_percent=Decimal(sys.argv[6]),
        reference_window_size=int(sys.argv[7]) if len(sys.argv) > 7 else 5,
        holding_horizon_bars=int(sys.argv[8]) if len(sys.argv) > 8 else 3,
    )
    print(json.dumps(_study_payload(study), sort_keys=True))


if __name__ == "__main__":
    main()
