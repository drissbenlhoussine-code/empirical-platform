"""MILESTONE-084 trade proposal listing CLI.

Lists the proposals in one status, in a deterministic order. The intended use
is `PREPARED`: the queue of proposals waiting for a human to decide on them.

`run_list_trade_proposals` is split out from `main()` so that `main()`'s
argument handling and output formatting can be unit-tested by monkeypatching
this one function -- without touching real persistence.
"""

from __future__ import annotations

import json
import sys

from empirical_platform.entrypoints._composition import postgres_repository_runtime
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.usecases.decision_to_approval import (
    ListTradeProposalsHandler,
    ListTradeProposalsQuery,
    ProposalStatus,
    TradeProposal,
)
from empirical_platform.usecases.decision_to_approval_io import (
    InputError,
    render_money,
    render_proposal_json,
)

_USAGE = "usage: empirical-platform-list-trade-proposals [--json] [status]"


def run_list_trade_proposals(
    *,
    status: ProposalStatus,
    config: PostgreSQLConfigSnapshot | None = None,
) -> tuple[TradeProposal, ...]:
    with postgres_repository_runtime(config) as runtime:
        handler = ListTradeProposalsHandler(trade_proposal_repository=runtime.trade_proposals)
        return handler.handle(ListTradeProposalsQuery(status=status))


def _status(raw: str) -> ProposalStatus:
    try:
        return ProposalStatus(raw)
    except ValueError as error:
        permitted = ", ".join(sorted(member.value for member in ProposalStatus))
        raise InputError(f"status must be one of {permitted}; got {raw!r}") from error


def main() -> None:
    args = sys.argv[1:]
    as_json = "--json" in args
    positional = [argument for argument in args if argument != "--json"]
    if len(positional) > 1:
        raise SystemExit(_USAGE)

    status = _status(positional[0]) if positional else ProposalStatus.PREPARED
    proposals = run_list_trade_proposals(status=status)

    if as_json:
        print(json.dumps([render_proposal_json(p) for p in proposals], sort_keys=True))
    elif not proposals:
        print(f"no proposals in {status.value}")
    else:
        for proposal in proposals:
            price = "market" if proposal.limit_price is None else render_money(proposal.limit_price)
            print(
                f"{proposal.proposal_governance_id}  {proposal.side} {proposal.quantity} "
                f"{proposal.symbol} @ {price}  expires {proposal.expires_at.isoformat()}"
            )


if __name__ == "__main__":
    main()
