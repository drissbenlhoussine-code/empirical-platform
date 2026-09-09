"""MILESTONE-085 -- rendering paper-execution results for an operator.

THE JSON KEY SETS ARE CLOSED AND CHECKED. Each renderer below returns exactly the
keys `tests/integration/test_m085_authority_contract.py` requires, no more and no
fewer. That matters more here than in a read-only milestone: an operator decides
whether to authorize a real broker request from what these functions print, so a
field silently disappearing from the preview would remove something a human was
supposed to see before consenting.

NOTHING IS REDACTED THAT AN OPERATOR NEEDS, AND NOTHING IS PRINTED THAT IS A
SECRET. The account is shown as its stable reference, never as a broker account
number, and no credential reaches any of these functions -- they take domain
objects, and no domain object has a credential field.

MONEY IS RENDERED FROM Decimal, NEVER FROM float. `render_money` reuses M084's
exact function so a limit price prints the same way in both milestones.
"""

from __future__ import annotations

from typing import Any

from empirical_platform.decision_candidate.paper_execution import (
    BrokerAcknowledgement,
    ExecutionAttempt,
    ExecutionAuthorization,
    PaperAccountSnapshot,
    PaperExecutionEvent,
    SubmissionPreview,
)
from empirical_platform.usecases.decision_to_approval_io import render_money
from empirical_platform.usecases.paper_execution import (
    PaperExecutionStatus,
    PaperSubmissionResult,
    VerifyPaperEnvironmentResult,
)

__all__ = [
    "render_acknowledgement_json",
    "render_account_json",
    "render_account_text",
    "render_attempt_json",
    "render_attempt_text",
    "render_authorization_json",
    "render_authorization_text",
    "render_environment_json",
    "render_environment_text",
    "render_event_json",
    "render_preview_json",
    "render_preview_text",
    "render_status_json",
    "render_status_text",
    "render_submission_json",
    "render_submission_text",
]


def _money(value: object) -> str | None:
    from decimal import Decimal

    if value is None:
        return None
    if not isinstance(value, Decimal):
        raise TypeError("amounts must be Decimal, never float")
    return render_money(value)


def render_environment_json(result: VerifyPaperEnvironmentResult) -> dict[str, Any]:
    return {
        "endpoint_host": result.endpoint_host,
        "is_the_pinned_paper_host": result.is_the_pinned_paper_host,
        "account_reachable": result.account_reachable,
        "account_status": result.account_status,
        "account_reference": result.account_reference,
        "market_data_host": result.market_data_host,
    }


def render_environment_text(result: VerifyPaperEnvironmentResult) -> str:
    lines = [
        f"trading endpoint    : {result.endpoint_host}",
        f"pinned paper host   : {'yes' if result.is_the_pinned_paper_host else 'NO'}",
        f"market data endpoint: {result.market_data_host}",
        f"account reachable   : {'yes' if result.account_reachable else 'NO'}",
        f"account status      : {result.account_status}",
        f"account reference   : {result.account_reference}",
        "",
        "This is a PAPER environment. A paper acknowledgement is not a real-market",
        "execution, and paper fills do not predict live fills.",
        "",
    ]
    return "\n".join(lines)


def render_account_json(account: PaperAccountSnapshot) -> dict[str, Any]:
    return {
        "snapshot_id": account.snapshot_id,
        "environment": account.environment.value,
        "endpoint_host": account.endpoint_host,
        "account_reference": account.account_reference,
        "account_status": account.account_status,
        "currency": account.currency,
        "buying_power": _money(account.buying_power),
        "cash": _money(account.cash),
        "equity": _money(account.equity),
        "multiplier": account.multiplier,
        "shorting_enabled": account.shorting_enabled,
        "trading_blocked": account.trading_blocked,
        "transfers_blocked": account.transfers_blocked,
        "account_blocked": account.account_blocked,
        "trade_suspended_by_user": account.trade_suspended_by_user,
        "captured_at": account.captured_at.isoformat(),
        "is_dispatchable": account.is_dispatchable,
    }


