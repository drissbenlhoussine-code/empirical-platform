"""Real end-to-end trading-opportunity-scan composition root.

Composes the MILESTONE-058 vertical slice through the shared MILESTONE-053
resource-lifecycle helper. A real caller supplies a deterministic
multi-instrument market observation as a JSON universe-fixture file (see
MILESTONE_058_TRADING_OPPORTUNITY_SCANNER_SCOPE_AND_DESIGN.md Section 12 for
the exact fixture shape) and receives the structured, persisted, ranked
scan result.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from empirical_platform.application.command import CommandEntryPoint
from empirical_platform.entrypoints._composition import postgres_repository_runtime
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import (
    DecisionCandidateId,
    EvidencePackageId,
    TradingOpportunityScanId,
)
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.shared.identifiers import (
    RuntimeIdentifierGenerator,
    UuidRuntimeIdentifierGenerator,
)
from empirical_platform.usecases.run_trading_opportunity_scan import (
    Bar,
    BarInterval,
    Instrument,
    ObservationWindow,
    RunTradingOpportunityScanCommand,
    RunTradingOpportunityScanHandler,
    ScanUniverseEntry,
    StrategyParameters,
    TradingOpportunityScan,
)


def _parse_bar(entry: dict[str, str]) -> Bar:
    return Bar(
        instrument=Instrument(entry["instrument"]),
        interval=BarInterval(entry["interval"]),
        timestamp=datetime.fromisoformat(entry["timestamp"]),
        open=Decimal(entry["open"]),
        high=Decimal(entry["high"]),
        low=Decimal(entry["low"]),
        close=Decimal(entry["close"]),
        volume=int(entry["volume"]),
    )


def _parse_universe_file(
    path: str, identifier_generator: RuntimeIdentifierGenerator
) -> tuple[ScanUniverseEntry, ...]:
    """Parse a deterministic JSON universe-fixture file into an ordered
    tuple of `ScanUniverseEntry`.

    Expected shape: a JSON object with an `instruments` array, each entry
    carrying a `decision_candidate_governance_id` (the caller-supplied
    governance identity for that instrument's resulting DecisionCandidate)
    and a `bars` array in the same per-bar shape consumed by M057's
    `evaluate_trading_observation` fixture files.
    """
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or "instruments" not in raw:
        raise ValueError("universe file must contain a JSON object with an 'instruments' array")
    entries = []
    for instrument_entry in raw["instruments"]:
        bars = tuple(_parse_bar(bar) for bar in instrument_entry["bars"])
        window = ObservationWindow(bars=bars)
        identity = DomainIdentity(
            governance_id=DecisionCandidateId(instrument_entry["decision_candidate_governance_id"]),
            runtime_id=identifier_generator.generate(),
        )
        entries.append(ScanUniverseEntry(decision_candidate_identity=identity, window=window))
    return tuple(entries)


def run_run_trading_opportunity_scan(
    *,
    scan_governance_id: str,
    target_evidence_package_governance_id: str,
    universe_file: str,
    reference_window_size: int = 5,
    identifier_generator: RuntimeIdentifierGenerator | None = None,
    config: PostgreSQLConfigSnapshot | None = None,
) -> TradingOpportunityScan:
    """Run a deterministic multi-instrument scan, end-to-end, against real PostgreSQL."""
    resolved_generator = identifier_generator or UuidRuntimeIdentifierGenerator()
    universe = _parse_universe_file(universe_file, resolved_generator)
    with postgres_repository_runtime(config) as runtime:
        handler = RunTradingOpportunityScanHandler(
            decision_candidate_repository=runtime.decision_candidates,
            trading_opportunity_scan_repository=runtime.trading_opportunity_scans,
        )
        entry_point = CommandEntryPoint(handler)
        scan_identity = DomainIdentity(
            governance_id=TradingOpportunityScanId(scan_governance_id),
            runtime_id=resolved_generator.generate(),
        )
        command = RunTradingOpportunityScanCommand(
            scan_identity=scan_identity,
            target_evidence_package_id=EvidencePackageId(target_evidence_package_governance_id),
            universe=universe,
            parameters=StrategyParameters(reference_window_size=reference_window_size),
        )
        return entry_point(command)


def _scan_payload(scan: TradingOpportunityScan) -> dict[str, object]:
    """Return a plain, JSON-serializable representation of one TradingOpportunityScan."""
    return {
        "governance_id": str(scan.identity.governance_id),
        "runtime_id": str(scan.identity.runtime_id),
        "target_evidence_package_id": str(scan.target_evidence_package_id),
        "strategy_id": scan.strategy_id,
        "strategy_version": scan.strategy_version,
        "ranking_model_id": scan.ranking_model_id,
        "ranking_model_version": scan.ranking_model_version,
        "evaluation_cutoff": scan.evaluation_cutoff.isoformat(),
        "total_instruments": scan.total_instruments,
        "candidate_count": scan.candidate_count,
        "no_trade_count": scan.no_trade_count,
        "ranked_opportunities": [
            {
                "rank": entry.rank,
                "instrument": str(entry.instrument),
                "decision_candidate_id": str(entry.decision_candidate_id),
                "score": str(entry.score),
                "current_close": str(entry.measurements.current_close),
                "current_volume": str(entry.measurements.current_volume),
                "reference_high": str(entry.measurements.reference_high),
                "reference_average_volume": str(entry.measurements.reference_average_volume),
                "reasons": [reason.value for reason in entry.reasons],
            }
            for entry in scan.ranked_opportunities
        ],
    }


def main() -> None:
    """Run one trading opportunity scan from CLI arguments, and print the result."""
    if len(sys.argv) not in (4, 5):
        raise SystemExit(
            "usage: empirical-platform-run-trading-opportunity-scan "
            "<scan_governance_id> <target_evidence_package_governance_id> "
            "<universe_file> [reference_window_size]"
        )
    scan = run_run_trading_opportunity_scan(
        scan_governance_id=sys.argv[1],
        target_evidence_package_governance_id=sys.argv[2],
        universe_file=sys.argv[3],
        reference_window_size=int(sys.argv[4]) if len(sys.argv) > 4 else 5,
    )
    print(json.dumps(_scan_payload(scan), sort_keys=True))


if __name__ == "__main__":
    main()
