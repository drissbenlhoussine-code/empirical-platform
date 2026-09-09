"""MILESTONE-085 -- the bounded real Alpaca PAPER acceptance run.

    python tools/m085_paper_acceptance.py            # run and write the evidence
    python tools/m085_paper_acceptance.py --dry-run  # everything except dispatch

THE ONLY THING IN THIS REPOSITORY THAT MAY TOUCH A REAL BROKER CREDENTIAL. Every
other test, gate and tool runs without one. This harness is separate precisely so
that "the suite does not need real credentials" stays true.

WHAT IS AUTHORIZED. At most ONE bounded paper verification order: BUY only, one
approved highly liquid US equity, no leverage, simulated notional no greater than
USD 5, a limit price deliberately far below the market so it cannot execute,
extended hours disabled, one deterministic `client_order_id`, submitted only
through the real MILESTONE-085 human-approval flow, cancelled immediately after
acknowledgement, and reconciled to an honestly observed terminal state.

THE SAFETY CONSTANTS BELOW ARE NOT PARAMETERS. They are not read from the
environment, not settable by a flag, and not loosened when a run would otherwise
be blocked. If the market data cannot support a safe limit, or the notional
ceiling cannot be respected, or any identity is ambiguous, this harness records
the external submission as measured BLOCKED and stops -- it does not raise the
ceiling, switch to a market order, widen the freshness tolerance, or pick a
cheaper speculative asset to force a success. A blocker is a result.

WHY THE M084 INPUT QUOTE IS NOT A MARKET OBSERVATION. MILESTONE-084 derives the
limit price from an OPERATOR-ASSERTED quote and states, as part of its own frozen
authority, that it never verifies such a quote against a venue. The quote asserted
below is chosen deliberately to produce a limit price far beneath the real market,
which is what makes the order unable to execute. It is a SAFETY INPUT and is not
offered as evidence about what AAPL traded at. The M085 preview separately records
the REAL IEX quote, so the evidence shows both side by side and a reader can see
which is which.
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE = REPO_ROOT / "external-review" / "MILESTONE-085"
EVIDENCE = PACKAGE / "paper-acceptance-results.md"

# --------------------------------------------------------------------------
# Safety constants. Not configurable, and not relaxed to make a run succeed.
# --------------------------------------------------------------------------

#: The approved symbol for this run. Highly liquid, a real US equity, and NOT
#: chosen for being cheap -- the limit price is what keeps the order unexecutable.
APPROVED_SYMBOL = "AAPL"
APPROVED_WATCHLIST = frozenset({APPROVED_SYMBOL})

#: The ceiling the Owner authorized. Never raised.
MAXIMUM_NOTIONAL = Decimal("5")

#: The limit price the order carries, and the asserted ask that derives it.
#: 4.00 against a real market in the hundreds is roughly a 98% discount.
ACCEPTANCE_LIMIT_PRICE = Decimal("4.00")

#: The freshness tolerance. 60 seconds, the same value an ordinary operator run
#: would use. Deliberately NOT widened for this harness: a quote hours old cannot
#: establish that a limit price is safe, and widening the gate to get past it
#: would be weakening the control this milestone exists to demonstrate.
QUOTE_MAXIMUM_AGE_SECONDS = 60

#: The limit must be at most this fraction of the prevailing bid, so a BUY cannot
#: cross the spread. Checked against the REAL quote, not the asserted one.
MAXIMUM_LIMIT_FRACTION_OF_BID = Decimal("0.5")

#: How long the human authorization is valid. Short, because it is single-use and
#: consumed immediately.
AUTHORIZATION_VALIDITY_SECONDS = 300

_IDS = {
    "configuration": "CFG-085-ACCEPT",
    "context": "ECX-085-ACCEPT",
    "watermark": "WM-085-ACCEPT",
    "proposal": "PRP-085-ACCEPT",
    "intent": "INT-085-ACCEPT",
    "snapshot": "SNP-085-ACCEPT",
    "preview": "PVW-085-ACCEPT",
    "authorization": "AUT-085-ACCEPT",
    "attempt": "ATT-085-ACCEPT",
}


class BlockedError(RuntimeError):
    """A safety gate refused. Recorded as a measured result, not worked around."""


class Log:
    """The step log, printed as it happens and written out at the end."""

    def __init__(self) -> None:
        self.lines: list[str] = []

    def step(self, number: str, title: str, expectation: str) -> None:
        self.write(f"\n### Step {number} -- {title}")
        self.write(f"\n*Expected:* {expectation}\n")

    def write(self, line: str) -> None:
        self.lines.append(line)
        print(line, flush=True)

    def fact(self, name: str, value: object) -> None:
        self.write(f"- **{name}**: `{value}`")


def build_m084_chain(log: Log) -> object:
    """The real M084 chain, through the real M084 engine and repositories.

    Nothing is hand-inserted. The intent this produces is the one M085 consumes,
    so if M084 would have refused these inputs there is no intent to dispatch.
    """
    from datetime import time as clock_time

    from empirical_platform.decision_candidate.evaluation_context import (
        build_evaluation_context,
    )
    from empirical_platform.decision_candidate.operator_trading_configuration import (
        AccountMode,
        KillSwitchState,
        LimitPricePolicy,
        OperatorTradingConfiguration,
        OrderType,
        TradingSession,
    )
    from empirical_platform.decision_candidate.product_market_inputs import (
        AccountSnapshot,
        DataFeedKind,
        InstrumentMetadata,
        LiquiditySnapshot,
        MarketStatus,
        QuoteSnapshot,
        SessionSnapshot,
        TradingCostEstimate,
    )
    from empirical_platform.decision_candidate.trade_approval import (
        OperatorAction,
        build_approved_order_intent,
        record_operator_decision,
    )
    from empirical_platform.decision_candidate.trade_proposal import (
        ProposalStatus,
        evaluate_trade_proposal,
    )
    from empirical_platform.entrypoints._composition import postgres_repository_runtime

    evaluated_at = datetime.now(UTC)
    configuration = OperatorTradingConfiguration(
        configuration_governance_id=_IDS["configuration"],
        configuration_version=1,
        base_currency="USD",
        permitted_markets=("XNAS",),
        watchlist=(APPROVED_SYMBOL,),
        prohibited_instruments=("PENNY",),
        maximum_deployable_capital=Decimal("10000"),
        # Sized so that the engine derives EXACTLY one share at the asserted ask.
        maximum_capital_per_trade=MAXIMUM_NOTIONAL,
        maximum_percent_per_trade=Decimal("20"),
        minimum_cash_reserve=Decimal("1000"),
        maximum_simultaneous_positions=3,
        maximum_daily_loss=Decimal("500"),
        maximum_daily_order_count=10,
        # Lowered so the asserted safety price is representable at all. This is a
        # POLICY bound on what may be proposed, not one of the M085 execution
        # safety gates, and it is stated here rather than buried.
        minimum_price=Decimal("1"),
        maximum_price=Decimal("1000"),
        minimum_liquidity_shares=100_000,
        maximum_spread_percent=Decimal("5"),
        maximum_estimated_slippage_percent=Decimal("1"),
        maximum_evidence_age_seconds=86_400,
        maximum_market_data_age_seconds=600,
        permitted_session=TradingSession.REGULAR,
        earliest_entry_time=clock_time(0, 1),
        latest_entry_time=clock_time(23, 58),
        mandatory_liquidation_time=clock_time(23, 59),
        operator_timezone="UTC",
        exchange_calendar_policy="XNAS-REGULAR-2026",
        proposal_expiry_seconds=3600,
        approval_expiry_seconds=1800,
        default_order_type=OrderType.LIMIT,
        permitted_order_types=(OrderType.LIMIT,),
        limit_price_policy=LimitPricePolicy.ASK,
        stop_loss_percent=Decimal("2"),
        profit_exit_percent=Decimal("4"),
        maximum_leverage=Decimal("1"),
        short_selling_permitted=False,
        overnight_positions_permitted=False,
        account_mode=AccountMode.PREPARATION,
        kill_switch=KillSwitchState.DISENGAGED,
    )

    with postgres_repository_runtime() as m084:
        m084.operator_trading_configurations.save(configuration)
        watermark = m084.evaluation_evidence_watermarks.capture(
            watermark_governance_id=_IDS["watermark"]
        )
        context = build_evaluation_context(
            evaluation_context_id=_IDS["context"],
            configuration=configuration,
            watermark=watermark,
            quote_id="QTE-085-ACCEPT",
            account_snapshot_id="ACC-085-ACCEPT",
            session_id="SES-085-ACCEPT",
            cost_estimate_id="CST-085-ACCEPT",
            instrument_universe_version="UNIVERSE-2026-09",
            strategy_version="M085-ACCEPTANCE",
            created_at=evaluated_at,
        )
        m084.evaluation_contexts.save(context)

        outcome = evaluate_trade_proposal(
            configuration=configuration,
            evaluation_context_id=context.evaluation_context_id,
            proposal_governance_id=_IDS["proposal"],
            evaluated_at=evaluated_at,
            symbol=APPROVED_SYMBOL,
            # THE SAFETY INPUT. Not a market observation -- see the module
            # docstring. It exists to derive a limit price far below the market.
            quote=QuoteSnapshot(
                quote_id="QTE-085-ACCEPT",
                provider_id="OPERATOR-ASSERTED-SAFETY-INPUT",
                symbol=APPROVED_SYMBOL,
                bid=ACCEPTANCE_LIMIT_PRICE - Decimal("0.05"),
                ask=ACCEPTANCE_LIMIT_PRICE,
                last_trade=ACCEPTANCE_LIMIT_PRICE,
                observed_at=evaluated_at - timedelta(seconds=5),
                feed_kind=DataFeedKind.REAL_TIME,
            ),
            account=AccountSnapshot(
                account_snapshot_id="ACC-085-ACCEPT",
                provider_id="OPERATOR-ASSERTED-SAFETY-INPUT",
                account_reference="PAPER-ACCEPTANCE",
                base_currency="USD",
                cash_available=Decimal("5000"),
                equity_total=Decimal("10000"),
                realized_pnl_today=Decimal("0"),
                orders_submitted_today=0,
                observed_at=evaluated_at - timedelta(seconds=5),
            ),
            session=SessionSnapshot(
                session_id="SES-085-ACCEPT",
                provider_id="OPERATOR-ASSERTED-SAFETY-INPUT",
                market="XNAS",
                status=MarketStatus.OPEN,
                observed_at=evaluated_at - timedelta(seconds=5),
            ),
            instrument=InstrumentMetadata(
                symbol=APPROVED_SYMBOL,
                market="XNAS",
                currency="USD",
                is_fractionable=False,
                lot_size=1,
            ),
            liquidity=LiquiditySnapshot(
                symbol=APPROVED_SYMBOL,
                average_daily_volume_shares=50_000_000,
                observed_at=evaluated_at - timedelta(seconds=5),
            ),
            cost_estimate=TradingCostEstimate(
                estimate_id="CST-085-ACCEPT",
                provider_id="OPERATOR-ASSERTED-SAFETY-INPUT",
                symbol=APPROVED_SYMBOL,
                commission=Decimal("0.00"),
                estimated_slippage_percent=Decimal("0.1"),
                observed_at=evaluated_at - timedelta(seconds=5),
            ),
            positions=(),
            open_orders=(),
            evidence_age_seconds=Decimal("60"),
        )
        if outcome.proposal is None:
            raise BlockedError(
                f"MILESTONE-084 refused to propose: {outcome.no_trade_reason}. "
                "No intent exists, so there is nothing for M085 to dispatch."
            )
        proposal = m084.trade_proposals.save(outcome.proposal)
        log.fact("M084 derived quantity", proposal.quantity)
        log.fact("M084 derived limit price", proposal.limit_price)
        log.fact("M084 proposal fingerprint", proposal.content_fingerprint)

        decision = record_operator_decision(
            proposal=proposal,
            decision_governance_id="DEC-085-ACCEPT",
            action=OperatorAction.APPROVE,
            operator_identity="owner",
            decided_at=datetime.now(UTC),
            approval_expiry_seconds=configuration.approval_expiry_seconds,
        )
        m084.approval_decisions.record(decision)
        approved = m084.trade_proposals.set_status(
            proposal.proposal_governance_id, ProposalStatus.APPROVED
        )
        intent = build_approved_order_intent(
            intent_governance_id=_IDS["intent"],
            proposal=approved,
            decision=decision,
            created_at=datetime.now(UTC),
            idempotency_key="IDEM-085-ACCEPT",
        )
        stored = m084.approved_order_intents.issue(intent)
        log.fact("M084 intent", stored.intent_governance_id)
        log.fact("M084 submission_state", stored.submission_state.value)
        return stored


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="do everything except dispatch, even if every gate permits it",
    )
    arguments = parser.parse_args(argv)

    from empirical_platform.entrypoints._paper_composition import paper_execution_runtime
    from empirical_platform.usecases.paper_execution import (
        AuthorizePaperSubmissionCommand,
        AuthorizePaperSubmissionHandler,
        CancelPaperOrderCommand,
        CancelPaperOrderHandler,
        PreviewPaperSubmissionCommand,
        PreviewPaperSubmissionHandler,
        ReconcilePaperOrderCommand,
        ReconcilePaperOrderHandler,
        SubmitAuthorizedPaperOrderCommand,
        SubmitAuthorizedPaperOrderHandler,
        VerifyPaperEnvironmentHandler,
        VerifyPaperEnvironmentQuery,
    )
    from empirical_platform.usecases.paper_execution_io import render_preview_text

    log = Log()
    log.write("# MILESTONE-085 -- Bounded Alpaca Paper Acceptance Run")
    log.write("")
    log.write(f"Run at `{datetime.now(UTC).isoformat()}` (UTC).")
    log.write("")
    log.write("Every number below was measured against the real Alpaca **paper** endpoint.")
    log.write("Balances are simulated. A paper acknowledgement is not a real-market execution.")
    log.write("")
    log.write("## Authorized bounds, none of them relaxed by this run")
    log.write("")
    log.fact("symbol", APPROVED_SYMBOL)
    log.fact("side", "BUY only (the request type cannot express a sell)")
    log.fact("maximum notional", MAXIMUM_NOTIONAL)
    log.fact("limit price", ACCEPTANCE_LIMIT_PRICE)
    log.fact("quote freshness tolerance", f"{QUOTE_MAXIMUM_AGE_SECONDS}s")
    log.fact("limit must be at most this fraction of the bid", MAXIMUM_LIMIT_FRACTION_OF_BID)
    log.fact("extended hours", False)

    blocked: str | None = None
    try:
        log.step("1", "Environment verification (read-only)", "the pinned paper host answers")
        with paper_execution_runtime() as context:
            environment = VerifyPaperEnvironmentHandler(
                broker=context.broker, market_data=context.market_data
            ).handle(VerifyPaperEnvironmentQuery())
            log.fact("trading endpoint", environment.endpoint_host)
            log.fact("is the pinned paper host", environment.is_the_pinned_paper_host)
            log.fact("market data endpoint", environment.market_data_host)
            log.fact("account reachable", environment.account_reachable)
            log.fact("account status", environment.account_status)
            log.fact("account reference (redacted digest)", environment.account_reference)
            if not environment.is_the_pinned_paper_host or not environment.account_reachable:
                raise BlockedError("the paper environment did not verify")

        log.step("2", "Real market evidence", "measured, and reported whatever it says")
        with paper_execution_runtime() as context:
            clock = context.broker.fetch_clock()
            asset = context.broker.fetch_asset(APPROVED_SYMBOL)
            position = context.broker.fetch_position(APPROVED_SYMBOL)
            quote = context.market_data.fetch_quote(APPROVED_SYMBOL)
            now = datetime.now(UTC)
            log.fact("market is_open", clock.is_open)
            log.fact("next_open", clock.next_open.isoformat() if clock.next_open else None)
            log.fact("asset tradable / status", f"{asset.tradable} / {asset.status}")
            log.fact("existing position", 0 if position is None else position.quantity)
            if quote is None:
                raise BlockedError(
                    "no quote is available, so no limit price can be shown to be safe"
                )
            age = (now - quote.captured_at).total_seconds()
            log.fact("real quote bid / ask", f"{quote.bid} / {quote.ask}")
            log.fact("real quote captured_at", quote.captured_at.isoformat())
            log.fact("real quote age", f"{age:.0f}s")
            log.fact("quote source", quote.source)

            # The limit must be far BELOW the prevailing bid, checked against the
            # REAL quote rather than the asserted safety input.
            if quote.bid is None or Decimal(quote.bid) <= 0:
                raise BlockedError(
                    f"the real bid is {quote.bid!r}, so it cannot be shown that a limit of "
                    f"{ACCEPTANCE_LIMIT_PRICE} sits far below the market"
                )
            bid = Decimal(quote.bid)
            fraction = (ACCEPTANCE_LIMIT_PRICE / bid).quantize(Decimal("0.0001"))
            log.fact("limit / bid", fraction)
            if fraction > MAXIMUM_LIMIT_FRACTION_OF_BID:
                raise BlockedError(
                    f"the limit is {fraction} of the bid, above the "
                    f"{MAXIMUM_LIMIT_FRACTION_OF_BID} ceiling, so it could execute"
                )
            if age > QUOTE_MAXIMUM_AGE_SECONDS:
                raise BlockedError(
                    f"the only available quote is {age:.0f}s old, beyond the "
                    f"{QUOTE_MAXIMUM_AGE_SECONDS}s freshness tolerance. The tolerance is a "
                    "safety control and is NOT widened to get past this; the market is "
                    f"closed (is_open={clock.is_open}) and IEX publishes no new quotes while "
                    "it is."
                )

        log.step("3", "MILESTONE-084 chain", "a real approved intent, derived not fabricated")
        intent = build_m084_chain(log)

        log.step("4", "Submission preview", "the exact order, and every refusal")
        with paper_execution_runtime() as context:
            preview = PreviewPaperSubmissionHandler(
                intents=context.m084.approved_order_intents,
                snapshots=context.paper.paper_account_snapshots,
                previews=context.paper.submission_previews,
                events=context.paper.paper_execution_events,
                broker=context.broker,
                market_data=context.market_data,
                kill_switch=context.paper.execution_kill_switch,
            ).handle(
                PreviewPaperSubmissionCommand(
                    intent_governance_id=intent.intent_governance_id,  # type: ignore[attr-defined]
                    preview_id=_IDS["preview"],
                    account_snapshot_id=_IDS["snapshot"],
                    approved_watchlist=APPROVED_WATCHLIST,
                    maximum_notional=MAXIMUM_NOTIONAL,
                    quote_maximum_age_seconds=QUOTE_MAXIMUM_AGE_SECONDS,
                    created_at=datetime.now(UTC),
                )
            )
            log.write("")
            log.write("```")
            log.write(render_preview_text(preview))
            log.write("```")
            log.fact("authorizable", preview.is_authorizable)
            log.fact("cost ceiling", preview.order.notional_ceiling)
            log.fact("client_order_id", preview.order.client_order_id)
            log.fact("request fingerprint", preview.request_fingerprint)
            if preview.order.notional_ceiling is None:
                raise BlockedError("the order has no knowable cost ceiling")
            if preview.order.notional_ceiling > MAXIMUM_NOTIONAL:
                raise BlockedError(
                    f"the cost ceiling {preview.order.notional_ceiling} exceeds the "
                    f"authorized {MAXIMUM_NOTIONAL}"
                )
            if not preview.is_authorizable:
                raise BlockedError(
                    "the preview refuses authorization: " + "; ".join(preview.refusals)
                )
            fingerprint = preview.request_fingerprint

        if arguments.dry_run:
            raise BlockedError("--dry-run was requested, so no authorization was created")

        log.step("5", "Human authorization", "single-use, expiring, bound to this fingerprint")
        with paper_execution_runtime() as context:
            authorization = AuthorizePaperSubmissionHandler(
                previews=context.paper.submission_previews,
                authorizations=context.paper.execution_authorizations,
                events=context.paper.paper_execution_events,
            ).handle(
                AuthorizePaperSubmissionCommand(
                    authorization_id=_IDS["authorization"],
                    preview_id=_IDS["preview"],
                    expected_request_fingerprint=fingerprint,
                    authorized_by="owner",
                    authorized_at=datetime.now(UTC),
                    validity_seconds=AUTHORIZATION_VALIDITY_SECONDS,
                )
            )
            log.fact("authorization", authorization.authorization_id)
            log.fact("expires at", authorization.expires_at.isoformat())

        log.step("6", "Dispatch", "exactly one order, one client_order_id")
        with paper_execution_runtime() as context:
            result = SubmitAuthorizedPaperOrderHandler(
                intents=context.m084.approved_order_intents,
                previews=context.paper.submission_previews,
                authorizations=context.paper.execution_authorizations,
                attempts=context.paper.execution_attempts,
                acknowledgements=context.paper.broker_acknowledgements,
                events=context.paper.paper_execution_events,
                snapshots=context.paper.paper_account_snapshots,
                broker=context.broker,
                market_data=context.market_data,
                kill_switch=context.paper.execution_kill_switch,
            ).handle(
                SubmitAuthorizedPaperOrderCommand(
                    intent_governance_id=intent.intent_governance_id,  # type: ignore[attr-defined]
                    attempt_id=_IDS["attempt"],
                    account_snapshot_id=_IDS["snapshot"] + "-2",
                    approved_watchlist=APPROVED_WATCHLIST,
                    maximum_notional=MAXIMUM_NOTIONAL,
                    quote_maximum_age_seconds=QUOTE_MAXIMUM_AGE_SECONDS,
                    at=datetime.now(UTC),
                )
            )
            log.fact("dispatched", result.dispatched)
            log.fact("http status", result.http_status)
            log.fact("broker status", result.broker_status)
            log.fact("state", result.attempt.state.value)
            log.fact("broker order id", result.attempt.broker_order_id)
            log.fact("note", result.note)

        log.step("7", "Cancellation", "requested immediately; a request is not a cancellation")
        with paper_execution_runtime() as context:
            cancelled = CancelPaperOrderHandler(
                attempts=context.paper.execution_attempts,
                acknowledgements=context.paper.broker_acknowledgements,
                events=context.paper.paper_execution_events,
                broker=context.broker,
            ).handle(
                CancelPaperOrderCommand(
                    intent_governance_id=intent.intent_governance_id,  # type: ignore[attr-defined]
                    at=datetime.now(UTC),
                )
            )
            log.fact("state after cancel request", cancelled.state.value)

        log.step("8", "Reconciliation", "the broker decides the terminal state, not us")
        with paper_execution_runtime() as context:
            reconciled = ReconcilePaperOrderHandler(
                attempts=context.paper.execution_attempts,
                acknowledgements=context.paper.broker_acknowledgements,
                events=context.paper.paper_execution_events,
                broker=context.broker,
            ).handle(
                ReconcilePaperOrderCommand(
                    intent_governance_id=intent.intent_governance_id,  # type: ignore[attr-defined]
                    at=datetime.now(UTC),
                )
            )
            log.fact("final state", reconciled.state.value)
            log.fact("final broker status", reconciled.broker_status)
            log.fact("filled quantity", reconciled.filled_quantity)
    except BlockedError as reason:
        blocked = str(reason)
        log.write("")
        log.write("## RESULT: EXTERNAL PAPER SUBMISSION -- MEASURED BLOCKED")
        log.write("")
        log.write(f"**Reason:** {blocked}")
        log.write("")
        log.write(
            "No safety control was relaxed to get past this. The notional ceiling was not "
            "raised, the order type was not changed to market, the freshness tolerance was "
            "not widened, and no cheaper asset was substituted. All local, database and "
            "hostile-adapter validation is unaffected and is reported separately."
        )
    else:
        log.write("")
        log.write("## RESULT: EXTERNAL PAPER SUBMISSION COMPLETED")
        log.write("")
        log.write(
            "One bounded paper order was dispatched through the real human-approval flow, "
            "cancelled, and reconciled to an honestly observed terminal state."
        )

    log.write("")
    log.write("## What this run does NOT establish")
    log.write("")
    for claim in (
        "that a paper acknowledgement is a real-market execution",
        "that a paper fill predicts a live fill",
        "profitability, expected return, fillability or execution quality",
        "eligibility for, or readiness for, a live Alpaca account",
        "that the asserted M084 input quote describes what the market showed",
        "venue truth beyond what the Alpaca paper endpoint returned",
    ):
        log.write(f"- {claim}")
    log.write("")

    PACKAGE.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text("\n".join(log.lines) + "\n", encoding="utf-8", newline="\n")
    print(f"\nwrote {EVIDENCE.relative_to(REPO_ROOT)}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