def render_account_text(account: PaperAccountSnapshot) -> str:
    lines = [
        f"paper account       : {account.account_reference} ({account.environment.value})",
        f"endpoint            : {account.endpoint_host}",
        f"status              : {account.account_status}",
        f"currency            : {account.currency}",
        f"buying power        : {render_money(account.buying_power)}  (SIMULATED FUNDS)",
        f"cash                : {render_money(account.cash)}  (SIMULATED FUNDS)",
        f"equity              : {render_money(account.equity)}  (SIMULATED FUNDS)",
        f"multiplier          : {account.multiplier}",
        f"shorting enabled    : {account.shorting_enabled} (this product is long-only regardless)",
        f"trading blocked     : {account.trading_blocked}",
        f"account blocked     : {account.account_blocked}",
        f"dispatchable        : {'yes' if account.is_dispatchable else 'NO'}",
        f"captured at         : {account.captured_at.isoformat()}",
        "",
        "Balances above are PAPER balances. They are not real capital.",
        "",
    ]
    return "\n".join(lines)


def render_preview_json(preview: SubmissionPreview) -> dict[str, Any]:
    return {
        "preview_id": preview.preview_id,
        "intent_governance_id": preview.intent_governance_id,
        "preview_version": preview.preview_version,
        "account_snapshot_id": preview.account_snapshot_id,
        "account_reference": preview.account_reference,
        "symbol": preview.order.symbol,
        "side": preview.order.side,
        "quantity": preview.order.quantity,
        "order_type": preview.order.order_type.value,
        "limit_price": _money(preview.order.limit_price),
        "time_in_force": preview.order.time_in_force,
        "extended_hours": preview.order.extended_hours,
        "client_order_id": preview.order.client_order_id,
        "notional_ceiling": _money(preview.order.notional_ceiling),
        "request_fingerprint": preview.request_fingerprint,
        "approved_fingerprint": preview.approved_fingerprint,
        "market_is_open": preview.market_is_open,
        "market_next_open": (
            None if preview.market_next_open is None else preview.market_next_open.isoformat()
        ),
        "market_next_close": (
            None if preview.market_next_close is None else preview.market_next_close.isoformat()
        ),
        "quote_bid": _money(preview.quote_bid),
        "quote_ask": _money(preview.quote_ask),
        "quote_captured_at": (
            None if preview.quote_captured_at is None else preview.quote_captured_at.isoformat()
        ),
        "quote_source": preview.quote_source,
        "asset_tradable": preview.asset_tradable,
        "asset_status": preview.asset_status,
        "asset_class": preview.asset_class,
        "asset_exchange": preview.asset_exchange,
        "asset_fractionable": preview.asset_fractionable,
        "refusals": list(preview.refusals),
        "is_authorizable": preview.is_authorizable,
        "created_at": preview.created_at.isoformat(),
    }


def render_preview_text(preview: SubmissionPreview) -> str:
    """What a human reads before authorizing. Every consent-relevant fact is here.

    The fingerprint is printed prominently because authorizing requires typing it
    back: that is what makes the authorization an act about ONE exact order rather
    than about whatever the latest preview happens to be.
    """
    order = preview.order
    ceiling = order.notional_ceiling
    lines = [
        "=== PAPER SUBMISSION PREVIEW -- NOTHING HAS BEEN SENT ===",
        "",
        f"intent              : {preview.intent_governance_id}",
        f"preview             : {preview.preview_id} v{preview.preview_version}",
        f"paper account       : {preview.account_reference}",
        "",
        "THE EXACT ORDER THAT WOULD BE SENT:",
        f"  symbol            : {order.symbol}",
        f"  side              : {order.side}",
        f"  quantity          : {order.quantity} (whole shares; never fractional)",
        f"  order type        : {order.order_type.value}",
        f"  limit price       : {_money(order.limit_price) or '(none)'}",
        f"  time in force     : {order.time_in_force}",
        f"  extended hours    : {order.extended_hours}",
        f"  client order id   : {order.client_order_id}",
        f"  cost ceiling      : {render_money(ceiling) if ceiling is not None else 'UNKNOWABLE'}",
        "",
        "MARKET AND ASSET EVIDENCE:",
        f"  market open       : {preview.market_is_open}",
        f"  quote bid/ask     : {_money(preview.quote_bid) or '-'} / "
        f"{_money(preview.quote_ask) or '-'}",
        f"  quote source      : {preview.quote_source} (IEX only, NOT the consolidated tape)",
        f"  quote captured at : "
        f"{preview.quote_captured_at.isoformat() if preview.quote_captured_at else '(none)'}",
        f"  asset tradable    : {preview.asset_tradable} ({preview.asset_status}, "
        f"{preview.asset_class}, {preview.asset_exchange})",
        "",
        f"REQUEST FINGERPRINT : {preview.request_fingerprint}",
        "",
    ]
    if preview.refusals:
        lines.append("REFUSED -- this preview CANNOT be authorized:")
        lines.extend(f"  - {reason}" for reason in preview.refusals)
    else:
        lines.append("AUTHORIZABLE. To authorize, pass the fingerprint above back explicitly.")
        lines.append("An authorization is single-use, expires, and covers this order only.")
    lines.extend(
        [
            "",
            "This is the ALPACA PAPER environment. An acknowledgement here is not a",
            "real-market execution, does not predict a live fill, and says nothing",
            "about profitability or execution quality.",
            "",
        ]
    )
    return "\n".join(lines)


