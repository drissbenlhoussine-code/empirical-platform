"""Real end-to-end survivorship-aware robustness study composition root.

MILESTONE-064. A caller supplies one fixed local dataset bundle file, one
fixed local instrument-master file, one fixed local membership-manifest
file, each with its own caller-declared expected hash (tamper detection
happens before any parsing), two backtest-run governance-ID numeric bases
(one for the canonical membership-gated windows, one for the diagnostic
`CURRENT_UNIVERSE_BIAS_STRESS` windows), and explicit sizing inputs, and
receives one structured, persisted, deterministic survivorship-aware
robustness result plus its diagnostic comparison against forcing the final
universe backward across every window.
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
from empirical_platform.usecases.run_survivorship_aware_robustness_study import (
    RunSurvivorshipAwareRobustnessStudyHandler,
    build_run_survivorship_aware_robustness_study_command,
)
from empirical_platform.usecases.survivorship_study_io import (
    parse_instrument_master_file,
    parse_membership_manifest_file,
    parse_survivorship_dataset_bundle_file,
    survivorship_aware_robustness_study_payload,
)


def run_run_survivorship_aware_robustness_study(
    *,
    study_governance_id: str,
    stress_study_governance_id: str,
    dataset_bundle_file: str,
    expected_dataset_sha256: str,
    instrument_master_file: str,
    membership_manifest_file: str,
    expected_membership_hash: str,
    universe_source_kind: str,
    backtest_run_governance_id_base: int,
    stress_backtest_run_governance_id_base: int,
    account_equity: Decimal,
    risk_percent: Decimal,
    reference_window_size: int = 5,
    holding_horizon_bars: int = 3,
    identifier_generator: RuntimeIdentifierGenerator | None = None,
    config: PostgreSQLConfigSnapshot | None = None,
) -> object:
    """Run one deterministic survivorship-aware robustness study end-to-end
    against real PostgreSQL."""
    resolved_generator = identifier_generator or UuidRuntimeIdentifierGenerator()
    bundle = parse_survivorship_dataset_bundle_file(
        dataset_bundle_file, expected_sha256=expected_dataset_sha256
    )
    instrument_master = parse_instrument_master_file(instrument_master_file)
    membership_manifest = parse_membership_manifest_file(
        membership_manifest_file, expected_hash=expected_membership_hash
    )
    with postgres_repository_runtime(config) as runtime:
        handler = RunSurvivorshipAwareRobustnessStudyHandler(
            historical_backtest_run_repository=runtime.historical_backtests,
            robustness_study_repository=runtime.robustness_studies,
            survivorship_study_repository=runtime.survivorship_studies,
            instrument_master_repository=runtime.instrument_masters,
            universe_membership_repository=runtime.universe_memberships,
        )
        entry_point = CommandEntryPoint(handler)
        return entry_point(
            build_run_survivorship_aware_robustness_study_command(
                study_governance_id=study_governance_id,
                stress_study_governance_id=stress_study_governance_id,
                bundle=bundle,
                instrument_master=instrument_master,
                membership_manifest=membership_manifest,
                universe_source_kind=universe_source_kind,
                backtest_run_governance_id_base=backtest_run_governance_id_base,
                stress_backtest_run_governance_id_base=stress_backtest_run_governance_id_base,
                account_equity=account_equity,
                risk_percent=risk_percent,
                runtime_identifier_generator=resolved_generator,
                reference_window_size=reference_window_size,
                holding_horizon_bars=holding_horizon_bars,
            )
        )


def _study_payload(study: object) -> dict[str, object]:
    return survivorship_aware_robustness_study_payload(study)


def main() -> None:
    if len(sys.argv) not in (13, 14, 15):
        raise SystemExit(
            "usage: empirical-platform-run-survivorship-aware-robustness-study "
            "<study_governance_id> <stress_study_governance_id> <dataset_bundle_file> "
            "<expected_dataset_sha256> <instrument_master_file> <membership_manifest_file> "
            "<expected_membership_hash> <universe_source_kind> "
            "<backtest_run_governance_id_base> <stress_backtest_run_governance_id_base> "
            "<account_equity> <risk_percent> "
            "[reference_window_size] [holding_horizon_bars]"
        )
    study = run_run_survivorship_aware_robustness_study(
        study_governance_id=sys.argv[1],
        stress_study_governance_id=sys.argv[2],
        dataset_bundle_file=sys.argv[3],
        expected_dataset_sha256=sys.argv[4],
        instrument_master_file=sys.argv[5],
        membership_manifest_file=sys.argv[6],
        expected_membership_hash=sys.argv[7],
        universe_source_kind=sys.argv[8],
        backtest_run_governance_id_base=int(sys.argv[9]),
        stress_backtest_run_governance_id_base=int(sys.argv[10]),
        account_equity=Decimal(sys.argv[11]),
        risk_percent=Decimal(sys.argv[12]),
        reference_window_size=int(sys.argv[13]) if len(sys.argv) > 13 else 5,
        holding_horizon_bars=int(sys.argv[14]) if len(sys.argv) > 14 else 3,
    )
    print(json.dumps(_study_payload(study), sort_keys=True))


if __name__ == "__main__":
    main()
