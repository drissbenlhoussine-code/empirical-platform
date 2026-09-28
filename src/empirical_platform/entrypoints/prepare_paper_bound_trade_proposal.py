"""MILESTONE-085 Paper-bound trade proposal CLI.

WHY A SECOND WAY TO PREPARE A PROPOSAL. MILESTONE-084's `prepare-trade-proposal` is
frozen and stays exactly as it is. The proposal it stores carries `expires_at` and
`mandatory_liquidation_at`, written on this host's clock at the moment of
evaluation, and nothing about how that clock related to the broker's. Those two
deadlines become the order intent's. Without a basis measured at THIS moment they
cannot be placed on the broker's clock, so a proposal prepared through M084 alone
cannot lead to a paper dispatch, and no basis is derived for it later.

This command reads the broker's clock (`GET /v2/clock`, read-only), then runs
MILESTONE-084's own evaluation, unchanged, with the conservative host reading taken
after that response as `evaluated_at`, and stores the measured interval beside the
proposal. There is deliberately no `evaluated_at` argument. It places no order.

`run_prepare_paper_bound_trade_proposal` is split out from `main()` so that argument
handling and output formatting can be unit-tested by monkeypatching this one
function -- without touching a real broker or a real database.
"""

from __future__ import annotations

import json
import sys

from empirical_platform.entrypoints._operator_cli import operator_command
from empirical_platform.entrypoints._paper_composition import paper_execution_runtime
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.usecases.decision_to_approval_io import load_json_file, read_market_inputs
from empirical_platform.usecases.paper_execution import (
    PaperBoundProposal,
    PreparePaperBoundTradeProposalCommand,
    PreparePaperBoundTradeProposalHandler,
)
from empirical_platform.usecases.paper_execution_io import (
    render_paper_bound_proposal_json,
    render_paper_bound_proposal_text,
)

_USAGE = (
    "usage: empirical-platform-prepare-paper-bound-trade-proposal [--json] "
    "<proposal_governance_id> <evaluation_context_id> <symbol> <inputs.json>"
)


def run_prepare_paper_bound_trade_proposal(
    *,
    command: PreparePaperBoundTradeProposalCommand,
    config: PostgreSQLConfigSnapshot | None = None,
) -> PaperBoundProposal:
    with paper_execution_runtime(config) as context:
        handler = PreparePaperBoundTradeProposalHandler(
            configurations=context.m084.operator_trading_configurations,
            contexts=context.m084.evaluation_contexts,
            proposals=context.m084.trade_proposals,
            time_bases=context.paper.time_bases,
            # Read-only `GET /v2/clock`. This command places no order.
            broker=context.broker,
            time_source=context.time_source,
        )
        return handler.handle(command)


def _main() -> None:
    args = sys.argv[1:]
    as_json = "--json" in args
    positional = [argument for argument in args if argument != "--json"]
    if len(positional) != 4:
        raise SystemExit(_USAGE)

    proposal_id, context_id, symbol, inputs_path = positional
    inputs = read_market_inputs(load_json_file(inputs_path))
    prepared = run_prepare_paper_bound_trade_proposal(
        command=PreparePaperBoundTradeProposalCommand(
            proposal_governance_id=proposal_id,
            evaluation_context_id=context_id,
            symbol=symbol,
            quote=inputs.quote,
            account=inputs.account,
            session=inputs.session,
            instrument=inputs.instrument,
            liquidity=inputs.liquidity,
            cost_estimate=inputs.cost_estimate,
            positions=inputs.positions,
            open_orders=inputs.open_orders,
            evidence_age_seconds=inputs.evidence_age_seconds,
        )
    )
    if as_json:
        print(json.dumps(render_paper_bound_proposal_json(prepared), sort_keys=True))
    else:
        print(render_paper_bound_proposal_text(prepared), end="")


main = operator_command(_main)


if __name__ == "__main__":
    main()
