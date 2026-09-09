"""MILESTONE-084 NO_TRADE explanation CLI.

`prepare-trade-proposal` answers "what happened" and reports ONE reason,
selected by explicit precedence. This command answers "why, and what else was
true at the same time": it re-runs the identical evaluation and prints every
check with its outcome and detail.

The distinction matters to an operator debugging a refusal. A reported reason
of MARKET_NOT_OPEN does not mean every other rule passed -- it means that rule
came first in the precedence order. Fixing only the reported reason can produce
a second refusal for a rule that was already failing.

Nothing is written. This command persists no proposal even when the evaluation
would produce one; it is a read of the reasoning, not a re-evaluation of
record.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime

from empirical_platform.entrypoints._composition import postgres_repository_runtime
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.usecases.decision_to_approval import (
    NotFoundError,
    PrepareTradeProposalCommand,
    TradeProposalOutcome,
    evaluate_without_persisting,
)
from empirical_platform.usecases.decision_to_approval_io import (
    InputError,
    load_json_file,
    read_market_inputs,
    render_no_trade_explanation_json,
    render_no_trade_explanation_text,
)

_USAGE = (
    "usage: empirical-platform-explain-no-trade [--json] <evaluation_context_id> "
    "<symbol> <evaluated_at> <inputs.json>"
)


def run_explain_no_trade(
    *,
    command: PrepareTradeProposalCommand,
    config: PostgreSQLConfigSnapshot | None = None,
) -> TradeProposalOutcome:
    with postgres_repository_runtime(config) as runtime:
        return evaluate_without_persisting(
            command,
            configuration_repository=runtime.operator_trading_configurations,
            evaluation_context_repository=runtime.evaluation_contexts,
        )


def _evaluated_at(raw: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as error:
        raise InputError(f"evaluated_at is not an ISO-8601 instant: {raw!r}") from error
    if parsed.tzinfo is None:
        raise InputError("evaluated_at must carry a UTC offset")
    return parsed


def main() -> None:
    args = sys.argv[1:]
    as_json = "--json" in args
    positional = [argument for argument in args if argument != "--json"]
    if len(positional) != 4:
        raise SystemExit(_USAGE)

    context_id, symbol, evaluated_at_raw, inputs_path = positional
    inputs = read_market_inputs(load_json_file(inputs_path))
    try:
        outcome = run_explain_no_trade(
            command=PrepareTradeProposalCommand(
                # A dry run needs no identity of its own: nothing is stored, so
                # this name never reaches the database.
                proposal_governance_id="EXPLAIN-DRY-RUN",
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
    except NotFoundError as error:
        print(f"REFUSED: {error}", file=sys.stderr)
        raise SystemExit(1) from error

    if as_json:
        print(json.dumps(render_no_trade_explanation_json(outcome), sort_keys=True))
    else:
        print(render_no_trade_explanation_text(outcome), end="")


if __name__ == "__main__":
    main()
