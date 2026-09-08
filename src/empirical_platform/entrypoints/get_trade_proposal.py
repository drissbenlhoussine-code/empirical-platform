"""MILESTONE-084 trade proposal CLI (read).

Prints one stored proposal, its order terms, its fingerprint, and the risk
checks it passed. Read-only: nothing here can change a proposal's status, and
the database refuses any change to its terms regardless.

`run_get_trade_proposal` is split out from `main()` so that `main()`'s argument
handling and output formatting can be unit-tested by monkeypatching this one
function -- without touching real persistence.
"""

from __future__ import annotations

import json
import sys

from empirical_platform.entrypoints._composition import postgres_repository_runtime
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.usecases.decision_to_approval import (
    GetTradeProposalHandler,
    GetTradeProposalQuery,
    TradeProposal,
)
from empirical_platform.usecases.decision_to_approval_io import (
    render_proposal_json,
    render_proposal_text,
)

_USAGE = "usage: empirical-platform-get-trade-proposal [--json] <proposal_governance_id>"


def run_get_trade_proposal(
    *,
    proposal_governance_id: str,
    config: PostgreSQLConfigSnapshot | None = None,
) -> TradeProposal:
    with postgres_repository_runtime(config) as runtime:
        handler = GetTradeProposalHandler(trade_proposal_repository=runtime.trade_proposals)
        return handler.handle(GetTradeProposalQuery(proposal_governance_id=proposal_governance_id))


def main() -> None:
    args = sys.argv[1:]
    as_json = "--json" in args
    positional = [argument for argument in args if argument != "--json"]
    if len(positional) != 1:
        raise SystemExit(_USAGE)

    proposal = run_get_trade_proposal(proposal_governance_id=positional[0])

    if as_json:
        print(json.dumps(render_proposal_json(proposal), sort_keys=True))
    else:
        print(render_proposal_text(proposal), end="")


if __name__ == "__main__":
    main()
