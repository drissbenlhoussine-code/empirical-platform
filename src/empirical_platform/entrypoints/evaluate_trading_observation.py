"""Real end-to-end trading-observation evaluation composition root.

Composes the MILESTONE-057 vertical slice through the shared MILESTONE-053
resource-lifecycle helper. A real caller supplies a deterministic market
observation as a JSON bar-fixture file (see
MILESTONE_057_TRADING_EVALUATION_SCOPE_AND_DESIGN.md Section 14 for the
exact fixture shape) and receives the structured, persisted evaluation.
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
from empirical_platform.identifiers.types import DecisionCandidateId, EvidencePackageId
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.shared.identifiers import (
    RuntimeIdentifierGenerator,
    UuidRuntimeIdentifierGenerator,
)
from empirical_platform.usecases.evaluate_trading_observation import (
    Bar,
    BarInterval,
    DecisionCandidate,
    EvaluateTradingObservationCommand,
    EvaluateTradingObservationHandler,
    Instrument,
    ObservationWindow,
    StrategyParameters,
)


def _parse_bars_file(path: str) -> tuple[Bar, ...]:
    """Parse a deterministic JSON bar-fixture file into an ordered tuple of Bars.

    Expected shape: a JSON array of objects, each with `instrument`,
    `interval` (`ONE_MINUTE`/`FIVE_MINUTE`), `timestamp` (ISO-8601,
    timezone-aware), `open`/`high`/`low`/`close` (decimal strings), and
    `volume` (integer).
    """
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("bars file must contain a JSON array of bar objects")
    bars = []
    for entry in raw:
        bars.append(
            Bar(
                instrument=Instrument(entry["instrument"]),
                interval=BarInterval(entry["interval"]),
                timestamp=datetime.fromisoformat(entry["timestamp"]),
                open=Decimal(entry["open"]),
                high=Decimal(entry["high"]),
                low=Decimal(entry["low"]),
                close=Decimal(entry["close"]),
                volume=int(entry["volume"]),
            )
        )
    return tuple(bars)


def run_evaluate_trading_observation(
    *,
    decision_candidate_governance_id: str,
    target_evidence_package_governance_id: str,
    bars_file: str,
    reference_window_size: int = 5,
    identifier_generator: RuntimeIdentifierGenerator | None = None,
    config: PostgreSQLConfigSnapshot | None = None,
) -> DecisionCandidate:
    """Evaluate a deterministic market observation, end-to-end, against real PostgreSQL."""
    resolved_generator = identifier_generator or UuidRuntimeIdentifierGenerator()
    bars = _parse_bars_file(bars_file)
    window = ObservationWindow(bars=bars)
    with postgres_repository_runtime(config) as runtime:
        handler = EvaluateTradingObservationHandler(
            decision_candidate_repository=runtime.decision_candidates
        )
        entry_point = CommandEntryPoint(handler)
        identity = DomainIdentity(
            governance_id=DecisionCandidateId(decision_candidate_governance_id),
            runtime_id=resolved_generator.generate(),
        )
        command = EvaluateTradingObservationCommand(
            identity=identity,
            target_evidence_package_id=EvidencePackageId(target_evidence_package_governance_id),
            window=window,
            parameters=StrategyParameters(reference_window_size=reference_window_size),
        )
        return entry_point(command)


def _candidate_payload(candidate: DecisionCandidate) -> dict[str, object]:
    """Return a plain, JSON-serializable representation of one DecisionCandidate."""
    outcome = candidate.outcome
    return {
        "governance_id": str(candidate.identity.governance_id),
        "runtime_id": str(candidate.identity.runtime_id),
        "target_evidence_package_id": str(candidate.target_evidence_package_id),
        "instrument": str(candidate.instrument),
        "interval": candidate.interval.value,
        "evaluation_timestamp": candidate.evaluation_timestamp.isoformat(),
        "strategy_id": candidate.strategy_id,
        "strategy_version": candidate.strategy_version,
        "reference_window_size": candidate.reference_window_size,
        "decision": outcome.decision.value,
        "reasons": [reason.value for reason in outcome.reasons],
        "measurements": {
            "current_close": str(outcome.measurements.current_close),
            "current_volume": str(outcome.measurements.current_volume),
            "reference_high": str(outcome.measurements.reference_high),
            "reference_average_volume": str(outcome.measurements.reference_average_volume),
        },
    }


def main() -> None:
    """Evaluate one market observation from CLI arguments, and print the result."""
    if len(sys.argv) not in (4, 5):
        raise SystemExit(
            "usage: empirical-platform-evaluate-trading-observation "
            "<decision_candidate_governance_id> <target_evidence_package_governance_id> "
            "<bars_file> [reference_window_size]"
        )
    candidate = run_evaluate_trading_observation(
        decision_candidate_governance_id=sys.argv[1],
        target_evidence_package_governance_id=sys.argv[2],
        bars_file=sys.argv[3],
        reference_window_size=int(sys.argv[4]) if len(sys.argv) > 4 else 5,
    )
    print(json.dumps(_candidate_payload(candidate), sort_keys=True))


if __name__ == "__main__":
    main()