def render_authorization_json(authorization: ExecutionAuthorization) -> dict[str, Any]:
    return {
        "authorization_id": authorization.authorization_id,
        "intent_governance_id": authorization.intent_governance_id,
        "preview_id": authorization.preview_id,
        "preview_version": authorization.preview_version,
        "request_fingerprint": authorization.request_fingerprint,
        "account_reference": authorization.account_reference,
        "client_order_id": authorization.client_order_id,
        "authorized_by": authorization.authorized_by,
        "authorized_at": authorization.authorized_at.isoformat(),
        "expires_at": authorization.expires_at.isoformat(),
        "consumed_at": (
            None if authorization.consumed_at is None else authorization.consumed_at.isoformat()
        ),
        "consumed_by_attempt_id": authorization.consumed_by_attempt_id,
        "is_consumed": authorization.is_consumed,
    }


def render_authorization_text(authorization: ExecutionAuthorization) -> str:
    lines = [
        f"authorization       : {authorization.authorization_id}",
        f"intent              : {authorization.intent_governance_id}",
        f"preview             : {authorization.preview_id} v{authorization.preview_version}",
        f"fingerprint         : {authorization.request_fingerprint}",
        f"paper account       : {authorization.account_reference}",
        f"client order id     : {authorization.client_order_id}",
        f"authorized by       : {authorization.authorized_by}",
        f"authorized at       : {authorization.authorized_at.isoformat()}",
        f"expires at          : {authorization.expires_at.isoformat()}",
        f"consumed            : {'yes' if authorization.is_consumed else 'no'}"
        + (
            f" (by {authorization.consumed_by_attempt_id})"
            if authorization.consumed_by_attempt_id
            else ""
        ),
        "",
        "SINGLE USE. This authorization permits exactly one dispatch of exactly this",
        "order to exactly this paper account, and expires at the instant above.",
        "",
    ]
    return "\n".join(lines)


def render_attempt_json(attempt: ExecutionAttempt) -> dict[str, Any]:
    return {
        "attempt_id": attempt.attempt_id,
        "intent_governance_id": attempt.intent_governance_id,
        "authorization_id": attempt.authorization_id,
        "client_order_id": attempt.client_order_id,
        "request_fingerprint": attempt.request_fingerprint,
        "state": attempt.state.value,
        "claimed_at": attempt.claimed_at.isoformat(),
        "submitted_at": (
            None if attempt.submitted_at is None else attempt.submitted_at.isoformat()
        ),
        "acknowledged_at": (
            None if attempt.acknowledged_at is None else attempt.acknowledged_at.isoformat()
        ),
        "terminal_at": (None if attempt.terminal_at is None else attempt.terminal_at.isoformat()),
        "broker_order_id": attempt.broker_order_id,
        "broker_status": attempt.broker_status,
        "filled_quantity": _money(attempt.filled_quantity),
        "filled_avg_price": _money(attempt.filled_avg_price),
        "failure_code": attempt.failure_code,
        "failure_detail": attempt.failure_detail,
        "is_terminal": attempt.is_terminal,
        "outcome_is_known": attempt.outcome_is_known,
    }


def render_attempt_text(attempt: ExecutionAttempt) -> str:
    lines = [
        f"attempt             : {attempt.attempt_id}",
        f"intent              : {attempt.intent_governance_id}",
        f"state               : {attempt.state.value}",
        f"client order id     : {attempt.client_order_id}",
        f"broker order id     : {attempt.broker_order_id or '(none)'}",
        f"broker status       : {attempt.broker_status or '(none)'}",
        f"filled quantity     : {_money(attempt.filled_quantity) or '0'}",
        f"filled avg price    : {_money(attempt.filled_avg_price) or '(none)'}",
        f"claimed at          : {attempt.claimed_at.isoformat()}",
        f"terminal            : {'yes' if attempt.is_terminal else 'no'}",
    ]
    if attempt.failure_code:
        lines.append(f"failure             : {attempt.failure_code} -- {attempt.failure_detail}")
    if not attempt.outcome_is_known:
        lines.extend(
            [
                "",
                "OUTCOME UNKNOWN. The request may have reached the broker. Reconcile using",
                "the SAME client order id above. Do NOT send this order again.",
            ]
        )
    lines.append("")
    return "\n".join(lines)


