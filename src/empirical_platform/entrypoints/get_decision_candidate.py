"""Real end-to-end DecisionCandidate retrieval composition root.

Composes the MILESTONE-057 retrieval vertical slice through the shared
MILESTONE-053 resource-lifecycle helper.
"""

from __future__ import annotations

import json
import sys

from empirical_platform.application.query import QueryEntryPoint
from empirical_platform.entrypoints._composition import postgres_repository_runtime
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import DecisionCandidateId
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.shared.identifiers import RuntimeIdentifier
from empirical_platform.usecases.get_decision_candidate import (
    DecisionCandidate,
    GetDecisionCandidateHandler,
    GetDecisionCandidateQuery,
)


def run_get_decision_candidate(
    *,
    decision_candidate_governance_id: str,
    decision_candidate_runtime_id: str,
    config: PostgreSQLConfigSnapshot | None = None,
) -> DecisionCandidate:
    """Retrieve one DecisionCandidate end-to-end against real PostgreSQL."""
    with postgres_repository_runtime(config) as runtime:
        handler = GetDecisionCandidateHandler(
            decision_candidate_repository=runtime.decision_candidates
        )
        entry_point = QueryEntryPoint(handler)
        identity = DomainIdentity(
            governance_id=DecisionCandidateId(decision_candidate_governance_id),
            runtime_id=RuntimeIdentifier(decision_candidate_runtime_id),
        )
        return entry_point(GetDecisionCandidateQuery(identity=identity))


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
    """Retrieve one DecisionCandidate by identity, supplied as two CLI arguments, and print it."""
    if len(sys.argv) != 3:
        raise SystemExit(
            "usage: empirical-platform-get-decision-candidate <governance_id> <runtime_id>"
        )
    candidate = run_get_decision_candidate(
        decision_candidate_governance_id=sys.argv[1],
        decision_candidate_runtime_id=sys.argv[2],
    )
    print(json.dumps(_candidate_payload(candidate), sort_keys=True))


if __name__ == "__main__":
    main()
