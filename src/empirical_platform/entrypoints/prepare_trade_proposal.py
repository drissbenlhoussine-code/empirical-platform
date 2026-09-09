"""MILESTONE-084 trade proposal CLI.

Evaluates one instrument against one stored evaluation context and one set of
OPERATOR-ASSERTED observations read from a file. The platform records and
checks what the operator asserted; it does not verify that the quote in the
file is what the market actually showed. See
`usecases/decision_to_approval.py` for the full statement of that boundary.

DELIBERATELY no quantity, price or risk-verdict argument. All three are derived
by the engine, because a caller who could supply them could size a trade the
configuration does not permit and have it recorded as though the rules had been
applied.

Most evaluations end in NO_TRADE, which is a legitimate answer and is printed
as one. Nothing is stored for a NO_TRADE: a refusal is not a proposal, and a
table full of them would obscure the few that are.

`run_prepare_trade_proposal` is split out from `main()` so that `main()`'s
argument handling and output formatting can be unit-tested by monkeypatching
this one function -- without touching real persistence.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime

from empirical_platform.application.command import CommandEntryPoint
from empirical_platform.entrypoints._composition import postgres_repository_runtime
from empirical_platform.entrypoints._operator_cli import operator_command
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.usecases.decision_to_approval import (
    PrepareTradeProposalCommand,
    PrepareTradeProposalHandler,
    TradeProposalOutcome,
)
from empirical_platform.usecases.decision_to_approval_io import (
    InputError,
    load_json_file,
    read_market_inputs,
    render_outcome_json,
    render_outcome_text,
)

_USAGE = (
    "usage: empirical-platform-prepare-trade-proposal [--json] <proposal_governance_id> "
    "<evaluation_context_id> <symbol> <evaluated_at> <inputs.json>"
)


def run_prepare_trade_proposal(
    *,
    command: PrepareTradeProposalCommand,
    config: PostgreSQLConfigSnapshot | None = None,
) -> TradeProposalOutcome:
    with postgres_repository_runtime(config) as runtime:
        handler = PrepareTradeProposalHandler(
            configuration_repository=runtime.operator_trading_configurations,
            evaluation_context_repository=runtime.evaluation_contexts,
            trade_proposal_repository=runtime.trade_proposals,
        )
        entry_point = CommandEntryPoint(handler)
        return entry_point(command)


def _evaluated_at(raw: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as error:
        raise InputError(f"evaluated_at is not an ISO-8601 instant: {raw!r}") from error
    if parsed.tzinfo is None:
        raise InputError("evaluated_at must carry a UTC offset")
    return parsed


def _main() -> None:
    args = sys.argv[1:]
    as_json = "--json" in args
    positional = [argument for argument in args if argument != "--json"]
    if len(positional) != 5:
        raise SystemExit(_USAGE)

    proposal_id, context_id, symbol, evaluated_at_raw, inputs_path = positional
    inputs = read_market_inputs(load_json_file(inputs_path))
    outcome = run_prepare_trade_proposal(
        command=PrepareTradeProposalCommand(
            proposal_governance_id=proposal_id,
            evaluation_context_id=context_id,
            symbol=symbol,
            evaluated_at=_evaluated_at(evaluated_at_raw),
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
        print(json.dumps(render_outcome_json(outcome), sort_keys=True))
    else:
        print(render_outcome_text(outcome), end="")


main = operator_command(_main)


if __name__ == "__main__":
    main()
