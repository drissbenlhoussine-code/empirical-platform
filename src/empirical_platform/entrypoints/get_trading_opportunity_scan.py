"""Real end-to-end TradingOpportunityScan retrieval composition root.

Composes the MILESTONE-058 retrieval vertical slice through the shared
MILESTONE-053 resource-lifecycle helper.
"""

from __future__ import annotations

import json
import sys

from empirical_platform.application.query import QueryEntryPoint
from empirical_platform.entrypoints._composition import postgres_repository_runtime
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import TradingOpportunityScanId
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.shared.identifiers import RuntimeIdentifier
from empirical_platform.usecases.get_trading_opportunity_scan import (
    GetTradingOpportunityScanHandler,
    GetTradingOpportunityScanQuery,
    TradingOpportunityScan,
)


def run_get_trading_opportunity_scan(
    *,
    scan_governance_id: str,
    scan_runtime_id: str,
    config: PostgreSQLConfigSnapshot | None = None,
) -> TradingOpportunityScan:
    """Retrieve one TradingOpportunityScan end-to-end against real PostgreSQL."""
    with postgres_repository_runtime(config) as runtime:
        handler = GetTradingOpportunityScanHandler(
            trading_opportunity_scan_repository=runtime.trading_opportunity_scans
        )
        entry_point = QueryEntryPoint(handler)
        identity = DomainIdentity(
            governance_id=TradingOpportunityScanId(scan_governance_id),
            runtime_id=RuntimeIdentifier(scan_runtime_id),
        )
        return entry_point(GetTradingOpportunityScanQuery(identity=identity))


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
    """Retrieve one TradingOpportunityScan by identity, supplied as two CLI
    arguments, and print it."""
    if len(sys.argv) != 3:
        raise SystemExit(
            "usage: empirical-platform-get-trading-opportunity-scan <governance_id> <runtime_id>"
        )
    scan = run_get_trading_opportunity_scan(
        scan_governance_id=sys.argv[1],
        scan_runtime_id=sys.argv[2],
    )
    print(json.dumps(_scan_payload(scan), sort_keys=True))


if __name__ == "__main__":
    main()