def render_acknowledgement_json(acknowledgement: BrokerAcknowledgement) -> dict[str, Any]:
    return {
        "acknowledgement_id": acknowledgement.acknowledgement_id,
        "attempt_id": acknowledgement.attempt_id,
        "sequence": acknowledgement.sequence,
        "kind": acknowledgement.kind,
        "observed_at": acknowledgement.observed_at.isoformat(),
        "http_status": acknowledgement.http_status,
        "broker_order_id": acknowledgement.broker_order_id,
        "broker_status": acknowledgement.broker_status,
        "client_order_id_echo": acknowledgement.client_order_id_echo,
        "payload_digest": acknowledgement.payload_digest,
    }


def render_event_json(event: PaperExecutionEvent) -> dict[str, Any]:
    return {
        "event_id": event.event_id,
        "intent_governance_id": event.intent_governance_id,
        "attempt_id": event.attempt_id,
        "event_type": event.event_type,
        "occurred_at": event.occurred_at.isoformat(),
        "detail": event.detail,
    }


def render_submission_json(result: PaperSubmissionResult) -> dict[str, Any]:
    return {
        "attempt": render_attempt_json(result.attempt),
        "dispatched": result.dispatched,
        "http_status": result.http_status,
        "broker_status": result.broker_status,
        "note": result.note,
    }


def render_submission_text(result: PaperSubmissionResult) -> str:
    lines = [
        "=== PAPER SUBMISSION RESULT ===",
        "",
        f"dispatched          : {'yes' if result.dispatched else 'no'}",
        f"http status         : {result.http_status if result.http_status is not None else '-'}",
        f"broker status       : {result.broker_status or '-'}",
        f"note                : {result.note}",
        "",
        render_attempt_text(result.attempt),
    ]
    return "\n".join(lines)


def render_status_json(status: PaperExecutionStatus) -> dict[str, Any]:
    return {
        "intent_governance_id": status.intent_governance_id,
        "state": status.state.value,
        "attempt": None if status.attempt is None else render_attempt_json(status.attempt),
        "authorization": (
            None
            if status.authorization is None
            else render_authorization_json(status.authorization)
        ),
        "preview": None if status.preview is None else render_preview_json(status.preview),
        "acknowledgements": [
            render_acknowledgement_json(acknowledgement)
            for acknowledgement in status.acknowledgements
        ],
        "events": [render_event_json(event) for event in status.events],
    }


def render_status_text(status: PaperExecutionStatus) -> str:
    lines = [
        "=== PAPER EXECUTION HISTORY ===",
        "",
        f"intent              : {status.intent_governance_id}",
        f"state               : {status.state.value}",
        "",
    ]
    if status.preview is not None:
        lines.append(
            f"latest preview      : {status.preview.preview_id} "
            f"v{status.preview.preview_version} "
            f"(authorizable={status.preview.is_authorizable})"
        )
    if status.authorization is not None:
        lines.append(
            f"latest authorization: {status.authorization.authorization_id} "
            f"(consumed={status.authorization.is_consumed})"
        )
    if status.attempt is not None:
        lines.extend(["", render_attempt_text(status.attempt)])
    if status.acknowledgements:
        lines.append("BROKER ACKNOWLEDGEMENTS (append-only, in order):")
        lines.extend(
            f"  {acknowledgement.sequence}. {acknowledgement.kind} "
            f"HTTP {acknowledgement.http_status} "
            f"status={acknowledgement.broker_status or '-'} "
            f"at {acknowledgement.observed_at.isoformat()}"
            for acknowledgement in status.acknowledgements
        )
        lines.append("")
    if status.events:
        lines.append("AUDIT EVENTS (append-only, in order):")
        lines.extend(
            f"  {event.occurred_at.isoformat()} {event.event_type}: {event.detail}"
            for event in status.events
        )
        lines.append("")
    return "\n".join(lines)
